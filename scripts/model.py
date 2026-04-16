from PySide2 import QtCore, QtGui, QtWidgets
from data_builder import InterpBlendShapeDataBuilder
from tree_item import InterpBlendShapeItem
from enums import ItemType, ActionID, HeaderColumn, AttrName
from maya_utils import isInterpBlendShape
from contextlib import contextmanager
from logger import getLogger
import maya.api.OpenMaya as om
import maya.cmds as cmds

import time

logger = getLogger("InterpBlendShape")

class UpdateBlocker:
    """
    A utility class to temporarily block UI updates triggered by callbacks (e.g., MNodeMessage)
    when the UI itself is making changes to Maya nodes.

    Use this to avoid feedback loops or recursive updates. Wrap any attribute changes
    inside `with blocker.block():` to prevent the connected callback from reacting.

    Example:
        blocker = UpdateBlocker()

        with blocker.block():
            cmds.setAttr("myNode.weight", 0.5)

        if blocker.isBlocked():
            print("Currently blocking updates")
    """

    def __init__(self):
        self._blocked = False

    @contextmanager
    def block(self):
        self._blocked = True
        try:
            yield
        finally:
            self._blocked = False

    def isBlocked(self):
        return self._blocked

class BlendShapeModelBuilder(QtCore.QObject):
    """
    Worker class to build the blend shape tree model off the main thread.

    Usage:
        1. Call collectSnapshots() on the main thread to gather Maya data safely.
        2. Move this object to a QThread and call run() to build the item tree
           in the background without touching the Maya API.

    Emits:
        finished(rootItem): Emitted when building is complete with the root item.
    """
    finished = QtCore.Signal(object)

    def __init__(self, nodeChangedCallback):
        super().__init__()
        self._onNodeChanged = nodeChangedCallback
        self._snapshots = []

    def collectSnapshots(self):
        """
        Scan all interpBlendShape nodes and snapshot their data into plain dicts.
        Must be called on the main thread before moving to a background thread.
        """
        self._snapshots = []
        it = om.MItDependencyNodes(om.MFn.kDependencyNode)
        while not it.isDone():
            fnNode = om.MFnDependencyNode(it.thisNode())
            if isInterpBlendShape(fnNode):
                try:
                    builder = InterpBlendShapeDataBuilder(fnNode.name(), fnNode)
                    self._snapshots.append((builder, builder.snapshot()))
                except Exception as e:
                    logger.warning("Failed to snapshot node '%s': %s", fnNode.name(), e)
            it.next()

    @QtCore.Slot()
    def run(self):
        """
        Build the item tree from pre-collected snapshots.
        Safe to run on a background thread — no Maya API calls.
        """
        start_time = time.time()

        rootItem = InterpBlendShapeItem(HeaderColumn.headers(), ItemType.ROOT)

        for builder, snapshot in self._snapshots:
            parentItem = self._buildParentItem(builder, snapshot)
            rootItem.appendChild(parentItem)

        logger.info("Data built in %.3f seconds", time.time() - start_time)
        self.finished.emit(rootItem)

    def _buildParentItem(self, builder, snapshot) -> InterpBlendShapeItem:
        """Build a parent InterpBlendShapeItem from a plain-dict snapshot."""
        data = [
            snapshot["nodeName"],
            snapshot["envelope"],
            "", "", "", "", "", "", "", "",
            False,
        ]
        parentItem = InterpBlendShapeItem(data, ItemType.PARENT, builder)
        parentItem.setSurfaceData(snapshot["surfaces"])

        parentItem.setLocked(snapshot["isLocked"])
        parentItem.setConnected(snapshot["isConnected"])
        parentItem.setKeyframes(snapshot["keyframes"])
        parentItem.setHasSDK(snapshot["hasSDK"])
        if snapshot["keyframes"]:
            parentItem.isKeyOnCurrentTime()

        for tgt in snapshot["targets"]:
            childItem = self._buildChildItem(builder, tgt)
            parentItem.appendChild(childItem)

        return parentItem

    def _buildChildItem(self, builder, tgt) -> InterpBlendShapeItem:
        """Build a child InterpBlendShapeItem from a target snapshot dict."""
        data = [
            tgt["name"],
            tgt["weight"],
            tgt["surfaceDriver"],
            tgt["blendUV"],
            tgt["blendBezier"],
            tgt["blendLive"],
            tgt["offset"],
            tgt["curvature"],
            tgt["precision"],
            tgt["cached"],
            False,
        ]
        childItem = InterpBlendShapeItem(data, ItemType.CHILD, builder, tgt["targetIndex"])
        childItem.weightNormalization = tgt["weightNormalization"]
        childItem.weightLocked        = tgt["weightLocked"]
        childItem.setLocked(tgt["isLocked"])
        childItem.setConnected(tgt["isConnected"])
        childItem.setKeyframes(tgt["keyframes"])
        childItem.setHasSDK(tgt["hasSDK"])
        if tgt["keyframes"]:
            childItem.isKeyOnCurrentTime()

        for name, weight in zip(tgt["inbetweenNames"], tgt["inbetweenWeights"]):
            ibIndex = int(weight * 1000.0 + 5000)
            ibItem = InterpBlendShapeItem(
                [name, weight], ItemType.INBETWEEN, builder, ibIndex
            )
            childItem.appendChild(ibItem)

        if tgt["inbetweenWeights"]:
            childItem.positions = tgt["inbetweenWeights"]

        return childItem

