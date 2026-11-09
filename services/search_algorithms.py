from typing import Any, Dict, Iterable, List, Optional, Tuple

Record = Dict[str, Any]


def _records(places: Any) -> List[Record]:
    """Accept a list of dictionaries or a pandas DataFrame."""
    if hasattr(places, "to_dict") and hasattr(places, "columns"):
        return places.to_dict(orient="records")
    if places is None:
        return []
    return [dict(place) for place in places]


def _normalise(value: Any) -> str:
    return "" if value is None else str(value).strip().casefold()

# sequential search
def sequential_search(
    places: Any, target: Any, key: str = "name"
) -> Tuple[Optional[Record], int]:
    """Return (first matching record or None, number of comparisons)."""
    records = _records(places)
    wanted = _normalise(target)
    comparisons = 0

    if not wanted:
        return None, comparisons

    for place in records:
        comparisons += 1
        if _normalise(place.get(key)) == wanted:
            return place, comparisons

    return None, comparisons


def sequential_search_contains(
    places: Any, query: str, key: str = "name"
) -> Tuple[List[Record], int]:
    """Return all records whose field contains query, case-insensitively."""
    records = _records(places)
    wanted = _normalise(query)
    comparisons = 0

    if not wanted:
        return [], comparisons

    matches = []
    for place in records:
        comparisons += 1
        if wanted in _normalise(place.get(key)):
            matches.append(place)

    return matches, comparisons


def binary_search(
    sorted_places: Any, target: Any, key: str = "name"
) -> Tuple[Optional[Record], int]:
    """Return (matching record or None, comparisons).

    IMPORTANT: sorted_places must be sorted ascending by `key`, case-insensitively.
    Use merge_sort_places(..., sort_by=key, descending=False) before calling.
    A ValueError is raised if the records are not sorted, preventing silent bad results.
    """
    records = _records(sorted_places)
    wanted = _normalise(target)
    comparisons = 0

    if not wanted:
        return None, comparisons

    values = [_normalise(place.get(key)) for place in records]
    if any(values[i] > values[i + 1] for i in range(len(values) - 1)):
        raise ValueError(
            f"Binary search requires records sorted ascending by '{key}'. "
            "Sort them first using merge_sort_places(..., descending=False)."
        )

    left, right = 0, len(records) - 1
    while left <= right:
        middle = (left + right) // 2
        comparisons += 1
        current = _normalise(records[middle].get(key))

        if current == wanted:
            return records[middle], comparisons
        if current < wanted:
            left = middle + 1
        else:
            right = middle - 1

    return None, comparisons
