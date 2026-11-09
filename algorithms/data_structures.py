class AccessibilityUndoStack:
    def __init__(self):
        self.stack = []

    def save_state_before_update(self, place_id, old_data):
        self.stack.append({
            "place_id": place_id,
            "old_data": old_data
        })

    def undo(self):
        if self.is_empty():
            return None, None, "No actions to undo."

        last_action = self.stack.pop()
        return last_action["place_id"], last_action["old_data"], "Undo successful!"

    def is_empty(self):
        return len(self.stack) == 0


class PlaceReviewQueue:
    def __init__(self):
        self.queue = []

    def add_place_request(self, place_data):
        self.queue.append(place_data)

    def review_next_place(self):
        if not self.is_empty():
            return self.queue.pop(0)
        return None

    def is_empty(self):
        return len(self.queue) == 0

    def get_pending_requests(self):
        return self.queue


class PlaceHashLookup:
    def __init__(self, place_service):
        self.place_service = place_service
        self.lookup_table = {}
        self.refresh()

    def refresh(self):
        self.lookup_table = {}
        places = self.place_service.get_all_places()
        for p in places:
            self.lookup_table[str(p.place_id).strip().upper()] = p

    def get_by_id(self, place_id):
        return self.lookup_table.get(str(place_id).strip().upper(), None)