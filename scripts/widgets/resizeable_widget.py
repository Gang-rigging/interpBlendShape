from PySide2 import QtCore, QtGui, QtWidgets

class ResizableMixin:
    EDGE_MARGIN = 8

    def _initResizable(self):
        self._pressed = False
        self._resizeDir = None
        self.oldPos = QtCore.QPoint()

    def _installEvent(self):
        self.installEventFilter(self)
        self.setMouseTracking(True)
        for w in self.findChildren(QtWidgets.QWidget):
            w.installEventFilter(self)
            w.setMouseTracking(True)

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.MouseMove:
            # Only update cursor — never reposition child widgets
            self._updateCursor()
        return super().eventFilter(obj, event)

    def _updateCursor(self):
        pos = self.mapFromGlobal(QtGui.QCursor.pos())
        if not self.rect().contains(pos):
            return
        cursor_map = {
            'left': QtCore.Qt.SizeHorCursor,
            'right': QtCore.Qt.SizeHorCursor,
            'top': QtCore.Qt.SizeVerCursor,
            'bottom': QtCore.Qt.SizeVerCursor,
            'top_left': QtCore.Qt.SizeFDiagCursor,
            'bottom_right': QtCore.Qt.SizeFDiagCursor,
            'top_right': QtCore.Qt.SizeBDiagCursor,
            'bottom_left': QtCore.Qt.SizeBDiagCursor,
        }
        direction = self._getResizeDirection(pos)
        self.setCursor(cursor_map.get(direction, QtCore.Qt.ArrowCursor))

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.oldPos = event.globalPos()
            self._pressed = True
            self._resizeDir = self._getResizeDirection(event.pos())
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._pressed = False
        self._resizeDir = None
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        if self._pressed:
            if self._resizeDir:
                self._resizeWindow(event.globalPos())
            else:
                delta = event.globalPos() - self.oldPos
                self.move(self.pos() + delta)
                self.oldPos = event.globalPos()
            event.accept()
        else:
            self._updateCursor()
        super().mouseMoveEvent(event)

    def _getResizeDirection(self, pos):
        margin, x, y, w, h = self.EDGE_MARGIN, pos.x(), pos.y(), self.width(), self.height()
        left, right, top, bottom = x <= margin, x >= w - margin, y <= margin, y >= h - margin
        if top and left: return 'top_left'
        if top and right: return 'top_right'
        if bottom and left: return 'bottom_left'
        if bottom and right: return 'bottom_right'
        if left: return 'left'
        if right: return 'right'
        if top: return 'top'
        if bottom: return 'bottom'
        return None

    def _resizeWindow(self, globalPos):
        diff = globalPos - self.oldPos
        geo = self.geometry()
        minW, minH = self.minimumWidth(), self.minimumHeight()
        new_geo = QtCore.QRect(geo)

        if 'left' in self._resizeDir:
            newX = geo.x() + diff.x()
            newW = geo.width() - diff.x()
            if newW >= minW:
                new_geo.setX(newX)
                new_geo.setWidth(newW)
        elif 'right' in self._resizeDir:
            newW = geo.width() + diff.x()
            new_geo.setWidth(max(newW, minW))

        if 'top' in self._resizeDir:
            newY = geo.y() + diff.y()
            newH = geo.height() - diff.y()
            if newH >= minH:
                new_geo.setY(newY)
                new_geo.setHeight(newH)
        elif 'bottom' in self._resizeDir:
            newH = geo.height() + diff.y()
            new_geo.setHeight(max(newH, minH))

        self.setGeometry(new_geo)
        if 'left' in self._resizeDir or 'top' in self._resizeDir:
            self.oldPos = globalPos
        else:
            newX = globalPos.x() if 'right' in self._resizeDir else self.oldPos.x()
            newY = globalPos.y() if 'bottom' in self._resizeDir else self.oldPos.y()
            self.oldPos = QtCore.QPoint(newX, newY)
