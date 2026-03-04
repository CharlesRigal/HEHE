
class GraphGeo:
    def __init__(self):
        self._root_node:MagicalNode|None = None

    def add_node(self, primitive):
        if self._root_node is None:
            self._root_node = MagicalNode(primitive)
        else:
            node = self._root_node
            while node.child is not None:
                node = node.child
            node.child = MagicalNode(primitive)


class MagicalNode:
    def __init__(self, primitive, parent = None):
        self.primitive = primitive
        self.parent = parent
        self.child = None

    def set_child(self,child):
        self.child = child

