PAGE_EXPLORE = "Explore & Search"
PAGE_COMPARE = "Compare Places"
PAGE_RECOMMEND = "Recommendations"
PAGE_DASHBOARD = "Dashboard"
PAGE_ALGORITHM_LAB = "Algorithm Lab"
PAGE_MANAGE_PLACES = "Manage Places"
PAGE_REVIEW_QUEUE = "Review Queue"


class PermissionDeniedError(Exception):
    pass

#inheritance user-visitor-admin-reviewer
class User:
    role_name = "User"
    description = ""

    def get_allowed_pages(self):
        return [
            PAGE_EXPLORE,
            PAGE_COMPARE,
            PAGE_RECOMMEND,
            PAGE_DASHBOARD,
            PAGE_ALGORITHM_LAB,
        ]

    def can_access_page(self, page_name):
        return page_name in self.get_allowed_pages()

    def can_submit_place_requests(self):
        return False

    def can_edit_places(self):
        return False

    def can_review_requests(self):
        return False

    def can_undo_changes(self):
        return False


class Visitor(User):
    role_name = "Visitor"
    description = (
        "Search, filter, compare and get recommendations for accessible places, "
        "and explore the accessibility dashboard."
    )


class VenueAdmin(Visitor):
    role_name = "Venue Admin"
    description = (
        "Everything a visitor can do, plus submit new places for review "
        "and update the accessibility details of existing places."
    )
#polymorphism
    def get_allowed_pages(self):
        return super().get_allowed_pages() + [PAGE_MANAGE_PLACES]

    def can_submit_place_requests(self):
        return True

    def can_edit_places(self):
        return True

    def can_undo_changes(self):
        return True


class Reviewer(Visitor):
    role_name = "Reviewer"
    description = (
        "Everything a visitor can do, plus approve or reject pending place requests "
        "and undo recent changes."
    )

    def get_allowed_pages(self):
        return super().get_allowed_pages() + [PAGE_REVIEW_QUEUE]

    def can_review_requests(self):
        return True

    def can_undo_changes(self):
        return True


ROLE_CLASSES = {
    Visitor.role_name: Visitor,
    VenueAdmin.role_name: VenueAdmin,
    Reviewer.role_name: Reviewer,
}

ROLE_NAMES = list(ROLE_CLASSES.keys())


def create_user(role_name):
    if role_name not in ROLE_CLASSES:
        raise ValueError(
            f"Unknown role '{role_name}'. Choose one of: " + ", ".join(ROLE_NAMES) + "."
        )
    return ROLE_CLASSES[role_name]()
