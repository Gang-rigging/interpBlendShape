from PySide2 import QtCore, QtGui, QtWidgets
class ToggleButtonWidget(QtWidgets.QWidget):
    toggled = QtCore.Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._checked = False
        self._hovered = False
        self._pressed = False

        self.label = QtWidgets.QLabel(self)
        self.label.setAlignment(QtCore.Qt.AlignCenter)
        self.label.setFixedSize(20, 20)
        self.label.setFont(QtGui.QFont("Segoe UI Symbol", 12))
        self.label.setCursor(QtCore.Qt.PointingHandCursor)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.addWidget(self.label)

        self._updateStyle()

    def isChecked(self):
        return self._checked

    def setValue(self, value):
        self._checked = bool(value)
        self._updateStyle()

    def _updateStyle(self):
        self.label.setText("\u25C9" if self._checked else "\u25CB")
        if self._pressed:
            color = "rgba(68, 136, 155, 255)"
        elif self._hovered:
            color = "rgba(85, 170, 195, 200)" if self._checked else "rgba(255, 255, 255, 100)"
        else:
            color = "rgba(85, 170, 195, 200)" if self._checked else "rgba(255, 255, 255, 40)"
        self.label.setStyleSheet(f"color: {color};")

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self._pressed = True
            self._updateStyle()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._pressed and self.rect().contains(event.pos()):
            self._checked = not self._checked
            self.toggled.emit(self._checked)
        self._pressed = False
        self._updateStyle()
        super().mouseReleaseEvent(event)

    def enterEvent(self, event):
        self._hovered = True
        self._updateStyle()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._updateStyle()
        super().leaveEvent(event)

    def sizeHint(self):
        return QtCore.QSize(20, 20)

class HoverButton(QtWidgets.QPushButton):
    def __init__(self, normal_icon, hover_icon, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.normal_icon = QtGui.QIcon(normal_icon)
        self.hover_icon = QtGui.QIcon(hover_icon)
        self.setIcon(self.normal_icon)
        self.setIconSize(QtCore.QSize(16, 16))

    def enterEvent(self, event):
        self.setIcon(self.hover_icon)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setIcon(self.normal_icon)
        super().leaveEvent(event)