class FilterProxyModel(QtCore.QSortFilterProxyModel):
    """
    Proxy model that filters blend shape tree items based on a regular expression.
    Allows filtering items recursively so parents are shown if any child matches.
    """
    def filterAcceptsRow(self, source_row, source_parent):
        """
        Determines if a row in the source model should be included in the filtered model.

        Args:
            source_row (int): Row number in the source model.
            source_parent (QModelIndex): Parent index in the source model.

        Returns:
            bool: True if the row or any of its children match the filter, False otherwise.
        """
        model = self.sourceModel()
        index0 = model.index(source_row, 0, source_parent)

        # Check current item
        data = model.data(index0, QtCore.Qt.DisplayRole)
        if data and self.filterRegExp().indexIn(data) >= 0:
            return True

        # Check recursively children
        for i in range(model.rowCount(index0)):
            if self.filterAcceptsRow(i, index0):
                return True

        return False

    def supportedDropActions(self):
        return self.sourceModel().supportedDropActions()

    def canDropMimeData(self, data, action, row, column, parent):
        if parent.isValid():
            sourceParent = self.mapToSource(parent)
            return self.sourceModel().canDropMimeData(data, action, row, column, sourceParent)
        return self.sourceModel().canDropMimeData(data, action, row, column, QtCore.QModelIndex())

    def dropMimeData(self, data, action, row, column, parent):
        if parent.isValid():
            sourceParent = self.mapToSource(parent)
            return self.sourceModel().dropMimeData(data, action, row, column, sourceParent)
        return self.sourceModel().dropMimeData(data, action, row, column, QtCore.QModelIndex())

