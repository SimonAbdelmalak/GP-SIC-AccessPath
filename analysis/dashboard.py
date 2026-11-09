import streamlit as st
from analysis import analytics

def _show(value, suffix=""):
    return "N/A" if value is None else f"{value}{suffix}"


def render_dashboard(df, cleaning_summary=None):
    if df.empty:
        st.info("No places to analyze yet.")
        return

    metrics = analytics.get_dashboard_metrics(df)
    columns = st.columns(5)
    columns[0].metric("Places", metrics["total_places"])
    columns[1].metric("Cities", metrics["total_cities"])
    columns[2].metric("Categories", metrics["total_categories"])
    columns[3].metric("Avg rating", _show(metrics["average_rating"], " / 5"))
    columns[4].metric("Avg accessibility", _show(metrics["average_accessibility_score"], " / 100"))

    st.subheader("Key insights")
    for insight in analytics.get_data_insights(df):
        st.markdown(f"- {insight}")

    left, right = st.columns(2)
    with left:
        st.subheader("Places by category")
        st.bar_chart(analytics.get_places_by_category(df), x="category", y="number_of_places")
    with right:
        st.subheader("Accessibility score distribution")
        st.bar_chart(
            analytics.get_accessibility_score_distribution(df),
            x="score_range", y="number_of_places",
        )

    left, right = st.columns(2)
    with left:
        st.subheader("Feature availability (%)")
        st.bar_chart(analytics.get_feature_availability(df), x="feature", y="availability_percent")
    with right:
        st.subheader("Places added over time")
        st.line_chart(analytics.get_places_added_over_time(df), x="month", y="cumulative_places")

    if cleaning_summary:
        with st.expander("Data cleaning report"):
            st.json(cleaning_summary)