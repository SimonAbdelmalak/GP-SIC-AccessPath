import pandas as pd
import streamlit as st

from analysis import dashboard
from services.app_services import AccessPathSystem
from models.place import ACCESSIBILITY_FEATURES, ALLOWED_CATEGORIES
from services.place_service import PlaceDataFileError
from services.roles import (
    PAGE_ALGORITHM_LAB,
    PAGE_COMPARE,
    PAGE_DASHBOARD,
    PAGE_EXPLORE,
    PAGE_MANAGE_PLACES,
    PAGE_RECOMMEND,
    PAGE_REVIEW_QUEUE,
    ROLE_NAMES,
    create_user,
)

st.set_page_config(page_title="AccessPath", page_icon="♿", layout="wide")

FEATURE_LABELS = {feature: feature.replace("_", " ").title() for feature in ACCESSIBILITY_FEATURES}

SORT_OPTIONS = {
    "Accessibility score": "score",
    "Rating": "rating",
    "Name": "name",
    "City": "city",
    "Category": "category",
}

SEARCH_METHODS = {
    "Sequential search (partial name match)": "sequential",
    "Binary search (exact name)": "binary",
}

RESULT_COLUMNS = {
    "place_id": "ID",
    "name": "Name",
    "category": "Category",
    "city": "City",
    "address": "Address",
    "rating": "Rating",
    "accessibility_score": "Accessibility score",
    "available_features_count": "Features available",
}


def get_system():
    if "system" not in st.session_state:
        try:
            st.session_state["system"] = AccessPathSystem()
        except PlaceDataFileError as error:
            st.error(str(error))
            st.stop()
    return st.session_state["system"]


def flash(kind, messages):
    st.session_state["flash"] = (kind, list(messages))


def show_flash():
    pending_flash = st.session_state.pop("flash", None)
    if pending_flash:
        kind, messages = pending_flash
        for message in messages:
            if kind == "success":
                st.success(message)
            else:
                st.error(message)


def finish_action(success, messages):
    flash("success" if success else "error", messages)
    st.rerun()


def yes_no_symbol(value):
    return "✅ Yes" if value else "❌ No"


def build_results_table(records):
    if not records:
        return pd.DataFrame(columns=list(RESULT_COLUMNS.values()))
    table = pd.DataFrame(records)[list(RESULT_COLUMNS.keys())]
    return table.rename(columns=RESULT_COLUMNS)


def choose_all_or_value(value):
    return None if value == "All" else value


def render_place_details(system, place_id):
    place = system.find_place_by_id(place_id)
    if place is None:
        st.warning(f"No place found with ID '{place_id}'.")
        return

    st.markdown(f"### {place.name}")
    st.caption(f"{place.category} · {place.city} · {place.address}")

    detail_columns = st.columns(3)
    detail_columns[0].metric("Rating", f"{place.rating} / 5")
    detail_columns[1].metric("Accessibility score", f"{system.get_place_score(place)} / 100")
    detail_columns[2].metric("Added on", place.date_added)

    feature_columns = st.columns(2)
    for index, feature in enumerate(ACCESSIBILITY_FEATURES):
        symbol = "✅" if place.accessibility_details[feature] else "❌"
        feature_columns[index % 2].markdown(f"{symbol} {FEATURE_LABELS[feature]}")


