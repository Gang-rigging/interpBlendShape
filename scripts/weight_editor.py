from PySide2 import QtWidgets, QtCore, QtGui
from widgets import ResizableMixin, styles
from paint_tool import TitleBar
from enums import ItemType, AttrName
from logger import getLogger

logger = getLogger("InterpBlendShape")

class WeightTableModel(QtCore.QAbstractTableModel):
    """Model for displaying and editing vertex interpBlendShape weights in a QTableView."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.groupedHeaders  = []  # [[parentA, childA, childB], ...] – nested column headers
        self.flatHeaders     = []  # [childA, childB, childC, ...] – flat list of all leaf headers
        self.colToGroupChild = []  # [(groupIndex, childIndex), ...] – maps each column to its header location
        self.vertexBlocks    = []  # [{vertexIds, pathName, geomIndex}, ...] – data blocks per vertex group

    def updateData(self, groupedHeaders, vertexBlocks):
        self.beginResetModel()
        self.groupedHeaders = groupedHeaders
        self.vertexBlocks = vertexBlocks

        self.flatHeaders.clear()
        self.colToGroupChild.clear()
        for groupIdx, group in enumerate(groupedHeaders):
            for childIdx, item in enumerate(group):  # include parents (childIdx == 0)
                self.flatHeaders.append(item)
                self.colToGroupChild.append((groupIdx, childIdx))
        self.endResetModel()

    def columnCount(self, parent=QtCore.QModelIndex()):
        return len(self.flatHeaders)

    def rowCount(self, parent=QtCore.QModelIndex()):
        total = 0
        for block in self.vertexBlocks:
            total += 3 + len(block["vertexIds"])
        return total

    def resolveRow(self, row):
        currentRow = 0
        for i, block in enumerate(self.vertexBlocks):
            blockRows = 3 + len(block["vertexIds"])
            if currentRow <= row < currentRow + blockRows:
                return i, row - currentRow
            currentRow += blockRows
        return None, None

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid() or role not in (QtCore.Qt.DisplayRole, QtCore.Qt.EditRole):
            return None

        row, col = index.row(), index.column()
        blockIdx, localRow = self.resolveRow(row)
        if blockIdx is None or col >= len(self.colToGroupChild):
            return None

        groupIdx, childIdx = self.colToGroupChild[col]
        if groupIdx != blockIdx:
            return ""

        block = self.vertexBlocks[blockIdx]
        groupItems = self.groupedHeaders[groupIdx]
        item = groupItems[childIdx]

        if localRow in (0, 1):
            if item.type() == ItemType.PARENT:
                return ""

            attrName = "weightLocked" if localRow == 0 else "weightNormalization"
            return "on" if getattr(item, attrName, False) else "off"
        elif localRow == 2:
            return ""
        else:
            idx = localRow - 3
            vid = block["vertexIds"][idx]
            if hasattr(item, "builder"):
                builder = item.builder()
                if childIdx == 0:
                    val = builder.getBaseWeights(vid, block["geomIndex"])
                else:
                    val = builder.getTargetVertexWeights(item.name(), vid, block["geomIndex"])
                return f"{val:.3f}"
            return "0.000"

    def setData(self, index, value, role=QtCore.Qt.EditRole):
        if not index.isValid() or role != QtCore.Qt.EditRole:
            return False

        row, col = index.row(), index.column()
        blockIdx, localRow = self.resolveRow(row)
        if blockIdx is None or col >= len(self.colToGroupChild):
            return False

        groupIdx, childIdx = self.colToGroupChild[col]
        if groupIdx != blockIdx:
            return False

        block = self.vertexBlocks[blockIdx]
        childItem = self.flatHeaders[col]
        valStr = str(value).strip().lower()

        # Handle metadata rows
        if localRow in (0, 1):
            if childItem.type() == ItemType.PARENT:
                return False

            attr = AttrName.TARGET_WEIGHT_LOCKED if localRow == 0 else AttrName.TARGET_WEIGHT_NORMALIZATION
            result = self._interpretBoolFromStr(valStr)

            if result is None:
                return False
            status = childItem.builder().setTargetValue(childItem.name(), attr, result)
            if not status:
                logger.warning("Failed to apply target weight value.")
                return False

            self.dataChanged.emit(index, index)
            return True

        # Path row is not editable
        if localRow == 2:
            return False

        # Handle weight rows
        idx = localRow - 3
        try:
            fval = float(valStr)
        except ValueError:
            return False

        vid = block["vertexIds"][idx]

        if childItem.type() == ItemType.PARENT:
            # Parent column: set base weight
            childItem.builder().setBaseWeight(vid, block["geomIndex"], fval)
            normalize = False
        else:
            # Target column: respect lock and normalization flags
            if getattr(childItem, "weightLocked", False):
                logger.warning("Target weight is locked; cannot modify.")
                return False

            normalize = bool(getattr(childItem, "weightNormalization", False))
            childItem.builder().setTargetVertexWeight(
                childItem.name(),
                vid,
                block["geomIndex"],
                fval,
                normalize
            )

        # Emit change for normalized columns in same block
        emitSet = set()
        emitSet.add((index.row(), col))  # Always include current cell

        if normalize:
            for otherCol, (gIdx, cIdx) in enumerate(self.colToGroupChild):
                if otherCol == col or gIdx != blockIdx:
                    continue
                otherItem = self.flatHeaders[otherCol]
                if otherItem.type() != ItemType.PARENT and getattr(otherItem, "weightNormalization", False):
                    emitSet.add((index.row(), otherCol))

        for r, c in emitSet:
            idx = self.index(r, c)
            self.dataChanged.emit(idx, idx, [QtCore.Qt.DisplayRole])

        return True

    def flags(self, index):
        if not index.isValid():
            return QtCore.Qt.NoItemFlags

        flags = QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled
        row, col = index.row(), index.column()
        blockIdx, localRow = self.resolveRow(row)
        if blockIdx is None or col >= len(self.colToGroupChild):
            return flags

        groupIdx, childIdx = self.colToGroupChild[col]
        if groupIdx != blockIdx:
            return flags

        item = self.flatHeaders[col]
        if localRow in (0, 1):
            if item.type() != ItemType.PARENT:
                flags |= QtCore.Qt.ItemIsEditable
        elif localRow >= 3:
            flags |= QtCore.Qt.ItemIsEditable

        return flags

    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
        if role != QtCore.Qt.DisplayRole:
            return None

        if orientation == QtCore.Qt.Horizontal:
            if 0 <= section < len(self.flatHeaders):
                groupIdx, childIdx = self.colToGroupChild[section]
                item = self.flatHeaders[section]
                if childIdx == 0:
                    return self.groupedHeaders[groupIdx][0].name()
                return item.name()

        if orientation == QtCore.Qt.Vertical:
            blockIdx, localRow = self.resolveRow(section)
            if blockIdx is None:
                return None

            block = self.vertexBlocks[blockIdx]
            if localRow == 0:
                return "Hold"
            elif localRow == 1:
                return "Normalize"
            elif localRow == 2:
                return block.get("pathName", "")
            else:
                idx = localRow - 3
                vertexIds = block.get("vertexIds", [])
                if 0 <= idx < len(vertexIds):
                    return f"vtx[{vertexIds[idx]}]"

        return None

    def _interpretBoolFromStr(self, s):
        if s in ("on", "true"):
            return True
        elif s in ("off", "false"):
            return False
        try:
            return float(s) >= 1
        except ValueError:
            return None

class WeightTableView(QtWidgets.QTableView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pressIndex = None
        self._pressPos = None
        self._dragThreshold = QtWidgets.QApplication.startDragDistance()
        self._initView()

    def _initView(self):
        # Disable column stretching, enable horizontal scroll
        header = self.horizontalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
        header.setStretchLastSection(False)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectItems)
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)

        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setFocusPolicy(QtCore.Qt.NoFocus)

    def mousePressEvent(self, event):
        index = self.indexAt(event.pos())
        if index.isValid() and index.flags() & QtCore.Qt.ItemIsEditable:
            self._pressIndex = index
            self._pressPos = event.pos()
        else:
            self.clearSelection()
            self.setCurrentIndex(QtCore.QModelIndex())

        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        moved = False
        if self._pressPos:
            moved = (event.pos() - self._pressPos).manhattanLength() >= self._dragThreshold
        super().mouseReleaseEvent(event)
        if not moved:
            idx = self.indexAt(event.pos())
            if idx.isValid() and idx.flags() & QtCore.Qt.ItemIsEditable:
                self.edit(idx)
        else:
            cur = self.currentIndex()
            if cur.isValid() and cur.flags() & QtCore.Qt.ItemIsEditable:
                self.edit(cur)
        self._pressIndex = None
        self._pressPos = None

    def commitData(self, editor):
        selectedIndexes = self.selectedIndexes()
        if not selectedIndexes:
            return

        text = editor.text().strip()
        if text.startswith('.'):
            text = '0' + text

        model = self.model()
        # Only update editable items
        for idx in selectedIndexes:
            if idx.flags() & QtCore.Qt.ItemIsEditable:
                model.setData(idx, text, QtCore.Qt.EditRole)


class WeightEditor(ResizableMixin, QtWidgets.QWidget):
    """Main widget containing the weight table view and data model."""

    def __init__(self, parent=None, sceneMonitor=None):
        super().__init__(parent)

        self.sceneMonitor = sceneMonitor
        if self.sceneMonitor:
            self.sceneMonitor.selectionChanged.connect(self.selectionChangedCallback)

        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint |
            QtCore.Qt.Tool
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setMinimumSize(400, 200)
        self.resize(600, 400)
        self._initResizable()
        self._buildUI()
        self.setStyleSheet(styles.MAIN_UI_STYLE)
        self._installEvent()

    def _buildUI(self):

        # Main layout for the whole widget
        mainLayout = QtWidgets.QVBoxLayout(self)
        mainLayout.setContentsMargins(0, 0, 0, 0)
        mainLayout.setSpacing(0)

        # --- Container holds title bar + buttons + list ---
        container = QtWidgets.QFrame()
        container.setObjectName("Container")
        container.setStyleSheet(
            "#Container { background-color: #4C4C4C; border-radius: 12px; }"
        )
        containerLayout = QtWidgets.QVBoxLayout(container)
        containerLayout.setContentsMargins(0, 0, 0, 10)
        containerLayout.setSpacing(6)

        titleBarWidget = TitleBar("InterpBlendShape Weight Editor", self)
        titleBarWidget.closeBtn.clicked.connect(self.close)

        containerLayout.addWidget(titleBarWidget)

        # --- Content table view widget
        contentWidget = QtWidgets.QWidget()
        contentLayout = QtWidgets.QVBoxLayout(contentWidget)
        contentLayout.setContentsMargins(10, 0, 10, 0)
        contentLayout.setSpacing(6)

        # Table view
        self.view = WeightTableView(self)
        self.model = WeightTableModel()
        self.view.setModel(self.model)
        self.view.resizeColumnsToContents()
        self.view.setEditTriggers(
            QtWidgets.QAbstractItemView.DoubleClicked | QtWidgets.QAbstractItemView.SelectedClicked)

        contentLayout.addWidget(self.view)

        containerLayout.addWidget(contentWidget)
        mainLayout.addWidget(container, 1)

        # Adjust row height
        self.view.verticalHeader().setDefaultSectionSize(18)

    def getParentItemFromTracker(self, nodeName):
        if self.sceneMonitor:
            if self.sceneMonitor.trackerManager:
                return self.sceneMonitor.trackerManager.getItem(nodeName)
        return None

    def selectionChangedCallback(self, selectedComponents):
        headerData = []
        selectionData = []
        for pathName, geomIndex, (indices, deformers) in selectedComponents:
            parentItem = self.getParentItemFromTracker(deformers[0].name())
            if not parentItem:
                continue

            treeItemList = [parentItem] + [parentItem.child(i) for i in range(parentItem.childCount())]
            headerData.append(treeItemList)
            selectionData.append({
                "vertexIds": indices,
                "pathName": pathName,
                "geomIndex": geomIndex,
            })
        self.model.updateData(headerData, selectionData)

    def closeEvent(self, event):
        if self.sceneMonitor:
            self.sceneMonitor.clearSelectionCallback()
        super().closeEvent(event)
