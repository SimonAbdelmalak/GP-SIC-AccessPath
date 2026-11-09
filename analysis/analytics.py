from pathlib import Path
import numpy as np
import pandas as pd

from models.place import ACCESSIBILITY_FEATURES, PLACE_CSV_COLUMNS

DEFAULT_CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "places.csv"
REQUIRED_COLUMNS = list(PLACE_CSV_COLUMNS)

MIN_RATING = 0.0
MAX_RATING = 5.0

SCORE_BINS = [0, 20, 40, 60, 80, 100]
SCORE_LABELS = ["0-20", "20-40", "40-60", "60-80", "80-100"]

BOOLEAN_MAP = {
    "true": True,
    "false": False,
    "1": True,
    "0": False,
    "yes": True,
    "no": False,
    "y": True,
    "n": False,
}

def _to_nullable_boolean(value):
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if value is None or pd.isna(value):
        return pd.NA
    return BOOLEAN_MAP.get(str(value).strip().lower(), pd.NA)


def default_accessibility_score(feature_values, category=None):
    known = [
        bool(value) for value in feature_values.values()
        if value is not None and not pd.isna(value)
    ]
    if not known:
        return np.nan
    return round(sum(known) / len(known) * 100, 1)


def add_accessibility_scores(df, score_function=None):
    score_function = score_function or default_accessibility_score
    feature_columns = [c for c in ACCESSIBILITY_FEATURES if c in df.columns]

    scores = []
    for record in df.to_dict("records"):
        feature_values = {
            feature: (None if pd.isna(record[feature]) else bool(record[feature]))
            for feature in feature_columns
        }
        score = score_function(feature_values, record.get("category"))
        if score is None or pd.isna(score):
            scores.append(np.nan)
        else:
            scores.append(round(min(max(float(score), 0.0), 100.0), 1))

    df = df.copy()
    df["accessibility_score"] = pd.Series(scores, index=df.index, dtype="float64")
    return df


def clean_places_data(df, score_function=None):
    df = df.copy()
    df.columns = df.columns.str.strip()

    # Remove records without an ID or name, and duplicate IDs.
    df["place_id"] = df["place_id"].astype("string").str.strip()
    df["name"] = df["name"].astype("string").str.strip()
    df = df.dropna(subset=["place_id", "name"])
    df = df[(df["place_id"] != "") & (df["name"] != "")]
    df = df.drop_duplicates(subset=["place_id"], keep="first")

    # Clean text columns where available.
    for column in ("category", "city", "address"):
        if column in df.columns:
            df[column] = df[column].astype("string").str.strip()

    # Convert numbers safely.
    for column in ("rating", "latitude", "longitude"):
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    # Ratings outside the expected 0–5 range are invalid for analysis.
    if "rating" in df.columns:
        df.loc[~df["rating"].between(0, 5), "rating"] = pd.NA

    # Parse dates; invalid dates become missing.
    if "date_added" in df.columns:
        df["date_added"] = pd.to_datetime(df["date_added"], errors="coerce")

    for feature in ACCESSIBILITY_FEATURES:
        if feature in df.columns:
            df[feature] = df[feature].map(_to_nullable_boolean).astype("boolean")

    # denominator instead of being counted as unavailable.
    feature_columns = [c for c in ACCESSIBILITY_FEATURES if c in df.columns]
    if feature_columns:
        df["known_features_count"] = df[feature_columns].notna().sum(axis=1)
        df["available_features_count"] = (
            df[feature_columns].fillna(False).astype(int).sum(axis=1)
        )
    else:
        df["available_features_count"] = 0
        df["known_features_count"] = 0

    df = add_accessibility_scores(df, score_function)
    return df.reset_index(drop=True)


def load_places_data(csv_path=DEFAULT_CSV_PATH, score_function=None, return_raw=False):
    raw = pd.read_csv(csv_path)
    raw.columns = raw.columns.str.strip()

    missing_columns = [c for c in REQUIRED_COLUMNS if c not in raw.columns]
    if missing_columns:
        raise ValueError(
            "Dataset is missing required columns: " + ", ".join(missing_columns)
        )

    cleaned = clean_places_data(raw, score_function)
    return (cleaned, raw) if return_raw else cleaned