def render_explore_page(system):
    st.subheader("Find accessible places")
    options = system.get_filter_options()

    query_column, method_column = st.columns([3, 2])
    query = query_column.text_input(
        "Search by place name",
        key="explore_query",
        placeholder="For example: cafe, hospital, park",
    )
    method_label = method_column.radio(
        "Search method", list(SEARCH_METHODS), key="explore_method"
    )

    filter_columns = st.columns(4)
    category = filter_columns[0].selectbox(
        "Category", ["All"] + options["categories"], key="explore_category"
    )
    city = filter_columns[1].selectbox("City", ["All"] + options["cities"], key="explore_city")
    min_rating = filter_columns[2].slider(
        "Minimum rating", 0.0, 5.0, 0.0, 0.5, key="explore_min_rating"
    )
    min_score = filter_columns[3].slider(
        "Minimum accessibility score", 0, 100, 0, 5, key="explore_min_score"
    )

    required_features = st.multiselect(
        "Required accessibility features",
        ACCESSIBILITY_FEATURES,
        format_func=lambda feature: FEATURE_LABELS[feature],
        key="explore_required_features",
    )

    sort_columns = st.columns(2)
    sort_label = sort_columns[0].selectbox("Sort by", list(SORT_OPTIONS), key="explore_sort_by")
    order_label = sort_columns[1].radio(
        "Order", ["Highest first", "Lowest first"], horizontal=True, key="explore_order"
    )

    outcome = system.find_places(
        query=query,
        method=SEARCH_METHODS[method_label],
        category=choose_all_or_value(category),
        city=choose_all_or_value(city),
        min_rating=min_rating if min_rating > 0 else None,
        required_features=required_features,
        min_score=min_score if min_score > 0 else None,
        sort_by=SORT_OPTIONS[sort_label],
        descending=(order_label == "Highest first"),
    )
    results = outcome["results"]

    metric_columns = st.columns(4)
    metric_columns[0].metric("Places found", len(results))
    if outcome["search"] is not None:
        metric_columns[1].metric("Search comparisons", outcome["search"]["comparisons"])
    else:
        metric_columns[1].metric("Search comparisons", "-")
    metric_columns[2].metric("Merge sort comparisons", outcome["sort_metrics"]["comparisons"])
    metric_columns[3].metric("Merge sort recursive calls", outcome["sort_metrics"]["recursive_calls"])

    if outcome["search"] is not None and outcome["search"]["method"] == "binary":
        st.caption(
            f"Binary search first sorted the places by name with merge sort "
            f"({outcome['search']['pre_sort_comparisons']} comparisons), "
            f"then needed {outcome['search']['comparisons']} comparisons to find the name."
        )

    if not results:
        st.info("No places match these search words and filters. Try removing a filter.")
    else:
        st.dataframe(build_results_table(results), hide_index=True)

        download_columns = st.columns(2)
        download_columns[0].download_button(
            "Download results (CSV)",
            pd.DataFrame(results).to_csv(index=False).encode("utf-8"),
            file_name="accesspath_results.csv",
            mime="text/csv",
            key="download_results",
        )
        show_map = download_columns[1].checkbox("Show results on a map", key="explore_show_map")
        if show_map:
            map_data = pd.DataFrame(results)[["latitude", "longitude"]].dropna()
            st.map(map_data, latitude="latitude", longitude="longitude")

        st.markdown("#### Place details")
        detail_labels = {f"{record['place_id']} - {record['name']}": record["place_id"] for record in results}
        chosen_label = st.selectbox("Choose a place", list(detail_labels), key="explore_detail_choice")
        render_place_details(system, detail_labels[chosen_label])

    st.markdown("#### Quick lookup by place ID")
    lookup_id = st.text_input("Place ID (for example P001)", key="explore_lookup_id")
    if lookup_id.strip():
        render_place_details(system, lookup_id)


def render_compare_page(system):
    st.subheader("Compare places side by side")
    all_names = sorted({record["name"] for record in system.get_place_records()})
    selected_names = st.multiselect(
        "Choose 2 to 4 places to compare",
        all_names,
        max_selections=4,
        key="compare_names",
    )

    if len(selected_names) < 2:
        st.info("Select at least two places to see the comparison.")
        return

    comparison, error_message = system.compare_places(selected_names)
    if error_message:
        st.error(error_message)
        return

    row_labels = ["Category", "Rating", "Accessibility score"] + [
        FEATURE_LABELS[feature] for feature in ACCESSIBILITY_FEATURES
    ]
    table_columns = {}
    for _, row in comparison.iterrows():
        values = [row["category"], row["rating"], row["accessibility_score"]] + [
            yes_no_symbol(row[feature]) for feature in ACCESSIBILITY_FEATURES
        ]
        table_columns[f"{row['name']} ({row['city']})"] = [str(value) for value in values]
    st.dataframe(pd.DataFrame(table_columns, index=row_labels))

    best_place = comparison.iloc[0]
    st.success(
        f"Most accessible: {best_place['name']} with {best_place['accessibility_score']} / 100."
    )
    st.bar_chart(comparison, x="name", y="accessibility_score")


