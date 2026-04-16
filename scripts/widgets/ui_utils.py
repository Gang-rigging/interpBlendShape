from PySide2 import QtCore, QtWidgets


def screen_available_geometry(global_pos, margin=8):
    app = QtWidgets.QApplication.instance()
    if app is not None and hasattr(app, "screenAt"):
        screen = app.screenAt(global_pos)
        if screen is not None:
            return screen.availableGeometry().adjusted(margin, margin, -margin, -margin)

    desktop = QtWidgets.QApplication.desktop()
    if desktop is not None:
        screen_number = desktop.screenNumber(global_pos)
        return desktop.availableGeometry(screen_number).adjusted(margin, margin, -margin, -margin)

    return QtCore.QRect(global_pos.x() - 400, global_pos.y() - 300, 800, 600)


def clamp_point_in_rect(position, size, bounds):
    max_x = max(bounds.left(), bounds.right() - size.width() + 1)
    max_y = max(bounds.top(), bounds.bottom() - size.height() + 1)
    return QtCore.QPoint(
        min(max(position.x(), bounds.left()), max_x),
        min(max(position.y(), bounds.top()), max_y),
    )


def global_rect_from_widget_rect(widget, rect):
    return QtCore.QRect(widget.mapToGlobal(rect.topLeft()), rect.size())


def anchored_popup_pos(anchor_rect, popup_size, gap=4, prefer_below=True, margin=8):
    bounds = screen_available_geometry(anchor_rect.center(), margin=margin)

    below_y = anchor_rect.bottom() + 1 + gap
    above_y = anchor_rect.top() - popup_size.height() - gap
    y = below_y if prefer_below else above_y

    if prefer_below and y + popup_size.height() - 1 > bounds.bottom():
        y = above_y
    elif not prefer_below and y < bounds.top():
        y = below_y

    position = QtCore.QPoint(anchor_rect.left(), y)
    return clamp_point_in_rect(position, popup_size, bounds)
