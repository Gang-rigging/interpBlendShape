from PySide2 import QtCore, QtGui, QtWidgets

from . import styles, ui_utils


class ListPopupWidget(QtWidgets.QWidget):
    valueSelected = QtCore.Signal(str)

    def __init__(self, options, parent=None, currentValue=None, maxWidthRatio=0.5):
        super().__init__(parent, QtCore.Qt.Popup | QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Tool)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.options      = options
        self.currentValue = currentValue
        self.maxWidthRatio = maxWidthRatio

        self._buildUI()
        QtWidgets.QApplication.instance().installEventFilter(self)

    def _buildUI(self):
        self.frame = QtWidgets.QFrame(self)
        self.frame.setObjectName("popupFrame")
        self.frame.setFocusPolicy(QtCore.Qt.NoFocus)
        self.frame.setStyleSheet(styles.popup_frame_style(alpha=230))
        self.listWidget = QtWidgets.QListWidget()
        self.listWidget.setFocusPolicy(QtCore.Qt.NoFocus)
        self.listWidget.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.listWidget.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.listWidget.setIconSize(QtCore.QSize(12, 12))
        self.listWidget.setStyleSheet(styles.POPUP_LIST_WIDGET_STYLE)

        for option in self.options:
            item = QtWidgets.QListWidgetItem(option)
            if option == self.currentValue:
                # Add checkmark icon to current value
                item.setForeground(QtGui.QColor(styles.ACCENT_COLOR))
                checkIcon = self._makeCheckIcon()
                item.setIcon(checkIcon)
            self.listWidget.addItem(item)

        self.listWidget.itemClicked.connect(self._onItemClicked)

        layout = QtWidgets.QVBoxLayout(self.frame)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.listWidget)

        mainLayout = QtWidgets.QVBoxLayout(self)
        mainLayout.setContentsMargins(0, 0, 0, 0)
        mainLayout.addWidget(self.frame)

    def _makeCheckIcon(self):
        pixmap = QtGui.QPixmap(12, 12)
        pixmap.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        pen = QtGui.QPen(QtGui.QColor(styles.ACCENT_COLOR))
        pen.setWidth(2)
        pen.setCapStyle(QtCore.Qt.RoundCap)
        pen.setJoinStyle(QtCore.Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawLine(2, 6, 5, 9)
        painter.drawLine(5, 9, 10, 3)
        painter.end()
        return QtGui.QIcon(pixmap)

    def _onItemClicked(self, item):
        self.valueSelected.emit(item.text())
        self.close()

    def showAt(self, anchorRectGlobal, cellWidth):
        targetWidth = max(int(cellWidth * self.maxWidthRatio), 120)
        rowHeight = self.listWidget.sizeHintForRow(0)
        if rowHeight <= 0:
            rowHeight = self.fontMetrics().height() + 8

        visibleRows = max(1, min(self.listWidget.count(), 6))
        targetHeight = min(180, visibleRows * rowHeight + 16)

        self.resize(targetWidth, targetHeight)

        if isinstance(anchorRectGlobal, QtCore.QPoint):
            anchorRectGlobal = QtCore.QRect(anchorRectGlobal, QtCore.QSize(max(cellWidth, 1), 1))

        popupPos = ui_utils.anchored_popup_pos(anchorRectGlobal, self.size(), gap=2)
        self.move(popupPos)
        self.show()

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.MouseButtonPress:
            if not self.rect().contains(self.mapFromGlobal(event.globalPos())):
                if event.button() != QtCore.Qt.RightButton:
                    self.close()
                    return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        QtWidgets.QApplication.instance().removeEventFilter(self)
        super().closeEvent(event)
