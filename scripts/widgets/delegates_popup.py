from PySide2 import QtCore, QtGui, QtWidgets

from enums import HeaderColumn

from . import styles, ui_utils
from .listpopup_widget import ListPopupWidget
from .slider_widget import SliderPopupWidget


class LineEditDelegate(QtWidgets.QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        line_edit = QtWidgets.QLineEdit(parent)
        line_edit.setStyleSheet(
            styles.line_edit_style(
                background=styles.FIELD_BG_COLOR,
                padding="2px 6px",
            )
        )
        return line_edit

    def setEditorData(self, editor, index):
        model = index.model()
        if isinstance(model, QtCore.QSortFilterProxyModel):
            source_index = model.mapToSource(index)
            text = model.sourceModel().data(source_index, QtCore.Qt.EditRole)
        else:
            text = model.data(index, QtCore.Qt.EditRole)

        editor.setText(str(text))

    def setModelData(self, editor, model, index):
        if isinstance(model, QtCore.QSortFilterProxyModel):
            source_index = model.mapToSource(index)
            source_model = model.sourceModel()
            source_model.setData(source_index, editor.text(), QtCore.Qt.EditRole)
        else:
            model.setData(index, editor.text(), QtCore.Qt.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        text = index.model().data(index, QtCore.Qt.DisplayRole)
        font_metrics = editor.fontMetrics()
        text_width = font_metrics.horizontalAdvance(str(text)) + 10
        min_width = 55
        width = max(text_width, min_width)

        vertical_margin = 4
        editor.setGeometry(
            option.rect.x(),
            option.rect.y() + vertical_margin // 2,
            width,
            option.rect.height() - vertical_margin,
        )

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(26)
        return size


class SliderPopupDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._parent = parent

    def paint(self, painter, option, index):
        if option.state & QtWidgets.QStyle.State_HasFocus:
            option.state &= ~QtWidgets.QStyle.State_HasFocus

        value = index.data(QtCore.Qt.DisplayRole)
        if isinstance(value, float):
            style_option = QtWidgets.QStyleOptionViewItem(option)
            self.initStyleOption(style_option, index)
            style_option.text = f"{value:.2f}"

            is_hovered = False
            if option.state & QtWidgets.QStyle.State_MouseOver:
                view = option.widget
                if view is not None:
                    mouse_pos = view.viewport().mapFromGlobal(QtGui.QCursor.pos())
                    hovered_index = view.indexAt(mouse_pos)
                    is_hovered = (
                        hovered_index.column() == index.column()
                        and hovered_index.row() == index.row()
                    )

            if is_hovered:
                style_option.palette.setColor(QtGui.QPalette.Text, QtGui.QColor("#55AAC3"))

            QtWidgets.QApplication.style().drawControl(
                QtWidgets.QStyle.CE_ItemViewItem, style_option, painter
            )
        else:
            super().paint(painter, option, index)

    def createEditor(self, parent, option, index):
        if isinstance(index.model(), QtCore.QSortFilterProxyModel):
            source_index = index.model().mapToSource(index)
        else:
            source_index = index

        initial_value = source_index.data(QtCore.Qt.EditRole)
        try:
            initial_value = float(initial_value)
        except (TypeError, ValueError):
            initial_value = 0.0

        col_config = {
            HeaderColumn.OFFSET: ("Offset", 1.0, 1.0),
            HeaderColumn.CURVATURE: ("Curvature", 5.0, 1.0),
            HeaderColumn.PRECISION: ("Precision", 100.0, 1.0),
        }
        label, max_value, default_value = col_config.get(source_index.column(), ("", 1.0, 1.0))

        popup = SliderPopupWidget(parent, 0.0, max_value, initial_value, label=label, defaultValue=default_value)

        model = source_index.model()
        pre_drag = [initial_value]
        final_value = [initial_value]
        is_dragging = [False]

        def onSliderPressed(preDragValue):
            is_dragging[0] = True
            pre_drag[0] = preDragValue

        def onValueChanged(value):
            final_value[0] = value
            model.setData(source_index, value, QtCore.Qt.EditRole, live=True)

        def onSliderReleased():
            rounded_final_value = round(final_value[0], 3)
            model.setData(source_index, pre_drag[0], QtCore.Qt.EditRole, live=True)
            model.setData(source_index, rounded_final_value, QtCore.Qt.EditRole, live=False)
            is_dragging[0] = False

        def onReset():
            pre_drag[0] = source_index.data(QtCore.Qt.EditRole) or initial_value
            model.setData(source_index, pre_drag[0], QtCore.Qt.EditRole, live=True)
            model.setData(source_index, default_value, QtCore.Qt.EditRole, live=False)
            popup.setValue(default_value)

        def onDataChanged(topLeft, bottomRight, roles):
            if is_dragging[0]:
                return
            if topLeft.row() == source_index.row() and topLeft.column() == source_index.column():
                new_value = source_index.data(QtCore.Qt.EditRole)
                if new_value is not None:
                    popup.setValue(float(new_value))

        model.dataChanged.connect(onDataChanged)

        def disconnectDataChanged():
            try:
                model.dataChanged.disconnect(onDataChanged)
            except (RuntimeError, TypeError):
                pass

        popup.destroyed.connect(disconnectDataChanged)

        popup.sliderPressed.connect(onSliderPressed)
        popup.sliderReleased.connect(onSliderReleased)
        popup.valueChanged.connect(onValueChanged)
        popup.resetBtn.clicked.disconnect()
        popup.resetBtn.clicked.connect(onReset)

        anchor_rect_global = ui_utils.global_rect_from_widget_rect(parent, option.rect)
        popup.move(ui_utils.anchored_popup_pos(anchor_rect_global, popup.size(), gap=4))
        popup.show()
        return None


class ListPopupDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)

    def _getSourceIndexAndParent(self, index):
        """Map a proxy index to source and return its parent item."""
        if isinstance(index.model(), QtCore.QSortFilterProxyModel):
            source_index = index.model().mapToSource(index)
        else:
            source_index = index
        parent_index = source_index.parent()
        parent_item = parent_index.internalPointer() if parent_index.isValid() else None
        return source_index, parent_item

    def paint(self, painter, option, index):
        if option.state & QtWidgets.QStyle.State_HasFocus:
            option.state &= ~QtWidgets.QStyle.State_HasFocus

        QtWidgets.QApplication.style().drawPrimitive(
            QtWidgets.QStyle.PE_PanelItemViewItem, option, painter
        )

        value = index.data(QtCore.Qt.DisplayRole)
        if value is None:
            return

        is_none = value == "NONE"

        is_hovered = False
        if option.state & QtWidgets.QStyle.State_MouseOver:
            view = option.widget
            if view is not None:
                mouse_pos = view.viewport().mapFromGlobal(QtGui.QCursor.pos())
                hovered_index = view.indexAt(mouse_pos)
                is_hovered = (
                    hovered_index.column() == index.column()
                    and hovered_index.row() == index.row()
                )

        source_index, parent_item = self._getSourceIndexAndParent(index)
        surfaces = parent_item.getAllSurfaces()
        has_surfaces = any(key != "NONE" for key in surfaces)
        rect = option.rect

        text_color = QtGui.QColor(option.palette.color(QtGui.QPalette.Text))
        if is_none:
            text_color.setAlpha(80)
        painter.save()
        painter.setPen(text_color)
        text_rect = rect.adjusted(6, 0, -12 if has_surfaces else -4, 0)
        painter.drawText(text_rect, QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, str(value))
        painter.restore()

        if has_surfaces:
            arrow_color = QtGui.QColor("#55AAC3") if is_hovered else QtGui.QColor("#666666" if is_none else "#888888")
            triangle_width = 6
            triangle_height = 4
            center_x = rect.right() - 2
            center_y = rect.center().y()
            points = [
                QtCore.QPointF(center_x - triangle_width / 2, center_y - triangle_height / 2),
                QtCore.QPointF(center_x + triangle_width / 2, center_y - triangle_height / 2),
                QtCore.QPointF(center_x, center_y + triangle_height / 2),
            ]
            painter.save()
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            painter.setBrush(QtGui.QBrush(arrow_color))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawPolygon(QtGui.QPolygonF(points))
            painter.restore()

    def createEditor(self, parent, option, index):
        source_index, parent_item = self._getSourceIndexAndParent(index)
        current_value = source_index.data(QtCore.Qt.DisplayRole)

        surfaces = ["NONE"]
        if parent_item and parent_item.builder():
            surfaces_dict = parent_item.builder().getAllInputTargetSurfaces()
            surfaces = list(surfaces_dict.keys())
            item = source_index.internalPointer()
            actual_surface = parent_item.builder().getSurfaceDriver(item.name()) or "NONE"
            if actual_surface != current_value:
                source_index.model().updateColumnData(item, HeaderColumn.SURFACE, actual_surface)
                current_value = actual_surface

        dummy_editor = QtWidgets.QWidget(parent)
        dummy_editor.setFixedSize(0, 0)
        dummy_editor.setVisible(False)

        popup = ListPopupWidget(surfaces, parent=parent, currentValue=current_value)
        popup.valueSelected.connect(
            lambda value: source_index.model().setData(source_index, value, QtCore.Qt.EditRole)
        )
        popup.valueSelected.connect(
            lambda: self.commitData.emit(dummy_editor)
        )

        anchor_rect_global = ui_utils.global_rect_from_widget_rect(parent, option.rect)
        popup.showAt(anchor_rect_global, option.rect.width())
        return dummy_editor