def render_recommend_page(system):
    st.subheader("Get a recommendation")
    st.caption("Tell us what you need and AccessPath picks the best matching place.")
    options = system.get_filter_options()

    input_columns = st.columns(3)
    category = input_columns[0].selectbox(
        "Category", ["All"] + options["categories"], key="recommend_category"
    )
    city = input_columns[1].selectbox("City", ["All"] + options["cities"], key="recommend_city")
    top_n = input_columns[2].slider("How many suggestions", 1, 10, 3, key="recommend_top_n")

    min_score = st.slider("Minimum accessibility score", 0, 100, 0, 5, key="recommend_min_score")
    required_features = st.multiselect(
        "Features you need",
        ACCESSIBILITY_FEATURES,
        format_func=lambda feature: FEATURE_LABELS[feature],
        key="recommend_required_features",
    )

    best_place, top_places = system.recommend(
        category=choose_all_or_value(category),
        city=choose_all_or_value(city),
        min_score=min_score,
        required_features=required_features,
        top_n=top_n,
    )

    if best_place is None:
        st.warning(
            "No place satisfies all of these conditions. "
            "Try lowering the minimum score or removing a required feature."
        )
    else:
        st.success(f"Best match: {best_place['name']} ({best_place['category']}, {best_place['city']})")
        best_columns = st.columns(2)
        best_columns[0].metric("Accessibility score", f"{best_place['accessibility_score']} / 100")
        best_columns[1].metric("Rating", f"{best_place['rating']} / 5")
        st.caption(best_place["address"])

        st.markdown(f"#### Top {len(top_places)} suggestions")
        st.dataframe(
            pd.DataFrame(top_places)[
                ["place_id", "name", "category", "city", "rating", "accessibility_score"]
            ].rename(columns={
                "place_id": "ID",
                "name": "Name",
                "category": "Category",
                "city": "City",
                "rating": "Rating",
                "accessibility_score": "Accessibility score",
            }),
            hide_index=True,
        )

    with st.expander("Why a greedy algorithm?"):
        st.markdown(
            "The recommendation looks at every place once and always keeps the place with the "
            "highest accessibility score that still satisfies the visitor's conditions "
            "(category, city, minimum score, required features). Equal scores are broken by the "
            "higher rating. Choosing the best option at each step is enough here because the "
            "score of one place does not depend on any other place, so no backtracking is needed."
        )


def render_dashboard_page(system):
    dashboard.render_dashboard(system.get_places_dataframe(), system.get_cleaning_summary())
    st.download_button(
        "Download summary report",
        system.build_summary_report().encode("utf-8"),
        file_name="accesspath_report.md",
        mime="text/markdown",
        key="download_summary_report",
    )


