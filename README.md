# AccessPath

AccessPath helps people find, compare and improve accessible places (cafes, hospitals, museums, hotels and more).
The flow follows the project brief: add place, score accessibility, search, recommend.

## How to run

1. Put all files in one folder (the file names must stay exactly as they are).
2. Install the requirements: `pip install -r requirements.txt`
3. Start the app: `streamlit run app.py`
4. Run the tests (optional): `pip install pytest` then `python -m pytest`

## User roles

| Role | What they can do |
|---|---|
| Visitor | Search, filter, sort, compare, get recommendations, view the dashboard and the algorithm lab |
| Venue Admin | Everything a visitor can do, plus submit new places for review, update accessibility details, and undo changes |
| Reviewer | Everything a visitor can do, plus approve or reject pending place requests, and undo changes |

The role is chosen in the sidebar. Permissions are enforced in `app_services.py`, not only hidden in the interface.

## Files and owners

| File | Owner | Purpose |
|---|---|---|
| `place.py`, `place_service.py`, `places.csv` | Mennatallah ahmed| Place class, validation, storage, browsing, adding and updating places, dataset |
| `search_algorithms.py`, `sorting_algorithms.py`, `place_filters.py` | Mai elaraby | Sequential and binary search, manual merge sort, filtering |
| `accessibility.py`, `recommendations.py`, `data_structures.py` | hagar ahmed | Accessibility score, compare places, greedy recommendation, stack, queue, hash-like lookup |
| `analytics.py`, `dashboard.py`, `test_analytics.py` | Simon Abdelmalak| Pandas cleaning, grouping, insights, charts, tests |
| `app.py`, `app_services.py`, `roles.py` | Moamen hamed | Streamlit interface, integration of all modules, user roles |
| `test_place_service.py`, `test_system.py` | Shared | Tests for storage, algorithms and the full workflow |

## Dataset

`places.csv` holds 30 sample places in 5 cities. The names and accessibility values are made up for the project.
Each place has an ID, name, category, city, address, coordinates, rating, seven accessibility features (True or False) and the date it was added.
The app works with changed data: edit or replace `places.csv` (keeping the same columns) and use "Reload places.csv" in the sidebar.

## Main data structures

- **Dictionary by place ID** (`PlaceService`, `PlaceHashLookup`): finding a place by its ID in one step.
- **Nested dictionary** `{city: {category: [place IDs]}}` (`PlaceService`): browsing by city and category.
- **Nested dictionary** for each place's accessibility details `{feature: True or False}`.
- **Queue** (`PlaceReviewQueue`): place requests are reviewed first in, first out.
- **Stack** (`AccessibilityUndoStack`): the last change is the first to be undone.
- **Classes and inheritance**: `Place`, `PlaceService`, and the roles `Visitor`, `VenueAdmin` and `Reviewer` (the last two extend `Visitor`).
- **Validation**: a regex for place IDs (`P` followed by 3 or more digits), ranges for ratings and coordinates, allowed categories, duplicate checks, and custom exceptions.

## Algorithms and why

- **Sequential search**: used for partial name search, because the data is not sorted by name.
- **Binary search**: used for exact name search only after the places are sorted by name; it refuses unsorted input.
- **Merge sort (written by hand, no built-in sort)**: sorts by score, rating, name, city or category. It counts comparisons and recursive calls, shown in the app.
- **Greedy algorithm**: the recommendation keeps the highest-scoring place that satisfies the visitor's conditions in a single pass, because one place's score does not depend on another's.
- **Weighted scoring**: the accessibility score out of 100 uses fixed weights per feature (step-free entrance 20, ramp 20, elevator 20, restroom 15, parking 10, wide doorways 10, braille 5).

The Algorithm Lab tab shows live evidence: comparisons for sequential vs binary search and the merge sort effort on the current data.

## Analytics

`analytics.py` cleans the data (missing and invalid ratings, dates, duplicates, unknown features), groups and aggregates it, and produces insights, a time-based view of places added per month, and four charts on the Dashboard tab. The dashboard also shows a cleaning report and can download a summary report.

## Testing notes

- `test_place_service.py`: validation, CSV loading with bad rows, adding, duplicates, nested index, updating details.
- `test_system.py`: sorting with missing values, both searches, filters, score, stack, queue, lookup, greedy choice, role permissions, and the submit, approve and undo workflow.
- `test_analytics.py`: cleaning, scores, insights, and numbers changing with the data.

## AI-use log 


| app.py | tab and design