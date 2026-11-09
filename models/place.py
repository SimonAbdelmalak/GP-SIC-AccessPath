import re
from datetime import date, datetime


ACCESSIBILITY_FEATURES = [
    "step_free_entrance",
    "wheelchair_ramp",
    "elevator",
    "accessible_restroom",
    "accessible_parking",
    "braille_signage",
    "wide_doorways",
]


ALLOWED_CATEGORIES = [
    "Cafe",
    "Restaurant",
    "Hospital",
    "Shopping Mall",
    "Museum",
    "Park",
    "Library",
    "University",
    "Hotel",
    "Transport Station",
    "Cinema",
]


PLACE_CSV_COLUMNS = [
    "place_id",
    "name",
    "category",
    "city",
    "address",
    "latitude",
    "longitude",
    "rating",
] + ACCESSIBILITY_FEATURES + ["date_added"]


PLACE_ID_PATTERN = re.compile(r"^P\d{3,}$")

DATE_FORMAT = "%Y-%m-%d"

MIN_RATING = 0.0
MAX_RATING = 5.0


class InvalidPlaceDataError(ValueError):

    def __init__(self, error_messages):
        self.error_messages = list(error_messages)
        super().__init__("; ".join(self.error_messages))


def _clean_text(value):
    if value is None:
        return ""
    return " ".join(str(value).split())


