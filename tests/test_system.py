import shutil
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from services.accessibility import calculate_accessibility_score, compare_multiple_places
from services.app_services import AccessPathSystem
from algorithms.data_structures import AccessibilityUndoStack, PlaceHashLookup, PlaceReviewQueue
from models.place import ACCESSIBILITY_FEATURES
from services.place_filters import filter_places, search_places, sort_places
from services.place_service import PlaceService
from services.recommendations import greedy_best_match, recommend_top_places
from services.roles import PermissionDeniedError, create_user
from services.search_algorithms import binary_search, sequential_search, sequential_search_contains
from services.sorting_algorithms import merge_sort_places

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "places.csv"

def make_temporary_csv():
    csv_path = Path(tempfile.mkdtemp()) / "places.csv"
    shutil.copy(DATA_FILE, csv_path)
    return csv_path


def make_system():
    return AccessPathSystem(make_temporary_csv())


def sample_records():
    return [
        {"name": "Beta", "rating": 4.0, "accessibility_score": 60, "elevator": True},
        {"name": "alpha", "rating": 4.8, "accessibility_score": 90, "elevator": False},
        {"name": "Gamma", "rating": 3.5, "accessibility_score": 30, "elevator": True},
        {"name": "Delta", "rating": 4.8, "accessibility_score": 75, "elevator": True},
    ]


def test_merge_sort_matches_expected_order_and_does_not_change_input():
    records = sample_records()
    original = [dict(record) for record in records]
    ordered, metrics = merge_sort_places(records, sort_by="rating", descending=True)
    assert [r["name"] for r in ordered] == ["alpha", "Delta", "Beta", "Gamma"]
    assert records == original
    assert metrics["comparisons"] > 0 and metrics["recursive_calls"] > 0


def test_merge_sort_agrees_with_python_sorted_on_every_field():
    records = sample_records() * 3
    for field, key in (("rating", "rating"), ("score", "accessibility_score")):
        ordered, _ = merge_sort_places(records, sort_by=field, descending=False)
        assert [r[key] for r in ordered] == sorted(r[key] for r in records)


def test_merge_sort_puts_none_nan_and_na_ratings_last():
    records = [{"name": "a", "rating": 4.0}, {"name": "b", "rating": np.nan},
               {"name": "c", "rating": 5.0}, {"name": "d", "rating": None},
               {"name": "e", "rating": pd.NA}, {"name": "f", "rating": 3.0}]
    for descending in (True, False):
        ordered, _ = merge_sort_places(records, sort_by="rating", descending=descending)
        assert [r["name"] for r in ordered[:3]] in (["c", "a", "f"], ["f", "a", "c"])
        assert sorted(r["name"] for r in ordered[3:]) == ["b", "d", "e"]


def test_merge_sort_rejects_unknown_field_and_missing_score():
    for call in (lambda: merge_sort_places(sample_records(), sort_by="color"),
                 lambda: merge_sort_places([{"name": "x"}, {"name": "y"}], sort_by="score")):
        try:
            call()
            assert False
        except ValueError:
            pass


def test_merge_sort_handles_empty_and_single_item_lists():
    assert merge_sort_places([], "rating")[0] == []
    assert merge_sort_places([{"rating": 1}], "rating")[0] == [{"rating": 1}]


def test_sequential_search_exact_partial_and_not_found():
    records = sample_records()
    match, comparisons = sequential_search(records, " ALPHA ")
    assert match["name"] == "alpha" and comparisons == 2
    matches, comparisons = sequential_search_contains(records, "ta")
    assert [m["name"] for m in matches] == ["Beta", "Delta"] and comparisons == 4
    assert sequential_search(records, "nothing")[0] is None
    assert sequential_search(records, "")[0] is None


def test_binary_search_needs_sorted_data():
    ordered, _ = merge_sort_places(sample_records(), sort_by="name", descending=False)
    match, comparisons = binary_search(ordered, "gamma")
    assert match["name"] == "Gamma" and comparisons >= 1
    assert binary_search(ordered, "zeta")[0] is None
    try:
        binary_search(sample_records(), "alpha")
        assert False
    except ValueError:
        pass


def test_binary_search_uses_fewer_comparisons_than_sequential_on_large_data():
    records = [{"name": f"place {number:04d}"} for number in range(1000)]
    _, sequential_comparisons = sequential_search(records, "place 0999")
    _, binary_comparisons = binary_search(records, "place 0999")
    assert binary_comparisons <= 10 < sequential_comparisons


def test_search_places_binary_reports_the_cost_of_sorting_first():
    outcome = search_places(sample_records(), "delta", method="binary")
    assert outcome["results"][0]["name"] == "Delta"
    assert outcome["pre_sort_comparisons"] > 0
    try:
        search_places(sample_records(), "delta", method="magic")
        assert False
    except ValueError:
        pass


