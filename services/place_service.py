import csv
from pathlib import Path

from models.place import (
    Place,
    InvalidPlaceDataError,
    PLACE_CSV_COLUMNS,
    validate_and_clean_place_data,
)


DEFAULT_CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "places.csv"

class PlaceNotFoundError(LookupError):
    pass


class PlaceDataFileError(Exception):
    pass

#encapsulation
class PlaceService:

    def __init__(self, csv_path=DEFAULT_CSV_PATH):
        self.csv_path = Path(csv_path)
        self._places_by_id = {}
        self._place_ids_by_city_and_category = {}

        self.load_error_messages = []

        self.load_places_from_csv()

    def load_places_from_csv(self):
        self._places_by_id = {}
        self._place_ids_by_city_and_category = {}
        self.load_error_messages = []

        if not self.csv_path.exists():
            raise PlaceDataFileError(f"Data file not found: {self.csv_path}")

        try:
            with open(self.csv_path, mode="r", newline="", encoding="utf-8") as csv_file:
                reader = csv.DictReader(csv_file)

                missing_columns = [
                    column for column in PLACE_CSV_COLUMNS
                    if column not in (reader.fieldnames or [])
                ]
                if missing_columns:
                    raise PlaceDataFileError(
                        "places.csv is missing column(s): " + ", ".join(missing_columns)
                    )

                for row_number, row in enumerate(reader, start=2):
                    try:
                        place = Place.from_csv_row(row)
                    except InvalidPlaceDataError as error:
                        self.load_error_messages.append(f"Row {row_number}: {error}")
                        continue

                    if place.place_id in self._places_by_id:
                        self.load_error_messages.append(
                            f"Row {row_number}: duplicate place ID {place.place_id} was skipped."
                        )
                        continue

                    self._store_place(place)
        except OSError as error:
            raise PlaceDataFileError(f"Could not read {self.csv_path}: {error}")

        return len(self._places_by_id)

    def save_places_to_csv(self):
        try:
            with open(self.csv_path, mode="w", newline="", encoding="utf-8") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=PLACE_CSV_COLUMNS)
                writer.writeheader()
                for place in self._places_by_id.values():
                    writer.writerow(place.to_csv_row())
        except OSError as error:
            raise PlaceDataFileError(f"Could not save {self.csv_path}: {error}")

    def _store_place(self, place):
        self._places_by_id[place.place_id] = place
        categories_in_city = self._place_ids_by_city_and_category.setdefault(place.city, {})
        categories_in_city.setdefault(place.category, []).append(place.place_id)

    def _unstore_place(self, place):
        del self._places_by_id[place.place_id]
        categories_in_city = self._place_ids_by_city_and_category[place.city]
        categories_in_city[place.category].remove(place.place_id)
        if not categories_in_city[place.category]:
            del categories_in_city[place.category]
        if not categories_in_city:
            del self._place_ids_by_city_and_category[place.city]

    def _find_existing_city_spelling(self, city_text):
        wanted = " ".join(str(city_text).split()).lower()
        for existing_city in self._place_ids_by_city_and_category:
            if existing_city.lower() == wanted:
                return existing_city
        return city_text

    def _place_name_exists_in_city(self, name, city):
        wanted_name = " ".join(str(name).split()).lower()
        wanted_city = " ".join(str(city).split()).lower()
        for place in self._places_by_id.values():
            if place.name.lower() == wanted_name and place.city.lower() == wanted_city:
                return True
        return False

    def generate_next_place_id(self):
        highest_number = 0
        for place_id in self._places_by_id:
            number = int(place_id[1:])
            if number > highest_number:
                highest_number = number
        return f"P{highest_number + 1:03d}"

    def get_all_places(self):
        return list(self._places_by_id.values())

    def get_place_count(self):
        return len(self._places_by_id)

    def get_place_by_id(self, place_id):
        clean_id = str(place_id).strip().upper()
        if clean_id not in self._places_by_id:
            raise PlaceNotFoundError(f"No place found with ID '{place_id}'.")
        return self._places_by_id[clean_id]

    def get_available_cities(self):
        return list(self._place_ids_by_city_and_category.keys())

    def get_available_categories(self):
        used_categories = []
        for categories_in_city in self._place_ids_by_city_and_category.values():
            for category in categories_in_city:
                if category not in used_categories:
                    used_categories.append(category)
        return used_categories

    def browse_places(self, city=None, category=None):
        if city is None and category is None:
            return self.get_all_places()

        wanted_city = None if city is None else str(city).strip().lower()
        wanted_category = None if category is None else str(category).strip().lower()

        matching_places = []
        for city_name, categories_in_city in self._place_ids_by_city_and_category.items():
            if wanted_city is not None and city_name.lower() != wanted_city:
                continue
            for category_name, place_ids in categories_in_city.items():
                if wanted_category is not None and category_name.lower() != wanted_category:
                    continue
                for place_id in place_ids:
                    matching_places.append(self._places_by_id[place_id])
        return matching_places

    def get_accessibility_details(self, place_id):
        place = self.get_place_by_id(place_id)
        return dict(place.accessibility_details)

    def get_all_place_rows(self):
        return [place.to_csv_row() for place in self._places_by_id.values()]

    def validate_new_place(
        self,
        name,
        category,
        city,
        address,
        latitude,
        longitude,
        rating,
        accessibility_details,
    ):
        city = self._find_existing_city_spelling(city)

        candidate_place = Place(
            place_id=self.generate_next_place_id(),
            name=name,
            category=category,
            city=city,
            address=address,
            latitude=latitude,
            longitude=longitude,
            rating=rating,
            accessibility_details=accessibility_details,
        )

        if self._place_name_exists_in_city(candidate_place.name, candidate_place.city):
            raise InvalidPlaceDataError(
                [f"'{candidate_place.name}' already exists in {candidate_place.city}."]
            )
        return candidate_place

    def add_place(
        self,
        name,
        category,
        city,
        address,
        latitude,
        longitude,
        rating,
        accessibility_details,
        save_to_file=True,
    ):
        new_place = self.validate_new_place(
            name, category, city, address,
            latitude, longitude, rating, accessibility_details,
        )
        self._store_place(new_place)
        if save_to_file:
            self.save_places_to_csv()
        return new_place

    def update_accessibility_details(self, place_id, new_accessibility_details, save_to_file=True):
        place = self.get_place_by_id(place_id)

        cleaned_data, error_messages = validate_and_clean_place_data(
            place.place_id,
            place.name,
            place.category,
            place.city,
            place.address,
            place.latitude,
            place.longitude,
            place.rating,
            new_accessibility_details,
            place.date_added,
        )
        if error_messages:
            raise InvalidPlaceDataError(error_messages)

        old_accessibility_details = dict(place.accessibility_details)
        place.accessibility_details = cleaned_data["accessibility_details"]
        if save_to_file:
            self.save_places_to_csv()
        return old_accessibility_details

    def remove_place(self, place_id, save_to_file=True):
        place = self.get_place_by_id(place_id)
        self._unstore_place(place)
        if save_to_file:
            self.save_places_to_csv()
        return place