def _convert_to_boolean(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("true", "yes", "y", "1"):
            return True
        if text in ("false", "no", "n", "0"):
            return False
    raise ValueError("value must be True or False")


def _convert_to_float(value):
    if isinstance(value, bool):
        raise ValueError("value must be a number")
    return float(value)


def validate_and_clean_place_data(
    place_id,
    name,
    category,
    city,
    address,
    latitude,
    longitude,
    rating,
    accessibility_details,
    date_added=None,
):
    error_messages = []
    cleaned = {}

    place_id = _clean_text(place_id).upper()
    if not PLACE_ID_PATTERN.match(place_id):
        error_messages.append(
            "Place ID must start with 'P' followed by at least 3 digits (example: P001)."
        )
    cleaned["place_id"] = place_id

    name = _clean_text(name)
    if len(name) < 2 or len(name) > 100:
        error_messages.append("Name must be between 2 and 100 characters.")
    elif not any(character.isalnum() for character in name):
        error_messages.append("Name must contain at least one letter or digit.")
    cleaned["name"] = name

    category_text = _clean_text(category)
    matching_category = None
    for allowed_category in ALLOWED_CATEGORIES:
        if allowed_category.lower() == category_text.lower():
            matching_category = allowed_category
            break
    if matching_category is None:
        error_messages.append(
            "Category must be one of: " + ", ".join(ALLOWED_CATEGORIES) + "."
        )
        cleaned["category"] = category_text
    else:
        cleaned["category"] = matching_category

    city = _clean_text(city)
    if len(city) < 2 or len(city) > 50:
        error_messages.append("City must be between 2 and 50 characters.")
    cleaned["city"] = city

    address = _clean_text(address)
    if len(address) < 5 or len(address) > 150:
        error_messages.append("Address must be between 5 and 150 characters.")
    cleaned["address"] = address

    try:
        latitude_number = _convert_to_float(latitude)
        if not -90 <= latitude_number <= 90:
            error_messages.append("Latitude must be between -90 and 90.")
        cleaned["latitude"] = latitude_number
    except (ValueError, TypeError):
        error_messages.append("Latitude must be a number.")
        cleaned["latitude"] = latitude

    try:
        longitude_number = _convert_to_float(longitude)
        if not -180 <= longitude_number <= 180:
            error_messages.append("Longitude must be between -180 and 180.")
        cleaned["longitude"] = longitude_number
    except (ValueError, TypeError):
        error_messages.append("Longitude must be a number.")
        cleaned["longitude"] = longitude

    try:
        rating_number = _convert_to_float(rating)
        if not MIN_RATING <= rating_number <= MAX_RATING:
            error_messages.append(
                f"Rating must be between {MIN_RATING:g} and {MAX_RATING:g}."
            )
        cleaned["rating"] = round(rating_number, 1)
    except (ValueError, TypeError):
        error_messages.append("Rating must be a number.")
        cleaned["rating"] = rating

    cleaned_details = {}
    if not isinstance(accessibility_details, dict):
        error_messages.append("Accessibility details must be a dictionary.")
    else:
        unknown_features = [
            feature for feature in accessibility_details
            if feature not in ACCESSIBILITY_FEATURES
        ]
        if unknown_features:
            error_messages.append(
                "Unknown accessibility feature(s): " + ", ".join(map(str, unknown_features)) + "."
            )
        for feature in ACCESSIBILITY_FEATURES:

            raw_value = accessibility_details.get(feature, False)
            try:
                cleaned_details[feature] = _convert_to_boolean(raw_value)
            except ValueError:
                error_messages.append(f"'{feature}' must be True or False.")
                cleaned_details[feature] = False
    cleaned["accessibility_details"] = cleaned_details

    if date_added is None or _clean_text(date_added) == "":
        cleaned["date_added"] = date.today().strftime(DATE_FORMAT)
    else:
        date_text = _clean_text(date_added)
        try:
            parsed_date = datetime.strptime(date_text, DATE_FORMAT).date()
            if parsed_date > date.today():
                error_messages.append("Date added cannot be in the future.")
            cleaned["date_added"] = date_text
        except ValueError:
            error_messages.append("Date added must look like YYYY-MM-DD (example: 2026-10-12).")
            cleaned["date_added"] = date_text

    return cleaned, error_messages


class Place:

    def __init__(
        self,
        place_id,
        name,
        category,
        city,
        address,
        latitude,
        longitude,
        rating,
        accessibility_details,
        date_added=None,
    ):
        cleaned, error_messages = validate_and_clean_place_data(
            place_id, name, category, city, address,
            latitude, longitude, rating, accessibility_details, date_added,
        )
        if error_messages:
            raise InvalidPlaceDataError(error_messages)

        self.place_id = cleaned["place_id"]
        self.name = cleaned["name"]
        self.category = cleaned["category"]
        self.city = cleaned["city"]
        self.address = cleaned["address"]
        self.latitude = cleaned["latitude"]
        self.longitude = cleaned["longitude"]
        self.rating = cleaned["rating"]

        self.accessibility_details = cleaned["accessibility_details"]
        self.date_added = cleaned["date_added"]

    def get_available_features(self):
        return [
            feature for feature, is_available in self.accessibility_details.items()
            if is_available
        ]

    def get_missing_features(self):
        return [
            feature for feature, is_available in self.accessibility_details.items()
            if not is_available
        ]

    def to_dict(self):
        return {
            "place_id": self.place_id,
            "name": self.name,
            "category": self.category,
            "city": self.city,
            "address": self.address,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "rating": self.rating,
            "accessibility_details": dict(self.accessibility_details),
            "date_added": self.date_added,
        }

    def to_csv_row(self):
        row = {
            "place_id": self.place_id,
            "name": self.name,
            "category": self.category,
            "city": self.city,
            "address": self.address,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "rating": self.rating,
            "date_added": self.date_added,
        }
        for feature in ACCESSIBILITY_FEATURES:
            row[feature] = self.accessibility_details[feature]
        return {column: row[column] for column in PLACE_CSV_COLUMNS}

    @classmethod
    def from_csv_row(cls, row):
        accessibility_details = {
            feature: row.get(feature) for feature in ACCESSIBILITY_FEATURES
        }
        return cls(
            place_id=row.get("place_id"),
            name=row.get("name"),
            category=row.get("category"),
            city=row.get("city"),
            address=row.get("address"),
            latitude=row.get("latitude"),
            longitude=row.get("longitude"),
            rating=row.get("rating"),
            accessibility_details=accessibility_details,
            date_added=row.get("date_added"),
        )

    def __str__(self):
        return f"{self.place_id} - {self.name} ({self.category}, {self.city}) - rating {self.rating}"

    def __repr__(self):
        return f"Place(place_id={self.place_id!r}, name={self.name!r}, city={self.city!r})"