def test_filter_places_by_features_rating_and_score():
    records = sample_records()
    assert len(filter_places(records, required_features=["elevator"])) == 3
    assert len(filter_places(records, min_rating=4.5)) == 2
    assert len(filter_places(records, min_score=70, required_features=["elevator"])) == 1
    records[0]["rating"] = np.nan
    assert all(r["name"] != "Beta" for r in filter_places(records, min_rating=1))
    try:
        filter_places(records, required_features=["jetpack"])
        assert False
    except ValueError:
        pass
    try:
        filter_places([{"name": "x"}], min_score=10)
        assert False
    except ValueError:
        pass


def test_accessibility_score_is_weighted_and_stays_between_0_and_100():
    assert calculate_accessibility_score({f: True for f in ACCESSIBILITY_FEATURES}) == 100
    assert calculate_accessibility_score({f: False for f in ACCESSIBILITY_FEATURES}) == 0
    assert calculate_accessibility_score({"elevator": True}) == 20
    assert calculate_accessibility_score({"braille_signage": "yes", "wide_doorways": 1}) == 15
    assert calculate_accessibility_score({}) == 0


def test_compare_places_is_sorted_and_reports_problems():
    service = PlaceService(make_temporary_csv())
    names = [place.name for place in service.get_all_places()[:4]]
    comparison = compare_multiple_places(service, names)
    scores = list(comparison["accessibility_score"])
    assert scores == sorted(scores, reverse=True)
    assert "error" in compare_multiple_places(service, ["no such place"])
    assert "error" in compare_multiple_places(service, [])


def test_undo_stack_is_last_in_first_out_and_safe_when_empty():
    stack = AccessibilityUndoStack()
    assert stack.undo() == (None, None, "No actions to undo.")
    stack.save_state_before_update("P001", {"a": 1})
    stack.save_state_before_update("P002", None)
    assert stack.undo()[:2] == ("P002", None)
    assert stack.undo()[:2] == ("P001", {"a": 1})
    assert stack.is_empty()


def test_review_queue_is_first_in_first_out():
    queue = PlaceReviewQueue()
    assert queue.review_next_place() is None
    queue.add_place_request({"name": "first"})
    queue.add_place_request({"name": "second"})
    assert queue.review_next_place() == {"name": "first"}
    assert queue.get_pending_requests() == [{"name": "second"}]


def test_hash_lookup_ignores_case_and_follows_changes_after_refresh():
    service = PlaceService(make_temporary_csv())
    lookup = PlaceHashLookup(service)
    first = service.get_all_places()[0]
    assert lookup.get_by_id(f" {first.place_id.lower()} ") is first
    created = service.add_place("Lookup Cafe", "Cafe", "Cairo", "4 Lookup Street", 30, 31, 4, {}, save_to_file=False)
    assert lookup.get_by_id(created.place_id) is None
    lookup.refresh()
    assert lookup.get_by_id(created.place_id) is created
    assert lookup.get_by_id("P999999") is None


def test_greedy_best_match_picks_highest_score_and_breaks_ties_by_rating():
    service = PlaceService(make_temporary_csv())
    best = greedy_best_match(service)
    top_score = max(calculate_accessibility_score(place) for place in service.get_all_places())
    assert best["accessibility_score"] == top_score
    tied = [p for p in service.get_all_places() if calculate_accessibility_score(p) == top_score]
    assert best["rating"] == max(p.rating for p in tied)
    assert greedy_best_match(service, category="Cafe", min_score=101) is None
    assert greedy_best_match(service, category="Atlantis") is None


def test_greedy_best_match_respects_city_and_required_features():
    service = PlaceService(make_temporary_csv())
    best = greedy_best_match(service, city="Cairo", required_features=["braille_signage"])
    assert best["city"] == "Cairo" and best["braille_signage"] is True


def test_recommend_top_places_is_limited_and_sorted():
    service = PlaceService(make_temporary_csv())
    top = recommend_top_places(service, top_n=4)
    scores = [place["accessibility_score"] for place in top]
    assert len(top) == 4 and scores == sorted(scores, reverse=True)


def test_dashboard_scores_match_the_accessibility_engine():
    system = make_system()
    dataframe = system.get_places_dataframe()
    for _, row in dataframe.iterrows():
        place = system.find_place_by_id(row["place_id"])
        assert row["accessibility_score"] == calculate_accessibility_score(place)


def test_find_places_combines_filters_search_and_sorting():
    system = make_system()
    outcome = system.find_places(query="cafe", city="Cairo", sort_by="rating")
    assert outcome["results"]
    assert all("cafe" in r["name"].lower() and r["city"] == "Cairo" for r in outcome["results"])
    ratings = [r["rating"] for r in outcome["results"]]
    assert ratings == sorted(ratings, reverse=True)
    assert outcome["search"]["comparisons"] == outcome["records_after_filters"]
    assert system.find_places(query="zzzz")["results"] == []