# Metrics and summaries
def get_dashboard_metrics(df):
    has_score = "accessibility_score" in df.columns and df["accessibility_score"].notna().any()
    has_rating = "rating" in df.columns and df["rating"].notna().any()
    return {
        "total_places": int(len(df)),
        "total_cities": int(df["city"].nunique()) if "city" in df.columns else 0,
        "total_categories": int(df["category"].nunique()) if "category" in df.columns else 0,
        "average_rating": round(float(df["rating"].mean()), 2) if has_rating else None,
        "average_accessibility_score": (
            round(float(df["accessibility_score"].mean()), 1) if has_score else None
        ),
    }

def _count_by(df, column, output_name="number_of_places"):
    if column not in df.columns:
        return pd.DataFrame(columns=[column, output_name])
    return (
        df.dropna(subset=[column])
        .groupby(column)
        .size()
        .reset_index(name=output_name)
        .sort_values([output_name, column], ascending=[False, True])
        .reset_index(drop=True)
    )

def _average_by(df, group_column, value_column, output_name):
    if group_column not in df.columns or value_column not in df.columns:
        return pd.DataFrame(columns=[group_column, output_name])
    result = (
        df.dropna(subset=[group_column])
        .groupby(group_column, as_index=False)[value_column]
        .mean()
        .rename(columns={value_column: output_name})
    )
    result[output_name] = result[output_name].round(2)
    return result.sort_values(
        [output_name, group_column], ascending=[False, True], na_position="last"
    ).reset_index(drop=True)


def get_places_by_category(df):
    return _count_by(df, "category")


def get_places_by_city(df):
    return _count_by(df, "city")

def get_average_rating_by_category(df):
    return _average_by(df, "category", "rating", "average_rating")


def get_average_score_by_category(df):
    return _average_by(df, "category", "accessibility_score", "average_score")


def get_average_score_by_city(df):
    return _average_by(df, "city", "accessibility_score", "average_score")


def get_feature_availability(df):
    columns = ["feature", "column", "available_places", "known_places", "availability_percent"]
    rows = []
    for feature in ACCESSIBILITY_FEATURES:
        if feature not in df.columns:
            continue
        known_values = df[feature].dropna()
        known_count = int(known_values.shape[0])
        available_count = int(known_values.astype(bool).sum()) if known_count else 0
        percent = round(available_count / known_count * 100, 1) if known_count else np.nan
        rows.append({
            "feature": feature.replace("_", " ").title(),
            "column": feature,
            "available_places": available_count,
            "known_places": known_count,
            "availability_percent": percent,
        })

    return (
        pd.DataFrame(rows, columns=columns)
        .sort_values("availability_percent", ascending=False, na_position="last")
        .reset_index(drop=True)
    )

def get_accessibility_score_distribution(df):
    if "accessibility_score" not in df.columns:
        df = clean_places_data(df)

    scores = df["accessibility_score"].dropna()
    binned = pd.cut(scores, bins=SCORE_BINS, labels=SCORE_LABELS, include_lowest=True)
    counts = binned.value_counts().reindex(SCORE_LABELS, fill_value=0)
    return counts.rename_axis("score_range").reset_index(name="number_of_places")


def get_feature_count_distribution(df):
    if "available_features_count" not in df.columns:
        df = clean_places_data(df)
    return (
        df.groupby("available_features_count")
        .size()
        .reindex(range(len(ACCESSIBILITY_FEATURES) + 1), fill_value=0)
        .rename_axis("available_features_count")
        .reset_index(name="number_of_places")
    )


def get_places_added_over_time(df):
    empty = pd.DataFrame(columns=["month", "places_added", "cumulative_places"])
    if "date_added" not in df.columns:
        return empty

    dated = df.dropna(subset=["date_added"]).copy()
    if dated.empty:
        return empty

    dated["month"] = dated["date_added"].dt.to_period("M").astype(str)
    result = (
        dated.groupby("month")
        .size()
        .reset_index(name="places_added")
        .sort_values("month")
        .reset_index(drop=True)
    )
    result["cumulative_places"] = result["places_added"].cumsum()
    return result

