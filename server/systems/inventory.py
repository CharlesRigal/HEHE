class InventoryIsFull(Exception):
    pass


class Inventory:
    def __init__(self, inventory_slot: int):
        self.inventory_slot = inventory_slot
        self._items = [] # no stack in the system

    def add_item(self, item) -> bool:
        if self._items.__len__() <= self.inventory_slot:
            self._items.append(item)
            return True
        else:
            return False

    def get_items(self) -> list:
        return self._items

    def remove_item(self, item):
        self._items.remove(item)