from PySide2 import QtCore, QtGui, QtWidgets

from . import styles


class ShapeEditComboBox(QtWidgets.QComboBox):
    def paintEvent(self, event):
        super().paintEvent(event)

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtGui.QColor(styles.TEXT_COLOR))

        rect = self.rect()
        arrowCenterX = rect.right() - 11
        arrowCenterY = rect.center().y() + 1
        triangle = QtGui.QPolygonF([
            QtCore.QPointF(arrowCenterX - 4, arrowCenterY - 2),
            QtCore.QPointF(arrowCenterX + 4, arrowCenterY - 2),
            QtCore.QPointF(arrowCenterX, arrowCenterY + 3),
        ])
        painter.drawPolygon(triangle)


class ShapeEditOptionsPopup(QtWidgets.QWidget):
    optionsChanged = QtCore.Signal(dict)
    POPUP_BG = QtGui.QColor(*styles.POPUP_BG_RGBA)
    POPUP_BORDER = QtGui.QColor(styles.POPUP_BORDER_COLOR)

    AXIS_ITEMS = (
        ("Object X", "YZ"),
        ("Object Y", "XZ"),
        ("Object Z", "XY"),
    )
    DIRECTION_ITEMS = (
        ("-", False),
        ("+", True),
    )
    ASSOCIATION_ITEMS = (
        ("Closest Component", "closestComponent"),
        ("Closest Point", "closestPoint"),
        ("Closest UV (Global)", "closestUVGlobal"),
        ("Closest UV (Shell Center)", "closestUVShellCenter"),
    )

    def __init__(self, parent=None):
        super().__init__(parent, QtCore.Qt.FramelessWindowHint | QtCore.Qt.SubWindow)
        self.setObjectName("shapeEditOptionsPopup")
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, False)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self._cornerRadius = 8
        self.setMinimumWidth(208)
        self.setStyleSheet(f"""
            QWidget#shapeEditOptionsPopup {{
                background: transparent;
                border: none;
            }}
            QLabel#shapeEditOptionsLabel {{
                color: {styles.TEXT_COLOR};
                font-size: 11px;
                background: transparent;
            }}
            QComboBox {{
                min-height: 18px;
                padding: 0px 22px 0px 6px;
                background-color: {styles.POPUP_FIELD_COLOR};
                border: 1px solid {styles.POPUP_BORDER_COLOR};
                border-radius: 4px;
                color: {styles.TEXT_COLOR};
                font-size: 11px;
                selection-background-color: #5285A6;
            }}
            QComboBox:hover {{
                background-color: {styles.POPUP_FIELD_HOVER_COLOR};
            }}
            QComboBox:focus {{
                border: 1px solid #5285A6;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 18px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {styles.POPUP_PANEL_COLOR};
                color: {styles.TEXT_COLOR};
                selection-background-color: #5285A6;
                border: 1px solid {styles.POPUP_BORDER_COLOR};
                outline: none;
            }}
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(0)

        form = QtWidgets.QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(6)
        form.setLabelAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

        self.directionCombo = ShapeEditComboBox(self)
        self.axisCombo = ShapeEditComboBox(self)
        self.associationCombo = ShapeEditComboBox(self)

        for label, value in self.DIRECTION_ITEMS:
            self.directionCombo.addItem(label, value)
        for label, value in self.AXIS_ITEMS:
            self.axisCombo.addItem(label, value)
        for label, value in self.ASSOCIATION_ITEMS:
            self.associationCombo.addItem(label, value)

        form.addRow(self._createFormLabel("Mirror Direction"), self.directionCombo)
        form.addRow(self._createFormLabel("Symmetry Axis"), self.axisCombo)
        form.addRow(self._createFormLabel("Surface Match"), self.associationCombo)
        layout.addLayout(form)

        self.directionCombo.currentIndexChanged.connect(self._emitOptions)
        self.axisCombo.currentIndexChanged.connect(self._emitOptions)
        self.associationCombo.currentIndexChanged.connect(self._emitOptions)

    def setOptions(self, options):
        self._setComboValue(self.directionCombo, options.get("mirrorInverse", False))
        self._setComboValue(self.axisCombo, options.get("mirrorMode", "YZ"))
        self._setComboValue(self.associationCombo, options.get("surfaceAssociation", "closestPoint"))

    def options(self):
        return {
            "mirrorInverse": bool(self.directionCombo.currentData()),
            "mirrorMode": str(self.axisCombo.currentData()),
            "surfaceAssociation": str(self.associationCombo.currentData()),
        }

    def _setComboValue(self, combo, value):
        if combo is self.associationCombo and value == "closestUV":
            value = "closestUVGlobal"
        block = combo.blockSignals(True)
        try:
            index = combo.findData(value)
            combo.setCurrentIndex(index if index >= 0 else 0)
        finally:
            combo.blockSignals(block)

    def _emitOptions(self, *_):
        self.optionsChanged.emit(self.options())

    def _createFormLabel(self, text):
        label = QtWidgets.QLabel(text, self)
        label.setObjectName("shapeEditOptionsLabel")
        return label

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setPen(QtGui.QPen(self.POPUP_BORDER, 1))
        painter.setBrush(self.POPUP_BG)
        rect = QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.drawRoundedRect(rect, self._cornerRadius, self._cornerRadius)

    def showEvent(self, event):
        super().showEvent(event)
        QtWidgets.QApplication.instance().installEventFilter(self)

    def hideEvent(self, event):
        app = QtWidgets.QApplication.instance()
        if app:
            app.removeEventFilter(self)
        super().hideEvent(event)

    def eventFilter(self, obj, event):
        if not self.isVisible():
            return False

        if event.type() == QtCore.QEvent.MouseButtonPress:
            activePopup = QtWidgets.QApplication.activePopupWidget()
            if activePopup is not None:
                return False

            localPos = self.mapFromGlobal(event.globalPos())
            if not self.rect().contains(localPos):
                self.hide()
        elif event.type() == QtCore.QEvent.KeyPress and event.key() == QtCore.Qt.Key_Escape:
            self.hide()

        return super().eventFilter(obj, event)
