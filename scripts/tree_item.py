from enums import ItemType, HeaderColumn
from maya_utils import getUniqueName, getCurrentFrame
from logger import getLogger

logger = getLogger("InterpBlendShape")

class InterpBlendShapeItem:
    def __init__(
        self,
        data,
        itemType=ItemType.ROOT,
        builder=None,
        targetIndex=-1,
    ):
        """
        Initialize a new InterpBlendShapeItem.

        Args:
            data        List of column values for this item.
            itemType    Role of this item in the tree (ROOT, PARENT, etc.).
            builder     Optional builder instance that created this item.
            targetIndex For array attributes (e.g. weight[index]), default is -1.
        """
        # identity & hierarchy
        self._type        = itemType
        self._data        = data
        self._parent      = None
        self._children    = []

        # node data specifics
        self._surfaces    = {}
        self._positions   = []
        self._targetIndex = targetIndex

        # state flags
        self._locked      = False
        self._connected   = False

        # animation data
        self._keyframes   = []
        self._hasSDK      = False
        # helpers
        self._builder     = builder
        self._tracker     = None

        # painted weights
        self._weightLocked = False
        self._weightNormalization = False

    def __repr__(self):
        """Return a string representation of the item."""
        return f"<Item {self._data} type={self._type}>"

    def name(self):
        """Convenience method to return the name (first column)."""
        return self.data(0)

    def getAttrName(self):
        """
        Return 'envelope' for parent items, else the target weight name.
        """
        return "envelope" if self.type() == ItemType.PARENT else self.name()

    def targetIndex(self):
        """
        Return the current target index. Parent items use -1.
        """
        return self._targetIndex

    def setTargetIndex(self, index):
        """
        Set the target index to the given value.
        """
        self._targetIndex = index

    def setLocked(self, value: bool):
        """Set whether the attribute is locked."""
        self._locked = value

    def getKeyframes(self) -> list[int]:
        """
        Returns a copy of the stored keyframe list.

        Returns:
            list[int]: Sorted list of stored keyframe times.
        """
        return list(self._keyframes)  # return a copy to prevent external mutation

    def setKeyframes(self, value):
        """
        Store a list of keyframe times for this item. This does not create or modify
        actual keyframes in Maya—it is only used for internal UI or state tracking.

        Args:
            value (list[int]): A list of frame numbers representing keyframe positions.
        """
        self._keyframes = value

    def clearKeyframes(self):
        """Clear all keyframes."""
        self._keyframes = []

    def hasSDK(self):
        """Return whether this item has SDK."""
        return self._hasSDK

    def setHasSDK(self, value):
        """Set whether this item has SDK."""
        self._hasSDK = bool(value)

    def setConnected(self, value: bool):
        """Set whether the attribute is connected to another node."""
        self._connected = value

    def isLocked(self):
        """Check if the attribute is locked."""
        return self._locked

    def hasKeyed(self):
        """
        Return True if there are any keyframes.
        """
        return bool(self.getKeyframes())

    def isConnected(self):
        """Check if the attribute is connected to another node."""
        return self._connected

    def isKeyOnCurrentTime(self):
        """
        Update and return whether the current frame has a keyframe (only if not SDK-driven).

        Returns:
            bool: True if there's a keyframe at the current frame, False otherwise.
        """
        has_key = False
        if not self.hasSDK():
            has_key = getCurrentFrame() in self.getKeyframes()

        self.setData(HeaderColumn.KEY, has_key)
        return has_key

    def appendChild(self, item):
        """Add a child item and set its parent to this item."""
        item._parent = self
        self._children.append(item)

    def insertChild(self, row, item):
        self._children.insert(row, item)
        item._parent = self

    def removeChild(self, child):
        """Remove the given child item from this item."""
        if child in self._children:
            self._children.remove(child)
            child._parent = None

    def child(self, row):
        """Return the child at the given row index."""
        if 0 <= row < len(self._children):
            return self._children[row]
        return None

    def childCount(self):
        """Return the number of children this item has."""
        return len(self._children)

    def columnCount(self):
        """Return the number of data columns in this item."""
        return len(self._data) if self._data else 0

    def data(self, column):
        """Return the data value at the given column index."""
        if 0 <= column < len(self._data):
            return self._data[column]
        return None

    def setData(self, column, value):
        """
        Set the data value at the given column index.

        Args:
            column (int): Column index to set.
            value (Any): Value to set.

        Returns:
            bool: True if successful, False otherwise.
        """
        if 0 <= column < len(self._data):
            self._data[column] = value
            return True
        return False

    def parent(self):
        """Return the parent item."""
        return self._parent

    def row(self):
        """
        Return the row index of this item within its parent's children list.

        Returns:
            int: Row index, or 0 if parent not found.
        """
        if self._parent:
            try:
                return self._parent._children.index(self)
            except ValueError:
                return 0
        return 0

    def type(self):
        """Return the item type (ROOT, PARENT, CHILD, INBETWEEN)."""
        return self._type

    def builder(self):
        """Return the builder/controller associated with this item."""
        return self._builder

    def getAllSurfaces(self):
        """Return the dictionary of all associated surface drivers."""
        return self._surfaces

    def setSurfaceData(self, value):
        """Set the dictionary of associated surface drivers."""
        self._surfaces = value

    def getSurfaceId(self, name):
        """
        Return the surfaceId for the given surface name, or None if not found.
        """
        return self._surfaces.get(name)

    def addSurface(self, name, surfaceId):
        """
        Add or update a surface driver entry, ensuring surfaceId is unique.

        - If surfaceId already exists (excluding "NONE": 0), replace the existing entry with the new name.
        - If not, create a new entry with a unique name.
        - The "NONE": 0 entry is preserved and never modified.

        Args:
            name (str): Desired surface name or label.
            surfaceId (int): Unique surface driver ID.

        Returns:
            str: The dictionary key used for the surface entry.
        """
        # Skip "NONE": 0 when checking for duplicates
        for key, val in list(self._surfaces.items()):
            if key == "NONE":
                continue
            if val == surfaceId:
                # Rename if name is different
                if key != name:
                    del self._surfaces[key]
                    self._surfaces[name] = surfaceId
                    return name
                else:
                    # Same name, overwrite value just in case
                    self._surfaces[key] = surfaceId
                    return key

        # surfaceId is new, add with unique name
        uniqueName = getUniqueName(name, self._surfaces)
        self._surfaces[uniqueName] = surfaceId
        return uniqueName

    def removeSurface(self, surfaceId):
        """
        Remove a surface driver entry by its unique surface ID.

        This method deletes any entry from the internal surface dictionary
        (`self._surfaces`) whose value matches the given `surfaceId`.
        The entry with name "NONE" is always preserved regardless of its value.

        Args:
            surfaceId (int): The unique surface driver ID to remove.

        Example:
            # Before: {"NONE": 0, "SurfaceA": 1, "SurfaceB": 2}
            removeSurface(1)
            # After: {"NONE": 0, "SurfaceB": 2}
        """
        self._surfaces = {
            name: sid for name, sid in self._surfaces.items()
            if name == "NONE" or sid != surfaceId
        }

    def removePosition(self, weight):
        """
        Safely removes a weight from the internal positions list if it exists.

        Parameters:
            weight (float): The weight value to remove.
        """
        if self._positions and weight in self._positions:
            self._positions.remove(weight)

    def addPosition(self, weight):
        """
        Adds a new inbetween weight or positional value to the internal positions list.

        Ensures no duplicates and maintains sorted order.

        Parameters:
            weight (float): The weight value to add (e.g., 0.5 for inbetween).

        Returns:
            bool: True if added, False if it already existed.
        """
        if not hasattr(self, '_positions') or self._positions is None:
            self._positions = []

        if weight in self._positions:
            return False

        self._positions.append(weight)
        self._positions.sort()
        return True

    def cleanup(self):
        if self._tracker:
            self._tracker.remove()
            self._tracker = None
        for child in self._children:
            child.cleanup()

    @property
    def positions(self):
        """
        Gets the current list of inbetween weights or positional data.

        Returns:
            list[float]: The list of stored weights.
        """
        return self._positions

    @positions.setter
    def positions(self, value):
        """
        Sets the list of inbetween weights or positional data.

        Parameters:
            value (list[float]): The new list of weights.
        """
        self._positions = value

    @property
    def weightLocked(self):
        """Whether the weight is locked."""
        return self._weightLocked

    @weightLocked.setter
    def weightLocked(self, value):
        """Set whether the weight is locked."""
        self._weightLocked = value

    @property
    def weightNormalization(self):
        """Whether weight normalization is enabled."""
        return self._weightNormalization

    @weightNormalization.setter
    def weightNormalization(self, value):
        """Set whether weight normalization is enabled."""
        self._weightNormalization = value
