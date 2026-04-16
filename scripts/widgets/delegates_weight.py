from PySide2 import QtCore, QtWidgets

import maya.cmds as cmds

from enums import ItemType
from logger import getLogger

from .delegate_common import ReturnKeyCommitFilter
from .slider_widget import SliderWeightWidget

logger = getLogger("InterpBlendShape")


class SliderWeightDelegate(QtWidgets.QStyledItemDelegate):
    def _isSliderEditor(self, editor):
        return (
            hasattr(editor, "slider")
            and hasattr(editor, "lineEdit")
            and hasattr(editor, "floatToInt")
        )

    def _parentTreeView(self, editor):
        tree_getter = getattr(editor, "parentTreeView", None)
        if callable(tree_getter):
            return tree_getter()

        parent = editor.parent()
        while parent and not isinstance(parent, QtWidgets.QTreeView):
            parent = parent.parent()
        return parent

    def _setEditorValue(self, editor, value):
        if self._isSliderEditor(editor):
            editor.slider.blockSignals(True)
            editor.lineEdit.blockSignals(True)
            editor.slider.setValue(editor.floatToInt(value))
            editor.lineEdit.setText(f"{value:.3f}")
            editor.slider.blockSignals(False)
            editor.lineEdit.blockSignals(False)
            return

        blocker = getattr(editor, "blockSignals", None)
        if callable(blocker):
            editor.blockSignals(True)
        editor.setValue(value)
        if callable(blocker):
            editor.blockSignals(False)

    def paint(self, painter, option, index):
        if option.state & QtWidgets.QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        else:
            painter.fillRect(option.rect, option.palette.base())

    def createEditor(self, parent, option, index):
        source_index = index
        if isinstance(index.model(), QtCore.QSortFilterProxyModel):
            source_index = index.model().mapToSource(index)

        item = source_index.internalPointer()

        editor = SliderWeightWidget(
            positions=item.positions,
            itemType=item.type(),
            parent=parent,
        )

        editor.lineEdit.setKeyed(item.hasKeyed(), item.hasSDK(), item.isKeyOnCurrentTime())
        editor.setLockStatus(item.isLocked(), item.isConnected())
        if item.hasSDK() and item.isConnected():
            editor.slider.setActive(item.isLocked())
        editor.lineEdit.refreshStyle()

        editor._isDragging = False
        editor._valueBeforeDrag = None

        editor.slider.sliderPressed.connect(
            lambda: self._onSliderPressed(editor, source_index)
        )
        editor.slider.sliderReleased.connect(
            lambda: self._onSliderReleased(editor, source_index)
        )
        editor.slider.valueChanged.connect(
            lambda: self._onSliderValueChanged(editor, source_index)
        )
        editor.lineEdit.editingFinished.connect(
            lambda: self.commitData.emit(editor)
        )

        filter_obj = ReturnKeyCommitFilter(editor, self)
        editor.lineEdit.installEventFilter(filter_obj)
        return editor

    def _onSliderPressed(self, editor, source_index):
        editor._isDragging = True
        tree = self._parentTreeView(editor)
        if tree:
            tree._sliderDragging = True
        item = source_index.internalPointer()
        builder = item.builder()
        try:
            if item.type() == ItemType.PARENT:
                pre_drag = cmds.getAttr(f"{builder.node}.envelope")
            else:
                pre_drag = cmds.getAttr(f"{builder.node}.{item.getAttrName()}")
        except Exception:
            pre_drag = source_index.model().data(source_index, QtCore.Qt.EditRole)
        editor._valueBeforeDrag = pre_drag

    def _onSliderValueChanged(self, editor, source_index):
        if not editor._isDragging:
            return
        value = round(editor.value(), 3)

        if self._isSliderEditor(editor):
            editor.lineEdit.blockSignals(True)
            editor.lineEdit.setText(f"{value:.3f}")
            editor.lineEdit.blockSignals(False)

        item = source_index.internalPointer()
        item._data[source_index.column()] = value

        builder = item.builder()
        try:
            if item.type() == ItemType.PARENT:
                builder.setEnvelopeLive(value)
            else:
                builder.setTargetWeightLive(item.getAttrName(), value)
        except Exception as exc:
            logger.warning(f"[live] {exc}")

    def _onSliderReleased(self, editor, source_index):
        final_value = round(editor.value(), 3)

        if editor._valueBeforeDrag is None:
            editor._isDragging = False
            tree = self._parentTreeView(editor)
            if tree:
                tree._sliderDragging = False
            return

        pre_drag_value = editor._valueBeforeDrag
        item = source_index.internalPointer()
        builder = item.builder()

        try:
            if item.type() == ItemType.PARENT:
                plug = builder.fnNode.findPlug("envelope", False)
                plug.setFloat(pre_drag_value)
            else:
                idx = builder.getTargetIndex(item.getAttrName())
                if idx is not None:
                    plug = builder._weightPlug.elementByLogicalIndex(idx)
                    plug.setFloat(pre_drag_value)
        except Exception as exc:
            logger.warning(f"[release revert] {exc}")

        item._data[source_index.column()] = pre_drag_value

        source_index.model().setData(
            source_index, final_value, QtCore.Qt.EditRole, live=False
        )

        editor._isDragging = False
        self._setEditorValue(editor, final_value)

        tree = self._parentTreeView(editor)
        if tree:
            QtCore.QTimer.singleShot(0, lambda: setattr(tree, "_sliderDragging", False))

    def setEditorData(self, editor, index):
        if getattr(editor, "_isDragging", False):
            return
        tree = self._parentTreeView(editor)
        if tree and getattr(tree, "_sliderDragging", False):
            return
        if isinstance(index.model(), QtCore.QSortFilterProxyModel):
            index = index.model().mapToSource(index)
        value = index.model().data(index, QtCore.Qt.EditRole)
        if value is not None:
            self._setEditorValue(editor, value)

    def setModelData(self, editor, model, index):
        if isinstance(index.model(), QtCore.QSortFilterProxyModel):
            source_index = index.model().mapToSource(index)
            source_model = index.model().sourceModel()
        else:
            source_index = index
            source_model = model
        value = round(editor.value(), 3)
        source_model.setData(source_index, value, QtCore.Qt.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(26)
        return size
