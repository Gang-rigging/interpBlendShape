"""
main_window.py

Contains the InterpBlendShapeEditor QMainWindow subclass.
Loads necessary plugins during initialization to ensure required commands are available.
Handles UI setup and interaction logic.
"""
import datetime

from PySide2 import QtCore, QtGui, QtWidgets

import app_config
from enums import HeaderColumn, ItemType, VERSION_NUMBER
from logger import getLogger
from maya_utils import loadPlugin
from tree_view import InterpBlendShapeView
from widgets import HoverButton, ResizableMixin, SpinnerWidget, TopBarWidget, styles
from widgets.shape_edit_popup import ShapeEditOptionsPopup
from widgets import ui_utils

logger = getLogger("InterpBlendShape")


class InterpBlendShapeEditor(ResizableMixin, QtWidgets.QMainWindow):

    def __init__(self, parent=None):
        super().__init__(parent)

        loadPlugin("interpBlendShape")

        self._initResizable()

        self.setWindowTitle(app_config.WINDOW_TITLE)
        self.setObjectName(app_config.WINDOW_OBJECT_NAME)
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.Window)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)

        self.oldPos = None
        self._pressed = False
        self._resizeDir = None
        self._normalGeometry = self.geometry()
        self._startOpenTime = None  # Set externally in showUI()
        self._shapeEditOptions = self._loadShapeEditOptions()
        self._shapeOptionsPopup = None
        self._shapesMenu = None
        self._actionMirrorTarget = None
        self._actionFlipTarget = None
        self._actionShapeOptions = None
        self._selectionModelRef = None

        self._setup_ui()
        self._installEvent()

    # Setup
    def _setup_ui(self):
        central = QtWidgets.QWidget()
        central.setObjectName("centralWidget")
        central.setStyleSheet(styles.CENTRAL_WIDGET_STYLE)

        mainLayout = QtWidgets.QVBoxLayout(central)
        mainLayout.setContentsMargins(0, 0, 0, 0)
        mainLayout.setSpacing(2)

        mainLayout.addWidget(self._buildTitleBar())
        mainLayout.addWidget(self._buildMenuBar())
        mainLayout.addWidget(self._buildContent())
        mainLayout.addLayout(self._buildCopyrightLayout())

        self.setCentralWidget(central)
        self._buildOverlay()
        self._connectSignals()
        self._updateShapeMenuState()

        self.resize(680, 400)
        self.setStyleSheet(styles.MAIN_UI_STYLE)

    def _buildTitleBar(self):
        title_bar = QtWidgets.QWidget()
        title_bar.setFixedHeight(36)
        title_bar.setObjectName("titleBar")
        title_bar.setStyleSheet(styles.TITLE_BAR_STYLE)

        layout = QtWidgets.QHBoxLayout(title_bar)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.addWidget(QtWidgets.QLabel("InterpBlendShape Editor",
                                          styleSheet="color: white;"))
        layout.addStretch()

        closeBtn = HoverButton(styles.ICON_CLOSE_DEFAULT, styles.ICON_CLOSE_HOVER)
        closeBtn.setFixedSize(24, 24)
        closeBtn.setStyleSheet(styles.CLOSE_BUTTON_STYLE)
        closeBtn.clicked.connect(self.close)

        minBtn = QtWidgets.QPushButton()
        minBtn.setIcon(QtGui.QIcon(styles.ICON_MINIMIZE))
        minBtn.setFixedSize(24, 24)
        minBtn.setStyleSheet(styles.MINMAX_BUTTON_STYLE)
        minBtn.clicked.connect(self.showMinimized)

        self.maxBtn = QtWidgets.QPushButton()
        self.maxBtn.setIcon(QtGui.QIcon(styles.ICON_MAXIMIZE))
        self.maxBtn.setFixedSize(24, 24)
        self.maxBtn.setStyleSheet(styles.MINMAX_BUTTON_STYLE)
        self.maxBtn.clicked.connect(self.toggleMaxRestore)

        layout.addWidget(minBtn)
        layout.addWidget(self.maxBtn)
        layout.addWidget(closeBtn)

        return title_bar

    def _buildMenuBar(self):
        menuBar = QtWidgets.QMenuBar(self)
        menuBar.setStyleSheet(styles.MENU_BAR_STYLE)

        # Define actions
        self._actionCreateNode = QtWidgets.QAction("InterpBlendShape", self)
        self._actionCreateNode.triggered.connect(lambda: self.tree.addNewNodeClicked())

        self._actionAddTarget = QtWidgets.QAction("Add Selection as Target", self)
        self._actionAddTarget.triggered.connect(lambda: self.tree.addTargetClicked())
        self._actionAddTarget.setEnabled(False)

        self._actionAddInbetween = QtWidgets.QAction("Add Selection as In-Between Target", self)
        self._actionAddInbetween.triggered.connect(
            lambda: self.tree.menuHandler.handleAddInbetweenTarget(self.tree.getSelectedItem())
        )
        self._actionAddInbetween.setEnabled(False)

        createMenu = menuBar.addMenu("Create")
        createMenu.addAction(self._actionCreateNode)
        createMenu.addSeparator()
        createMenu.addAction(self._actionAddTarget)
        createMenu.addAction(self._actionAddInbetween)

        self._shapeOptionsPopup = ShapeEditOptionsPopup(self)
        self._shapeOptionsPopup.setOptions(self._shapeEditOptions)
        self._shapeOptionsPopup.optionsChanged.connect(self._onShapeEditOptionsChanged)

        self._shapesMenu = menuBar.addMenu("Shapes")
        self._actionMirrorTarget = QtWidgets.QAction("Mirror Target", self)
        self._actionMirrorTarget.triggered.connect(lambda: self._applyShapeEdit(flipTarget=False))
        self._actionFlipTarget = QtWidgets.QAction("Flip Target", self)
        self._actionFlipTarget.triggered.connect(lambda: self._applyShapeEdit(flipTarget=True))
        self._actionShapeOptions = QtWidgets.QAction("Options...", self)
        self._actionShapeOptions.triggered.connect(
            lambda: self._showShapeOptionsPopup(QtGui.QCursor.pos())
        )
        self._actionAboutInterpBlendShape = QtWidgets.QAction("InterpBlendShape Docs", self)
        self._actionAboutInterpBlendShape.triggered.connect(self._openDocumentation)
        self._actionReportIssue = QtWidgets.QAction("Report Issue", self)
        self._actionReportIssue.triggered.connect(self._openIssueTracker)
        self._shapesMenu.addAction(self._actionMirrorTarget)
        self._shapesMenu.addAction(self._actionFlipTarget)
        self._shapesMenu.addSeparator()
        self._shapesMenu.addAction(self._actionShapeOptions)
        self._shapesMenu.aboutToShow.connect(self._updateShapeMenuState)

        helpMenu = menuBar.addMenu("Help")
        helpMenu.addAction(self._actionAboutInterpBlendShape)
        helpMenu.addAction(self._actionReportIssue)

        return menuBar

    def _buildContent(self):
        content = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(content)
        layout.setContentsMargins(10, 10, 10, 10)

        self.topbarWidget = TopBarWidget()
        self.tree = InterpBlendShapeView(self)

        layout.addWidget(self.topbarWidget)
        layout.addWidget(self.tree)

        return content

    def _buildCopyrightLayout(self):
        label = QtWidgets.QLabel(
            f"(C) Zhenggang Deng. All rights reserved.  v{VERSION_NUMBER}"
        )
        label.setStyleSheet("color: #aaa; font-size: 10px;")
        label.setAlignment(QtCore.Qt.AlignRight)

        layout = QtWidgets.QHBoxLayout()
        layout.addStretch()
        layout.addWidget(label)
        layout.setContentsMargins(20, 0, 50, 5)

        return layout

    def _buildOverlay(self):
        self.overlay = QtWidgets.QWidget(self)
        self.overlay.setStyleSheet(styles.OVERLAY_STYLE)
        self.overlay.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)
        self.overlay.hide()

        self.spinner = SpinnerWidget(self.overlay)
        self.spinner.setMinimumSize(80, 80)

        layout = QtWidgets.QVBoxLayout(self.overlay)
        layout.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.spinner)

    def _connectSignals(self):
        self.tree.modelLoadStarted.connect(self.startOverlaySpinner)
        self.tree.modelLoadFinished.connect(self.stopOverlaySpinner)
        self.tree.modelLoadFinished.connect(self._onModelLoaded)

        self.topbarWidget.searchWidget.searchTriggered.connect(self.tree.onFilterChanged)
        self.topbarWidget.createBtn.clicked.connect(self.tree.addNewNodeClicked)
        self.topbarWidget.addTargetBtn.clicked.connect(self.tree.addTargetClicked)
        self.topbarWidget.deleteBtn.clicked.connect(self.tree.deleteSelectedItems)
        self.topbarWidget.addSurfaceBtn.clicked.connect(self.tree.addSurfaceToItem)
        self.topbarWidget.rebindBtn.clicked.connect(self.tree.rebindSelNode)
        self.topbarWidget.paintBtn.clicked.connect(self.tree.openPaintTool)
        self.topbarWidget.dataBtn.clicked.connect(self.tree.openWeightEditor)

    # Slots
    def _onModelLoaded(self):
        currentSelectionModel = self.tree.selectionModel()
        if currentSelectionModel is not None and currentSelectionModel is not self._selectionModelRef:
            if self._selectionModelRef is not None:
                try:
                    self._selectionModelRef.selectionChanged.disconnect(self.onSelectionChanged)
                except (RuntimeError, TypeError):
                    pass

            currentSelectionModel.selectionChanged.connect(self.onSelectionChanged)
            self._selectionModelRef = currentSelectionModel

        self._updateCreateMenuState()
        self._updateShapeMenuState()

    def onSelectionChanged(self, selected, deselected):
        selectedIndexes = self.tree.selectionModel().selectedIndexes()
        selectedRows = {idx.row() for idx in selectedIndexes if idx.column() == 0}
        rowCount = len(selectedRows)

        self.topbarWidget.updateTopbarState(rowCount == 1)
        self.topbarWidget.deleteBtn.setEnabled(rowCount >= 1)
        self._updateCreateMenuState()
        self._updateShapeMenuState()

    def _updateCreateMenuState(self):
        item = self.tree.getSelectedItem()
        isParent = item is not None and item.type() == ItemType.PARENT
        isChild  = item is not None and item.type() == ItemType.CHILD

        self._actionAddTarget.setEnabled(isParent or isChild)
        self._actionAddInbetween.setEnabled(isChild)

    def _loadShapeEditOptions(self):
        return app_config.shape_edit_options()

    def _saveShapeEditOptions(self):
        app_config.save_shape_edit_options(self._shapeEditOptions)

    def _openDocumentation(self):
        QtGui.QDesktopServices.openUrl(
            QtCore.QUrl("https://www.cgdzg.com/docs/interpblendshape-docs.html#")
        )

    def _openIssueTracker(self):
        QtGui.QDesktopServices.openUrl(
            QtCore.QUrl("https://github.com/Gang-rigging/interpBlendShape/issues")
        )

    def _showShapeOptionsPopup(self, globalPos=None):
        if not self._shapeOptionsPopup:
            return

        self._shapeOptionsPopup.setOptions(self._shapeEditOptions)
        self._shapeOptionsPopup.adjustSize()

        if globalPos is None:
            globalPos = self.mapToGlobal(QtCore.QPoint(40, 72))

        popupSize = self._shapeOptionsPopup.size()
        anchorPos = self.mapFromGlobal(globalPos)
        margin = 8
        gap = 6

        bounds = self.rect().adjusted(margin, margin, -margin, -margin)
        localPos = anchorPos + QtCore.QPoint(gap, 0)

        if localPos.y() + popupSize.height() > bounds.bottom():
            localPos.setY(anchorPos.y() - popupSize.height() - gap)

        localPos = ui_utils.clamp_point_in_rect(localPos, popupSize, bounds)

        self._shapeOptionsPopup.move(localPos)
        self._shapeOptionsPopup.show()
        self._shapeOptionsPopup.raise_()

    def _onShapeEditOptionsChanged(self, options):
        self._shapeEditOptions = dict(options)
        self._saveShapeEditOptions()
        self._updateShapeMenuState()

    def _shapeOptionSummary(self):
        axisLabels = {
            "YZ": "Object X",
            "XZ": "Object Y",
            "XY": "Object Z",
        }
        direction = "+" if self._shapeEditOptions["mirrorInverse"] else "-"
        associationLabels = {
            "closestComponent": "Closest Component",
            "closestPoint": "Closest Point",
            "closestUV": "Closest UV (Global)",
            "closestUVGlobal": "Closest UV (Global)",
            "closestUVShellCenter": "Closest UV (Shell Center)",
        }
        axisLabel = axisLabels.get(self._shapeEditOptions["mirrorMode"], "Object X")
        associationLabel = associationLabels.get(
            self._shapeEditOptions["surfaceAssociation"],
            "Closest Component",
        )
        return f"Direction: {direction} | Axis: {axisLabel} | Match: {associationLabel}"

    def _updateShapeMenuState(self):
        hasSelection = False
        item = getattr(self.tree, "getSelectedItem", lambda: None)()
        if item is not None:
            hasSelection = item.type() == ItemType.CHILD

        summary = self._shapeOptionSummary()
        if self._actionMirrorTarget:
            self._actionMirrorTarget.setEnabled(hasSelection)
            self._actionMirrorTarget.setToolTip(f"Mirror the selected target shape. {summary}")
        if self._actionFlipTarget:
            self._actionFlipTarget.setEnabled(hasSelection)
            self._actionFlipTarget.setToolTip(f"Flip the selected target shape. {summary}")
        if self._actionShapeOptions:
            self._actionShapeOptions.setToolTip(f"Open shape options. {summary}")

    def _selectedShapeOperationTarget(self, item=None):
        item = item or self.tree.getSelectedItem()
        if not item or item.type() != ItemType.CHILD:
            logger.warning("Select a target shape first.")
            return None, None, None

        builder = item.builder()
        if not builder:
            logger.warning("Selected target does not have a valid builder.")
            return None, None, None

        targetName = item.name()
        return builder, targetName, targetName

    def _applyShapeEdit(self, flipTarget=False, item=None):
        builder, destinationShapes, displayName = self._selectedShapeOperationTarget(item=item)
        if not builder:
            return

        operationLabel = "flip" if flipTarget else "mirror"
        options = self._shapeEditOptions
        success = builder.editTargetShape(
            destinationShapes,
            mirrorMode=options["mirrorMode"],
            surfaceAssociation=options["surfaceAssociation"],
            mirrorInverse=options["mirrorInverse"],
            flipTarget=flipTarget,
        )

        if not success:
            logger.warning(f"Failed to {operationLabel} target '{displayName}'.")

    def applyShapeEditToItem(self, item, flipTarget=False):
        self._applyShapeEdit(flipTarget=flipTarget, item=item)

    def showShapeEditOptions(self, globalPos=None):
        self._showShapeOptionsPopup(globalPos)

    def startOverlaySpinner(self):
        self.overlay.setGeometry(self.rect())
        self.overlay.raise_()
        self.overlay.show()
        self.spinner.start()

    def stopOverlaySpinner(self):
        self.spinner.stop()
        self.overlay.hide()

    # Events
    def showEvent(self, event):
        super().showEvent(event)
        if self._startOpenTime:
            elapsed = (datetime.datetime.now() - self._startOpenTime).total_seconds()
            logger.info(f"[InterpBlendShapeEditor] UI opened in {elapsed:.3f} seconds")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.overlay.setGeometry(self.rect())
        self.resizeStretchColumnWidth()

    def closeEvent(self, event):
        if self._selectionModelRef is not None:
            try:
                self._selectionModelRef.selectionChanged.disconnect(self.onSelectionChanged)
            except (RuntimeError, TypeError):
                pass
            self._selectionModelRef = None

        self.tree.saveExpandedState()
        self.tree.cleanup()
        if self.tree.sceneMonitor:
            self.tree.sceneMonitor.clear()
        if self.tree.weightEditorUI:
            self.tree.weightEditorUI.close()
        super().closeEvent(event)

    # Helpers
    def resizeStretchColumnWidth(self):
        total_width = self.tree.viewport().width()
        stretch_cols = [HeaderColumn.NAME, HeaderColumn.WEIGHT, HeaderColumn.SURFACE]

        default_widths = {
            HeaderColumn.NAME:    140,
            HeaderColumn.WEIGHT:  160,
            HeaderColumn.SURFACE:  60,
        }
        ratios = {
            HeaderColumn.NAME:    2,
            HeaderColumn.WEIGHT:  1.5,
            HeaderColumn.SURFACE: 1,
        }

        fixed_width = sum(
            self.tree.columnWidth(col)
            for col in range(self.tree.model.columnCount())
            if col not in stretch_cols
        )

        defaultTotal = sum(default_widths[col] for col in stretch_cols)
        remaining = total_width - fixed_width - defaultTotal

        if remaining < 0:
            for col in stretch_cols:
                self.tree.setColumnWidth(col, default_widths[col])
            return

        totalRatio = sum(ratios.values())
        for col in stretch_cols:
            extra = int(remaining * ratios[col] / totalRatio)
            self.tree.setColumnWidth(col, default_widths[col] + extra)

    def toggleMaxRestore(self):
        if self.isMaximized():
            self.showNormal()
            self.setGeometry(self._normalGeometry)
            self.maxBtn.setIcon(QtGui.QIcon(styles.iconPath("maximize.svg")))
        else:
            if not self.isMinimized():
                self._normalGeometry = self.geometry()
            self.showMaximized()
            self.maxBtn.setIcon(QtGui.QIcon(styles.iconPath("restore.svg")))

    def showNormalAndRestore(self):
        self.setGeometry(self._normalGeometry)
        self.showNormal()

