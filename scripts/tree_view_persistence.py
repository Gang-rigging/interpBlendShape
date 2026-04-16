import hashlib
import os
import uuid

from PySide2 import QtCore

import app_config
import maya.cmds as cmds

from enums import ItemType
from logger import getLogger

logger = getLogger("InterpBlendShape")


class TreeViewPersistenceMixin:
    """Persistence helpers for tree expansion state and saved node order."""

    def _getSceneKey(self) -> str:
        """Return a stable per-scene key, with a session fallback for unsaved scenes."""
        scenePath = cmds.file(q=True, sn=True)
        if not scenePath:
            if not self._unsavedSceneKey:
                self._unsavedSceneKey = f"UNSAVED_{uuid.uuid4().hex}"
            return self._unsavedSceneKey

        abs_path = os.path.abspath(scenePath).replace("\\", "/")
        return hashlib.sha1(abs_path.encode("utf-8")).hexdigest()

    def _normalizeKey(self, name):
        """Normalize a node name for use as a consistent QSettings key."""
        return name.strip().replace("|", "")

    def saveExpandedState(self):
        """Save expanded parent rows and node ordering for the current scene."""
        scene_key = self._getSceneKey()
        if not scene_key:
            logger.debug("Scene not saved. Skip saving UI state.")
            return

        settings = app_config.ui_settings()
        settings.beginGroup(app_config.scene_group(scene_key, app_config.SCENE_GROUP_EXPANDED_STATE))
        settings.clear()
        self._saveIndexExpansion(QtCore.QModelIndex(), settings)
        settings.endGroup()

        settings.beginGroup(app_config.scene_group(scene_key, app_config.SCENE_GROUP_NODE_ORDER))
        settings.clear()
        for i in range(self.model.rootItem.childCount()):
            parentItem = self.model.rootItem.child(i)
            if not parentItem:
                continue
            settings.setValue(str(i), parentItem.name())
            for j in range(parentItem.childCount()):
                childItem = parentItem.child(j)
                if childItem:
                    settings.setValue(f"{parentItem.name()}_{j}", childItem.name())
        settings.endGroup()

    def _saveIndexExpansion(self, proxyIndex, settings):
        """Recursively save expansion state for top-level parent items."""
        if proxyIndex.isValid():
            return

        for row in range(self.proxyModel.rowCount(proxyIndex)):
            childIndex = self.proxyModel.index(row, 0, proxyIndex)
            if not self.isExpanded(childIndex):
                continue
            sourceIndex = self.proxyModel.mapToSource(childIndex)
            item = sourceIndex.internalPointer()
            if item and item.type() == ItemType.PARENT:
                raw_name = item.name()
                key = self._normalizeKey(raw_name)
                logger.info(f"[SAVE] Expanded Parent - Name: {raw_name} -> Key: {key}")
                settings.setValue(key, True)

    def restoreExpandedState(self):
        """Restore the saved expanded state for the current scene."""
        scene_key = self._getSceneKey()
        if not scene_key:
            return

        settings = app_config.ui_settings()
        settings.beginGroup(app_config.scene_group(scene_key, app_config.SCENE_GROUP_EXPANDED_STATE))
        self._restoreIndexExpansion(QtCore.QModelIndex(), settings)
        settings.endGroup()

    def _restoreNodeOrder(self, orderedNames):
        """Restore saved parent and child ordering from settings."""
        settings = app_config.ui_settings()
        scene_key = self._getSceneKey()
        settings.beginGroup(app_config.scene_group(scene_key, app_config.SCENE_GROUP_NODE_ORDER))

        children = {item.name(): item for item in self.model.rootItem._children}
        newOrder = []
        for name in orderedNames:
            if name not in children:
                continue
            parentItem = children.pop(name)
            childMap = {c.name(): c for c in parentItem._children}
            childKeys = sorted(
                [k for k in settings.allKeys() if k.startswith(f"{name}_")],
                key=lambda k: int(k.split("_")[-1]),
            )
            if childKeys:
                newChildren = []
                for key in childKeys:
                    childName = settings.value(key)
                    if childName in childMap:
                        newChildren.append(childMap.pop(childName))
                newChildren.extend(childMap.values())
                parentItem._children = newChildren
            newOrder.append(parentItem)

        newOrder.extend(children.values())
        settings.endGroup()

        if newOrder != self.model.rootItem._children:
            self.model.beginResetModel()
            self.model.rootItem._children = newOrder
            self.model.endResetModel()

    def _restoreIndexExpansion(self, proxyIndex, settings):
        """Restore expansion only for top-level parent items."""
        if proxyIndex.isValid():
            return

        for row in range(self.proxyModel.rowCount(proxyIndex)):
            childIndex = self.proxyModel.index(row, 0, proxyIndex)
            sourceIndex = self.proxyModel.mapToSource(childIndex)
            item = sourceIndex.internalPointer()
            if item and item.type() == ItemType.PARENT:
                raw_name = item.name()
                key = self._normalizeKey(raw_name)
                expanded = settings.value(key, False, type=bool)
                logger.debug(f"[RESTORE] Parent: {raw_name} -> Key: {key}, Expanded: {expanded}")
                self.setExpanded(childIndex, expanded)
