from PySide2 import QtWidgets, QtCore, QtGui
from widgets import SearchWidget, ResizableMixin, HoverButton, styles
from maya_utils import getNodeFromSelection
from enums import AttrName
from logger import getLogger

logger = getLogger("InterpBlendShape")

class paintIconButton(QtWidgets.QPushButton):
    def __init__(self, normal, hover=None, pressed=None, parent=None, releaseEvent=True):
        super().__init__(parent)

        self.releaseEvent = releaseEvent
        self.icons = {
            "normal": QtGui.QIcon(normal),
            "hover": QtGui.QIcon(hover) if hover else QtGui.QIcon(normal),
            "pressed": QtGui.QIcon(pressed) if pressed else QtGui.QIcon(normal),
        }
        self.setIcon(self.icons["normal"])
        self.setFlat(True)
        self.setFixedSize(21, 21)
        self.setIconSize(QtCore.QSize(21, 21))
        self.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
            }
            QPushButton:hover {
                background: transparent;
            }
            QPushButton:pressed {
                background: transparent;
            }
            QPushButton::menu-indicator {
                image: none;
            }
        """)

    def enterEvent(self, event):
        self.setIcon(self.icons["hover"])
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setIcon(self.icons["normal"])
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        self.setIcon(self.icons["pressed"])
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if not self.releaseEvent:
            return
        self.setIcon(self.icons["hover"] if self.rect().contains(event.pos()) else self.icons["normal"])
        super().mouseReleaseEvent(event)

class TitleBar(QtWidgets.QFrame):

    def __init__(self, title="Title", parent=None):
        super().__init__(parent)
        self.setObjectName("TitleBar")
        self.setFixedHeight(30)

        # Layout setup
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)

        # Title label
        self.titleLabel = QtWidgets.QLabel(title)
        self.titleLabel.setStyleSheet("color: white;")
        layout.addWidget(self.titleLabel)

        # Spacer to push close button right
        layout.addStretch()

        self.closeBtn = HoverButton(styles.ICON_CLOSE_DEFAULT, styles.ICON_CLOSE_HOVER)
        self.closeBtn.setFixedSize(20, 20)
        self.closeBtn.setCursor(QtCore.Qt.PointingHandCursor)
        self.closeBtn.setObjectName("CloseButton")
        layout.addWidget(self.closeBtn)

        self.setStyleSheet("""
            #TitleBar {
                background-color: #597A83;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
            }
            #CloseButton {
                background: transparent;
                border-radius: 10px;
                color: white;
                font-weight: bold;
            }
            #CloseButton:hover {
                background-color: #e74c3c;
            }

        """)


class ListItemWidget(QtWidgets.QWidget):
    def __init__(self, text, locked=False, normalize=False, enable=True, treeItem=None, parent=None):
        super().__init__(parent)
        self.setObjectName("ItemWidget")

        self.treeItem = treeItem

        self.lockIcon = QtGui.QIcon(styles.iconPath("lock.svg"))
        self.unlockIcon = QtGui.QIcon(styles.iconPath("unlock.svg"))
        self.normalizeIcon = QtGui.QIcon(styles.iconPath("normalize.svg"))
        self.disableNormalizeIcon = QtGui.QIcon(styles.iconPath("normalizeDisable.svg"))

        # Store state
        self.locked = locked
        self.normalize = normalize

        # === Layout ===
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(2, 1, 2, 1)
        layout.setSpacing(2)

        # === Lock Button ===
        self.lockButton = QtWidgets.QPushButton()
        self._styleButton(self.lockButton, self.lockIcon if self.locked else self.unlockIcon)

        # === Normalize Button ===
        self.normalizeButton = QtWidgets.QPushButton()
        self._styleButton(self.normalizeButton, self.normalizeIcon if self.normalize else self.disableNormalizeIcon)
        self.normalizeButton.setIconSize(QtCore.QSize(18, 18))

        # === Label ===
        self.label = QtWidgets.QLabel(text)
        self.label.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)

        # === Add widgets ===
        layout.addWidget(self.lockButton)
        layout.addWidget(self.normalizeButton)
        layout.addSpacing(10)
        layout.addWidget(self.label)

        # === Connect buttons ===
        self.lockButton.clicked.connect(self.toggleLock)
        self.normalizeButton.clicked.connect(self.toggleNormalize)

        if not enable:
            self.lockButton.setEnabled(False)
            self.normalizeButton.setEnabled(False)

    def _styleButton(self, button, icon):
        button.setFixedSize(24, 20)
        button.setCursor(QtCore.Qt.PointingHandCursor)
        button.setIcon(icon)
        button.setIconSize(QtCore.QSize(20, 16))
        button.setFlat(True)
        button.setStyleSheet("""
            QPushButton {
                background-color: #5D5D5D;
                border: none;
                border-radius: 2px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #6A6A6A;
            }
            QPushButton:pressed {
                background-color: #4A4A4A;
            }
        """)

    def toggleLock(self):
        self.locked = not self.locked
        if self.treeItem:
            self.treeItem.builder().setTargetValue(self.label.text(), AttrName.TARGET_WEIGHT_LOCKED, self.locked)

    def toggleNormalize(self):
        self.normalize = not self.normalize
        if self.treeItem:
            self.treeItem.builder().setTargetValue(self.label.text(), AttrName.TARGET_WEIGHT_NORMALIZATION, self.normalize)

    def updateStates(self, locked=None, normalize=None):
        """Externally update button states from a model or signal."""
        if locked is not None:
            self.locked = locked
            self.lockButton.setIcon(self.lockIcon if self.locked else self.unlockIcon)

        if normalize is not None:
            self.normalize = normalize
            self.normalizeButton.setIcon(self.normalizeIcon if self.normalize else self.disableNormalizeIcon)


class LineDelegate(QtWidgets.QStyledItemDelegate):
    def paint(self, painter, option, index):
        # Remove focus state BEFORE default painting
        if option.state & QtWidgets.QStyle.State_HasFocus:
            option.state &= ~QtWidgets.QStyle.State_HasFocus

        super().paint(painter, option, index)

        # Draw a horizontal line below each item except the last one
        if index.row() < index.model().rowCount() - 1:
            pen = QtGui.QPen(QtGui.QColor("#555555"))  # line color
            pen.setWidth(1)
            painter.setPen(pen)
            bottom = option.rect.bottom()
            left = option.rect.left()
            right = option.rect.right()
            painter.drawLine(left, bottom, right, bottom)

class PaintToolWidget(ResizableMixin, QtWidgets.QWidget):
    def __init__(self, parent=None, trackerManager=None):
        super().__init__(parent)
        self._initResizable()
        self.trackerManager = trackerManager
        # State
        self.parentItems = {}
        self.mirrorMode = "YZ"
        self.surfaceAssociation = "closestPoint"
        self.mirrorInverse = False
        self.sourceShape = None

        # Window flags / sizing
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.Tool)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.resize(300, 280)
        self.setMinimumSize(150, 150)
        self.setObjectName("MainDialog")

        # Layouts
        mainLayout = QtWidgets.QVBoxLayout(self)
        mainLayout.setContentsMargins(0, 0, 0, 0)
        mainLayout.setSpacing(0)

        container = QtWidgets.QFrame(objectName="Container")
        containerLayout = QtWidgets.QVBoxLayout(container)
        containerLayout.setContentsMargins(0, 0, 0, 10)
        containerLayout.setSpacing(4)

        titleBarWidget = TitleBar("Paint Weights Tool", self)
        titleBarWidget.closeBtn.clicked.connect(self.close)
        containerLayout.addWidget(titleBarWidget)

        contentWidget = QtWidgets.QWidget()
        contentLayout = QtWidgets.QVBoxLayout(contentWidget)
        contentLayout.setContentsMargins(10, 0, 10, 0)
        contentLayout.setSpacing(6)

        # --- Button bar ---
        buttonBarWidget = QtWidgets.QWidget()
        buttonBarWidget.setStyleSheet(styles.TOOL_BUTTON_STYLE)
        buttonBarLayout = QtWidgets.QHBoxLayout(buttonBarWidget)
        buttonBarLayout.setContentsMargins(0, 0, 0, 0)
        buttonBarLayout.setSpacing(4)

        def makeBtn(attr, normal, hover=None, pressed=None, **kw):
            btn = paintIconButton(
                styles.iconPath(normal),
                styles.iconPath(hover) if hover else None,
                styles.iconPath(pressed) if pressed else None,
                **kw
            )
            btn.setFlat(True)
            setattr(self, attr, btn)
            return btn

        # Create buttons
        self.copybnt = makeBtn("copybnt", "copyNormal.svg", "copyHover.svg", "copyPressed.svg")
        self.pastebnt = makeBtn("pastebnt", "pasteNormal.svg", "pasteHover.svg", "pastePressed.svg")
        self.paintbnt = makeBtn("paintbnt", "paintNormal.svg", "paintHover.svg", "paintPressed.svg")
        self.mirrorbnt = makeBtn("mirrorbnt", "mirrorNormal.svg", "mirrorHover.svg", "mirrorPressed.svg")
        self.flipbnt = makeBtn("flipbnt", "flipNormal.svg", "flipHover.svg", "flipPressed.svg")
        self.settingBtn = makeBtn("settingBtn", "settingNormal.svg", "settingHover.svg", "settingPressed.svg", releaseEvent=False)

        # Attach menu to settings button
        self.settingBtn.setMenu(self._buildMenu())

        # Add buttons to layout
        for btn in (self.copybnt, self.pastebnt, self.mirrorbnt, self.flipbnt):
            buttonBarLayout.addWidget(btn)

        # Filter bar
        self.filterEdit = SearchWidget()
        self.filterEdit.setPlaceholderText("Filter...")
        self.filterEdit.textChanged.connect(self.filterList)
        buttonBarLayout.addWidget(self.filterEdit)
        buttonBarLayout.addWidget(self.paintbnt)
        buttonBarLayout.addWidget(self.settingBtn)
        contentLayout.addWidget(buttonBarWidget)

        # --- List Widget ---
        self.listWidget = QtWidgets.QListWidget(objectName="ListWidget")
        self.listWidget.setItemDelegate(LineDelegate(self.listWidget))
        self.listWidget.itemSelectionChanged.connect(self.onListWidgetSelectionChanged)

        self.listWidget.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.listWidget.customContextMenuRequested.connect(self._showListMenu)

        contentLayout.addWidget(self.listWidget)
        containerLayout.addWidget(contentWidget)
        mainLayout.addWidget(container, 1)

        # Button signals
        self.copybnt.clicked.connect(self.copyClicked)
        self.pastebnt.clicked.connect(self.pasteClicked)
        self.paintbnt.clicked.connect(self.paintClicked)
        self.mirrorbnt.clicked.connect(lambda: self._applyWeightOp("mirror"))
        self.flipbnt.clicked.connect(lambda: self._applyWeightOp("flip"))

        # Style
        self.setStyleSheet("""
            #Container {
                background-color: #4C4C4C;
                border-radius: 12px;
            }
            #ListWidget {
                background-color: #3a3a3a;
                border: none;
                border-radius: 4px;
            }
            #ItemWidget {
                background-color: #3a3a3a;
            }
        """)

        self._installEvent()
        self._updateToolTip()

    def _buildMenu(self) -> QtWidgets.QMenu:
        """
        Build and return the settings QMenu.
        Uses non-checkable QAction and sets tick icon manually to avoid style-dependent rectangle artifacts.
        """
        menu = QtWidgets.QMenu(self)
        menu.setFixedWidth(200)
        menu.setStyleSheet("""
            QMenu::item { icon-size: 10px 10px; }
            QMenu { font-size: 11px; }
            QMenu::indicator { width: 0px; height: 0px; }
        """)

        tickIcon = QtGui.QIcon(styles.iconPath("setDefault.svg"))

        # --- Mirror Across submenu ---
        subMenu = QtWidgets.QMenu("Mirror Across", menu)
        subMenu.setMinimumWidth(100)
        # store actions on self if you may want to change them later
        self.actionXY = subMenu.addAction("XY")
        self.actionYZ = subMenu.addAction("YZ")
        self.actionXZ = subMenu.addAction("XZ")

        def select_plane_action(selected_act):
            for act in (self.actionXY, self.actionYZ, self.actionXZ):
                act.setIcon(tickIcon if act is selected_act else QtGui.QIcon())
            self.mirrorMode = selected_act.text()

        self.actionXY.triggered.connect(lambda: select_plane_action(self.actionXY))
        self.actionYZ.triggered.connect(lambda: select_plane_action(self.actionYZ))
        self.actionXZ.triggered.connect(lambda: select_plane_action(self.actionXZ))
        select_plane_action(self.actionYZ)  # default

        menu.addMenu(subMenu)

        # --- Direction toggle (non-checkable) ---
        self.directionAction = menu.addAction("Positive to negative (+X to -X)")
        self._direction_on = True
        self.directionAction.setIcon(tickIcon)

        def _toggle_direction():
            self._direction_on = not self._direction_on
            self.directionAction.setIcon(tickIcon if self._direction_on else QtGui.QIcon())
            self.mirrorInverse = not self._direction_on

        self.directionAction.triggered.connect(_toggle_direction)

        # --- Surface Association submenu ---
        subSurface = QtWidgets.QMenu("Surface Association", menu)
        self.actionClosestPoint = subSurface.addAction("Closest Point On Surface")
        self.actionClosestComponent = subSurface.addAction("Closest Component")

        def select_surface_action(selected_act):
            for act in (self.actionClosestPoint, self.actionClosestComponent):
                act.setIcon(tickIcon if act is selected_act else QtGui.QIcon())
            self.surfaceAssociation = "closestComponent" if selected_act is self.actionClosestComponent else "closestPoint"

        self.actionClosestPoint.triggered.connect(lambda: select_surface_action(self.actionClosestPoint))
        self.actionClosestComponent.triggered.connect(lambda: select_surface_action(self.actionClosestComponent))
        select_surface_action(self.actionClosestPoint)  # default

        menu.addMenu(subSurface)

        return menu

    def _showListMenu(self, pos):
        menu = QtWidgets.QMenu(self)
        # === Lock group ===
        lockSelected = menu.addAction("Lock Selected")
        unlockSelected = menu.addAction("Unlock Selected")
        lockInverse = menu.addAction("Lock Inverse Selection")
        unlockInverse = menu.addAction("Unlock Inverse Selection")
        menu.addSeparator()
        # === Normalize group ===
        normalizeSelected = menu.addAction("Normalize Selected")
        disableNormalizeSelected = menu.addAction("Unnormalize Selected")
        normalizeInverse = menu.addAction("Normalize Inverse Selection")
        disableNormalizeInverse = menu.addAction("Unnormalize Inverse Selection")

        # Show menu at global position
        action = menu.exec_(self.listWidget.mapToGlobal(pos))

        # === Handle actions ===
        if action == lockSelected:
            self._applyAction(False, "locked", True, "toggleLock", "Lock Selected")
        elif action == unlockSelected:
            self._applyAction(False, "locked", False, "toggleLock", "Unlock Selected")
        elif action == lockInverse:
            self._applyAction(True, "locked", True, "toggleLock", "Lock Inverse Selection")
        elif action == unlockInverse:
            self._applyAction(True, "locked", False, "toggleLock", "Unlock Inverse Selection")

        elif action == normalizeSelected:
            self._applyAction(False, "normalize", True, "toggleNormalize", "Normalize Selected")
        elif action == disableNormalizeSelected:
            self._applyAction(False, "normalize", False, "toggleNormalize", "Disable Normalize (Selected)")
        elif action == normalizeInverse:
            self._applyAction(True, "normalize", True, "toggleNormalize", "Normalize Inverse Selection")
        elif action == disableNormalizeInverse:
            self._applyAction(True, "normalize", False, "toggleNormalize", "Disable Normalize (Inverse Selection)")

    def _applyAction(self, inverse, attrName, desiredState, toggleMethod, label):
        """
        Apply lock/normalize actions to widgets.

        Args:
            inverse (bool): Whether to use inverse selection.
            attrName (str): Attribute to check ('locked' or 'normalize').
            desiredState (bool): Target state to apply.
            toggleMethod (str): Method name to toggle ('toggleLock' or 'toggleNormalize').
            label (str): Label for debug printing.
        """
        widgets = self.getSelectedItemWidgets(inverse=inverse)
        if not widgets:
            return

        for wg in widgets:
            if getattr(wg, attrName) == desiredState:
                return
            getattr(wg, toggleMethod)()

    def getSelectedItemWidgets(self, inverse=False):
        """
        Return a list of selected widgets from the listWidget.
        Skips item[0] (base item).

        Args:
            inverse (bool): If True, return unselected (inverse) widgets.

        Returns:
            list: A list of QWidget objects.
        """
        # all items except index 0
        all_items = [self.listWidget.item(i) for i in range(1, self.listWidget.count())]
        selected_items = self.listWidget.selectedItems()

        if inverse:
            # items not in selection
            items = [item for item in all_items if item not in selected_items]
        else:
            # selected items only (but skip index 0 automatically)
            items = [item for item in selected_items if self.listWidget.row(item) > 0]

        widgets = [self.listWidget.itemWidget(item) for item in items if self.listWidget.itemWidget(item)]
        return widgets

    # --- Core helpers ---
    def _getSelectedTreeItem(self, requireSource=False, disallowBase=True):
        """
        Retrieve the first selected tree item and its associated widget.

        Args:
            requireSource (bool): If True, ensures a source shape has been copied; logs error if not.
            disallowBase (bool): If True, disallows returning the base item (first row); logs error if selected.

        Returns:
            tuple: (widget, treeItem) if a valid target is selected, else (None, None).
        """
        items = self.listWidget.selectedItems()
        if not items:
            return None, None
        widget = self.listWidget.itemWidget(items[0])
        if not widget:
            return None, None
        treeItem = getattr(widget, "treeItem", None)
        if not treeItem:
            return None, None

        if requireSource and not self.sourceShape:
            logger.error("A target shape must be copied first.")
            return None, None
        if disallowBase and items[0] == self.listWidget.item(0):
            logger.error("Base shapes are not supported currently.")
            return None, None

        return widget, treeItem

    def _applyWeightOp(self, opType):
        """
        Perform a weight operation (mirror, flip, or paste) on the selected target.

        Temporarily suspends attribute callbacks during the operation if a trackerManager exists.

        Args:
            opType (str): Type of operation to perform. Must be one of "mirror", "flip", or "paste".
        """
        widget, treeItem = self._getSelectedTreeItem(requireSource=(opType == "paste"))
        if not treeItem:
            return
        destinationTarget = widget.label.text()
        builder = treeItem.builder()

        if self.trackerManager:
            with self.trackerManager.suspended(builder.node):
                if opType == "mirror":
                    builder.mirrorWeight(destinationTarget, self.mirrorMode, self.surfaceAssociation, self.mirrorInverse)
                elif opType == "flip":
                    builder.flipWeight(destinationTarget, self.mirrorMode, self.surfaceAssociation)
                elif opType == "paste":
                    builder.copyWeight(self.sourceShape, destinationTarget, self.surfaceAssociation)

    # --- Button handlers ---
    def copyClicked(self):
        """
        Handle the Copy button click.

        Sets the selected target shape as the source shape and updates tooltips.
        Base items are ignored.
        """
        widget, _ = self._getSelectedTreeItem(disallowBase=True)
        if not widget:
            return
        self.sourceShape = widget.label.text()
        self._updateToolTip()

    def pasteClicked(self):
        """
        Handle the Paste button click.

        Copies the source shape weights to the currently selected target shape.
        """
        self._applyWeightOp("paste")

    def paintClicked(self):
        """
        Update the list widget based on the current selection.

        Preserves the previously selected row when possible. If the selection
        corresponds to a parent item, rebuilds the list from that parent.
        """
        prevNode, newSelNode = None, None
        firstItem = self.listWidget.item(0)
        if firstItem:
            firstWidget = self.listWidget.itemWidget(firstItem)
            if firstWidget:
                prevNode = firstWidget.label.text()

        currentRow = self.listWidget.currentRow()
        selection = getNodeFromSelection()

        if selection and selection in self.parentItems:
            parentItem = self.parentItems[selection]
            newSelNode = parentItem.name()
            self.updateListData(parentItem)

        if self.listWidget.count() == 0:
            return

        if (prevNode == newSelNode or (prevNode and not selection)) and 0 <= currentRow < self.listWidget.count():
            self.listWidget.clearSelection()
            self.listWidget.setCurrentRow(currentRow)
        else:
            self.listWidget.setCurrentRow(0)

    # --- Tooltips ---
    def _short_name(self, name, max_len=22):
        if not name:
            return "None"
        s = str(name)
        return s if len(s) <= max_len else s[: max_len - 1] + "…"

    def _updateToolTip(self):
        sel = self._short_name(self.sourceShape)
        self.copybnt.setToolTip(f"Copy target weights — sel: {sel}")
        self.pastebnt.setToolTip(f"Paste weights to current selection — sel: {sel}")
        inv = "inverse" if self.mirrorInverse else "normal"
        self.mirrorbnt.setToolTip(f"Mirror weights — plane: {self.mirrorMode}, {inv}, assoc: {self.surfaceAssociation}")
        self.flipbnt.setToolTip("Flip target weights")
        self.settingBtn.setToolTip("Open settings for copy & mirror")

    # --- Filter Function ---
    def filterList(self, text: str):
        """
        Filter listWidget items based on the label in each ListItemWidget.
        Preserve selection if the selected item is still visible.
        """
        search = text.lower().strip()
        current_item = self.listWidget.currentItem()
        current_label = None
        if current_item:
            current_widget = self.listWidget.itemWidget(current_item)
            if current_widget:
                current_label = current_widget.label.text()

        # Faster updates: disable repaint & signals while we update visibility
        self.listWidget.setUpdatesEnabled(False)
        self.listWidget.blockSignals(True)
        try:
            for i in range(self.listWidget.count()):
                item = self.listWidget.item(i)
                widget = self.listWidget.itemWidget(item)
                if widget:
                    lbl = widget.label.text().lower()
                    is_visible = (search in lbl) if search else True
                    item.setHidden(not is_visible)
        finally:
            self.listWidget.blockSignals(False)
            self.listWidget.setUpdatesEnabled(True)

        # restore selection if possible
        if current_label:
            for i in range(self.listWidget.count()):
                item = self.listWidget.item(i)
                if item.isHidden():
                    continue
                widget = self.listWidget.itemWidget(item)
                if widget and widget.label.text() == current_label:
                    self.listWidget.setCurrentItem(item)
                    break

    def onListWidgetSelectionChanged(self):
        """
        Handle selection changes in the list widget.

        If the first (base) item is selected, trigger painting of base weights.
        Otherwise, trigger painting of target weights based on the selected item.
        """
        items = self.listWidget.selectedItems()
        if not items:
            return
        widget = self.listWidget.itemWidget(items[0])
        if not widget:
            return
        treeItem = getattr(widget, "treeItem", None)
        if not treeItem:
            return

        # parent row (index 0) is base weight
        if items[0] == self.listWidget.item(0):
            # defensive: ensure builder exists and has method
            builder = treeItem.builder()
            if hasattr(builder, "paintBaseWeight"):
                builder.paintBaseWeight()
        else:
            builder = treeItem.builder()
            if hasattr(builder, "getTargetIndex") and hasattr(builder, "paintTargetWeight"):
                idx = builder.getTargetIndex(widget.label.text())
                builder.paintTargetWeight(idx)

    def setItemData(self, parentItems: dict):
        """
        Store the mapping of parent items for the list widget.

        Args:
            parentItems (dict): A dictionary of parent items to track.
        """
        self.parentItems = parentItems

    def addItem(self, item):
        """
        Add a new item to the parent items dictionary if not already present.

        Args:
            item: The item object to add.
        """
        name = item.name()
        if name not in self.parentItems:
            self.parentItems[name] = item

    def removeItem(self, item):
        """
        Remove an item from the parent items dictionary if it exists.

        Args:
            item: The item object to remove.
        """
        name = item.name()
        if name in self.parentItems:
            del self.parentItems[name]

    def updateListData(self, parentItem):
        """
        Rebuild the listWidget based on the given parentItem.

        This clears the current list and repopulates it with the parent item
        and its children. Signals and updates are temporarily blocked to
        prevent flickering or unnecessary callbacks during the rebuild.

        Args:
            parentItem: The root item containing child items to populate the list.
        """
        self.listWidget.setUpdatesEnabled(False)
        self.listWidget.blockSignals(True)
        try:
            self.listWidget.clear()

            def add_item(treeItem, locked=False, normalize=False, enable=True):
                """
                Helper to add a QListWidgetItem with an associated ListItemWidget.
                """
                name = treeItem.data(0)
                item = QtWidgets.QListWidgetItem()
                widget = ListItemWidget(
                    name, locked=locked, normalize=normalize, enable=enable, treeItem=treeItem
                )
                item.setSizeHint(QtCore.QSize(150, 22))
                self.listWidget.addItem(item)
                self.listWidget.setItemWidget(item, widget)

            # Add parent item first (disabled for editing)
            add_item(parentItem, enable=False)

            # Add child items
            for row in range(parentItem.childCount()):
                childItem = parentItem.child(row)
                locked = getattr(childItem, "weightLocked", False)
                normalize = getattr(childItem, "weightNormalization", False)
                add_item(childItem, locked=locked, normalize=normalize)
        finally:
            self.listWidget.blockSignals(False)
            self.listWidget.setUpdatesEnabled(True)
