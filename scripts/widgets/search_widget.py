from functools import partial

from PySide2 import QtCore, QtGui, QtWidgets


class SearchWidget(QtWidgets.QLineEdit):
    searchTriggered = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("Search...")
        self.arrowWidth = 6
        self.clearButtonWidth = 16
        self.setTextMargins(0, 0, self.arrowWidth + self.clearButtonWidth + 10, 0)

        font = self.font()
        font.setPointSize(10)
        self.setFont(font)
        self.setMinimumHeight(25)

        self.clearBtn = QtWidgets.QToolButton(self)
        self.clearBtn.setVisible(False)
        self.clearBtn.clicked.connect(self.clearAndEmit)
        self.setFocusPolicy(QtCore.Qt.ClickFocus)
        self.textChanged.connect(self.updateClearButtonVisibility)
        self.clearBtn.setText("x")
        self.clearBtn.setCursor(QtCore.Qt.PointingHandCursor)
        self.clearBtn.setStyleSheet("""
            QToolButton {
                border: none;
                padding: 0px;
                color: #aaa;
                font-weight: bold;
                background: transparent;
            }
            QToolButton:hover {
                color: white;
                background-color: #555;
                border-radius: 8px;
            }
        """)

        self.menu = QtWidgets.QMenu(self)
        self.history = []

        self.returnPressed.connect(self.handleSearch)

    def updateClearButtonVisibility(self, text):
        self.clearBtn.setVisible(bool(text))

    def clearAndEmit(self):
        self.setText("")
        self.searchTriggered.emit("")

    def handleSearch(self):
        text = self.text().strip()
        if text and text not in self.history:
            self.history.append(text)
            action = self.menu.addAction(text)
            action.triggered.connect(partial(self.setTextAndSearch, text))
        self.searchTriggered.emit(text)

    def setTextAndSearch(self, text):
        self.setText(text)
        self.searchTriggered.emit(text)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        h = self.height()
        y = (h - self.clearButtonWidth) // 2
        clearX = self.width() - self.arrowWidth - self.clearButtonWidth - 8
        self.clearBtn.setGeometry(clearX, y, self.clearButtonWidth, self.clearButtonWidth)

    def paintEvent(self, event):
        super().paintEvent(event)
        rect = self.arrowRect()
        painter = QtGui.QPainter(self)

        color = QtGui.QColor(187, 187, 187)
        painter.setBrush(color)
        painter.setPen(QtCore.Qt.NoPen)

        points = [
            QtCore.QPoint(rect.left(), rect.top()),
            QtCore.QPoint(rect.right(), rect.top()),
            QtCore.QPoint(rect.center().x(), rect.bottom()),
        ]

        painter.drawPolygon(QtGui.QPolygon(points))

    def arrowRect(self):
        h = self.height()
        arrowWidth = 10
        arrowHeight = 6

        x = self.width() - arrowWidth - 4
        y = (h - arrowHeight) // 2

        return QtCore.QRect(x, y, arrowWidth, arrowHeight)

    def arrowHitRect(self):
        h = self.height()
        hitboxWidth = 20
        hitboxHeight = 20
        x = self.width() - hitboxWidth - 4
        y = (h - hitboxHeight) // 2
        return QtCore.QRect(x, y, hitboxWidth, hitboxHeight)

    def mousePressEvent(self, event):
        if self.arrowHitRect().contains(event.pos()):
            if not self.menu.isEmpty():
                pos = self.mapToGlobal(QtCore.QPoint(0, self.height()))
                self.menu.setMinimumWidth(self.width())
                self.menu.exec_(pos)
        else:
            super().mousePressEvent(event)