class InterpBlendShapeModel(QtCore.QAbstractItemModel):
    """
    Model representing InterpBlendShape data with columns for various blendshape parameters.

    Attributes:
        NAME_COL (int): Column index for 'Name'.
        WEIGHT_COL (int): Column index for 'Weight'.
        SURFACE_COL (int): Column index for 'Drivers'.
        UV_COL (int): Column index for 'UV'.
        BEZIER_COL (int): Column index for 'Bezier'.
        LIVE_COL (int): Column index for 'Live'.
        OFFSET_COL (int): Column index for 'Offset'.
        CURVATURE_COL (int): Column index for 'Arc'.
        PRECISION_COL (int): Column index for 'Accu'.
        CACHE_COL (int): Column index for 'Cache'.
        KEY_COL (int): Column index for 'Key'.

    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.headers = HeaderColumn.headers()
        self.rootItem = InterpBlendShapeItem(self.headers, ItemType.ROOT)  # header root

        self._updateBlocker = UpdateBlocker()
        self._nodesCreatedFromUI = set()
        self._suppressSetData = False

    def flags(self, index):
        """
        Returns the item flags for the given model index, which define the item's capabilities.

        Items are editable unless:
          - They are in certain columns (UV, Bezier, Live).
          - They are INBETWEEN or PARENT type and the column is > 1.

        Args:
            index (QModelIndex): The index of the item.

        Returns:
            Qt.ItemFlags: The flags for the item (e.g., enabled, selectable, editable).
        """
        if not index.isValid():
            return QtCore.Qt.NoItemFlags | QtCore.Qt.ItemIsDropEnabled

        item = index.internalPointer()

        baseFlags = QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable

        # Drag enabled for PARENT and CHILD items (column 0 only)
        if index.column() == 0 and item.type() in (ItemType.PARENT, ItemType.CHILD):
            baseFlags |= QtCore.Qt.ItemIsDragEnabled

        # Drop enabled for PARENT and ROOT level
        if item.type() in (ItemType.PARENT, ItemType.ROOT):
            baseFlags |= QtCore.Qt.ItemIsDropEnabled

        # Editable columns
        if not (item.type() in (ItemType.PARENT, ItemType.INBETWEEN) and index.column() > 1) and \
                index.column() not in (HeaderColumn.UV, HeaderColumn.BEZIER, HeaderColumn.LIVE):
            baseFlags |= QtCore.Qt.ItemIsEditable

        return baseFlags

    def supportedDropActions(self):
        return QtCore.Qt.MoveAction

    def mimeTypes(self):
        return ["application/x-interpblendshape-item"]

    def mimeData(self, indexes):
        mimeData = QtCore.QMimeData()
        # Collect unique rows from column 0 only
        seen = set()
        payloads = []
        for index in indexes:
            if not index.isValid() or index.column() != 0:
                continue
            item = index.internalPointer()
            if item.type() not in (ItemType.PARENT, ItemType.CHILD):
                continue
            key = (item.type(), index.row())
            if key in seen:
                continue
            seen.add(key)
            parentName = item.parent().name() if item.type() == ItemType.CHILD else ""
            payloads.append(f"{item.type()}|{index.row()}|{parentName}")

        mimeData.setData(
            "application/x-interpblendshape-item",
            QtCore.QByteArray(";".join(payloads).encode())
        )
        return mimeData

    def canDropMimeData(self, data, action, row, column, parent):
        if not data.hasFormat("application/x-interpblendshape-item"):
            return False
        payload = data.data("application/x-interpblendshape-item").data().decode()
        try:
            # Take first entry only for validation
            firstEntry = payload.split(";")[0]
            itemType, sourceRow, parentName = firstEntry.split("|")
            itemType = int(itemType)
        except Exception:
            return False

        if itemType == ItemType.PARENT:
            return not parent.isValid()
        elif itemType == ItemType.CHILD:
            if not parent.isValid():
                return False
            parentItem = parent.internalPointer()
            return parentItem is not None and parentItem.name() == parentName
        return False

    def dropMimeData(self, data, action, row, column, parent):
        if action == QtCore.Qt.IgnoreAction:
            return True
        if not data.hasFormat("application/x-interpblendshape-item"):
            return False

        payload = data.data("application/x-interpblendshape-item").data().decode()
        entries = [e.split("|") for e in payload.split(";")]
        itemType = int(entries[0][0])

        if itemType == ItemType.PARENT:
            if parent.isValid():
                return False
            destRow = row if row != -1 else self.rootItem.childCount()
            sourceRows = sorted([int(e[1]) for e in entries], reverse=True)
            # Collect items before any removal
            items = [self.rootItem.child(r) for r in sourceRows if self.rootItem.child(r)]
            # Remove from bottom up to preserve indices
            for r in sourceRows:
                self.beginRemoveRows(QtCore.QModelIndex(), r, r)
                self.rootItem._children.pop(r)
                self.endRemoveRows()
                if r < destRow:
                    destRow -= 1
            # Insert at destination
            for item in reversed(items):
                self.beginInsertRows(QtCore.QModelIndex(), destRow, destRow)
                self.rootItem._children.insert(destRow, item)
                self.endInsertRows()
            return True

        elif itemType == ItemType.CHILD:
            if not parent.isValid():
                return False
            parentItem = parent.internalPointer()
            parentName = entries[0][2]
            if not parentItem or parentItem.name() != parentName:
                return False
            destRow = row if row != -1 else parentItem.childCount()
            sourceRows = sorted([int(e[1]) for e in entries], reverse=True)
            items = [parentItem.child(r) for r in sourceRows if parentItem.child(r)]
            parentIndex = self.indexFromItem(parentItem)
            for r in sourceRows:
                self.beginRemoveRows(parentIndex, r, r)
                parentItem._children.pop(r)
                self.endRemoveRows()
                if r < destRow:
                    destRow -= 1
            for item in reversed(items):
                self.beginInsertRows(parentIndex, destRow, destRow)
                parentItem._children.insert(destRow, item)
                self.endInsertRows()
            return True

        return False

    def setRootItem(self, rootItem):
        """
        Set the root item of the model and reset the model.

        Args:
            rootItem (InterpBlendShapeItem): The new root item for the model.
        """
        self.beginResetModel()
        self.rootItem = rootItem
        self.endResetModel()

    def rowCount(self, parent=QtCore.QModelIndex()):
        """
        Return the number of rows under the given parent.

        Args:
            parent (QModelIndex): The parent index.

        Returns:
            int: Number of child rows under parent.
        """
        if not parent.isValid():
            parentItem = self.rootItem
        else:
            parentItem = parent.internalPointer()
        return parentItem.childCount()

    def columnCount(self, parent=QtCore.QModelIndex()):
        """
        Return the number of columns for the children of the given parent.

        Args:
            parent (QModelIndex): The parent index.

        Returns:
            int: Number of columns.
        """
        return self.rootItem.columnCount()

    def data(self, index, role=QtCore.Qt.DisplayRole):
        """
        Returns the data stored under the given role for the item referred to by the index.

        Applies restrictions on which columns are accessible for certain item types.

        Args:
            index (QModelIndex): The index of the item to retrieve data for.
            role (int): The role for which data is requested (default is DisplayRole).

        Returns:
            Any: The data for the given role and index, or None if not valid or not applicable.
        """
        if not index.isValid():
            return None

        item = index.internalPointer()
        column = index.column()
        # Restrict accessible columns for INBETWEEN items
        if item.type() == ItemType.INBETWEEN:
            if column > HeaderColumn.WEIGHT:
                return None
        # Restrict accessible columns for PARENT items
        elif item.type() == ItemType.PARENT:
            if column > HeaderColumn.WEIGHT and column != HeaderColumn.KEY:
                return None

        if role == QtCore.Qt.ToolTipRole:
            if index.column() == HeaderColumn.SURFACE:
                value = item.data(HeaderColumn.SURFACE)
                return str(value) if value != "NONE" else None

        if role in (QtCore.Qt.DisplayRole, QtCore.Qt.EditRole):
            return item.data(column)

        return None

    def setData(self, index, value, role=QtCore.Qt.EditRole, live=False):
        """
        Sets the role data for the item at the given index to the specified value.

        This method also handles syncing changes with the Maya scene, and rolls back
        if the operation fails. Both DisplayRole and EditRole are emitted to ensure
        that proxy models and views update properly.

        Optimization:
            - If the new value is equal to the existing value (preValue), the update
              is skipped to avoid unnecessary signals and Maya sync.
            - For float values, a tolerance threshold (1e-5) is used to avoid redundant
              updates caused by precision rounding errors from UI input (e.g., sliders).

        Args:
            index (QModelIndex): The model index to update.
            value (Any): The new value to assign.
            role (int): The data role being edited (default is EditRole).

        Returns:
            bool: True if the value was set and synchronized successfully, False otherwise.
        """
        if getattr(self, "_suppressSetData", False):
            return False

        if not index.isValid() or role != QtCore.Qt.EditRole:
            return False

        item = index.internalPointer()
        column = index.column()
        preValue = item.data(column)

        if column not in (HeaderColumn.CACHE, HeaderColumn.KEY):
            # this runs for all columns except CACHE and KEY
            if isinstance(value, float) and isinstance(preValue, float):
                if abs(value - preValue) < 1e-5:
                    return False  # Skip update for nearly equal floats
            elif value == preValue:
                return False  # Skip update for exact matches

        item._data[column] = value

        # Emit dataChanged to refresh views and proxy models
        self.dataChanged.emit(index, index, [QtCore.Qt.DisplayRole, QtCore.Qt.EditRole])

        # Synchronize with Maya, rollback on failure
        targetName = self.getTargetName(index)
        if targetName:
            success = self.applyDataChangeToMaya(column, targetName, value, item, preValue, live=live)
            if not success:
                item._data[column] = preValue  # Revert change
                return False

        return True


    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
        if orientation != QtCore.Qt.Horizontal:
            return None

        try:
            column = HeaderColumn(section)
        except ValueError:
            return None

        if role == QtCore.Qt.DisplayRole:
            headers = HeaderColumn.headers()
            if 0 <= section < len(headers):
                return headers[section]
            return ""

        elif role == QtCore.Qt.ToolTipRole:
            tooltips = HeaderColumn.tooltips()
            if 0 <= section < len(tooltips):
                return tooltips[section]
            return ""

        return None

    def itemFromIndex(self, index):
        """
        Returns the internal item associated with the given model index.

        Args:
            index (QModelIndex): The model index to resolve.

        Returns:
            InterpBlendShapeItem or None: The item at the index, or None if invalid.
        """
        return index.internalPointer() if index.isValid() else None

    def indexFromItem(self, item, column=0):
        """
        Returns the QModelIndex for the given item and column.

        Args:
            item (InterpBlendShapeItem): The tree item to look up.
            column (int): The desired column index.

        Returns:
            QModelIndex: The index if found, otherwise an invalid index.
        """
        if item is None or item == self.rootItem:
            return QtCore.QModelIndex()

        parent = item.parent()
        if not parent:
            return QtCore.QModelIndex()

        try:
            row = parent._children.index(item)
        except ValueError:
            return QtCore.QModelIndex()

        return self.createIndex(row, column, item)

    def removeItems(self, items, modelOnly=False):
        """
        Removes one or more items from Maya (via their builder()) and the model.

        Args:
            items (InterpBlendShapeItem or list[InterpBlendShapeItem]): Single item or list of items to remove.
            modelOnly (bool): If True, skip Maya-side deletion and remove from model only.

        Returns:
            int: Number of successfully removed items.
        """
        if not isinstance(items, (list, tuple)):
            items = [items]  # Normalize to list

        deletedCount = 0
        itemsByParent = {}

        # Group items by parent
        for item in items:
            parent = item.parent()
            if parent:
                itemsByParent.setdefault(parent, []).append(item)

        for parentItem, children in itemsByParent.items():
            # Sort in reverse row order to avoid shifting issues
            for child in sorted(children, key=lambda i: i.row(), reverse=True):
                builder = child.builder()
                targetName = child.name()
                itemType = child.type()
                currentWeight = child.data(HeaderColumn.WEIGHT)
                success = False
                if not modelOnly:
                    try:
                        # Dispatch based on item type
                        if itemType == ItemType.PARENT:
                            with self._updateBlocker.block():
                                success = builder.deleteInterpBlendShape()

                        elif itemType == ItemType.CHILD:
                            with self._updateBlocker.block():
                                success = builder.deleteTarget(targetName)

                        elif itemType == ItemType.INBETWEEN:
                            targetName = child.parent().name()
                            with self._updateBlocker.block():
                                success = builder.deleteInbetween(targetName, currentWeight)

                            if success:
                                child.parent().removePosition(currentWeight)

                    except Exception as e:
                        logger.warning(f"[Builder Delete Error] Failed to delete {targetName}: {e}")
                        continue

                    if not success:
                        continue  # Skip model deletion if Maya-side deletion failed
                else:
                    if itemType == ItemType.INBETWEEN:
                        child.parent().removePosition(currentWeight)
                # Remove from model
                row = child.row()
                parentIndex = (
                    QtCore.QModelIndex()
                    if parentItem == self.rootItem
                    else self.createIndex(parentItem.row(), 0, parentItem)
                )
                aliasName = child.name()
                self.beginRemoveRows(parentIndex, row, row)
                parentItem.removeChild(child)
                # update target dict data
                if parentItem:
                    builder = parentItem.builder()
                    if builder:
                        builder.aliasDictCache.pop(aliasName, None)
                self.endRemoveRows()

                deletedCount += 1

        return deletedCount


    def index(self, row, column, parent):
        """
        Returns the QModelIndex for the given row, column, and parent.

        Args:
            row (int): Row number of the child.
            column (int): Column number.
            parent (QModelIndex): The parent index.

        Returns:
            QModelIndex: The index corresponding to the given row and column under the parent.
                        Returns invalid QModelIndex if parameters are out of range.
        """
        if not self.hasIndex(row, column, parent):
            return QtCore.QModelIndex()

        if not parent.isValid():
            parentItem = self.rootItem
        else:
            parentItem = parent.internalPointer()

        childItem = parentItem.child(row)
        if childItem:
            return self.createIndex(row, column, childItem)

        return QtCore.QModelIndex()

    def parent(self, index):
        """
        Returns the parent QModelIndex of the given index.

        Args:
            index (QModelIndex): The child index.

        Returns:
            QModelIndex: The parent index of the given child index.
                        Returns invalid QModelIndex if the parent is root or no parent exists.
        """
        if not index.isValid():
            return QtCore.QModelIndex()

        childItem = index.internalPointer()
        parentItem = childItem.parent()

        if parentItem == self.rootItem or parentItem is None:
            return QtCore.QModelIndex()

        return self.createIndex(parentItem.row(), 0, parentItem)

    def addNewInterpBlendShapeNode(self, nodeName=None):
        """
        Creates a new interpBlendShape node in Maya and adds it to the model.

        If no nodeName is provided, a new interpBlendShape node is created via the Maya command,
        and its name is tracked as originating from the UI. Then:
        - The node is resolved to an MObject and wrapped in an MFnDependencyNode.
        - An InterpBlendShapeDataBuilder is used to generate the corresponding model item.
        - The new item is inserted under the root of the model.

        Args:
            nodeName (str, optional): The name of an existing interpBlendShape node. If None,
                                      a new node will be created.

        Returns:
            InterpBlendShapeItem or bool: The created model item if successful, or False if creation failed.

        Raises:
            RuntimeError: If the node creation command fails (only caught internally).
        """
        try:

            if not nodeName:
                nodeName = cmds.interpBlendShape()
                self._nodesCreatedFromUI.add(nodeName)
            sel = om.MSelectionList()
            sel.add(nodeName)
            nodeObj = sel.getDependNode(0)
            fnNode = om.MFnDependencyNode(nodeObj)

            builder = InterpBlendShapeDataBuilder(nodeName, fnNode)
            newParentItem = builder.build(builder)

            self.insertItem(self.rootItem, newParentItem)
            return newParentItem

        except RuntimeError as e:
            logger.error(f"Failed to create interpBlendShape node: {e}")
            return False

    def insertItem(self, parentItem, newItems):
        if not isinstance(newItems, (list, tuple)):
            newItems = [newItems]

        for item in newItems:
            # Insert sorted only if item is inbetween
            if item.type() == ItemType.INBETWEEN:
                weight = item.data(HeaderColumn.WEIGHT)
                insertRow = 0
                for i, child in enumerate(parentItem._children):
                    if child.type() != ItemType.INBETWEEN:
                        continue
                    childWeight = child.data(HeaderColumn.WEIGHT)
                    if childWeight is None or childWeight > weight:
                        break
                    insertRow += 1
            else:
                # Default to appending at the end
                insertRow = parentItem.childCount()

            parentIndex = self.indexFromItem(parentItem)
            self.beginInsertRows(parentIndex, insertRow, insertRow)
            parentItem.insertChild(insertRow, item)
            self.endInsertRows()

    def getTargetName(self, index):
        """
        Returns the target attribute name used for syncing to Maya,
        based on the item type at the given model index.

        Args:
            index (QModelIndex): The index pointing to the item in the model.

        Returns:
            str or None: The name of the target attribute (e.g., alias name, 'envelope'),
                         or None if the index is invalid or item type is unrecognized.
        """
        item = self.itemFromIndex(index)
        if not item:
            return None

        if item.type() == ItemType.CHILD:
            return item.name()  # Use alias name
        elif item.type() == ItemType.PARENT:
            return "envelope"
        elif item.type() == ItemType.INBETWEEN:
            parent = item.parent()
            return parent.name() if parent else None

        return None

    def applyDataChangeToMaya(self, column, targetName, value, item, preValue, live=False):
        success = False
        itemType = item.type()
        builder = item.builder()

        with self._updateBlocker.block():
            # -- Rename Logic --
            if column == HeaderColumn.NAME:
                newName = None
                if itemType == ItemType.CHILD:
                    newName = builder.updateAlias(value, preValue)
                elif itemType == ItemType.PARENT:
                    newName = builder.renameNode(value)
                elif itemType == ItemType.INBETWEEN:
                    weight = item.data(HeaderColumn.WEIGHT)
                    newName = builder.setInbetweenTargetName(item.parent().name(), weight, value)

                if newName:
                    if newName != value:
                        self.revertValue(item, newName, column)
                    return True
                return False

            # -- Weight Logic --
            elif column == HeaderColumn.WEIGHT:
                if itemType == ItemType.INBETWEEN:
                    if 0 < value < 1:
                        success = builder.updateInbetweenTarget(targetName, value, preValue, item.name())
                        if success:
                            parent = item.parent()
                            parent.removePosition(preValue)
                            parent.addPosition(value)
                            item.setTargetIndex(int(value * 1000 + 5000))
                    else:
                        self.revertValue(item, preValue, column)
                        logger.warning("Inbetween weights must be between 0 and 1.")
                        return False
                elif live:
                    if itemType == ItemType.PARENT:
                        success = builder.setEnvelopeLive(value)
                    else:
                        success = builder.setTargetWeightLive(targetName, value)
                else:
                    # On release — inside _updateBlocker to suppress callback feedback,
                    # undo chunk is inside setTargetWeight/setEnvelopeValue
                    if itemType == ItemType.PARENT:
                        success = builder.setEnvelopeValue(value)
                    else:
                        success = builder.setTargetWeight(targetName, value)
            # -- Other Attribute Columns --
            elif column in (
                    HeaderColumn.SURFACE, HeaderColumn.UV, HeaderColumn.BEZIER, HeaderColumn.LIVE,
                    HeaderColumn.OFFSET, HeaderColumn.CURVATURE, HeaderColumn.PRECISION, HeaderColumn.CACHE
            ):
                attributeMap = {
                    HeaderColumn.SURFACE: AttrName.TARGET_SURFACE_ID,
                    HeaderColumn.UV: AttrName.TARGET_BLEND_UV,
                    HeaderColumn.BEZIER: AttrName.TARGET_BLEND_BEZIER,
                    HeaderColumn.LIVE: AttrName.TARGET_BLEND_LIVE,
                    HeaderColumn.OFFSET: AttrName.TARGET_OFFSET,
                    HeaderColumn.CURVATURE: AttrName.TARGET_CURVATURE,
                    HeaderColumn.PRECISION: AttrName.TARGET_PRECISION,
                    HeaderColumn.CACHE: AttrName.TARGET_REBIND,
                }

                attrName = attributeMap.get(column)
                if attrName:
                    if column == HeaderColumn.SURFACE:
                        parentItem = item.parent()
                        # Read from builder directly — same source as the popup
                        surfacesDict = builder.getAllInputTargetSurfaces() if parentItem else {"NONE": 0}
                        surfaceId = surfacesDict.get(value)
                        if surfaceId is not None:
                            success = builder.setTargetValue(targetName, attrName, surfaceId)
                    else:
                        if live:
                            success = builder.setTargetValueLive(targetName, attrName, value)
                        else:
                            success = builder.setTargetValue(targetName, attrName, value)
                # update cache status
                if success:
                    if column in (HeaderColumn.SURFACE, HeaderColumn.UV, HeaderColumn.BEZIER, HeaderColumn.LIVE):
                        # When live/UV/SURFACE is toggled, plugin may auto-update cache — refresh it
                        QtCore.QTimer.singleShot(100, lambda: self._syncCacheFromMaya(item, targetName, builder))

        # -- Special: KEY column, run after update block --
        if column == HeaderColumn.KEY:
            if item.isLocked():
                logger.warning("Unable to set key: attribute is locked.")
                return False
            success = builder.keyActions(targetName, ActionID.KEYCURRENT)

        return success

    def _syncCacheFromMaya(self, item, targetName, builder):
        """
        Poll cache attribute from Maya and update UI if plugin changed it.
        Called after live/Surface/UV toggle since plugin sets cache internally.
        """
        cacheValue = builder.getTargetAttribute(targetName, AttrName.TARGET_CACHED, False)
        currentCache = item.data(HeaderColumn.CACHE)

        if cacheValue != currentCache:
            self.updateColumnData(item, HeaderColumn.CACHE, cacheValue)

    def revertValue(self, item, prevalue, column):

        item._data[column] = prevalue
        index = self.indexFromItem(item, column)
        if index.isValid():
            self.dataChanged.emit(index, index, [QtCore.Qt.DisplayRole, QtCore.Qt.EditRole])


    def getChildItem(self, parentItem, targetIndex):
        """
        Returns the child item of the given parentItem that matches the targetIndex.

        Args:
            parentItem (InterpBlendShapeItem): The parent model item.
            targetIndex (int): The logical index to match.

        Returns:
            InterpBlendShapeItem or None: The matching child item, or None if not found.
        """
        if targetIndex == -1:
            logger.debug("Skipping index -1 (reserved for root or parent items)")
            return None

        for i in range(parentItem.childCount()):
            childItem = parentItem.child(i)
            if childItem.targetIndex() == targetIndex:
                return childItem

        return None

    def updateColumnData(self, item, column, value):
        self._suppressSetData = True
        item.setData(column, value)
        index = self.createIndex(item.row(), column, item)
        self.dataChanged.emit(index, index, [QtCore.Qt.DisplayRole])
        self._suppressSetData = False

    def clear(self):
        self.beginResetModel()
        if self.rootItem:
            # Clean up all parents
            for child in range(self.rootItem.childCount()):
                item = self.rootItem.child(child)
                item.cleanup()
        self.endResetModel()
