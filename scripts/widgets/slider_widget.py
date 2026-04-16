from PySide2 import QtCore, QtGui, QtWidgets
from enums import ItemType
from . import styles
import math
import maya.cmds as cmds

class Slider(QtWidgets.QSlider):
    def __init__(self, orientation=QtCore.Qt.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.markerValues = []  # actual values
        self.minValue = 0.0
        self.maxValue = 1.0

        self.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 4px;
                background: #1e1e1e;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #55AAC3;
                width: 7px;
                margin: -4px 0px;
                border-radius: 2px;
            }
            QSlider::handle:horizontal:hover {
                background: #62C3DF;
            }
            QSlider::handle:horizontal:pressed {
                background: #4890A5;
            }
            QSlider::sub-page:horizontal {
                background: #55AAC3;
                border-radius: 3px;
            }
        """)

    def setValueRange(self, minValue, maxValue):
        self.minValue = minValue
        self.maxValue = maxValue
        self.update()

    def setMarkersFromValues(self, values):
        self.markerValues = values
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)

        if not self.markerValues or self.maxValue == self.minValue:
            return

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        pen = QtGui.QPen(QtGui.QColor(255, 230, 100, 180))
        pen.setWidth(2)
        painter.setPen(pen)

        opt = QtWidgets.QStyleOptionSlider()
        self.initStyleOption(opt)

        groove_rect = self.style().subControlRect(
            QtWidgets.QStyle.CC_Slider, opt, QtWidgets.QStyle.SC_SliderGroove, self
        )

        for val in self.markerValues:
            norm = (val - self.minValue) / (self.maxValue - self.minValue)
            if not 0.0 <= norm <= 1.0:
                continue

            if self.orientation() == QtCore.Qt.Horizontal:
                x = groove_rect.left() + groove_rect.width() * norm
                y1 = groove_rect.top() - 4
                y2 = groove_rect.bottom() + 3.5
                painter.drawLine(QtCore.QPointF(x, y1), QtCore.QPointF(x, y2))
            else:
                y = groove_rect.bottom() - groove_rect.height() * norm
                x1 = groove_rect.left() - 4
                x2 = groove_rect.right() + 4
                painter.drawLine(QtCore.QPointF(x1, y), QtCore.QPointF(x2, y))

        painter.end()

    def setActive(self, locked=False):
        self.setEnabled(not locked)

    def setLocked(self, locked=False, connected=False):
        self.setEnabled(not (locked or connected))

class FloatLineEdit(QtWidgets.QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(55)
        self.setAlignment(QtCore.Qt.AlignLeft)

        self._isLocked           = False
        self._hasKeyed           = False
        self._hasSDK             = False
        self._isConnected        = False
        self._isActive           = True
        self._isKeyOnCurrentTime = False

        self.minValue = -10.0
        self.maxValue = 10.0

        validator = QtGui.QDoubleValidator(-9999, 9999, 3, self)
        validator.setNotation(QtGui.QDoubleValidator.StandardNotation)
        self.setValidator(validator)

        self.refreshStyle()

    def floatValue(self):
        try:
            return round(float(self.text()), 3)
        except ValueError:
            return 0.0

    def setFloatValue(self, value: float):
        clamped = max(self.minValue, min(self.maxValue, value))
        self.setText(f"{clamped:.3f}")

    def setActive(self, active: bool):
        self._isActive = active
        self.refreshStyle()

    def setLocked(self, locked=False, connected=False):
        self._isLocked = locked
        self._isConnected = connected
        self.setEnabled(not (locked or connected))

    def setKeyed(self, hasKey: bool, hasSDK: bool, keyOnCurrent: bool):
        """
        Update keying state.

        :param hasKeyed: Whether the item is generally keyed.
        :param isKeyOnCurrentTime: Whether it has a keyframe on the current time/frame.
        """
        self._hasKeyed = hasKey
        self._hasSDK = hasSDK
        self._isKeyOnCurrentTime = keyOnCurrent

    def refreshStyle(self):
        """
        Update the QLineEdit stylesheet based on the item's state.
        Priority: locked > connected > keyed+SDK > keyed-only > SDK-only > inactive.
        """
        # Define style rules in priority order
        rules = [
            (self._isLocked, {"bg": "#5C6874", "fg": "#000000"}),  # locked
            (self._isConnected, {"bg": "#F1F1A5", "fg": "#000000"}),  # connected
            (self._hasKeyed and self._hasSDK, {"bg": "#F1F1A5", "fg": "#000000"}),  # keyed+SDK
            (self._hasSDK, {"bg": "#5099DA", "fg": "#000000"}),  # SDK-only
            (self._hasKeyed, {"bg": "#DD727A", "fg": "#000000"}),  # keyed-only
        ]

        # Override keyed-only red if key is on current time
        if self._hasKeyed and not self._hasSDK and self._isKeyOnCurrentTime:
            rules.insert(4, (True, {"bg": "#CC2829", "fg": "#000000"}))

        # Inactive state always beat everything:
        if not self._isActive:
            bg, fg = "#444", None
        else:
            # Find first matching rule
            for cond, style in rules:
                if cond:
                    bg = style["bg"]
                    fg = style["fg"]
                    break
            else:
                bg, fg = "transparent", None

        # Build stylesheet
        parts = [
            "border-radius: 2px;",
            "padding: 2px 4px;",
        ]
        if bg and bg != "transparent":
            parts.append(f"background-color: {bg};")
        if fg:
            parts.append(f"color: {fg};")

        style = f"""
        QLineEdit {{
            {' '.join(parts)}
        }}
        QLineEdit:focus {{
            border: 1.3px solid #4682B4;
        }}
        """
        self.setStyleSheet(style)

    def keyPressEvent(self, event):
        # Override keyPressEvent to manually emit the signal because
        # the Enter key propagates to Maya automatically.
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            event.accept()
            self.editingFinished.emit()
        else:
            super().keyPressEvent(event)


class SliderWeightWidget(QtWidgets.QWidget):
    def __init__(self, positions=[], itemType=None, parent=None):
        super().__init__(parent)
        self.itemType = itemType
        self.sliderSteps = 10000
        self.positions = positions  # actual values like [1.0, 2.0]
        self.minVal = 0.0
        self.maxVal = 1.0

        self.layout = QtWidgets.QHBoxLayout(self)
        self.layout.setContentsMargins(2, 3, 2, 3)
        self.layout.setSpacing(4)
        self.slider = Slider(QtCore.Qt.Horizontal)
        self.slider.setRange(0, self.sliderSteps)

        self.slider.setValueRange(self.minVal, self.maxVal)
        self.slider.setMarkersFromValues(self.positions)

        self.sliderPlaceholder = QtWidgets.QWidget()
        self.sliderPlaceholder.setFixedSize(self.slider.sizeHint())  # Same size as slider

        # Create a container widget to hold the stacked layout
        self.sliderContainer = QtWidgets.QWidget()
        self.sliderStack = QtWidgets.QStackedLayout(self.sliderContainer)
        self.sliderStack.setContentsMargins(0, 0, 0, 0)
        self.sliderStack.setSpacing(0)
        self.sliderStack.addWidget(self.slider)
        self.sliderStack.addWidget(self.sliderPlaceholder)

        self.lineEdit = FloatLineEdit()
        self.lineEdit.setActive(True)
        self.lineEdit.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.lineEdit.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.lineEdit.customContextMenuRequested.connect(self.forwardContextMenuToParentTree)

        # Add widgets to the main layout
        self.layout.addWidget(self.lineEdit)
        self.layout.addWidget(self.sliderContainer)
        self.slider.valueChanged.connect(self.onSliderChanged)
        self.lineEdit.editingFinished.connect(self.onLineEditChanged)
        self.lineEdit.returnPressed.connect(self.lineEdit.clearFocus)
        if self.itemType == ItemType.INBETWEEN:
            self.setSliderVisible(False)

    def forwardContextMenuToParentTree(self, pos):
        tree = self.parentTreeView()
        if tree:
            globalPos = self.lineEdit.mapToGlobal(pos)
            viewPos = tree.viewport().mapFromGlobal(globalPos)
            # simulate right-click at that point in the tree view
            tree.menuHandler.showContextMenu(viewPos)

    def parentTreeView(self):
        # walk up the parent hierarchy to find the QTreeView
        parent = self.parent()
        while parent and not isinstance(parent, QtWidgets.QTreeView):
            parent = parent.parent()
        return parent

    def updateSliderRange(self):
        self.slider.setValueRange(self.minVal, self.maxVal)
        self.slider.setMarkersFromValues(self.positions)

    def floatToInt(self, floatVal):
        normalized = (floatVal - self.minVal) / (self.maxVal - self.minVal)
        return int(round(normalized * self.sliderSteps))

    def intToFloat(self, intVal):
        normalized = intVal / self.sliderSteps
        result = self.minVal + normalized * (self.maxVal - self.minVal)
        return round(result, 3)

    def onSliderChanged(self, intVal):
        floatVal = self.intToFloat(intVal)
        self.lineEdit.blockSignals(True)
        self.lineEdit.setText(f"{floatVal:.3f}")
        self.lineEdit.blockSignals(False)

    def onLineEditChanged(self):
        try:
            floatVal = float(self.lineEdit.text())

            if self.itemType == ItemType.PARENT:
                if floatVal < self.minVal:
                    self.minVal = max(floatVal * 2, -2)
                elif floatVal > self.maxVal:
                    self.maxVal = min(floatVal * 2, 2)

            elif self.itemType == ItemType.CHILD:
                if floatVal < self.minVal:
                    self.minVal = max(floatVal * 2, -10.0)
                elif floatVal > self.maxVal:
                    self.maxVal = min(floatVal * 2, 10.0)

            self.slider.blockSignals(True)
            self.slider.setValue(self.floatToInt(floatVal))
            self.slider.blockSignals(False)
            self.updateSliderRange()
        except ValueError:
            self.onSliderChanged(self.slider.value())

    def value(self):
        return self.intToFloat(self.slider.value())

    def setValue(self, floatVal):
        self.minVal = min(self.minVal, floatVal)
        self.maxVal = max(self.maxVal, floatVal)
        self.updateSliderRange()
        self.slider.setValue(self.floatToInt(floatVal))
        clamped = round(max(self.lineEdit.minValue, min(self.lineEdit.maxValue, floatVal)), 3)
        self.lineEdit.blockSignals(True)
        self.lineEdit.setText(f"{clamped:.3f}")
        self.lineEdit.blockSignals(False)

    def setSliderVisible(self, visible: bool):
        self.lineEdit.setActive(visible)
        self.slider.setVisible(visible)
        self.sliderStack.setCurrentIndex(0 if visible else 1)

    def inbetweenSliderRange(self, value: float) -> float:
        epsilon = 1e-6
        if value > self.maxVal:
            self.maxVal = float(math.ceil(value - epsilon))

        self.updateSliderRange()

    def setLockStatus(self, locked=False, connected=False):
        self.lineEdit.setLocked(locked, connected)
        self.slider.setLocked(locked, connected)

class SliderEventFilter(QtCore.QObject):
    def __init__(self, slider, callback):
        super().__init__(slider)
        self._slider   = slider
        self._callback = callback

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.MouseButtonPress:
            if event.button() == QtCore.Qt.LeftButton:
                self._callback(event)
        return False

class SliderPopupWidget(QtWidgets.QWidget):
    valueChanged = QtCore.Signal(float)
    sliderPressed = QtCore.Signal(float)
    sliderReleased = QtCore.Signal()

    def __init__(self, parent=None, minValue=0.0, maxValue=1.0, initialValue=0.5, label="", defaultValue=1.0):
        super().__init__(parent, QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Tool)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setWindowOpacity(0.0)

        self._min          = float(minValue)
        self._max          = float(maxValue)
        self._range        = self._max - self._min
        self._label        = label
        self._defaultValue = float(defaultValue)

        self._buildUI()
        self.setValue(initialValue)
        self._fadeIn()
        self.resize(120, 60)
        QtWidgets.QApplication.instance().installEventFilter(self)

        self._sliderFilter = SliderEventFilter(self.slider, self._onSliderClick)
        self.slider.installEventFilter(self._sliderFilter)

    def _onSliderClick(self, event):
        currentValue = self._min + (self.slider.value() / 1000.0) * self._range
        self.sliderPressed.emit(currentValue)
        value = QtWidgets.QStyle.sliderValueFromPosition(
            self.slider.minimum(), self.slider.maximum(),
            event.x(), self.slider.width()
        )
        self.slider.setValue(value)

    def _buildUI(self):
        self.frame = QtWidgets.QFrame(self)
        self.frame.setObjectName("popupFrame")
        self.frame.setFixedHeight(60)
        self.frame.setStyleSheet(
            styles.popup_frame_style(alpha=250)
            + """
            QSlider::groove:horizontal {{
                border: none;
                height: 4px;
                background: {panel};
                border-radius: 2px;
            }}
            QSlider::sub-page:horizontal {{
                background: {accent};
                border-radius: 2px;
            }}
            QSlider::add-page:horizontal {{
                background: {panel};
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {accent};
                width: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }}
            QSlider::handle:horizontal:hover {{
                background: {accent_hover};
            }}
            QSlider::handle:horizontal:pressed {{
                background: {accent_pressed};
            }}
            QPushButton {{
                background: {panel};
                color: {muted};
                border: none;
                border-radius: 3px;
                padding: 1px 5px;
                font-size: 9px;
            }}
            QPushButton:hover {{
                background: #3a3a3a;
                color: {muted_hover};
            }}
        """.format(
                panel=styles.POPUP_PANEL_COLOR,
                accent=styles.ACCENT_COLOR,
                accent_hover=styles.ACCENT_HOVER_COLOR,
                accent_pressed=styles.ACCENT_PRESSED_COLOR,
                muted=styles.POPUP_MUTED_TEXT_COLOR,
                muted_hover=styles.POPUP_MUTED_TEXT_HOVER_COLOR,
            )
        )

        # Top row: label + value + reset
        self.labelWidget = QtWidgets.QLabel(self._label)
        self.labelWidget.setStyleSheet(
            f"color: {styles.POPUP_MUTED_TEXT_COLOR}; font-size: 10px; background: transparent;"
        )

        # Replace valueLabel QLabel with QLineEdit
        self.valueLabel = QtWidgets.QLineEdit("0.000")
        self.valueLabel.setStyleSheet("""
            QLineEdit {{
                color: {accent};
                font-size: 11px;
                font-weight: bold;
                background: transparent;
                border: none;
                padding: 0px;
            }}
            QLineEdit:focus {{
                background: #222;
                border: 1px solid {accent};
                border-radius: 3px;
                padding: 0px 2px;
            }}
        """.format(accent=styles.ACCENT_COLOR))
        self.valueLabel.setAlignment(QtCore.Qt.AlignRight)
        self.valueLabel.setFixedWidth(40)
        self.valueLabel.setReadOnly(True)
        self.valueLabel.mouseDoubleClickEvent = self._onValueDoubleClick
        self.valueLabel.editingFinished.connect(self._onValueEdited)

        self.resetBtn = QtWidgets.QPushButton("reset")
        self.resetBtn.setFixedSize(32, 14)
        self.resetBtn.clicked.connect(self._onReset)

        topLayout = QtWidgets.QHBoxLayout()
        topLayout.setContentsMargins(0, 0, 0, 0)
        topLayout.setSpacing(4)
        topLayout.addWidget(self.labelWidget)
        topLayout.addStretch()
        topLayout.addWidget(self.valueLabel)
        topLayout.addWidget(self.resetBtn)

        # Slider
        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider.setMinimumHeight(16)
        self.slider.setRange(0, 1000)
        self.slider.sliderPressed.connect(self._onSliderPressed)
        self.slider.valueChanged.connect(self._onSliderChanged)

        innerLayout = QtWidgets.QVBoxLayout(self.frame)
        innerLayout.setContentsMargins(10, 6, 10, 6)
        innerLayout.setSpacing(4)
        innerLayout.addLayout(topLayout)
        innerLayout.addWidget(self.slider)

        outerLayout = QtWidgets.QVBoxLayout(self)
        outerLayout.setContentsMargins(0, 0, 0, 0)
        outerLayout.addWidget(self.frame)

        self.slider.sliderReleased.connect(lambda: self.sliderReleased.emit())

    def _onSliderPressed(self):
        if not self.valueLabel.isReadOnly():
            self._onValueEdited()
        self.valueLabel.setReadOnly(True)
        self.slider.setFocus()

    def _onValueDoubleClick(self, event):
        """Enable editing on double click."""
        self.valueLabel.setReadOnly(False)
        self.valueLabel.selectAll()
        self.valueLabel.setFocus()

    def _onValueEdited(self):
        """Commit typed value and return to read-only."""
        try:
            value = float(self.valueLabel.text())
            value = max(self._min, min(self._max, value))
            self.setValue(value)
            self.valueChanged.emit(value)
        except ValueError:
            # Restore current slider value if invalid input
            current = self._min + (self.slider.value() / 1000.0) * self._range
            self.valueLabel.setText(f"{current:.3f}")
        self.valueLabel.setReadOnly(True)

    def _onSliderChanged(self, sliderValue):
        floatValue = self._min + (sliderValue / 1000.0) * self._range
        if self.valueLabel.isReadOnly():
            self.valueLabel.setText(f"{floatValue:.2f}")
        self.valueChanged.emit(floatValue)

    def setValue(self, value):
        value = max(self._min, min(self._max, float(value)))
        sliderValue = int(round((value - self._min) / self._range * 1000))
        self.slider.blockSignals(True)
        self.slider.setValue(sliderValue)
        self.slider.blockSignals(False)
        self.valueLabel.setText(f"{value:.2f}")

    def _onReset(self):
        self.setValue(self._defaultValue)
        self.valueChanged.emit(self._defaultValue)

    def _fadeIn(self):
        self.anim = QtCore.QPropertyAnimation(self, b"windowOpacity")
        self.anim.setDuration(200)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.setEasingCurve(QtCore.QEasingCurve.InOutQuad)
        self.anim.start()

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.MouseButtonPress:
            if not self.rect().contains(self.mapFromGlobal(QtGui.QCursor.pos())):
                self.close()
        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        QtWidgets.QApplication.instance().removeEventFilter(self)
        super().closeEvent(event)

