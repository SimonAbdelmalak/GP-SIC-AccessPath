from typing import Any, Dict, Iterable, List, Optional

from services.search_algorithms import sequential_search, sequential_search_contains, binary_search
from services.sorting_algorithms import merge_sort_places


BOOLEAN_FEATURES = {
    "step_free_entrance",
    "wheelchair_ramp",
    "elevator",
    "accessible_restroom",
    "accessible_parking",
    "braille_signage",
    "wide_doorways",
}


def _records(places: Any) -> List[dict]:
    """Accept a list of dictionaries or a pandas DataFrame."""
    if hasattr(places, "to_dict") and hasattr(places, "columns"):
        return places.to_dict(orient="records")
    if places is None:
        return []
    return [dict(place) for place in places]


def _as_bool(value: Any) -> Optional[bool]:
    """Convert common CSV/string representations to bool; unknown values -> None."""
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    text = str(value).strip().casefold()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None


def filter_places(
    places: Any,
    category: Optional[str] = None,
    city: Optional[str] = None,
    min_rating: Optional[float] = None,
    required_features: Optional[Iterable[str]] = None,
    min_score: Optional[float] = None,
    max_score: Optional[float] = None,
) -> List[dict]:
    """Filter places using optional criteria and return matching records.

    Supported features are the seven boolean accessibility columns in places.csv.
    Score filtering is available only if another module has added 'score' or
    'accessibility_score' to each record.
    """
    records = _records(places)
    required = list(required_features or [])

    invalid_features = [feature for feature in required if feature not in BOOLEAN_FEATURES]
    if invalid_features:
        raise ValueError(
            "Unknown accessibility feature(s): " + ", ".join(invalid_features)
        )

    score_field = None
    if min_score is not None or max_score is not None:
        if records and all("accessibility_score" in p for p in records):
            score_field = "accessibility_score"
        elif records and all("score" in p for p in records):
            score_field = "score"
        else:
            raise ValueError(
                "Score filtering requires 'accessibility_score' or 'score' "
                "to be added by the Accessibility Engine."
            )

    results = []
    wanted_category = category.strip().casefold() if category else None
    wanted_city = city.strip().casefold() if city else None

    for place in records:
        place_category = str(place.get("category", "")).strip().casefold()
        place_city = str(place.get("city", "")).strip().casefold()

        if wanted_category and place_category != wanted_category:
            continue
        if wanted_city and place_city != wanted_city:
            continue

        if min_rating is not None:
            try:
                rating = float(place.get("rating"))
            except (TypeError, ValueError):
                continue
            if rating != rating or rating < float(min_rating):
                continue

        feature_match = True
        for feature in required:
            if _as_bool(place.get(feature)) is not True:
                feature_match = False
                break
        if not feature_match:
            continue

        if score_field is not None:
            try:
                score = float(place.get(score_field))
            except (TypeError, ValueError):
                continue
            if min_score is not None and score < float(min_score):
                continue
            if max_score is not None and score > float(max_score):
                continue

        results.append(place)

    return results


def get_filter_options(places: Any) -> dict:
    """Return unique categories and cities for dropdowns, without built-in sorting."""
    records = _records(places)
    categories, cities = set(), set()

    for place in records:
        category = place.get("category")
        city = place.get("city")
        if category is not None and str(category).strip():
            categories.add(str(category).strip())
        if city is not None and str(city).strip():
            cities.add(str(city).strip())

    return {"categories": list(categories), "cities": list(cities)}

#binary search
def search_places(places: Any, query: str, method: str = "sequential", partial: bool = True):
    selected_method = method.strip().casefold()
    if selected_method == "sequential":
        if partial:
            matches, comparisons = sequential_search_contains(places, query, key="name")
            return {"method": "sequential", "results": matches, "comparisons": comparisons}
        match, comparisons = sequential_search(places, query, key="name")
        return {"method": "sequential", "results": [match] if match else [], "comparisons": comparisons}

    if selected_method == "binary":
        sorted_places, sort_metrics = merge_sort_places(places, sort_by="name", descending=False)
        match, comparisons = binary_search(sorted_places, query, key="name")
        return {
            "method": "binary",
            "results": [match] if match else [],
            "comparisons": comparisons,
            "pre_sort_comparisons": sort_metrics["comparisons"],
        }

    raise ValueError("method must be 'sequential' or 'binary'.")


def sort_places(places: Any, sort_by: str = "rating", descending: bool = True):
    return merge_sort_places(places, sort_by=sort_by, descending=descending)
