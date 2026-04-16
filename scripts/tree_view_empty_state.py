from PySide2 import QtCore, QtWidgets


class TreeViewEmptyStateMixin:
    """Empty-state overlay helpers for the main tree view."""

    def _buildEmptyState(self):
        """Create and return the empty state overlay widget."""
        widget = QtWidgets.QWidget(self)
        widget.setObjectName("emptyState")
        widget.setStyleSheet(
            """
            #emptyState { background: transparent; }
            """
        )

        layout = QtWidgets.QVBoxLayout(widget)
        layout.setAlignment(QtCore.Qt.AlignCenter)
        layout.setSpacing(12)

        iconLabel = QtWidgets.QLabel("+")
        iconLabel.setAlignment(QtCore.Qt.AlignCenter)
        iconLabel.setFixedSize(48, 48)
        iconLabel.setStyleSheet(
            """
            background: #505558;
            border-radius: 24px;
            color: #55AAC3;
            font-size: 22px;
            """
        )

        title = QtWidgets.QLabel("No blend shapes in scene")
        title.setAlignment(QtCore.Qt.AlignCenter)
        title.setStyleSheet("color: #E0E0E0; font-size: 13px; font-weight: bold;")

        subtitle = QtWidgets.QLabel("Select a mesh and create an\nInterpBlendShape deformer to get started")
        subtitle.setAlignment(QtCore.Qt.AlignCenter)
        subtitle.setStyleSheet("color: #888; font-size: 11px;")

        button = QtWidgets.QPushButton("+ Create InterpBlendShape")
        button.setStyleSheet(
            """
            QPushButton {
                background: #55AAC3;
                color: #1a3a44;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover { background: #62C3DF; }
            QPushButton:pressed { background: #4890A5; }
            """
        )
        button.clicked.connect(self.addNewNodeClicked)

        layout.addWidget(iconLabel, alignment=QtCore.Qt.AlignCenter)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(button, alignment=QtCore.Qt.AlignCenter)

        widget.hide()
        return widget

    def _updateEmptyState(self):
        hasData = self.model.rowCount() > 0
        self._emptyState.setVisible(not hasData)
        if not hasData:
            self._emptyState.setGeometry(self.viewport().rect())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._emptyState.setGeometry(self.viewport().rect())
