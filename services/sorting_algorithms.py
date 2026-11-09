from typing import Any, Dict, List, Tuple

def _records(places: Any) -> List[dict]:
    if hasattr(places, "to_dict") and hasattr(places, "columns"):
        return places.to_dict(orient="records")
    if places is None:
        return []
    return [dict(place) for place in places]


def _is_missing(value) -> bool:
    if value is None:
        return True
    try:
        return bool(value != value)
    except TypeError:
        return True


def _sort_value(place: dict, sort_by: str):
    field = sort_by.strip().casefold()

    if field == "score":
        # Hager's Accessibility Engine may attach either field name.
        if "accessibility_score" in place:
            value = place.get("accessibility_score")
        elif "score" in place:
            value = place.get("score")
        else:
            raise ValueError(
                "Cannot sort by score: each place needs 'accessibility_score' "
                "or 'score' from the Accessibility Engine."
            )
    else:
        value = place.get(field)

    if _is_missing(value):
        return None
    if isinstance(value, str):
        return value.strip().casefold()
    return value


def merge_sort_places(
    places: Any, sort_by: str = "rating", descending: bool = True
) -> Tuple[List[dict], dict]:
    records = _records(places)
    field = sort_by.strip().casefold()
    allowed = {"name", "category", "city", "rating", "score"}
    if field not in allowed:
        raise ValueError(f"Unsupported sort field '{sort_by}'. Choose from {sorted(allowed)}.")

    metrics = {"comparisons": 0, "recursive_calls": 0}

    # Store original position to keep sorting stable when values are equal.
    indexed = list(enumerate(records))

    def value_for(item):
        return _sort_value(item[1], field)

    def comes_before(left_item, right_item):
        metrics["comparisons"] += 1
        left_value = value_for(left_item)
        right_value = value_for(right_item)

        # Missing values are always placed last.
        if left_value is None and right_value is None:
            return left_item[0] <= right_item[0]
        if left_value is None:
            return False
        if right_value is None:
            return True

        if left_value == right_value:
            return left_item[0] <= right_item[0]
        if descending:
            return left_value > right_value
        return left_value < right_value
#merge sort
    def merge_sort(items):
        metrics["recursive_calls"] += 1
        if len(items) <= 1:
            return items

        middle = len(items) // 2
        left = merge_sort(items[:middle])
        right = merge_sort(items[middle:])
        merged = []
        i = j = 0

        while i < len(left) and j < len(right):
            if comes_before(left[i], right[j]):
                merged.append(left[i])
                i += 1
            else:
                merged.append(right[j])
                j += 1

        merged.extend(left[i:])
        merged.extend(right[j:])
        return merged

    result = merge_sort(indexed)
    return [item[1] for item in result], metrics
