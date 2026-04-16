from PySide2 import QtCore, QtWidgets

from .common_button import ToggleButtonWidget
from .checkbox_widget import CheckBoxWidget


class ToggleButtonDelegate(QtWidgets.QStyledItemDelegate):
    def paint(self, painter, option, index):
        if option.state & QtWidgets.QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        else:
            painter.fillRect(option.rect, option.palette.base())

    def createEditor(self, parent, option, index):
        editor = ToggleButtonWidget(parent)
        editor.toggled.connect(lambda checked: self.commitData.emit(editor))
        return editor

    def setEditorData(self, editor, index):
        if isinstance(index.model(), QtCore.QSortFilterProxyModel):
            index = index.model().mapToSource(index)

        value = index.model().data(index, QtCore.Qt.EditRole)
        if editor.isChecked() != value and value is not None:
            editor.setValue(value)

    def setModelData(self, editor, model, index):
        if isinstance(index.model(), QtCore.QSortFilterProxyModel):
            source_model = index.model().sourceModel()
            index = index.model().mapToSource(index)
        else:
            source_model = model

        value = index.model().data(index, QtCore.Qt.EditRole)
        if editor.isChecked() != value:
            source_model.setData(index, editor.isChecked(), QtCore.Qt.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        size = editor.sizeHint()
        x_pos = option.rect.x() + (option.rect.width() - size.width()) // 2
        y_pos = option.rect.y() + (option.rect.height() - size.height()) // 2 - 1
        editor.setGeometry(x_pos, y_pos, size.width(), size.height())

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(26)
        return size


class CheckBoxDelegate(QtWidgets.QStyledItemDelegate):
    def paint(self, painter, option, index):
        if option.state & QtWidgets.QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        else:
            painter.fillRect(option.rect, option.palette.base())

    def createEditor(self, parent, option, index):
        source_index = index
        if isinstance(index.model(), QtCore.QSortFilterProxyModel):
            source_index = index.model().mapToSource(index)

        editor = CheckBoxWidget(parent)
        editor.setColumn(source_index.column())
        editor.label.clicked.connect(lambda: self.commitData.emit(editor))
        return editor

    def setEditorData(self, editor, index):
        if isinstance(index.model(), QtCore.QSortFilterProxyModel):
            index = index.model().mapToSource(index)

        value = index.model().data(index, QtCore.Qt.EditRole)
        if value is not None:
            editor.setValue(value)

    def setModelData(self, editor, model, index):
        if isinstance(index.model(), QtCore.QSortFilterProxyModel):
            index = index.model().mapToSource(index)
            model = index.model()

        model.setData(index, editor.isChecked(), QtCore.Qt.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(26)
        return size


class NoFocusDelegate(QtWidgets.QStyledItemDelegate):
    def paint(self, painter, option, index):
        if option.state & QtWidgets.QStyle.State_HasFocus:
            option.state &= ~QtWidgets.QStyle.State_HasFocus
        super().paint(painter, option, index)

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(26)
        return size