def test_roles_enforce_permissions():
    system = make_system()
    visitor, admin, reviewer = create_user("Visitor"), create_user("Venue Admin"), create_user("Reviewer")
    details = {feature: False for feature in ACCESSIBILITY_FEATURES}
    for call in (
        lambda: system.submit_place_request(visitor, "X Cafe", "Cafe", "Cairo", "1 X Street", 30, 31, 4, details),
        lambda: system.approve_next_request(admin),
        lambda: system.update_place_accessibility(visitor, "P001", details),
        lambda: system.undo_last_change(visitor),
    ):
        try:
            call()
            assert False
        except PermissionDeniedError:
            pass
    assert create_user("Venue Admin").can_access_page("Manage Places")
    assert not visitor.can_access_page("Review Queue") and reviewer.can_access_page("Review Queue")
    try:
        create_user("Hacker")
        assert False
    except ValueError:
        pass


def test_request_flow_submit_approve_and_undo():
    system = make_system()
    admin, reviewer = create_user("Venue Admin"), create_user("Reviewer")
    before = system.place_service.get_place_count()

    success, messages = system.submit_place_request(
        admin, "Flow Cafe", "Cafe", "Cairo", "7 Flow Street", "30.1", "31.2", 4.5, {"elevator": True})
    assert success and len(system.get_pending_requests()) == 1
    assert system.place_service.get_place_count() == before

    success, _ = system.submit_place_request(
        admin, "flow cafe", "Cafe", "Cairo", "7 Flow Street", 30, 31, 4, {})
    assert not success

    success, _ = system.approve_next_request(reviewer)
    new_place = system.place_service.get_all_places()[-1]
    assert success and new_place.name == "Flow Cafe" and system.find_place_by_id(new_place.place_id)
    assert len(system.get_places_dataframe()) == before + 1

    success, _ = system.undo_last_change(reviewer)
    assert success and system.place_service.get_place_count() == before
    assert system.find_place_by_id(new_place.place_id) is None


def test_invalid_requests_are_refused_with_every_message():
    system = make_system()
    admin = create_user("Venue Admin")
    success, messages = system.submit_place_request(admin, "", "Spaceship", "", "x", "abc", "999", 10, {})
    assert not success and len(messages) >= 5
    assert system.get_pending_requests() == []
    assert system.approve_next_request(create_user("Reviewer")) == (False, ["There are no pending requests."])


def test_reject_removes_request_without_adding_a_place():
    system = make_system()
    before = system.place_service.get_place_count()
    system.submit_place_request(create_user("Venue Admin"), "Reject Cafe", "Cafe", "Cairo", "8 Reject Street", 30, 31, 3, {})
    success, _ = system.reject_next_request(create_user("Reviewer"))
    assert success and system.get_pending_requests() == []
    assert system.place_service.get_place_count() == before


def test_editing_accessibility_updates_score_and_can_be_undone():
    system = make_system()
    admin = create_user("Venue Admin")
    place_id = system.place_service.get_all_places()[0].place_id
    old_score = system.get_place_score(system.find_place_by_id(place_id))
    all_true = {feature: True for feature in ACCESSIBILITY_FEATURES}

    success, _ = system.update_place_accessibility(admin, place_id, all_true)
    assert success and system.get_place_score(system.find_place_by_id(place_id)) == 100
    dataframe = system.get_places_dataframe()
    assert dataframe.loc[dataframe["place_id"] == place_id, "accessibility_score"].iloc[0] == 100

    assert system.update_place_accessibility(admin, place_id, all_true) == (False, ["No changes were made."])
    assert system.update_place_accessibility(admin, "P99999", all_true)[0] is False

    success, _ = system.undo_last_change(admin)
    assert success and system.get_place_score(system.find_place_by_id(place_id)) == old_score
    assert system.undo_last_change(admin) == (False, ["No actions to undo."])


def test_dashboard_numbers_change_when_data_changes():
    system = make_system()
    before = system.get_places_dataframe()
    system.place_service.add_place("Growth Cafe", "Cafe", "Cairo", "6 Growth Street", 30, 31, 4, {}, save_to_file=False)
    system._data_changed()
    after = system.get_places_dataframe()
    assert len(after) == len(before) + 1


def test_reports_can_be_built():
    system = make_system()
    report = system.build_summary_report()
    assert report.startswith("# AccessPath summary report") and "Top 5" in report
    evidence = system.get_merge_sort_evidence()
    assert evidence and all(row["comparisons"] > 0 for row in evidence)
    sequential, binary = system.compare_search_methods(system.place_service.get_all_places()[0].name)
    assert sequential["results"] and binary["results"]
