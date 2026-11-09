from datetime import datetime

import pandas as pd

from algorithms.data_structures import PlaceHashLookup, AccessibilityUndoStack, PlaceReviewQueue
from analysis import analytics
from models.place import PLACE_CSV_COLUMNS, InvalidPlaceDataError, ACCESSIBILITY_FEATURES
from services.accessibility import calculate_accessibility_score, compare_multiple_places
from services.place_filters import filter_places, get_filter_options, search_places, sort_places
from services.place_service import DEFAULT_CSV_PATH, PlaceDataFileError, PlaceNotFoundError, PlaceService
from services.recommendations import greedy_best_match, recommend_top_places
from services.roles import PermissionDeniedError


class AccessPathSystem:

    def __init__(self, csv_path=DEFAULT_CSV_PATH):
        self.place_service = PlaceService(csv_path)
        self.place_lookup = PlaceHashLookup(self.place_service)
        self.undo_stack = AccessibilityUndoStack()
        self.review_queue = PlaceReviewQueue()
        self.activity_log = []
        self._cached_raw_dataframe = None
        self._cached_places_dataframe = None

    @staticmethod
    def score_for_analytics(feature_values, category=None):
        return calculate_accessibility_score(feature_values)

    def _data_changed(self):
        self._cached_raw_dataframe = None
        self._cached_places_dataframe = None
        self.place_lookup.refresh()

    def _log_activity(self, user, action, details):
        self.activity_log.append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "role": user.role_name,
            "action": action,
            "details": details,
        })

    @staticmethod
    def _require_permission(is_allowed, action_description):
        if not is_allowed:
            raise PermissionDeniedError(
                f"Your role is not allowed to {action_description}."
            )

    def get_places_dataframe(self):
        if self._cached_places_dataframe is None:
            raw_dataframe = pd.DataFrame(
                self.place_service.get_all_place_rows(), columns=PLACE_CSV_COLUMNS
            )
            self._cached_raw_dataframe = raw_dataframe
            self._cached_places_dataframe = analytics.clean_places_data(
                raw_dataframe, score_function=self.score_for_analytics
            )
        return self._cached_places_dataframe

    def get_place_records(self):
        return self.get_places_dataframe().to_dict("records")

    def get_cleaning_summary(self):
        cleaned_dataframe = self.get_places_dataframe()
        summary = analytics.get_cleaning_summary(self._cached_raw_dataframe, cleaned_dataframe)
        summary["rows_rejected_while_loading_csv"] = len(self.place_service.load_error_messages)
        summary["loading_messages"] = list(self.place_service.load_error_messages)
        return summary

    def get_filter_options(self):
        options = get_filter_options(self.get_place_records())
        return {
            "categories": sorted(options["categories"]),
            "cities": sorted(options["cities"]),
        }

    def get_status_counts(self):
        return {
            "places": self.place_service.get_place_count(),
            "pending_requests": len(self.review_queue.get_pending_requests()),
            "undo_steps": len(self.undo_stack.stack),
        }

    def find_place_by_id(self, place_id):
        return self.place_lookup.get_by_id(place_id)

    def get_place_score(self, place):
        return calculate_accessibility_score(place)

    def find_places(
        self,
        query="",
        method="sequential",
        category=None,
        city=None,
        min_rating=None,
        required_features=None,
        min_score=None,
        sort_by="score",
        descending=True,
    ):
        records = self.get_place_records()
        filtered_records = filter_places(
            records,
            category=category,
            city=city,
            min_rating=min_rating,
            required_features=required_features,
            min_score=min_score,
        )

        search_details = None
        matching_records = filtered_records
        clean_query = (query or "").strip()
        if clean_query:
            search_details = search_places(
                filtered_records,
                clean_query,
                method=method,
                partial=(method == "sequential"),
            )
            matching_records = search_details["results"]

        sorted_records, sort_metrics = sort_places(
            matching_records, sort_by=sort_by, descending=descending
        )
        return {
            "results": sorted_records,
            "records_after_filters": len(filtered_records),
            "search": search_details,
            "sort_metrics": sort_metrics,
        }

    def compare_places(self, place_names):
        outcome = compare_multiple_places(self.place_service, place_names)
        if isinstance(outcome, dict):
            return None, outcome["error"]
        return outcome, None

    def recommend(self, category=None, city=None, min_score=0, required_features=None, top_n=3):
        best_place = greedy_best_match(
            self.place_service,
            category=category,
            min_score=min_score,
            city=city,
            required_features=required_features,
        )
        top_places = recommend_top_places(
            self.place_service,
            top_n=top_n,
            category=category,
            city=city,
            required_features=required_features,
            min_score=min_score,
        )
        return best_place, top_places

    def compare_search_methods(self, place_name):
        records = self.get_place_records()
        sequential_result = search_places(records, place_name, method="sequential", partial=False)
        binary_result = search_places(records, place_name, method="binary")
        return sequential_result, binary_result

    def get_merge_sort_evidence(self):
        records = self.get_place_records()
        total = len(records)
        sizes = []
        for size in (total // 4, total // 2, total):
            if size > 0 and size not in sizes:
                sizes.append(size)

        evidence_rows = []
        for size in sizes:
            for sort_field in ("score", "rating"):
                _, metrics = sort_places(records[:size], sort_by=sort_field, descending=True)
                evidence_rows.append({
                    "places_sorted": size,
                    "sorted_by": sort_field,
                    "comparisons": metrics["comparisons"],
                    "recursive_calls": metrics["recursive_calls"],
                })
        return evidence_rows

    def get_pending_requests(self):
        return list(self.review_queue.get_pending_requests())

    def get_undo_history(self):
        history = []
        for step_number, entry in enumerate(reversed(self.undo_stack.stack), start=1):
            action = "Added place" if entry["old_data"] is None else "Edited accessibility details"
            history.append({
                "step": step_number,
                "place_id": entry["place_id"],
                "action": action,
            })
        return history

    def submit_place_request(
        self,
        user,
        name,
        category,
        city,
        address,
        latitude,
        longitude,
        rating,
        accessibility_details,
    ):
        self._require_permission(user.can_submit_place_requests(), "submit place requests")

        try:
            candidate_place = self.place_service.validate_new_place(
                name, category, city, address,
                latitude, longitude, rating, accessibility_details,
            )
        except InvalidPlaceDataError as error:
            return False, error.error_messages

        for pending_request in self.review_queue.get_pending_requests():
            same_name = pending_request["name"].lower() == candidate_place.name.lower()
            same_city = pending_request["city"].lower() == candidate_place.city.lower()
            if same_name and same_city:
                return False, [
                    f"A request for '{candidate_place.name}' in {candidate_place.city} is already waiting for review."
                ]

        self.review_queue.add_place_request({
            "name": candidate_place.name,
            "category": candidate_place.category,
            "city": candidate_place.city,
            "address": candidate_place.address,
            "latitude": candidate_place.latitude,
            "longitude": candidate_place.longitude,
            "rating": candidate_place.rating,
            "accessibility_details": dict(candidate_place.accessibility_details),
        })
        queue_position = len(self.review_queue.get_pending_requests())
        self._log_activity(user, "Submitted request", candidate_place.name)
        return True, [
            f"'{candidate_place.name}' was sent for review (position {queue_position} in the queue)."
        ]

    def approve_next_request(self, user):
        self._require_permission(user.can_review_requests(), "review place requests")

        if self.review_queue.is_empty():
            return False, ["There are no pending requests."]

        request = self.review_queue.review_next_place()
        try:
            new_place = self.place_service.add_place(**request)
        except InvalidPlaceDataError as error:
            self._log_activity(user, "Request removed (invalid)", request["name"])
            return False, [
                f"'{request['name']}' was removed from the queue because it is no longer valid."
            ] + error.error_messages
        except PlaceDataFileError as error:
            return False, [str(error)]

        self.undo_stack.save_state_before_update(new_place.place_id, None)
        self._data_changed()
        self._log_activity(user, "Approved request", f"{new_place.name} ({new_place.place_id})")
        return True, [f"'{new_place.name}' was approved and added as {new_place.place_id}."]

    def reject_next_request(self, user):
        self._require_permission(user.can_review_requests(), "review place requests")

        if self.review_queue.is_empty():
            return False, ["There are no pending requests."]

        request = self.review_queue.review_next_place()
        self._log_activity(user, "Rejected request", request["name"])
        return True, [f"The request for '{request['name']}' was rejected."]

    def update_place_accessibility(self, user, place_id, new_accessibility_details):
        self._require_permission(user.can_edit_places(), "edit places")

        try:
            current_details = self.place_service.get_accessibility_details(place_id)
        except PlaceNotFoundError as error:
            return False, [str(error)]

        normalized_new_details = {
            feature: bool(new_accessibility_details.get(feature, False))
            for feature in ACCESSIBILITY_FEATURES
        }
        if normalized_new_details == current_details:
            return False, ["No changes were made."]

        try:
            old_details = self.place_service.update_accessibility_details(
                place_id, normalized_new_details
            )
        except InvalidPlaceDataError as error:
            return False, error.error_messages
        except PlaceDataFileError as error:
            return False, [str(error)]

        self.undo_stack.save_state_before_update(place_id.strip().upper(), old_details)
        self._data_changed()
        self._log_activity(user, "Edited accessibility details", place_id)
        return True, [f"Accessibility details of {place_id.strip().upper()} were updated."]

    def undo_last_change(self, user):
        self._require_permission(user.can_undo_changes(), "undo changes")

        place_id, old_data, message = self.undo_stack.undo()
        if place_id is None:
            return False, [message]

        try:
            if old_data is None:
                removed_place = self.place_service.remove_place(place_id)
                result_message = f"Undo: '{removed_place.name}' ({place_id}) was removed."
            else:
                self.place_service.update_accessibility_details(place_id, old_data)
                result_message = f"Undo: the previous accessibility details of {place_id} were restored."
        except PlaceNotFoundError:
            return False, [f"Cannot undo: {place_id} no longer exists."]
        except PlaceDataFileError as error:
            return False, [str(error)]

        self._data_changed()
        self._log_activity(user, "Undo", place_id)
        return True, [result_message]

    def build_summary_report(self):
        dataframe = self.get_places_dataframe()
        metrics = analytics.get_dashboard_metrics(dataframe)

        def show(value, suffix=""):
            return "N/A" if value is None else f"{value}{suffix}"

        lines = [
            "# AccessPath summary report",
            "",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            "## Overview",
            f"- Places: {metrics['total_places']}",
            f"- Cities: {metrics['total_cities']}",
            f"- Categories: {metrics['total_categories']}",
            f"- Average rating: {show(metrics['average_rating'], ' / 5')}",
            f"- Average accessibility score: {show(metrics['average_accessibility_score'], ' / 100')}",
            "",
            "## Key insights",
        ]
        for insight in analytics.get_data_insights(dataframe):
            lines.append(f"- {insight}")

        lines += ["", "## Average accessibility score by city"]
        for _, row in analytics.get_average_score_by_city(dataframe).iterrows():
            lines.append(f"- {row['city']}: {show(row['average_score'], ' / 100')}")

        lines += ["", "## Top 5 most accessible places"]
        for place in recommend_top_places(self.place_service, top_n=5):
            lines.append(
                f"- {place['name']} ({place['category']}, {place['city']}): "
                f"{place['accessibility_score']} / 100"
            )
        return "\n".join(lines) + "\n"
