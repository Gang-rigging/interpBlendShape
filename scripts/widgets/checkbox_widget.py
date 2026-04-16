from PySide2 import QtCore, QtGui, QtWidgets
from enums import HeaderColumn

class ClickableLabel(QtWidgets.QLabel):
    clicked = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setFixedSize(20, 20)

        font = self.font()
        font.setPointSize(12)
        font.setBold(True)
        self.setFont(font)

        self._pressed = False
        self._hovered = False
        self._checked = False
        self._column = -1

    def setColumn(self, column):
        self._column = column
        self.updateStyle()

    def setChecked(self, state: bool):
        self._checked = state
        self.updateStyle()

    def isChecked(self):
        return self._checked

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self._pressed = True
            self.updateStyle()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._pressed and self.rect().contains(event.pos()):
            self.clicked.emit()
        self._pressed = False
        self.updateStyle()
        super().mouseReleaseEvent(event)

    def enterEvent(self, event):
        self._hovered = True
        self.updateStyle()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.updateStyle()
        super().leaveEvent(event)

    def updateStyle(self):
        self.setFont(QtGui.QFont("Segoe UI Symbol", 12))
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setText("\u25C9" if self._checked else "\u25CB")

        # Define colors for each column
        if self._column == HeaderColumn.CACHE:  # Green (traffic light style)
            normal = (178, 255, 189)  # green
            hover = (129, 199, 132)  # light green
            pressed = (56, 142, 60)  # dark green
        elif self._column == HeaderColumn.KEY:  # Red (warning style)
            normal = (255, 76, 76)  # red
            hover = (129, 199, 132)   # light red
            pressed = (200, 50, 50)  # dark red
        else:
            normal = (255, 255, 255)
            hover = normal
            pressed = normal

        if self._pressed:
            r, g, b = pressed
            color = f"rgba({r}, {g}, {b}, 255)"
        elif self._hovered:
            if self._checked:
                r, g, b = hover
                color = f"rgba({r}, {g}, {b}, 200)"
            else:
                color = "rgba(255, 255, 255, 100)"
        else:
            if self._checked:
                r, g, b = normal
                color = f"rgba({r}, {g}, {b}, 200)"
            else:
                color = "rgba(255, 255, 255, 40)"

        self.setStyleSheet(f"color: {color};")


class CheckBoxWidget(QtWidgets.QWidget):
    """
    Widget wrapping a clickable label that acts like a checkbox.
    Shows a context menu only if column is 10.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)

        self.label = ClickableLabel()
        layout.addWidget(self.label)
        self.label.clicked.connect(self.onLabelClicked)

    def setColumn(self, column):
        self.label.setColumn(column)

    def onLabelClicked(self):
        if self.label._column == HeaderColumn.CACHE:
            if not self.label.isChecked():
                self.label.setChecked(True)

    def isChecked(self):
        return self.label.isChecked()

    def setValue(self, value):
        self.label.setChecked(value)