def get_data_insights(df):
    if df.empty:
        return ["No place data is available to analyze yet."]

    insights = []

    category_counts = get_places_by_category(df)
    if not category_counts.empty:
        top = category_counts.iloc[0]
        insights.append(
            f"Most represented category: {top['category']} "
            f"({int(top['number_of_places'])} places)."
        )

    rating_by_category = get_average_rating_by_category(df).dropna(subset=["average_rating"])
    if not rating_by_category.empty:
        top = rating_by_category.iloc[0]
        insights.append(
            f"Highest average rating: {top['category']} ({top['average_rating']}/5)."
        )

    feature_stats = get_feature_availability(df).dropna(subset=["availability_percent"])
    if not feature_stats.empty:
        most_common = feature_stats.iloc[0]
        least_common = feature_stats.iloc[-1]
        insights.append(
            f"Most available feature: {most_common['feature']} "
            f"({most_common['availability_percent']}%)."
        )
        insights.append(
            f"Least available feature: {least_common['feature']} "
            f"({least_common['availability_percent']}%)."
        )

    score_by_category = get_average_score_by_category(df).dropna(subset=["average_score"])

    if len(score_by_category) >= 2:
        best, worst = score_by_category.iloc[0], score_by_category.iloc[-1]
        insights.append(
            f"Most accessible category: {best['category']} "
            f"(average score {best['average_score']}/100); "
            f"least accessible: {worst['category']} ({worst['average_score']}/100)."
        )

    score_by_city = get_average_score_by_city(df).dropna(subset=["average_score"])
    if len(score_by_city) >= 2:
        worst_city = score_by_city.iloc[-1]
        insights.append(
            f"Lowest average accessibility by city: {worst_city['city']} "
            f"({worst_city['average_score']}/100)."
        )

    return insights


def get_cleaning_summary(original_df, cleaned_df):
    raw = original_df.copy()
    raw.columns = raw.columns.str.strip()

    def text_column(name):
        if name not in raw.columns:
            return pd.Series("", index=raw.index, dtype="string")
        return raw[name].astype("string").str.strip().fillna("")

    ids, names = text_column("place_id"), text_column("name")
    has_id_and_name = (ids != "") & (names != "")
    is_duplicate = ids[has_id_and_name].duplicated()

    # The raw rows that survive cleaning (same rule as clean_places_data).
    kept = raw[has_id_and_name][~is_duplicate]

    def count_invalid_and_missing(column, parser):
        if column not in kept.columns:
            return 0, 0
        present = kept[column].notna()
        parsed_ok = parser(kept[column]).notna()
        return int((present & ~parsed_ok).sum()), int((~present).sum())

    invalid_ratings, missing_ratings = count_invalid_and_missing(
        "rating",
        lambda s: pd.to_numeric(s, errors="coerce").where(
            pd.to_numeric(s, errors="coerce").between(MIN_RATING, MAX_RATING)
        ),
    )
    invalid_dates, missing_dates = count_invalid_and_missing(
        "date_added", lambda s: pd.to_datetime(s, errors="coerce")
    )

    unknown_by_feature = {
        feature: int(cleaned_df[feature].isna().sum())
        for feature in ACCESSIBILITY_FEATURES if feature in cleaned_df.columns
    }
    unrecognized_feature_values = sum(
        int((kept[f].notna() & kept[f].map(_to_nullable_boolean).isna()).sum())
        for f in ACCESSIBILITY_FEATURES if f in kept.columns
    )

    return {
        "original_rows": int(len(original_df)),
        "cleaned_rows": int(len(cleaned_df)),
        "removed_rows": int(len(original_df) - len(cleaned_df)),
        "rows_missing_id_or_name": int((~has_id_and_name).sum()),
        "duplicate_ids_removed": int(is_duplicate.sum()),
        "missing_ratings": missing_ratings,
        "invalid_ratings": invalid_ratings,
        "missing_dates": missing_dates,
        "invalid_dates": invalid_dates,
        "unknown_feature_values": int(sum(unknown_by_feature.values())),
        "unrecognized_feature_values": unrecognized_feature_values,
        "unknown_by_feature": unknown_by_feature,
    }