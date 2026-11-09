from services.accessibility import calculate_accessibility_score
from services.sorting_algorithms import merge_sort_places


def _place_matches_conditions(place, category, city, required_features):
    if category and category != "All" and place.category.lower() != category.lower():
        return False
    if city and city != "All" and place.city.lower() != city.lower():
        return False
    for feature in required_features or []:
        if not place.accessibility_details.get(feature, False):
            return False
    return True


def greedy_best_match(place_service, category=None, min_score=0, city=None, required_features=None):
    places = place_service.get_all_places()
    if not places:
        return None

    best_place = None
    max_score = -1

    for p in places:
        if not _place_matches_conditions(p, category, city, required_features):
            continue

        score = calculate_accessibility_score(p)
        if score < min_score:
            continue

        is_better_score = score > max_score
        is_tie_with_better_rating = score == max_score and p.rating > best_place.rating
        if is_better_score or is_tie_with_better_rating:
            max_score = score
            best_place = p

    if best_place:
        res = best_place.to_csv_row()
        res['accessibility_score'] = max_score
        return res
    return None


def recommend_top_places(place_service, top_n=3, category=None, city=None, required_features=None, min_score=0):
    places = place_service.get_all_places()
    scored_places = []

    for p in places:
        if not _place_matches_conditions(p, category, city, required_features):
            continue
        score = calculate_accessibility_score(p)
        if score < min_score:
            continue
        p_dict = p.to_csv_row()
        p_dict['accessibility_score'] = score
        scored_places.append(p_dict)

    sorted_places, _ = merge_sort_places(scored_places, sort_by="score", descending=True)
    return sorted_places[:top_n]
