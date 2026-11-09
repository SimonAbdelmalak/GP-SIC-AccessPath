import csv
import shutil
import tempfile
from pathlib import Path

from models.place import (
    ACCESSIBILITY_FEATURES,
    PLACE_CSV_COLUMNS,
    InvalidPlaceDataError,
    Place,
)
from services.place_service import PlaceDataFileError, PlaceNotFoundError, PlaceService

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "places.csv"

def make_temporary_csv():
    folder = Path(tempfile.mkdtemp())
    csv_path = folder / "places.csv"
    shutil.copy(DATA_FILE, csv_path)
    return csv_path


def all_features(value):
    return {feature: value for feature in ACCESSIBILITY_FEATURES}


def valid_place_arguments(**changes):
    arguments = {
        "place_id": "P500",
        "name": "Test Cafe",
        "category": "Cafe",
        "city": "Cairo",
        "address": "1 Test Street",
        "latitude": 30.0,
        "longitude": 31.0,
        "rating": 4.0,
        "accessibility_details": all_features(True),
    }
    arguments.update(changes)
    return arguments


def test_place_collects_every_validation_error_at_once():
    try:
        Place(**valid_place_arguments(
            place_id="X1", name="", category="Spaceship", city="C",
            address="x", latitude="abc", longitude=500, rating=9,
            accessibility_details={"jetpack": True, "elevator": "maybe"},
        ))
        assert False, "invalid data must raise InvalidPlaceDataError"
    except InvalidPlaceDataError as error:
        assert len(error.error_messages) >= 9


def test_place_cleans_text_and_converts_numbers():
    place = Place(**valid_place_arguments(
        place_id="p007", name="  Nile   Cafe ", category="cafe",
        latitude="30.5", rating="4.26",
        accessibility_details={"elevator": "yes", "wheelchair_ramp": 1},
    ))
    assert place.place_id == "P007"
    assert place.name == "Nile Cafe"
    assert place.category == "Cafe"
    assert place.latitude == 30.5
    assert place.rating == 4.3
    assert place.accessibility_details["elevator"] is True
    assert place.accessibility_details["braille_signage"] is False


def test_place_id_must_match_pattern():
    for bad_id in ("", "7", "P1", "PP001", "A001"):
        try:
            Place(**valid_place_arguments(place_id=bad_id))
            assert False, bad_id
        except InvalidPlaceDataError:
            pass
    assert Place(**valid_place_arguments(place_id="P1000")).place_id == "P1000"


def test_future_and_badly_formatted_dates_are_rejected():
    for bad_date in ("2999-01-01", "12/10/2026", "yesterday"):
        try:
            Place(**valid_place_arguments(date_added=bad_date))
            assert False, bad_date
        except InvalidPlaceDataError:
            pass


def test_to_csv_row_and_from_csv_row_round_trip():
    place = Place(**valid_place_arguments(date_added="2026-01-05"))
    row = place.to_csv_row()
    assert list(row.keys()) == PLACE_CSV_COLUMNS
    assert Place.from_csv_row(row).to_dict() == place.to_dict()


def test_service_loads_every_row_of_the_data_file():
    with open(DATA_FILE, newline="", encoding="utf-8") as csv_file:
        expected_rows = len(list(csv.DictReader(csv_file)))
    service = PlaceService(make_temporary_csv())
    assert service.get_place_count() == expected_rows
    assert service.load_error_messages == []


def test_service_skips_invalid_and_duplicate_rows_without_crashing():
    csv_path = make_temporary_csv()
    with open(csv_path, "a", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["BAD", "", "Nope"] + [""] * (len(PLACE_CSV_COLUMNS) - 3))
        writer.writerow(["P001", "Same Id", "Cafe", "Cairo", "1 Some Street", 30, 31, 4]
                        + ["True"] * len(ACCESSIBILITY_FEATURES) + ["2026-01-01"])
    expected_places = sum(1 for _ in open(DATA_FILE, encoding="utf-8")) - 1
    service = PlaceService(csv_path)
    assert service.get_place_count() == expected_places
    assert len(service.load_error_messages) == 2


def test_missing_file_and_missing_columns_raise_clear_errors():
    try:
        PlaceService(Path(tempfile.mkdtemp()) / "nothing.csv")
        assert False
    except PlaceDataFileError:
        pass

    broken_path = Path(tempfile.mkdtemp()) / "broken.csv"
    broken_path.write_text("place_id,name\nP001,A\n", encoding="utf-8")
    try:
        PlaceService(broken_path)
        assert False
    except PlaceDataFileError as error:
        assert "missing column" in str(error)


def test_add_place_creates_next_id_and_saves_to_file():
    csv_path = make_temporary_csv()
    service = PlaceService(csv_path)
    before = service.get_place_count()
    new_place = service.add_place("Saved Cafe", "cafe", "cairo", "2 Saved Street", 30, 31, 4, {"elevator": True})
    assert new_place.place_id == f"P{before + 1:03d}"
    assert new_place.city == "Cairo"
    reloaded = PlaceService(csv_path)
    assert reloaded.get_place_count() == before + 1
    assert reloaded.get_place_by_id(new_place.place_id).accessibility_details["elevator"] is True


def test_duplicate_name_in_same_city_is_rejected_but_allowed_in_another_city():
    service = PlaceService(make_temporary_csv())
    existing = service.get_all_places()[0]
    try:
        service.add_place(existing.name.upper(), existing.category, existing.city, "5 Another Street", 30, 31, 4, {})
        assert False
    except InvalidPlaceDataError as error:
        assert "already exists" in str(error)
    other_city = "Brand New City"
    created = service.add_place(existing.name, existing.category, other_city, "5 Another Street", 30, 31, 4, {})
    assert created.city == other_city


def test_nested_index_stays_in_sync_when_adding_and_removing():
    service = PlaceService(make_temporary_csv())
    created = service.add_place("Index Cafe", "Cafe", "Index City", "3 Index Street", 30, 31, 4, {}, save_to_file=False)
    assert created in service.browse_places(city="index city", category="CAFE")
    assert "Index City" in service.get_available_cities()
    service.remove_place(created.place_id, save_to_file=False)
    assert "Index City" not in service.get_available_cities()
    try:
        service.get_place_by_id(created.place_id)
        assert False
    except PlaceNotFoundError:
        pass


def test_browse_places_filters_ignore_case():
    service = PlaceService(make_temporary_csv())
    cairo_places = service.browse_places(city="cAiRo")
    assert cairo_places and all(place.city == "Cairo" for place in cairo_places)
    assert len(service.browse_places()) == service.get_place_count()
    assert service.browse_places(city="Atlantis") == []


def test_update_accessibility_details_returns_old_details_and_validates():
    csv_path = make_temporary_csv()
    service = PlaceService(csv_path)
    place_id = service.get_all_places()[0].place_id
    before = service.get_accessibility_details(place_id)
    old = service.update_accessibility_details(place_id, all_features(False))
    assert old == before
    assert not any(service.get_accessibility_details(place_id).values())
    assert not any(PlaceService(csv_path).get_accessibility_details(place_id).values())
    try:
        service.update_accessibility_details(place_id, {"jetpack": True})
        assert False
    except InvalidPlaceDataError:
        pass


def test_accessibility_details_copy_does_not_change_stored_place():
    service = PlaceService(make_temporary_csv())
    place_id = service.get_all_places()[0].place_id
    details = service.get_accessibility_details(place_id)
    details["elevator"] = not details["elevator"]
    assert service.get_accessibility_details(place_id)["elevator"] != details["elevator"]
