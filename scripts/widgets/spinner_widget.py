from PySide2 import QtWidgets, QtCore, QtGui

class SpinnerWidget(QtWidgets.QWidget):
    def __init__(self, parent=None, radius=20, line_width=6, line_count=12, speed=100):
        super().__init__(parent)
        self.radius = radius
        self.line_width = line_width
        self.line_count = line_count
        self.angle = 0
        self.speed = speed
        self.setFixedSize(radius * 2 + 4, radius * 2 + 4)

        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.rotate)

    def start(self):
        self.timer.start(self.speed)
        self.show()

    def stop(self):
        self.timer.stop()
        self.hide()

    def rotate(self):
        self.angle = (self.angle + 30) % 360
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.setRenderHint(QtGui.QPainter.HighQualityAntialiasing, True)

        painter.translate(self.rect().center())
        painter.rotate(self.angle)

        for i in range(self.line_count):
            alpha = int(255 * (i + 1) / self.line_count)
            color = QtGui.QColor("#3498db")
            color.setAlpha(alpha)
            painter.setBrush(color)
            painter.setPen(QtCore.Qt.NoPen)

            x = 0
            y = -self.radius
            radius = self.line_width / 2.0

            path = QtGui.QPainterPath()
            path.addEllipse(QtCore.QPointF(x, y), radius, radius)
            painter.drawPath(path)
            painter.rotate(360 / self.line_count)

    def sizeHint(self):
        return QtCore.QSize(100, 100)
