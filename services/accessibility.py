import pandas as pd

from services.sorting_algorithms import merge_sort_places

def calculate_accessibility_score(place_obj_or_dict):
    score = 0
    max_score = 100

    weights = {
        'step_free_entrance': 20,
        'wheelchair_ramp': 20,
        'elevator': 20,
        'accessible_restroom': 15,
        'accessible_parking': 10,
        'braille_signage': 5,
        'wide_doorways': 10
    }

    if hasattr(place_obj_or_dict, 'accessibility_details'):
        details = place_obj_or_dict.accessibility_details
    elif isinstance(place_obj_or_dict, dict):
        details = place_obj_or_dict.get('accessibility_details', place_obj_or_dict)
    else:
        details = {}

    for feature, weight in weights.items():
        val = details.get(feature) if isinstance(details, dict) else getattr(details, feature, None)
        if val is not None:
            if val == True or val == 1 or str(val).lower() in ['true', '1', 'yes', 'available']:
                score += weight

    return min(score, max_score)


def compare_multiple_places(place_services_or_df, place_names_list):
    if not place_names_list:
        return {"error": "Please select at least one place to compare."}

    if hasattr(place_services_or_df, 'get_all_places'):
        places = place_services_or_df.get_all_places()
        data = []
        for p in places:
            p_dict = p.to_csv_row()
            p_dict['accessibility_score'] = calculate_accessibility_score(p)
            data.append(p_dict)
        df = pd.DataFrame(data)
    else:
        df = place_services_or_df

    if df is None or df.empty:
        return {"error": "Database is empty or unavailable."}

    lower_names = [name.strip().lower() for name in place_names_list]
    matched_df = df[df['name'].str.lower().isin(lower_names)].copy()

    if matched_df.empty:
        return {"error": "Sorry, none of the specified places were found in the database."}

    sorted_records, _ = merge_sort_places(matched_df, sort_by='score', descending=True)
    return pd.DataFrame(sorted_records)