def render_algorithm_lab_page(system):
    st.subheader("Algorithm lab")
    st.caption("Live evidence of how the search and sorting algorithms behave on the current data.")

    st.markdown("#### Sequential search vs binary search")
    place_names = [record["name"] for record in system.get_place_records()]
    if not place_names:
        st.info("There are no places to search yet.")
        return

    searched_name = st.text_input(
        "Place name to look for (exact name)",
        value=place_names[0],
        key="lab_search_name",
    )
    sequential_result, binary_result = system.compare_search_methods(searched_name)
    comparison_table = pd.DataFrame([
        {
            "Method": "Sequential search",
            "Place found": "Yes" if sequential_result["results"] else "No",
            "Comparisons": sequential_result["comparisons"],
            "Needs sorted data": "No",
            "Sorting comparisons first": 0,
        },
        {
            "Method": "Binary search",
            "Place found": "Yes" if binary_result["results"] else "No",
            "Comparisons": binary_result["comparisons"],
            "Needs sorted data": "Yes",
            "Sorting comparisons first": binary_result["pre_sort_comparisons"],
        },
    ])
    st.dataframe(comparison_table, hide_index=True)
    st.caption(
        "Binary search needs far fewer comparisons, but it only works on sorted data, "
        "so the cost of sorting by name with merge sort is shown too."
    )

    st.markdown("#### Merge sort effort")
    evidence = pd.DataFrame(system.get_merge_sort_evidence()).rename(columns={
        "places_sorted": "Places sorted",
        "sorted_by": "Sorted by",
        "comparisons": "Comparisons",
        "recursive_calls": "Recursive calls",
    })
    st.dataframe(evidence, hide_index=True)

    with st.expander("Why these data structures?"):
        st.markdown(
            "- **Dictionary by place ID**: finding one place by its ID takes one step, "
            "used by the place storage and the hash-like lookup.\n"
            "- **Nested dictionary (city, then category)**: browsing places by city and category "
            "without scanning every place.\n"
            "- **Queue (first in, first out)**: place requests are reviewed in the order they arrive.\n"
            "- **Stack (last in, first out)**: the most recent change is the first one to be undone.\n"
            "- **Merge sort**: always about n log n comparisons, stable, and it counts its own work.\n"
            "- **Sequential search**: used on unsorted data and for partial name matches."
        )


def render_undo_controls(system, user, key_prefix):
    st.markdown("#### Undo history")
    history = system.get_undo_history()
    if history:
        st.dataframe(
            pd.DataFrame(history).rename(columns={
                "step": "Undo step",
                "place_id": "Place ID",
                "action": "Action",
            }),
            hide_index=True,
        )
    else:
        st.caption("There is nothing to undo yet.")

    if st.button("Undo last change", key=f"{key_prefix}_undo", disabled=not history):
        success, messages = system.undo_last_change(user)
        finish_action(success, messages)


def render_manage_page(system, user):
    st.subheader("Submit a new place")
    st.caption("New places are checked by a reviewer before they appear in the app.")

    with st.form("new_place_request_form", clear_on_submit=True):
        name = st.text_input("Place name")
        name_columns = st.columns(2)
        category = name_columns[0].selectbox("Category", ALLOWED_CATEGORIES)
        city = name_columns[1].text_input("City")
        address = st.text_input("Address")

        location_columns = st.columns(3)
        latitude = location_columns[0].text_input("Latitude", placeholder="For example 30.0444")
        longitude = location_columns[1].text_input("Longitude", placeholder="For example 31.2357")
        rating = location_columns[2].slider("Rating", 0.0, 5.0, 4.0, 0.1)

        st.markdown("**Accessibility features available at this place**")
        feature_columns = st.columns(2)
        new_details = {}
        for index, feature in enumerate(ACCESSIBILITY_FEATURES):
            new_details[feature] = feature_columns[index % 2].checkbox(
                FEATURE_LABELS[feature], key=f"new_place_{feature}"
            )

        submitted = st.form_submit_button("Submit for review")

    if submitted:
        success, messages = system.submit_place_request(
            user, name, category, city, address, latitude, longitude, rating, new_details
        )
        finish_action(success, messages)

    st.divider()
    st.subheader("Update accessibility details")

    places = system.place_service.get_all_places()
    if not places:
        st.info("There are no places to update yet.")
    else:
        place_labels = {f"{place.place_id} - {place.name} ({place.city})": place.place_id for place in places}
        chosen_label = st.selectbox("Choose a place", list(place_labels), key="edit_place_choice")
        chosen_place = system.find_place_by_id(place_labels[chosen_label])

        with st.form("edit_accessibility_form"):
            edit_columns = st.columns(2)
            edited_details = {}
            for index, feature in enumerate(ACCESSIBILITY_FEATURES):
                edited_details[feature] = edit_columns[index % 2].checkbox(
                    FEATURE_LABELS[feature],
                    value=chosen_place.accessibility_details[feature],
                    key=f"edit_{chosen_place.place_id}_{feature}",
                )
            saved = st.form_submit_button("Save changes")

        if saved:
            success, messages = system.update_place_accessibility(
                user, chosen_place.place_id, edited_details
            )
            finish_action(success, messages)

    st.divider()
    render_undo_controls(system, user, "manage")


