from PySide2 import QtCore, QtWidgets


class ReturnKeyCommitFilter(QtCore.QObject):
    def __init__(self, editor, delegate):
        super().__init__(editor)
        self.editor = editor
        self.delegate = delegate

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.KeyPress and event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            self.editor.onLineEditChanged()
            self.delegate.closeEditor.emit(self.editor, QtWidgets.QAbstractItemDelegate.NoHint)
            self.editor.lineEdit.clearFocus()
            return True
        return False
