from PySide2 import QtWidgets, QtCore,QtGui
from .search_widget import SearchWidget
from .styles import TOOL_BUTTON_STYLE, ICON_BUTTON_STYLE, iconPath

class IconButton(QtWidgets.QPushButton):
    def __init__(self, normalIcon, hoverIcon=None, pressedIcon=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.normalIcon = QtGui.QIcon(normalIcon)
        self.hoverIcon = QtGui.QIcon(hoverIcon) if hoverIcon else self.normalIcon
        self.pressedIcon = QtGui.QIcon(pressedIcon) if pressedIcon else self.hoverIcon
        self.setIcon(self.normalIcon)
        self.setIconSize(QtCore.QSize(20, 20))
        self.setFixedSize(20, 20)
        self.setEnabled(False)
        self.setStyleSheet(ICON_BUTTON_STYLE)

    def enterEvent(self, event):
        if not self.isEnabled():
            return
        self.setIcon(self.pressedIcon if self.isDown() else self.hoverIcon)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self.isEnabled():
            return
        self.setIcon(self.normalIcon)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if not self.isEnabled():
            return
        self.setIcon(self.pressedIcon)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if not self.isEnabled():
            return
        self.setIcon(self.hoverIcon if self.rect().contains(event.pos()) else self.normalIcon)
        super().mouseReleaseEvent(event)


class ToolButton(QtWidgets.QPushButton):
    def __init__(self, normal_icon, hover_icon=None, pressed_icon=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.normal_icon = QtGui.QIcon(normal_icon)
        self.hover_icon = QtGui.QIcon(hover_icon) if hover_icon else self.normal_icon
        self.pressed_icon = QtGui.QIcon(pressed_icon) if pressed_icon else self.normal_icon

        self.setIcon(self.normal_icon)
        self.setIconSize(QtCore.QSize(15, 15))
        self.setEnabled(False)
        self.setFlat(True)

        self.setStyleSheet(TOOL_BUTTON_STYLE)


class TopBarWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.createBtn = ToolButton(iconPath("create.svg"))
        self.addTargetBtn = ToolButton(iconPath("add.svg"))
        self.addSurfaceBtn = ToolButton(iconPath("surface.svg"))
        self.paintBtn = ToolButton(iconPath("paintNormal.svg"))
        self.paintBtn.setIconSize(QtCore.QSize(18, 18))

        self.rebindBtn = IconButton(
            iconPath("rebindNormal.svg"),
            iconPath("rebindHover.svg"),
            iconPath("rebindPressed.svg"),
        )

        self.dataBtn = IconButton(
            iconPath("dataNormal.svg"),
            iconPath("dataHover.svg"),
            iconPath("dataPressed.svg"),
        )

        self.deleteBtn = IconButton(
            iconPath("deleteNormal.svg"),
            iconPath("deleteHover.svg"),
            iconPath("deletePressed.svg"),
        )

        self.createBtn.setText("Create InterpBlendShape")
        self.addTargetBtn.setText("Add Target")
        self.addSurfaceBtn.setText("Add Surface")
        self.paintBtn.setText("Paint Tool")

        # tooltip
        self.createBtn.setToolTip("Create an interpBlendShape deformer for the selected object.")
        self.addTargetBtn.setToolTip("Add selected objects as targets.")
        self.addSurfaceBtn.setToolTip("Add selected surfaces to the deformer.")
        self.paintBtn.setToolTip("Open the Paint Weights Tool.")

        self.dataBtn.setToolTip("Open the weight editor UI.")
        self.rebindBtn.setToolTip("Rebind and cache all targets.")
        self.deleteBtn.setToolTip("Delete the selected deformer or target.")

        # always enable
        self.dataBtn.setEnabled(True)
        self.createBtn.setEnabled(True)

        # Add search widget
        self.searchWidget = SearchWidget()

        # Add toolbar buttons to layout
        for btn in [
            self.createBtn,
            self.addTargetBtn,
            self.addSurfaceBtn,
            self.paintBtn,
            self.searchWidget,
            self.dataBtn,
            self.rebindBtn,
            self.deleteBtn,
        ]:
            layout.addWidget(btn)

    def updateTopbarState(self, hasSelection: bool):
        """Enable/disable buttons based on current selection state."""
        for btn in [self.addTargetBtn,
                    self.addSurfaceBtn,
                    self.paintBtn,
                    self.rebindBtn]:
            btn.setEnabled(hasSelection)