def render_review_page(system, user):
    st.subheader("Pending place requests")
    pending_requests = system.get_pending_requests()

    if pending_requests:
        pending_table = pd.DataFrame([
            {
                "Position": position,
                "Name": request["name"],
                "Category": request["category"],
                "City": request["city"],
                "Address": request["address"],
                "Rating": request["rating"],
                "Features available": sum(request["accessibility_details"].values()),
            }
            for position, request in enumerate(pending_requests, start=1)
        ])
        st.dataframe(pending_table, hide_index=True)
        st.caption("Requests are reviewed in the order they arrived (first in, first out).")
    else:
        st.info("No requests are waiting for review.")

    button_columns = st.columns(2)
    if button_columns[0].button("Approve next request", key="approve_next", disabled=not pending_requests):
        success, messages = system.approve_next_request(user)
        finish_action(success, messages)
    if button_columns[1].button("Reject next request", key="reject_next", disabled=not pending_requests):
        success, messages = system.reject_next_request(user)
        finish_action(success, messages)

    st.divider()
    render_undo_controls(system, user, "review")

    st.divider()
    st.markdown("#### Activity history")
    if system.activity_log:
        st.dataframe(
            pd.DataFrame(system.activity_log).rename(columns={
                "time": "Time",
                "role": "Role",
                "action": "Action",
                "details": "Details",
            }),
            hide_index=True,
        )
    else:
        st.caption("No activity yet in this session.")


def render_sidebar(system):
    st.sidebar.title("AccessPath")
    st.sidebar.caption("Find, compare and improve accessible places.")

    role_name = st.sidebar.selectbox("Your role", ROLE_NAMES, key="selected_role")
    user = create_user(role_name)
    st.sidebar.info(user.description)

    counts = system.get_status_counts()
    st.sidebar.metric("Places in the system", counts["places"])
    st.sidebar.metric("Pending requests", counts["pending_requests"])
    st.sidebar.metric("Undo steps available", counts["undo_steps"])

    skipped_rows = len(system.place_service.load_error_messages)
    if skipped_rows:
        st.sidebar.warning(
            f"{skipped_rows} row(s) in places.csv were skipped because they were invalid. "
            "See the cleaning report on the Dashboard page."
        )

    if st.sidebar.button(
        "Reload places.csv",
        key="reload_data",
        help="Reads the data file again. Pending requests and undo history are cleared.",
    ):
        del st.session_state["system"]
        st.rerun()

    return user


def main():
    system = get_system()
    user = render_sidebar(system)

    st.title("♿ AccessPath")
    show_flash()

    page_renderers = {
        PAGE_EXPLORE: lambda: render_explore_page(system),
        PAGE_COMPARE: lambda: render_compare_page(system),
        PAGE_RECOMMEND: lambda: render_recommend_page(system),
        PAGE_DASHBOARD: lambda: render_dashboard_page(system),
        PAGE_ALGORITHM_LAB: lambda: render_algorithm_lab_page(system),
        PAGE_MANAGE_PLACES: lambda: render_manage_page(system, user),
        PAGE_REVIEW_QUEUE: lambda: render_review_page(system, user),
    }

    allowed_pages = user.get_allowed_pages()
    for tab, page_name in zip(st.tabs(allowed_pages), allowed_pages):
        with tab:
            page_renderers[page_name]()


main()
