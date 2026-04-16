from PySide2 import QtCore, QtGui, QtWidgets
import app_config
from model import FilterProxyModel, InterpBlendShapeModel, BlendShapeModelBuilder
from node_tracker import SceneNodeMonitor, NodeTrackerManager, CallbackSuppressor
from paint_tool import PaintToolWidget
from weight_editor import WeightEditor
from menu_handler import TreeViewMenuHandler
from tree_view_empty_state import TreeViewEmptyStateMixin
from tree_view_persistence import TreeViewPersistenceMixin
from enums import ItemType, HeaderColumn, CallbackType
from widgets import (
    NoFocusDelegate,
    ListPopupDelegate,
    LineEditDelegate,
    SliderPopupDelegate,
    SliderWeightDelegate,
    ToggleButtonDelegate,
    CheckBoxDelegate,
    CheckBoxWidget,
    SliderWeightWidget,
    styles,
)

from callback_handlers import (
    handleSet,
    handleAttrRenamed,
    handleNodeRenamed,
    handleArrayAdd,
    handleArrayRemoved,
    handleLock,
    handleConnection,
    handleDirtyPlug,
    handleKeyframeEdit,
)

from maya_utils import getMayaMainWindow
import maya.api.OpenMaya as om
import maya.cmds as cmds
import time
import uuid

from logger import getLogger

logger = getLogger("InterpBlendShape")

