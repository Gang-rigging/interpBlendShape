from PySide2 import QtCore, QtGui, QtWidgets
from enums import ActionID, ItemType, HeaderColumn
import maya.cmds as cmds

from logger import getLogger

logger = getLogger("InterpBlendShape")


class TreeViewMenuHandler:
    """
    Manage and display the context menu for the InterpBlendShape tree view.

    Handles different menu actions based on the clicked column and item type.
    """
    def __init__(self, view):
        """
        Initialize the menu handler with the given tree view.

        :param view: The QTreeView instance displaying InterpBlendShape items.
        """
        self.view = view
        self.model = self.view.model
        self.proxyModel = self.view.proxyModel

    def showContextMenu(self, pos):
        """
        Show a context menu at the given position in the view.

        Determines the clicked item and column, then populates actions accordingly.

        :param pos: QPoint within the view's viewport where the menu should appear.
        """
        proxyIndex = self.view.indexAt(pos)
        globalPos = self.view.viewport().mapToGlobal(pos)

        if not proxyIndex.isValid():
            return

        sourceIndex = self.proxyModel.mapToSource(proxyIndex)
        item = sourceIndex.internalPointer()
        if not item:
            return

        builder = item.builder()
        targetName = item.getAttrName()

        column = sourceIndex.column()
        menu = QtWidgets.QMenu()

        if column == HeaderColumn.NAME:
            if item.type() == ItemType.CHILD:
                menu.addAction("Key").triggered.connect(lambda: self.handleKeyActions(builder, targetName, ActionID.KEYCURRENT))
                menu.addAction("Reset").triggered.connect(lambda: self.handleKeyActions(builder, targetName, ActionID.RESET))
                menu.addSeparator()

                shapesMenu = menu.addMenu("Shapes")
                shapesMenu.addAction("Mirror Target").triggered.connect(
                    lambda checked=False, childItem=item: self.handleShapeEdit(childItem, flipTarget=False)
                )
                shapesMenu.addAction("Flip Target").triggered.connect(
                    lambda checked=False, childItem=item: self.handleShapeEdit(childItem, flipTarget=True)
                )
                shapesMenu.addSeparator()
                shapesMenu.addAction("Options...").triggered.connect(
                    lambda checked=False, popupPos=globalPos: self.handleShapeEditOptions(popupPos)
                )
                menu.addSeparator()

            menu.addAction("Add Selection as Target").triggered.connect(self.view.addTargetClicked)

            if item.type() != ItemType.PARENT:
                actionInbetween = menu.addAction("Add Selection as In-Between Target")
                actionInbetween.triggered.connect(lambda: self.handleAddInbetweenTarget(item))

            menu.addSeparator()
            menu.addAction("Select Base Mesh").triggered.connect(lambda: self.handleSelectBaseMesh(builder))
            if item.type() == ItemType.CHILD:
                menu.addAction("Select Target Mesh").triggered.connect(lambda: self.handleSelectTargetMesh(builder, targetName))

            menu.addAction("Select InterpBlendShape Node").triggered.connect(lambda: self.handleSelectBaseNode(builder))

            menu.addSeparator()
            menu.addAction("Delete").triggered.connect(self.view.deleteSelectedItems)

        elif column == HeaderColumn.WEIGHT and item.type() != ItemType.INBETWEEN:
            editorWidget = self.view.indexWidget(proxyIndex)

            if not editorWidget:
                return

            localPos = editorWidget.mapFrom(self.view.viewport(), pos)
            childWidget = editorWidget.childAt(localPos)

            if isinstance(childWidget, QtWidgets.QLineEdit):
                if getattr(childWidget, "_isLocked", False):
                    actionUnlock = menu.addAction("Unlock Attribute")
                    if builder:
                        actionUnlock.triggered.connect(lambda: builder.lockAttr(targetName, False))
                else:
                    if not item.isConnected() and not item.hasSDK():
                        actionKey = menu.addAction("Set Key")
                        if builder:
                            actionKey.triggered.connect(lambda: self.handleKeyActions(builder, targetName, ActionID.KEYCURRENT))

                    if item.isConnected() or item.hasSDK() or item.hasKeyed():
                        menu.addAction("Break Connection").triggered.connect(lambda: builder.disconnectAttr(targetName))

                    actionLock = menu.addAction("Lock Attribute")
                    if builder:
                        actionLock.triggered.connect(lambda: builder.lockAttr(targetName, True))

            elif isinstance(childWidget, QtWidgets.QSlider):
                if item.type() != ItemType.PARENT:
                    actionInbetween = menu.addAction("Add Selection as In-Between Target")
                    actionInbetween.triggered.connect(lambda: self.handleAddInbetweenTarget(item))

        elif column == HeaderColumn.SURFACE and item.type() == ItemType.CHILD:
            menu.addAction("Add Surface").triggered.connect(lambda: self.handleAddSurface(item))
            replaceSurfaceAction = menu.addAction("Replace Surface")
            removeSurfaceAction  = menu.addAction("Remove Surface")
            replaceSurfaceAction.triggered.connect(lambda: self.handleReplaceSurface(item))
            removeSurfaceAction.triggered.connect(lambda: self.handleRemoveSurface(item))

            if item.data(HeaderColumn.SURFACE) == "NONE":
                replaceSurfaceAction.setEnabled(False)
                removeSurfaceAction.setEnabled(False)

        elif column == HeaderColumn.KEY and item.type() != ItemType.INBETWEEN:

            actionKeyCurrent = menu.addAction("Key at Current")
            actionKeyZero = menu.addAction("Key at 0")
            actionKeyOne = menu.addAction("Key at 1")

            actionKeyCurrent.triggered.connect(lambda: self.handleKeyActions(builder, targetName, ActionID.KEYCURRENT))
            actionKeyZero.triggered.connect(lambda: self.handleKeyActions(builder, targetName, ActionID.KEYZERO))
            actionKeyOne.triggered.connect(lambda: self.handleKeyActions(builder, targetName, ActionID.KEYONE))
            if item.isLocked() or item.isConnected() or item.hasSDK():
                actionKeyCurrent.setEnabled(False)
                actionKeyZero.setEnabled(False)
                actionKeyOne.setEnabled(False)

            menu.addSeparator()
            actionRemove = menu.addAction("Remove Key")
            actionRemove.triggered.connect(lambda: self.handleKeyActions(builder, targetName, ActionID.REMOVEKEY))
            actionRemove.setEnabled(item.isKeyOnCurrentTime())

        menu.exec_(globalPos)

    def handleShapeEdit(self, childItem, flipTarget=False):
        """
        Mirror or flip the selected child target shape using the main window action path.

        :param childItem: Child target item to edit.
        :param flipTarget: If True, flip both sides instead of mirroring one side.
        """
        if not childItem or childItem.type() != ItemType.CHILD:
            return

        window = self.view.window()
        if hasattr(window, "applyShapeEditToItem"):
            window.applyShapeEditToItem(childItem, flipTarget=flipTarget)

    def handleShapeEditOptions(self, globalPos):
        """
        Open the shared shape edit options popup at the requested screen position.

        :param globalPos: Global screen position for the popup anchor.
        """
        window = self.view.window()
        if hasattr(window, "showShapeEditOptions"):
            window.showShapeEditOptions(globalPos)

    def handleKeyActions(self, builder, targetName, actionID):
        """
        Execute key action on the builder and log if it fails.

        :param builder:    The builder object to perform the key action.
        :param targetName: The attribute or target name to key.
        :param actionID:   One of ActionID.KEYCURRENT, KEYZERO, KEYONE, REMOVEKEY.
        """
        success = builder.keyActions(targetName, actionID)
        if not success:
            if actionID == ActionID.RESET:
                logger.warning("Cannot reset a locked or connected attribute.")
            else:
                logger.warning(f"Key action failed for '{targetName}'.")


    def handleAddInbetweenTarget(self, selectedItem):
        """
        Add an in-between target for the selected item, blocking model updates.

        Checks weight validity and inserts new in-between items if valid.

        :param selectedItem: The selected tree item used to resolve the target child item.
        """
        with self.model._updateBlocker.block():
            if selectedItem.type() == ItemType.PARENT:
                return
            if selectedItem.type() == ItemType.INBETWEEN:
                targetChildItem = selectedItem.parent()
            else:
                targetChildItem = selectedItem

            # Use the main child target's live weight, not the inbetween item's stored weight.
            weight = targetChildItem.data(HeaderColumn.WEIGHT)

            # Validate in-between weight
            if abs(weight - 0.0) < 1e-6 or abs(weight - 1.0) < 1e-6:
                logger.warning(f"[Inbetween] Invalid weight {weight:.3f}. In-between weights must be > 0 and < 1.")
                return

            inbetweenItems = targetChildItem.builder().addInbetweenTarget(targetChildItem, weight)
            if inbetweenItems:
                self.model.insertItem(targetChildItem, inbetweenItems)
                self.model.updateColumnData(targetChildItem, HeaderColumn.CACHE, True)

    def handleAddSurface(self, childItem):
        """
        Add a new surface connection for the given item.

        Opens an undo chunk, calls the builder to create the connection,
        then writes the new surface name back into the UI if successful.
        """
        cmds.undoInfo(openChunk=True)
        try:
            result = childItem.builder().addSurface(multiSurface=False)
            if not result:
                return False

            lastIndex, lastSurfaceName = result
            success = childItem.builder().setTargetValue(
                childItem.name(),
                "targetSurfaceId",
                lastIndex
            )
            if success:
                self.model.updateColumnData(
                    childItem,
                    HeaderColumn.SURFACE,
                    lastSurfaceName
                )
                return True
            return False
        finally:
            cmds.undoInfo(closeChunk=True)

    def handleReplaceSurface(self, childItem):
        """
        Replace the current surface connection on childItem with the
        last selected surface. Updates the UI label on success.
        """
        oldName = childItem.data(HeaderColumn.SURFACE)
        if oldName == "NONE":
            return False

        parent = childItem.parent()
        surfaceId = parent.getSurfaceId(oldName)
        if surfaceId is None:
            return False

        newName = childItem.builder().replaceSurface(surfaceId)
        if newName:
            self.model.updateColumnData(
                childItem,
                HeaderColumn.SURFACE,
                newName
            )
            return True
        return False

    def handleRemoveSurface(self, childItem):
        """
        Remove the current surface connection on childItem.
        Picks the next-highest surface name or 'NONE' and updates the UI.
        """
        name = childItem.data(HeaderColumn.SURFACE)
        if name == "NONE":
            return False

        parent = childItem.parent()
        surfaceId = parent.getSurfaceId(name)
        if surfaceId is None:
            return False

        # Remove the mapping and update the builder
        removed = childItem.builder().removeSurface(surfaceId)
        if not removed:
            return False

        surfacesDict = parent.getAllSurfaces()
        # Remove the name from the dict in-place
        surfacesDict.pop(name, None)

        # Choose next name
        if surfacesDict:
            nextName = max(surfacesDict, key=surfacesDict.get)
        else:
            nextName = "NONE"

        self.model.updateColumnData(
            childItem,
            HeaderColumn.SURFACE,
            nextName
        )
        return True

    def handleSelectBaseMesh(self, builder):
        """
        Selects the base mesh DAG object in Maya.
        """
        baseDag = builder.getBaseMesh()
        if baseDag:
            cmds.select(baseDag, r=True)

    def handleSelectBaseNode(self, builder):
        """
        Selects the builder's underlying dependency node in Maya.
        """
        node = builder.node
        if node:
            cmds.select(node, r=True)

    def handleSelectTargetMesh(self, builder, targetName):
        """
        Selects the target mesh (by name) in Maya.
        """
        meshes = builder.getTargetMesh(targetName)
        if meshes:
            cmds.select(meshes, r=True)
