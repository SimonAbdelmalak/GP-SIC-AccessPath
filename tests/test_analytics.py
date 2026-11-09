import numpy as np
import pandas as pd

from analysis import analytics

FEATURES = analytics.ACCESSIBILITY_FEATURES
def make_raw(rows):
    base = {
        "place_id": "P001", "name": "A", "category": "Cafe", "city": "Cairo",
        "address": "1 Test Street", "latitude": 30.0, "longitude": 31.0,
        "rating": 4.0, "date_added": "2026-01-10",
    }
    base.update({f: True for f in FEATURES})
    return pd.DataFrame([{**base, **row} for row in rows])


def test_unknown_features_are_not_false():
    raw = make_raw([{"elevator": None, "wheelchair_ramp": False}])
    df = analytics.clean_places_data(raw)
    assert pd.isna(df.loc[0, "elevator"])
    assert df.loc[0, "known_features_count"] == len(FEATURES) - 1
    # 5 available out of 6 known features
    assert df.loc[0, "accessibility_score"] == round(5 / 6 * 100, 1)


def test_score_stays_in_range_and_all_unknown_is_nan():
    raw = make_raw([{f: None for f in FEATURES}, {f: False for f in FEATURES}])
    raw.loc[1, "place_id"] = "P002"
    df = analytics.clean_places_data(raw)
    assert np.isnan(df.loc[0, "accessibility_score"])
    assert df.loc[1, "accessibility_score"] == 0.0


def test_custom_score_function_is_used_and_clamped():
    raw = make_raw([{}])
    df = analytics.clean_places_data(raw, score_function=lambda features, category: 150)
    assert df.loc[0, "accessibility_score"] == 100.0


def test_invalid_ratings_dates_and_duplicates_are_handled():
    raw = make_raw([
        {"place_id": "P001", "rating": 9},
        {"place_id": "P001", "name": "dup"},
        {"place_id": "P002", "rating": "abc", "date_added": "not a date"},
        {"place_id": "", "name": "no id"},
    ])
    df = analytics.clean_places_data(raw)
    summary = analytics.get_cleaning_summary(raw, df)
    assert len(df) == 2
    assert summary["duplicate_ids_removed"] == 1
    assert summary["rows_missing_id_or_name"] == 1
    assert summary["invalid_ratings"] == 2
    assert summary["invalid_dates"] == 1
    assert df["rating"].isna().all()


def test_analytics_update_when_data_changes():
    raw = make_raw([{"place_id": "P001"}, {"place_id": "P002", "category": "Park"}])
    df = analytics.clean_places_data(raw)
    assert analytics.get_dashboard_metrics(df)["total_places"] == 2
    bigger = analytics.clean_places_data(
        pd.concat([raw, make_raw([{"place_id": "P003", "category": "Park"}])], ignore_index=True)
    )
    counts = analytics.get_places_by_category(bigger).set_index("category")["number_of_places"]
    assert analytics.get_dashboard_metrics(bigger)["total_places"] == 3
    assert counts["Park"] == 2


def test_score_distribution_covers_all_places():
    raw = make_raw([{"place_id": f"P00{i}"} for i in range(1, 4)])
    raw.loc[0, FEATURES] = False
    df = analytics.clean_places_data(raw)
    distribution = analytics.get_accessibility_score_distribution(df)
    assert distribution["number_of_places"].sum() == 3
    assert list(distribution["score_range"]) == analytics.SCORE_LABELS


def test_empty_dataframe_does_not_crash():
    df = analytics.clean_places_data(make_raw([{}]).iloc[0:0])
    assert analytics.get_dashboard_metrics(df)["total_places"] == 0
    assert analytics.get_data_insights(df) == ["No place data is available to analyze yet."]
    assert analytics.get_places_added_over_time(df).empty