class InterpBlendShapeView(TreeViewEmptyStateMixin, TreeViewPersistenceMixin, QtWidgets.QTreeView):
    modelLoadStarted = QtCore.Signal()
    modelLoadFinished = QtCore.Signal()

    # Map depth level -> set of HeaderColumn values to open
    LEVEL_COLUMNS = {
        0: {HeaderColumn.WEIGHT, HeaderColumn.KEY},
        1: {HeaderColumn.WEIGHT, HeaderColumn.UV, HeaderColumn.BEZIER,
            HeaderColumn.LIVE, HeaderColumn.CACHE, HeaderColumn.KEY},
        2: {HeaderColumn.WEIGHT},
    }

    FIXED_ROW_HEIGHT = 26

    def __init__(self, parent=None):
        super().__init__(parent)

        # Shared suppression controller
        self.suppressor = CallbackSuppressor()

        self.trackerManager = NodeTrackerManager(suppressor=self.suppressor)
        self.sceneMonitor = SceneNodeMonitor("interpBlendShape", self.trackerManager, suppressor=self.suppressor)
        self.sceneMonitor.nodeAdded.connect(self.onNodeAdded)
        self.sceneMonitor.nodeRemoved.connect(self.onNodeRemoved)
        self.sceneMonitor.timeChanged.connect(self.onTimeChanged)
        self.sceneMonitor.keyframeEdit.connect(self.onkeyframeEdit)
        self.sceneMonitor.sceneOpened.connect(self._setupAsyncModelLoad)  # Full refresh
        self.sceneMonitor.sceneSaved.connect(self.saveExpandedState)

        self.setItemDelegate(NoFocusDelegate(self))
        self.setUniformRowHeights(False)
        self.model = InterpBlendShapeModel()
        self.setHeaderHidden(False)

        self.proxyModel = FilterProxyModel(self)
        self.proxyModel.setSourceModel(self.model)
        self.proxyModel.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self.proxyModel.setFilterKeyColumn(0)

        self.setModel(self.proxyModel)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)

        self.header().setStretchLastSection(False)
        self.header().setDefaultAlignment(QtCore.Qt.AlignCenter)

        self.setColumnWidths()

        self.setStyle(QtWidgets.QStyleFactory.create("plastique"))
        self.setStyleSheet(styles.TREE_VIEW_STYLE)

        self._setupAsyncModelLoad()

        self.menuHandler = TreeViewMenuHandler(self)

        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.menuHandler.showContextMenu)

        self.proxyModel.rowsInserted.connect(self.onProxyRowsInserted)
        self.verticalScrollBar().valueChanged.connect(self._onScrollChanged)

        self._isFiltering    = False
        self.paintToolWidget = None  # keep reference
        self.weightEditorUI  = None

        self._dragStartPos   = None
        self._dragIndex      = None
        self._unsavedSceneKey = None

        self._emptyState = self._buildEmptyState()

        # empty state
        self.model.modelReset.connect(self._updateEmptyState)
        self.model.rowsInserted.connect(self._updateEmptyState)
        self.model.rowsRemoved.connect(self._updateEmptyState)

        # drag drop
        self.setDragEnabled(False)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(False)
        self.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.setDefaultDropAction(QtCore.Qt.MoveAction)

        # drop line
        self._dropLine = QtWidgets.QWidget(self.viewport())
        self._dropLine.setFixedHeight(2)
        self._dropLine.setStyleSheet("background-color: #5285A6;")
        self._dropLine.hide()

    def _setupAsyncModelLoad(self):
        if not hasattr(self, "sceneMonitor"):
            logger.info("[Warning] sceneMonitor not initialized yet.")
            return
        if not cmds.file(q=True, sn=True):
            self._unsavedSceneKey = f"UNSAVED_{uuid.uuid4().hex}"
        self.cleanup()
        QtCore.QTimer.singleShot(0, self._startModelBuilder)

    def _startModelBuilder(self):
        self.modelLoadStarted.emit()

        self._uiStartTime = time.time()
        self.modelBuilderThread = QtCore.QThread()
        self.modelBuilder = BlendShapeModelBuilder(self._onNodeChanged)

        # Collect Maya data on main thread first — safe, fast
        self.modelBuilder.collectSnapshots()

        # Then move tree-building to background thread
        self.modelBuilder.moveToThread(self.modelBuilderThread)

        self.modelBuilder.finished.connect(self._onModelBuilt)
        self.modelBuilder.finished.connect(self.modelBuilderThread.quit)
        self.modelBuilder.finished.connect(self.modelBuilder.deleteLater)
        self.modelBuilderThread.finished.connect(self.modelBuilderThread.deleteLater)

        self.modelBuilderThread.started.connect(self.modelBuilder.run)
        self.modelBuilderThread.start()

    @QtCore.Slot(str, str, int, int, dict)
    def _onNodeChanged(self, nodeName, attrName, idx, ctype, payload):
        if ctype == CallbackType.NODE_RENAMED:
            oldName = payload.get("oldName")
            newName = payload.get("newName")
            parentItem = self.trackerManager.getItem(oldName)
            if not parentItem:
                logger.warning(f"[Model] Item not found for renamed node: {nodeName}")
                return
            self.trackerManager.renameItem(oldName, newName, parentItem)

            # update paintUI item data
            if self.paintToolWidget:
                if oldName in self.paintToolWidget.parentItems:
                    # copy value to new key
                    self.paintToolWidget.parentItems[newName] = self.paintToolWidget.parentItems[oldName]
                    # delete old key
                    del self.paintToolWidget.parentItems[oldName]

            nodeName = newName

        if self.model._updateBlocker.isBlocked():
            logger.info(f"[Model] Blocked node change: {nodeName}.{attrName}")
            return
        # find the parent item
        parentItem = self.trackerManager.getItem(nodeName)
        if not parentItem:
            logger.debug(f"No parent item for {nodeName}.{attrName} ({CallbackType(ctype).name})")
            return

        dispatcher = {
            CallbackType.ATTRIBUTE_SET:          handleSet,
            CallbackType.ATTRIBUTE_RENAMED:      handleAttrRenamed,
            CallbackType.NODE_RENAMED:           handleNodeRenamed,
            CallbackType.ATTRIBUTE_ARRAYADD:     handleArrayAdd,
            CallbackType.ATTRIBUTE_ARRAYREMOVED: handleArrayRemoved,
            CallbackType.ATTRIBUTE_LOCK:         handleLock,
            CallbackType.ATTRIBUTE_CONNECT:      handleConnection,
            CallbackType.ATTRIBUTE_DISCONNECT:   handleConnection,
            CallbackType.ATTRIBUTE_DIRTYPLUG:    handleDirtyPlug,
        }
        handler = dispatcher.get(CallbackType(ctype))

        if not handler:
            logger.warning(f"Unhandled callback type: {ctype}")
            return

        # now defer into Maya’s event loop, passing `self` first:
        QtCore.QTimer.singleShot(
            0,
            lambda: handler(self, parentItem, attrName, idx, ctype, payload)
        )


    def onNodeAdded(self, nodeName):
        QtCore.QTimer.singleShot(200, lambda: self._processNodeAdded(nodeName))

    def _processNodeAdded(self, nodeName):
        if nodeName in self.model._nodesCreatedFromUI:
            self.model._nodesCreatedFromUI.remove(nodeName)
            logger.debug("Node already handled: %s", nodeName)
            return

        parentItem = self.model.addNewInterpBlendShapeNode(nodeName)

        if parentItem:
            self.trackerManager.register(nodeName, parentItem, self._onNodeChanged)

            # update paint ui parentItem data
            if self.paintToolWidget:
                self.paintToolWidget.addItem(parentItem)

    def onNodeRemoved(self, nodeName):
        if self.model._updateBlocker.isBlocked():
            logger.debug("Duplicate removal event ignored: %s", nodeName)
            return
        # Get item from trackerManager
        item = self.trackerManager.getItem(nodeName)

        # update paint ui parentItem data
        if self.paintToolWidget:
            self.paintToolWidget.removeItem(item)

        # Unregister tracker and cleanup
        self.trackerManager.unregister(nodeName)

        # Remove from model if item exists
        if item:
            self.model.removeItems([item], modelOnly=True)
            self.setCurrentIndex(QtCore.QModelIndex())
            self.clearSelection()
            self.clearFocus()

    def onkeyframeEdit(self, nodeName, attrName, keyType, logicIndex, hasSDK, keyframesList):
        if self.model._updateBlocker.isBlocked():
            logger.info(f"[Model] Blocked node change: {nodeName}.{attrName}")
            return

        parentItem = self.trackerManager.getItem(nodeName)
        if not parentItem:
            logger.debug(f"No parent item found. skip callback: {type}")
            return

        handleKeyframeEdit(self, parentItem, attrName, logicIndex, keyType, hasSDK, keyframesList)

    def onTimeChanged(self, currentTime):
        # grab viewport rect once
        vpRect = self.viewport().rect()

        # build a flat list of items that might need refreshing
        toRefresh = []
        for parent in self.trackerManager.getAllItems():
            if parent.hasKeyed() or parent.isConnected():
                toRefresh.append(parent)
            # inline child‑gathering without range lookups
            childCount = parent.childCount()
            for i in range(childCount):
                child = parent.child(i)
                if child and child.hasKeyed() or parent.isConnected():
                    toRefresh.append(child)

        # only refresh those actually visible
        for srcItem in toRefresh:
            proxyIndex = self.getProxyIndex(srcItem)
            if not proxyIndex.isValid():
                continue

            # do a single visualRect compare
            if not self.visualRect(proxyIndex).intersects(vpRect):
                continue

            # update appearance & locks immediately
            self._refreshWidgetState(srcItem, proxyIndex)

            # schedule the weight‑value update
            QtCore.QTimer.singleShot(
                50,
                lambda it=srcItem: self._delayedUpdate(it, it.getAttrName(), None)
            )


    def _refreshItemFromCallback(self, item, value=None, ctype=None):
        """
        Refresh UI for a single item from callback.
        """
        proxyIndex = self.getProxyIndex(item)
        if ctype != CallbackType.ATTRIBUTE_DIRTYPLUG:
            self._refreshWidgetState(item, proxyIndex, ctype)

        if ctype != CallbackType.ATTRIBUTE_DISCONNECT:
            attr = item.getAttrName()
            QtCore.QTimer.singleShot(
                50,
                lambda it=item, a=attr, v=value: self._delayedUpdate(it, a, v)
            )

    def _delayedUpdate(self, item, attrName, value=None):
        if value is None:
            value = item.builder().getAttrValue(attrName)
        self.model.updateColumnData(item, HeaderColumn.WEIGHT, value)


    def _refreshWidgetState(self, item, proxyIndex, ctype=None):

        weightIndex = proxyIndex.sibling(proxyIndex.row(), HeaderColumn.WEIGHT)
        keyIndex = proxyIndex.sibling(proxyIndex.row(), HeaderColumn.KEY)

        slider = self.indexWidget(weightIndex)
        checkbox = self.indexWidget(keyIndex)
        if isinstance(slider, SliderWeightWidget):
            slider.lineEdit.setKeyed(item.hasKeyed(), item.hasSDK(), item.isKeyOnCurrentTime())

            if ctype in (CallbackType.ATTRIBUTE_CONNECT, CallbackType.ATTRIBUTE_DISCONNECT):
                slider.setLockStatus(item.isLocked(), item.isConnected())
                if item.hasSDK() and item.isConnected():
                    # enable widget when sdk and keyframe model
                    slider.slider.setActive(item.isLocked())

            slider.lineEdit.refreshStyle()

        if not item.isConnected() and isinstance(checkbox, CheckBoxWidget):
            checkbox.setValue(item.isKeyOnCurrentTime() and not item.hasSDK())

    def _onScrollChanged(self, value):
        # Delay a bit to avoid spamming on rapid scroll
        QtCore.QTimer.singleShot(100, self._refreshScrolledIntoViewItems)

    def _refreshIfVisible(self, item):
        proxyIndex = self.getProxyIndex(item)
        if proxyIndex.isValid() and self.visualRect(proxyIndex).intersects(self.viewport().rect()):
            self._refreshWidgetState(item, proxyIndex=proxyIndex)
            self._delayedUpdate(item, item.getAttrName())

    def _refreshScrolledIntoViewItems(self):
        for parentItem in self.trackerManager.getAllItems():
            if parentItem.hasKeyed():
                self._refreshIfVisible(parentItem)

            for i in range(parentItem.childCount()):
                childItem = parentItem.child(i)
                if childItem and childItem.hasKeyed():
                    self._refreshIfVisible(childItem)

    def onProxyRowsInserted(self, proxyParentIndex, start, end):
        # schedule the real work for the next event loop iteration
        QtCore.QTimer.singleShot(0,
                                 lambda: self._handleProxyRowsInserted(proxyParentIndex, start, end)
                                 )

    def openEditorsInChunks(self, indices, batchSize=30, delay=1):
        if not indices:
            self.modelLoadFinished.emit()
            return
        self.viewport().update()
        batch = indices[:batchSize]
        for index in batch:
            self.openPersistentEditor(index)

        remaining = indices[batchSize:]
        QtCore.QTimer.singleShot(delay, lambda: self.openEditorsInChunks(remaining, batchSize, delay))

    def _getDepth(self, index):
        """
        Compute depth of given proxy index (0 = root-level item).
        """
        depth = 0
        parent = index.parent()
        while parent.isValid():
            depth += 1
            parent = parent.parent()
        return depth

    def _collectIndices(self, parentIndex, start=None, end=None):
        """
        Traverse subtree under parentIndex, optionally limiting to rows [start..end]
        Returns a list of QModelIndex objects to open.
        """
        indices = []

        def recurse(parent, row_range=None):
            rowCount = self.proxyModel.rowCount(parent)
            rows = row_range if row_range is not None else range(rowCount)
            for row in rows:
                idx0 = self.proxyModel.index(row, 0, parent)
                if not idx0.isValid():
                    continue
                # determine depth and pick columns
                depth = self._getDepth(idx0)
                # fallback to highest known level if deeper
                max_lvl = max(self.LEVEL_COLUMNS.keys())
                cols = self.LEVEL_COLUMNS.get(depth, self.LEVEL_COLUMNS[max_lvl])
                for col in cols:
                    idx = self.proxyModel.index(row, col, parent)
                    if idx.isValid():
                        indices.append(idx)
                # recurse into children
                recurse(idx0)

        row_range = range(start, end + 1) if start is not None else None
        recurse(parentIndex, row_range)
        return indices

    def _openEditorsForVisibleItems(self):
        indices = self._collectIndices(QtCore.QModelIndex())
        if not indices:
            self.modelLoadFinished.emit()
            return
        batch_size = max(10, min(100, len(indices) // 10))
        QtCore.QTimer.singleShot(0,
                                 lambda: self.openEditorsInChunks(indices, batch_size, delay=1)
                                 )

    def updateViewData(self):
        self._applyDelegates()
        self._openEditorsForVisibleItems()

    def _applyDelegates(self):
        self.setItemDelegateForColumn(HeaderColumn.NAME, LineEditDelegate(self))
        self.setItemDelegateForColumn(HeaderColumn.SURFACE, ListPopupDelegate(self))
        self.setItemDelegateForColumn(HeaderColumn.OFFSET, SliderPopupDelegate(self))
        self.setItemDelegateForColumn(HeaderColumn.CURVATURE, SliderPopupDelegate(self))
        self.setItemDelegateForColumn(HeaderColumn.PRECISION, SliderPopupDelegate(self))
        self.setItemDelegateForColumn(HeaderColumn.WEIGHT, SliderWeightDelegate(self))
        self.setItemDelegateForColumn(HeaderColumn.UV, ToggleButtonDelegate(self))
        self.setItemDelegateForColumn(HeaderColumn.BEZIER, ToggleButtonDelegate(self))
        self.setItemDelegateForColumn(HeaderColumn.LIVE, ToggleButtonDelegate(self))
        self.setItemDelegateForColumn(HeaderColumn.CACHE, CheckBoxDelegate(self))
        self.setItemDelegateForColumn(HeaderColumn.KEY, CheckBoxDelegate(self))

    def onFilterChanged(self, text):
        self._isFiltering = True

        if text:
            self.saveExpandedState()

        self.closeAllPersistentEditors()
        regex = QtCore.QRegExp(text, QtCore.Qt.CaseInsensitive, QtCore.QRegExp.FixedString)
        self.proxyModel.setFilterRegExp(regex)

        QtCore.QTimer.singleShot(0, self._finishFilter)

    def _onModelBuilt(self, rootItem):
        self.model.setRootItem(rootItem)
        self.registerTrackers(rootItem)

        if self.paintToolWidget:
            self.paintToolWidget.setItemData(self.getAllParentItems())

        # Restore node order BEFORE opening editors
        scene_key = self._getSceneKey()
        settings = app_config.ui_settings()
        settings.beginGroup(app_config.scene_group(scene_key, app_config.SCENE_GROUP_NODE_ORDER))
        # Parent keys are pure integers: "0", "1", "2"...
        # Child keys are: "parentName_0", "parentName_1"...
        keys = sorted(
            [k for k in settings.allKeys() if k.isdigit()],
            key=lambda k: int(k)
        )
        if keys:
            orderedNames = [settings.value(k) for k in keys]
            self._restoreNodeOrder(orderedNames)
        settings.endGroup()

        QtCore.QTimer.singleShot(0, self._postModelBuilt)

    def _onEditorsReady(self):
        try:
            self.modelLoadFinished.disconnect(self._onEditorsReady)
        except RuntimeError:
            pass

        scene_key = self._getSceneKey()
        settings = app_config.ui_settings()
        settings.beginGroup(app_config.scene_group(scene_key, app_config.SCENE_GROUP_EXPANDED_STATE))
        hasAnyState = bool(settings.allKeys())
        settings.endGroup()

        if hasAnyState:
            self.restoreExpandedState()

        self.setUpdatesEnabled(True)
        self.viewport().update()

    def _postModelBuilt(self):
        self.setUpdatesEnabled(False)
        self.expandAll()
        QtWidgets.QApplication.processEvents()
        # Connect BEFORE updateViewData so signal is ready when emitted
        try:
            self.modelLoadFinished.disconnect(self._onEditorsReady)
        except RuntimeError:
            pass
        self.modelLoadFinished.connect(self._onEditorsReady)
        self.updateViewData()

    def _finishFilter(self):
        self.expandAll()
        self.updateViewData()

        if self.proxyModel.filterRegExp().isEmpty():
            self._pendingRestore = True  # set BEFORE _isFiltering = False
            # Guard against duplicate connections
            try:
                self.modelLoadFinished.disconnect(self._onFilterEditorsReady)
            except RuntimeError:
                pass
            self.modelLoadFinished.connect(self._onFilterEditorsReady)
        else:
            self._pendingRestore = False

        self._isFiltering = False  # set AFTER _pendingRestore

    def _onFilterEditorsReady(self):
        try:
            self.modelLoadFinished.disconnect(self._onFilterEditorsReady)
        except RuntimeError:
            pass
        if getattr(self, '_pendingRestore', False):
            self._pendingRestore = False
            self.restoreExpandedState()

    def _handleProxyRowsInserted(self, proxyParentIndex, start, end):
        if self._isFiltering or getattr(self, '_pendingRestore', False):
            return

        root = proxyParentIndex if proxyParentIndex.isValid() else QtCore.QModelIndex()

        if root.isValid():
            # Adding children to existing node — just expand that parent
            self.expand(root)
        else:
            # Adding new top-level nodes — only expand the new ones, not everything
            for row in range(start, end + 1):
                idx = self.proxyModel.index(row, 0, QtCore.QModelIndex())
                if idx.isValid():
                    self.expand(idx)

        indices = self._collectIndices(root, start, end)
        QtCore.QTimer.singleShot(0, lambda: self.openEditorsInChunks(indices))

    def _openIndices(self, indices):
        for idx in indices:
            self.expand(idx.parent())
        QtCore.QTimer.singleShot(0, lambda: self.openEditorsInChunks(indices))

    def closeAllPersistentEditors(self):
        model = self.proxyModel
        def recurse(parentIndex):
            for row in range(model.rowCount(parentIndex)):
                childIndex = model.index(row, 0, parentIndex)
                for col in range(model.columnCount(parentIndex)):
                    index = model.index(row, col, parentIndex)
                    if index.isValid():
                        self.closePersistentEditor(index)
                recurse(childIndex)

        recurse(QtCore.QModelIndex())

    def getProxyIndex(self, item, column=0):
        sourceIndex = self.model.indexFromItem(item, column)
        proxyIndex = self.proxyModel.mapFromSource(sourceIndex)
        return proxyIndex

    def registerTrackers(self, rootItem):
        for i in range(rootItem.childCount()):
            item = rootItem.child(i)
            name = item.name()
            if item.type() == ItemType.PARENT and name:
                self.trackerManager.register(name, item, self._onNodeChanged)
            else:
                logger.debug(f"[registerTrackers] Skipped item: {item} (type={item.type()}, name={name})")

    def getSelectedItem(self):
        """
        Returns the currently selected item from the source model,
        mapped from the selected index in the proxy model.

        Returns:
            InterpBlendShapeItem or None: The selected item, or None if invalid.
        """
        proxyIndex = self.currentIndex()
        if not proxyIndex.isValid():
            logger.debug("No valid selection.")
            return None

        sourceIndex = self.proxyModel.mapToSource(proxyIndex)
        item = sourceIndex.internalPointer()
        if not item:
            logger.debug("Selected index has no valid item.")
        return item

    def parentItemFromSelection(self):
        """
        Returns the selected item's parent, or the item itself if it's already a parent.

        Returns:
            InterpBlendShapeItem or None: The parent item, or None if not found/invalid.
        """
        selectedItem = self.getSelectedItem()
        if not selectedItem:
            return None

        if selectedItem.type() == ItemType.PARENT:
            return selectedItem
        elif selectedItem.type() == ItemType.CHILD:
            return selectedItem.parent()
        elif selectedItem.type() == ItemType.INBETWEEN:
            return selectedItem.parent().parent()

        return None

    def addTargetClicked(self):
        """
        Handles the logic when the "Add Child" button is clicked.
        Adds a new child item to the currently selected parent in the model.
        """
        # Ensure we're working with a parent item
        parentItem = self.parentItemFromSelection()
        if not parentItem:
            return

        with self.model._updateBlocker.block():
            # Use the builder to add a new child/target under the parent item
            childrenItems = parentItem.builder().addTarget(parentItem)
            if childrenItems:
                self.model.insertItem(parentItem, childrenItems)

    def addNewNodeClicked(self):
        # non-callback action
        parentItem = self.model.addNewInterpBlendShapeNode()
        if not parentItem:
            return
        self.trackerManager.register(parentItem.name(), parentItem, self._onNodeChanged)
        # update paint ui parentItem data
        if self.paintToolWidget:
            self.paintToolWidget.addItem(parentItem)

    def deleteSelectedItems(self):
        """
        Deletes all currently selected items via the model.
        """
        selectionModel = self.selectionModel()
        if not selectionModel:
            return

        selectedProxyIndexes = selectionModel.selectedRows()
        if not selectedProxyIndexes:
            return

        selectedItems = []
        for proxyIndex in selectedProxyIndexes:
            sourceIndex = self.proxyModel.mapToSource(proxyIndex)
            item = sourceIndex.internalPointer()
            if item and item not in selectedItems:
                selectedItems.append(item)

        deletedCount = self.model.removeItems(selectedItems)

        if deletedCount == len(selectedItems):
            self.setCurrentIndex(QtCore.QModelIndex())
            self.clearSelection()
            self.clearFocus()

            for item in selectedItems:
                if item.type() == ItemType.PARENT:
                    # update paint ui parentItem data
                    if self.paintToolWidget:
                        self.paintToolWidget.removeItem(item)

            logger.info(f"Deleted {deletedCount} selected item(s).")
        else:
            # Reset paintUI data if the delete action fails partially
            if self.paintToolWidget:
                self.paintToolWidget.setItemData(self.getAllParentItems())

            failedCount = len(selectedItems) - deletedCount
            logger.warning(f"{failedCount} item(s) failed to delete out of {len(selectedItems)} selected.")

    def addSurfaceToItem(self):
        """
        Connect all selected surfaces and attach them to the node.
        """
        # add connection and callback will handle internal data update
        parentItem = self.parentItemFromSelection()
        parentItem.builder().addSurface()

    def setColumnWidths(self):
        stretch_cols = {HeaderColumn.NAME, HeaderColumn.WEIGHT, HeaderColumn.SURFACE}
        for i, width in enumerate(HeaderColumn.widths()):
            self.setColumnWidth(i, width)
            if i in stretch_cols:
                self.header().setSectionResizeMode(i, QtWidgets.QHeaderView.Interactive)
            else:
                self.header().setSectionResizeMode(i, QtWidgets.QHeaderView.Fixed)

    def startDrag(self, supportedActions):
        # Only allow if middle mouse initiated
        if getattr(self, '_dragStartPos', None) is None:
            return

        sourceIndex = self.proxyModel.mapToSource(self._dragIndex)
        mimeData = self.model.mimeData([sourceIndex])

        item = sourceIndex.internalPointer()
        name = item.name() if item else ""

        fm = QtGui.QFontMetrics(QtWidgets.QApplication.font())
        textWidth = fm.horizontalAdvance(name) + 16
        image = QtGui.QImage(textWidth, 18, QtGui.QImage.Format_ARGB32)
        image.fill(QtGui.QColor(85, 170, 195, 160))
        painter = QtGui.QPainter(image)
        painter.setPen(QtGui.QColor("#ffffff"))
        painter.setFont(QtWidgets.QApplication.font())
        painter.drawText(8, 13, name)
        painter.end()
        pixmap = QtGui.QPixmap.fromImage(image)

        drag = QtGui.QDrag(self)
        drag.setMimeData(mimeData)
        drag.setPixmap(pixmap)
        drag.setHotSpot(QtCore.QPoint(textWidth // 2, 9))
        drag.exec_(QtCore.Qt.MoveAction)

    def mousePressEvent(self, event):
        index = self.indexAt(event.pos())
        modifiers = event.modifiers()

        if event.button() == QtCore.Qt.MiddleButton:
            if index.isValid():
                sourceIndex = self.proxyModel.mapToSource(index)
                item = sourceIndex.internalPointer()
                if item and item.type() in (ItemType.PARENT, ItemType.CHILD):
                    self._dragStartPos = event.pos()
                    self._dragIndex = index
            return

        if modifiers & (QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier):
            self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        else:
            self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)

        if not index.isValid():
            self.clearSelection()
            self.setCurrentIndex(QtCore.QModelIndex())

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (getattr(self, '_dragStartPos', None) is not None and
                event.buttons() & QtCore.Qt.MiddleButton):

            if ((event.pos() - self._dragStartPos).manhattanLength()
                    < QtWidgets.QApplication.startDragDistance()):
                return

            # Collect all selected source indexes (column 0 only)
            selectedIndexes = self.selectionModel().selectedRows(0)
            sourceIndexes = []
            for idx in selectedIndexes:
                if isinstance(idx.model(), QtCore.QSortFilterProxyModel):
                    sourceIndexes.append(idx.model().mapToSource(idx))
                else:
                    sourceIndexes.append(idx)

            if not sourceIndexes:
                return

            drag = QtGui.QDrag(self)
            mimeData = self.model.mimeData(sourceIndexes)
            drag.setMimeData(mimeData)

            # Drag pixmap showing count if multiple
            count = len(sourceIndexes)
            item = sourceIndexes[0].internalPointer()
            name = item.name() if item else ""
            label = f"{name} (+{count - 1})" if count > 1 else name

            fm = QtGui.QFontMetrics(QtWidgets.QApplication.font())
            textWidth = fm.horizontalAdvance(label) + 16
            image = QtGui.QImage(textWidth, 18, QtGui.QImage.Format_ARGB32)
            image.fill(QtGui.QColor(85, 170, 195, 160))
            painter = QtGui.QPainter(image)
            painter.setPen(QtGui.QColor("#ffffff"))
            painter.setFont(QtWidgets.QApplication.font())
            painter.drawText(8, 13, label)
            painter.end()
            pixmap = QtGui.QPixmap.fromImage(image)
            drag.setPixmap(pixmap)
            drag.setHotSpot(QtCore.QPoint(textWidth // 2, 9))

            self.setDragEnabled(True)
            drag.exec_(QtCore.Qt.MoveAction)
            self.setDragEnabled(False)

            self._dragStartPos = None
            self._dragIndex = None
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.MiddleButton:
            self._dragStartPos = None
            self._dragIndex = None
        else:
            super().mouseReleaseEvent(event)

    def dragEnterEvent(self, event):
        if event.source() == self:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.source() != self:
            event.ignore()
            self._dropLine.hide()
            return

        pos = event.pos()
        index = self.indexAt(pos)

        if index.isValid():
            sourceIndex = self.proxyModel.mapToSource(index)
            item = sourceIndex.internalPointer()

            # For PARENT items dropping at root level — use root as parent
            # For CHILD items dropping inside parent — use parent item
            if item and item.type() == ItemType.PARENT:
                checkParent = QtCore.QModelIndex()  # root level
                checkRow = sourceIndex.row()
            else:
                checkParent = sourceIndex.parent()
                checkRow = sourceIndex.row()

            canDrop = self.model.canDropMimeData(
                event.mimeData(),
                event.proposedAction(),
                checkRow, 0,
                checkParent
            )
        else:
            canDrop = self.model.canDropMimeData(
                event.mimeData(),
                event.proposedAction(),
                -1, 0,
                QtCore.QModelIndex()
            )

        if not canDrop:
            event.ignore()
            self._dropLine.hide()
            return

        event.acceptProposedAction()

        if index.isValid():
            rect = self.visualRect(index)
            y = rect.top() if pos.y() < rect.center().y() else rect.bottom()
        else:
            y = self.viewport().height()

        self._dropLine.setGeometry(0, y - 1, self.viewport().width(), 2)
        self._dropLine.show()

    def dragLeaveEvent(self, event):
        self._dropLine.hide()

    def dropEvent(self, event):
        self._dropLine.hide()
        super().dropEvent(event)

    def openPaintTool(self):
        """
        Open the Paint Weights Tool UI.

        Creates and shows the PaintToolWidget if not already visible,
        sets its data, connects selection change signals, and syncs initial selection.
        If already open, brings the window to the front.
        """
        if self.paintToolWidget is None or not self.paintToolWidget.isVisible():
            self.paintToolWidget = PaintToolWidget(self, trackerManager=self.trackerManager)
            self.paintToolWidget.setItemData(self.getAllParentItems())
            self.paintToolWidget.show()

            # Connect only once when widget is created
            self.selectionModel().selectionChanged.connect(self.onTreeSelectionChanged)

            # Manually trigger selection-based sync once
            self.onTreeSelectionChanged(
                self.selectionModel().selection(), QtCore.QItemSelection()
            )

        else:
            self.paintToolWidget.activateWindow()

    def openWeightEditor(self):
        """
        Open the Weight Editor UI.

        Creates and shows the WeightEditor if not already visible,
        registers selection callbacks, and initializes selection state.
        If already open, brings the window to the front.
        """
        if self.weightEditorUI is None or not self.weightEditorUI.isVisible():
            self.weightEditorUI = WeightEditor(parent=getMayaMainWindow(), sceneMonitor=self.sceneMonitor)
            self.weightEditorUI.show()
            self.sceneMonitor.registerSelectionCallback()

            # Initialize selection callback
            selList = om.MGlobal.getActiveSelectionList()
            om.MGlobal.setActiveSelectionList(selList, om.MGlobal.kReplaceList)

        else:
            self.weightEditorUI.activateWindow()

    def onTreeSelectionChanged(self, selected, deselected):
        parentItem = self.parentItemFromSelection()
        if not parentItem:
            # clean paintTool UI
            if self.paintToolWidget:
                self.paintToolWidget.listWidget.clear()
            return

        if self.paintToolWidget:
            self.paintToolWidget.updateListData(parentItem)

    def getAllParentItems(self):
        """
        Retrieve all parent items tracked by the tracker manager.

        Returns:
            dict: A dictionary mapping parent item names (str) to their corresponding parent item objects.
        """

        parentItemDict = {}
        parentItems = self.trackerManager.getAllItems()
        if parentItems:
            for parentItem in parentItems:
                parentItemDict[parentItem.name()] = parentItem

        return parentItemDict

    def rebindSelNode(self):
        """
        Rebinds all targets for the currently selected node and updates
        the cache column in the UI for each child item.
        """

        parentItem = self.parentItemFromSelection()
        if not parentItem:
            return

        parentItem.builder().rebindAll()

        # Refresh the cache column for each child
        for row in range(parentItem.childCount()):
            childItem = parentItem.child(row)
            self.model.updateColumnData(
                childItem,
                HeaderColumn.CACHE,
                True
            )

    def _buildEmptyState(self):
        """Create and return the empty state overlay widget."""
        return TreeViewEmptyStateMixin._buildEmptyState(self)

    def _updateEmptyState(self):
        return TreeViewEmptyStateMixin._updateEmptyState(self)

    def resizeEvent(self, event):
        return TreeViewEmptyStateMixin.resizeEvent(self, event)

    def cleanup(self):
        logger.info("[View] Cleaning up trackers and scene monitor...")
        self.trackerManager.clear()
        self.model.clear()

    def sizeHintForRow(self, row: int) -> int:
        return self.FIXED_ROW_HEIGHT

