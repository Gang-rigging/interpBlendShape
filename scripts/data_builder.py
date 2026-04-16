from __future__ import annotations

import re

import maya.api.OpenMaya as om
import maya.api.OpenMayaAnim as oma
import maya.cmds as cmds

from builder_ops import (
    copy_weight,
    edit_target_shape,
    flip_weight,
    mirror_weight,
    normalize_target_weight,
    paint_base_weight,
    paint_target_weight,
    select_paintable_base_mesh,
    set_base_weight,
    set_target_vertex_weight,
)
from builder_queries import (
    get_all_input_target_surfaces,
    get_base_mesh,
    get_base_weight,
    get_dag_path_from_plug,
    get_input_mesh,
    get_inbetween_targets,
    get_input_target_surface,
    get_keyframes,
    get_last_element_index,
    get_target_vertex_weight,
    get_target_mesh,
    get_target_meshes_for_item,
    is_connected,
    is_inbetween_index_valid,
    is_locked,
)
from enums import ActionID, AttrName, ItemType
from logger import getLogger
from maya_utils import getUniqueName, normalizeName
from tree_item import InterpBlendShapeItem

logger = getLogger("InterpBlendShape")


class InterpBlendShapeDataBuilder:
    """
    Data builder and Maya interface for a single interpBlendShape deformer node.

    Provides all read/write operations needed to query and manipulate the node's
    internal state — weights, targets, inbetweens, surfaces, keyframes, and vertex
    weights. Also builds the UI tree item structure used by the Qt model.

    Sections:
        - Initialization & Snapshot
        - Alias & Cache
        - Plug & Attribute Access
        - Item Building
        - State Queries
        - Mesh Queries
        - Weight Setters
        - Target Management
        - Surface Management
        - Attribute Operations
        - Vertex Weight Operations
        - Paint Operations

    Args:
        interpBlendShapeNode (str): Name of the interpBlendShape node in Maya.
        fnNode (MFnDependencyNode): Function set wrapping the node.
    """

    # ------------------------------------------------------------------
    # Initialization & Snapshot
    # ------------------------------------------------------------------

    def __init__(self, interpBlendShapeNode, fnNode):
        self.node   = interpBlendShapeNode
        self.fnNode = fnNode

        self.aliasDictCache = None
        self.targetsCache   = None

        # Cached MPlugs
        self._weightPlug        = self.fnNode.findPlug("weight", False)
        self._inputSurfacePlug  = self.fnNode.findPlug("inputSurface", False)
        self._inputTargetPlug   = self.fnNode.findPlug("inputTarget", False)

        # Cached attribute MObjects for repeated access
        self._attrInputTargetGroup   = self.fnNode.attribute("inputTargetGroup")
        self._attrInputTargetItem    = self.fnNode.attribute("inputTargetItem")
        self._attrTargetSurfaceId    = self.fnNode.attribute("targetSurfaceId")
        self._attrInputTargetSurface = self.fnNode.attribute("inputTargetSurface")
        self._attrInbetweenInfo      = self.fnNode.attribute("inbetweenInfo")
        self._attrInbetweenTargetName = self.fnNode.attribute("inbetweenTargetName")

    @staticmethod
    def _normalizeInbetweenWeight(value: float) -> float:
        """Snap inbetween weights to Maya's supported 0.001 precision grid."""
        return float(f"{float(value):.3f}")

    @classmethod
    def _inbetweenItemId(cls, value: float) -> int:
        """Convert an inbetween weight to its item id on the 5000-based scale."""
        return int(round(cls._normalizeInbetweenWeight(value) * 1000.0)) + 5000

    def snapshot(self) -> dict:
        """
        Collect all node data into plain Python dicts/lists.
        No MObjects or MPlugs — safe to pass to a background thread.

        Returns:
            dict: Full snapshot of node state including all targets, surfaces,
                  keyframes, and connection info.
        """
        self.refreshAliasCache()
        targets = self.getTargets(refresh=True)

        targetSnapshots = []
        for name in targets:
            keyframes, hasSDK = self.getKeyframes(name, weightPlug=True)
            inbetweenNames, inbetweenWeights = self.getInbetweenTargets(name)
            targetSnapshots.append({
                "name":              name,
                "weight":            self.getAttrValue(name),
                "surfaceDriver":     self.getSurfaceDriver(name) or "NONE",
                "blendUV":           self.getTargetAttribute(name, AttrName.TARGET_BLEND_UV, False),
                "blendBezier":       self.getTargetAttribute(name, AttrName.TARGET_BLEND_BEZIER, False),
                "blendLive":         self.getTargetAttribute(name, AttrName.TARGET_BLEND_LIVE, False),
                "offset":            self.getTargetAttribute(name, AttrName.TARGET_OFFSET, 1.0),
                "curvature":         self.getTargetAttribute(name, AttrName.TARGET_CURVATURE, 1.0),
                "precision":         self.getTargetAttribute(name, AttrName.TARGET_PRECISION, 1.0),
                "cached":            self.getTargetAttribute(name, AttrName.TARGET_CACHED, False),
                "targetIndex":       self.getTargetIndex(name),
                "weightNormalization": self.getTargetAttribute(name, AttrName.TARGET_WEIGHT_NORMALIZATION, False),
                "weightLocked":      self.getTargetAttribute(name, AttrName.TARGET_WEIGHT_LOCKED, False),
                "isLocked":          self.isLocked(name, weightPlug=True),
                "isConnected":       self.isConnected(name, weightPlug=True),
                "keyframes":         keyframes,
                "hasSDK":            hasSDK,
                "inbetweenNames":    inbetweenNames,
                "inbetweenWeights":  inbetweenWeights,
            })

        envelopeKeyframes, envelopeHasSDK = self.getKeyframes("envelope", weightPlug=False)

        return {
            "nodeName":    self.node,
            "envelope":    self.getAttrValue("envelope"),
            "surfaces":    self.getAllInputTargetSurfaces(),
            "isLocked":    self.isLocked("envelope", weightPlug=False),
            "isConnected": self.isConnected("envelope", weightPlug=False),
            "keyframes":   envelopeKeyframes,
            "hasSDK":      envelopeHasSDK,
            "targets":     targetSnapshots,
        }

    # ------------------------------------------------------------------
    # Alias & Cache
    # ------------------------------------------------------------------

    def refreshAliasCache(self) -> None:
        """
        Refresh the alias-to-attribute dictionary cache.

        Queries all aliases on the node via cmds.aliasAttr and rebuilds
        the mapping. Clears to an empty dict if the result is malformed.
        """
        aliases = cmds.aliasAttr(self.node, query=True) or []
        if len(aliases) % 2 != 0:
            self.aliasDictCache = {}
        else:
            self.aliasDictCache = {aliases[i]: aliases[i + 1] for i in range(0, len(aliases), 2)}

    def hasAlias(self, aliasName: str) -> bool:
        """
        Check whether an alias name exists on this node.

        Args:
            aliasName (str): The alias name to check.

        Returns:
            bool: True if the alias exists, False otherwise.
        """
        if self.aliasDictCache is None:
            self.refreshAliasCache()
        return aliasName in self.aliasDictCache

    def updateAliasDictCache(self, oldAlias: str, newAlias: str) -> None:
        """
        Replace an alias name in the cached alias dictionary.

        Args:
            oldAlias (str): The alias name to replace.
            newAlias (str): The new alias name to use.
        """
        if not oldAlias or not newAlias:
            return
        if oldAlias in self.aliasDictCache:
            value = self.aliasDictCache.pop(oldAlias)
            self.aliasDictCache[newAlias] = value

    def getTargetIndex(self, targetName: str) -> int | None:
        """
        Retrieve the logical index for a given target alias name.

        Args:
            targetName (str): The alias name of the target.

        Returns:
            int | None: The logical index, or None if not found.
        """
        if self.aliasDictCache is None:
            self.refreshAliasCache()
        attr = self.aliasDictCache.get(targetName)
        if not attr:
            return None
        match = re.search(r'\[(\d+)\]', attr)
        return int(match.group(1)) if match else None

    def getTargets(self, refresh: bool = False) -> list[str]:
        """
        Return a cached list of all target alias names under the weight attribute.

        Args:
            refresh (bool): If True, forces a cache refresh. Defaults to False.

        Returns:
            list[str]: List of target alias names.
        """
        if refresh or self.targetsCache is None:
            self.targetsCache = cmds.listAttr(f"{self.node}.weight", m=True) or []
        return self.targetsCache

    def updateAlias(self, alias: str, preAlias: str) -> str | bool:
        """
        Rename an attribute alias on the node.

        Args:
            alias (str): The new alias name. Will be normalized (spaces → underscores).
            preAlias (str): The existing alias name to replace.

        Returns:
            str: The new alias name if successful, False otherwise.
        """
        if self.aliasDictCache is None:
            self.refreshAliasCache()
        alias = normalizeName(alias)
        if alias in self.aliasDictCache or preAlias not in self.aliasDictCache:
            return False
        attrName = self.aliasDictCache[preAlias]
        try:
            cmds.aliasAttr(alias, f"{self.node}.{attrName}")
            self.aliasDictCache[alias] = attrName
            self.aliasDictCache.pop(preAlias, None)
            return alias
        except Exception as e:
            logger.warning(f"Failed to update alias '{alias}': {e}")
            return False

    # ------------------------------------------------------------------
    # Plug & Attribute Access
    # ------------------------------------------------------------------

    def _getPlug(self, attrName: str, weightPlug: bool = False) -> om.MPlug | None:
        """
        Retrieve the MPlug for the given attribute name.

        Args:
            attrName (str): The attribute name or alias.
            weightPlug (bool): If True, returns the weight plug for this target.

        Returns:
            MPlug | None: The plug object if found, otherwise None.
        """
        if weightPlug:
            index = self.getTargetIndex(attrName)
            if index is None:
                return None
            return self._weightPlug.elementByLogicalIndex(index)
        return self.fnNode.findPlug(attrName, False)

    def getAttrValue(self, attr: str, default: float = 1.0):
        """
        Get the value of an attribute using cmds.getAttr.

        Args:
            attr (str): The attribute name (e.g. "envelope", "pSphere1").
            default: Value to return if the attribute does not exist.

        Returns:
            The attribute value, or default if not found.
        """
        fullAttr = f"{self.node}.{attr}"
        return cmds.getAttr(fullAttr) if cmds.objExists(fullAttr) else default

    def _getTargetPlugValue(self, index: int, attrName: str, default=False):
        """
        Retrieve a specific attribute value from a target's inputTargetGroup plug.

        Args:
            index (int): Logical index of the target.
            attrName (str): The attribute name to read.
            default: Default value used to infer return type (bool, float, int, str).

        Returns:
            The plug value cast to the same type as default, or False on error.
        """
        try:
            inputTargetPlug = self._inputTargetPlug.elementByLogicalIndex(0)
            attrObj  = self.fnNode.attribute(attrName)
            groupPlug = inputTargetPlug.child(self._attrInputTargetGroup).elementByLogicalIndex(index)
            valuePlug = groupPlug.child(attrObj)
            if isinstance(default, bool):
                return valuePlug.asBool()
            elif isinstance(default, float):
                return valuePlug.asFloat()
            elif isinstance(default, int):
                return valuePlug.asInt()
            elif isinstance(default, str):
                return valuePlug.asString()
            else:
                logger.warning(f"Unsupported default type: {type(default).__name__}")
                return False
        except Exception as e:
            logger.warning(f"Failed to get '{attrName}' at index {index}: {e}")
            return False

    def getTargetAttribute(self, targetName: str, attrName: str, defaultValue):
        """
        Retrieve a specific attribute value from a target by alias name.

        Args:
            targetName (str): The alias name of the target.
            attrName (str): The attribute to retrieve.
            defaultValue: Returned if the target or attribute is not found.

        Returns:
            The attribute value, or defaultValue if not found.
        """
        index = self.getTargetIndex(targetName)
        if index is None:
            return defaultValue
        return self._getTargetPlugValue(index, attrName, defaultValue)

    def _setTargetPlugValue(self, index: int, attrName: str, value=1.0) -> bool:
        """
        Set a specific attribute value on all inputTargetGroup elements for a target index.

        Uses cmds.setAttr for undo support.

        Args:
            index (int): Logical index of the target.
            attrName (str): Attribute name to modify.
            value: Value to set. Supported types: float, int, bool, str.

        Returns:
            bool: True if successful, False otherwise.
        """
        try:
            attrObj = self.fnNode.attribute(attrName)
            for i in range(self._inputTargetPlug.numElements()):
                try:
                    elementPlug   = self._inputTargetPlug.elementByPhysicalIndex(i)
                    groupPlug     = elementPlug.child(self.fnNode.attribute("inputTargetGroup"))
                    targetGrpPlug = groupPlug.elementByLogicalIndex(index)
                    valuePlug     = targetGrpPlug.child(attrObj)
                    attrFullName  = valuePlug.name()
                    if isinstance(value, str):
                        cmds.setAttr(attrFullName, value, type="string")
                    else:
                        cmds.setAttr(attrFullName, value)
                except Exception as innerErr:
                    logger.warning(f"[TargetPlug] Failed to set {attrName}={value} at index {index}: {innerErr}")
                    return False
            return True
        except Exception as outerErr:
            logger.warning(f"[TargetPlug] Failed to set '{attrName}' for index {index}: {outerErr}")
            return False

    def _setTargetPlugValue(self, index: int, attrName: str, value=1.0, live=False) -> bool:
        try:
            attrObj = self.fnNode.attribute(attrName)
            if not live:
                cmds.undoInfo(openChunk=True)
            try:
                for i in range(self._inputTargetPlug.numElements()):
                    try:
                        elementPlug = self._inputTargetPlug.elementByPhysicalIndex(i)
                        groupPlug = elementPlug.child(self.fnNode.attribute("inputTargetGroup"))
                        targetGrpPlug = groupPlug.elementByLogicalIndex(index)
                        valuePlug = targetGrpPlug.child(attrObj)
                        attrFullName = valuePlug.name()

                        if live:
                            if isinstance(value, float):
                                valuePlug.setFloat(value)
                            elif isinstance(value, bool):
                                valuePlug.setBool(value)
                            elif isinstance(value, int):
                                valuePlug.setInt(value)
                            else:
                                cmds.setAttr(attrFullName, value)
                        else:
                            if isinstance(value, str):
                                cmds.setAttr(attrFullName, value, type="string")
                            else:
                                cmds.setAttr(attrFullName, value)

                    except Exception as innerErr:
                        logger.warning(f"[TargetPlug] Failed to set {attrName}={value} at index {index}: {innerErr}")
                        return False
                return True
            finally:
                if not live:
                    cmds.undoInfo(closeChunk=True)
        except Exception as outerErr:
            logger.warning(f"[TargetPlug] Failed to set '{attrName}' for index {index}: {outerErr}")
            return False

    def setTargetValue(self, targetName: str, attr: str, value: float = 1.0) -> bool:
        index = self.getTargetIndex(targetName)
        if index is None:
            logger.warning(f"Target '{targetName}' not found.")
            return False
        return self._setTargetPlugValue(index, attr, value, live=False)

    def setTargetValueLive(self, targetName: str, attr: str, value: float) -> bool:
        index = self.getTargetIndex(targetName)
        if index is None:
            return False
        return self._setTargetPlugValue(index, attr, value, live=True)

    # ------------------------------------------------------------------
    # Item Building
    # ------------------------------------------------------------------

    def build(self, builder=None) -> 'InterpBlendShapeItem':
        """
        Construct the root InterpBlendShapeItem for this node and populate it
        with child items for each target.

        Args:
            builder: Optional builder object used during item creation.

        Returns:
            InterpBlendShapeItem: The root item with all child target items.
        """
        parentData = [self.node, self.getAttrValue("envelope"), "", "", "", "", "", "", "", "", False]
        rootItem = InterpBlendShapeItem(parentData, ItemType.PARENT, builder)
        rootItem.setSurfaceData(self.getAllInputTargetSurfaces())
        self.updateItemConnectionStatus(rootItem, "envelope", weightPlug=False)
        for name in self.getTargets(refresh=True):
            rootItem.appendChild(self.addChildItem(name, builder))
        return rootItem

    def addChildItem(self, name: str, builder) -> 'InterpBlendShapeItem':
        """
        Create and return a child InterpBlendShapeItem for the given target name.

        Populates the item with attributes, keyframe, connection, and lock state.
        Also appends inbetween target items as children if any exist.

        Args:
            name (str): The alias name of the target.
            builder: The builder object associated with this item.

        Returns:
            InterpBlendShapeItem: The populated child item.
        """
        data = [
            name,
            self.getAttrValue(name),
            self.getSurfaceDriver(name) or "NONE",
            self.getTargetAttribute(name, AttrName.TARGET_BLEND_UV, False),
            self.getTargetAttribute(name, AttrName.TARGET_BLEND_BEZIER, False),
            self.getTargetAttribute(name, AttrName.TARGET_BLEND_LIVE, False),
            self.getTargetAttribute(name, AttrName.TARGET_OFFSET, 1.0),
            self.getTargetAttribute(name, AttrName.TARGET_CURVATURE, 1.0),
            self.getTargetAttribute(name, AttrName.TARGET_PRECISION, 1.0),
            self.getTargetAttribute(name, AttrName.TARGET_CACHED, False),
            False
        ]
        targetLogicalIndex = self.getTargetIndex(name)
        childItem = InterpBlendShapeItem(data, ItemType.CHILD, builder, targetLogicalIndex)
        childItem.weightNormalization = self.getTargetAttribute(name, AttrName.TARGET_WEIGHT_NORMALIZATION, False)
        childItem.weightLocked        = self.getTargetAttribute(name, AttrName.TARGET_WEIGHT_LOCKED, False)
        self.updateItemConnectionStatus(childItem, name, weightPlug=True)

        inbetweenTargetNames, inbetweenWeights = self.getInbetweenTargets(name)
        if inbetweenTargetNames:
            for inbetweenName, weight in zip(inbetweenTargetNames, inbetweenWeights):
                inbetweenIndex = int(weight * 1000.0 + 5000)
                inbetweenItem = InterpBlendShapeItem(
                    [inbetweenName, weight], ItemType.INBETWEEN, builder, inbetweenIndex
                )
                childItem.appendChild(inbetweenItem)
            childItem.positions = inbetweenWeights

        return childItem

    # ------------------------------------------------------------------
    # State Queries
    # ------------------------------------------------------------------

    def isLocked(self, attrName: str, weightPlug: bool = False) -> bool:
        """
        Check if the specified attribute plug is locked.

        Args:
            attrName (str): The attribute name.
            weightPlug (bool): If True, check the weight plug variant.

        Returns:
            bool: True if locked, False otherwise.
        """
        return is_locked(self._getPlug, attrName, weightPlug)

    def isConnected(self, attrName: str, weightPlug: bool = False) -> bool:
        """
        Check if the attribute is connected to any non-animCurve node.

        Args:
            attrName (str): The attribute name.
            weightPlug (bool): If True, check the weight plug variant.

        Returns:
            bool: True if connected to a non-animCurve node, False otherwise.
        """
        return is_connected(self._getPlug, attrName, weightPlug)

    def getKeyframes(self, attrName: str, weightPlug: bool = False) -> tuple[list[float], bool]:
        """
        Retrieve keyframe times for the specified attribute plug.

        Args:
            attrName (str): The attribute name to inspect.
            weightPlug (bool): If True, resolve the weight variant of the plug.

        Returns:
            tuple[list[float], bool]: Keyframe times and a flag indicating SDK presence.
        """
        return get_keyframes(self._getPlug, attrName, weightPlug)

    def updateItemConnectionStatus(self, item, attrName: str, weightPlug: bool = False) -> None:
        """
        Update a tree item's lock, connection, keyframe, and SDK state from Maya.

        Args:
            item (InterpBlendShapeItem): The item to update.
            attrName (str): The attribute name to inspect.
            weightPlug (bool): If True, use the weight plug variant.
        """
        keyframes, hasSDK = self.getKeyframes(attrName, weightPlug)
        item.setConnected(self.isConnected(attrName, weightPlug))
        item.setLocked(self.isLocked(attrName, weightPlug))
        item.setKeyframes(keyframes)
        item.setHasSDK(hasSDK)
        if keyframes:
            item.isKeyOnCurrentTime()

    def getInbetweenTargets(self, targetName: str) -> tuple[list[str], list[float]]:
        """
        Retrieve inbetween target names and weights for a given target.

        Args:
            targetName (str): Alias name of the main target.

        Returns:
            tuple[list[str], list[float]]: Inbetween names and their weights (excluding 0 and 1).
        """
        return get_inbetween_targets(
            self._getPlug,
            self._attrInbetweenInfo,
            self._attrInbetweenTargetName,
            self.getTargetIndex,
            self.isInbetweenIndexValid,
            targetName,
        )

    def isInbetweenIndexValid(self, targetIndex: int, inbetweenIndex: int) -> bool:
        """
        Check whether a given inbetween index exists in the inputTargetItem plug.

        Args:
            targetIndex (int): Logical index of the parent target.
            inbetweenIndex (int): Logical index of the inbetween.

        Returns:
            bool: True if the inbetween index exists, False otherwise.
        """
        return is_inbetween_index_valid(
            self._inputTargetPlug,
            self._attrInputTargetGroup,
            self._attrInputTargetItem,
            targetIndex,
            inbetweenIndex,
        )

    # ─────────────────────────────────────────────
    # Mesh Queries
    # ─────────────────────────────────────────────

    def getInputMesh(self, index: int = 0) -> str | None:
        """
        Retrieve the input geometry transform connected to this deformer's
        inputGeometry plug.

        Traverses upstream through intermediate nodes until a supported shape
        node is found. Meshes and NURBS curves are both valid inputs for the
        plugin, so either type may be returned here.

        Args:
            index (int): Logical index for multi-input deformers. Defaults to 0.

        Returns:
            str | None: Full DAG path of the input geometry transform, or None if
                not found.
        """
        return get_input_mesh(self._getPlug, index)

    def getBaseMesh(self) -> list[str]:
        """
        Retrieve the base mesh transform(s) by traversing downstream through the deformer stack.

        Unlike a simple outputGeometry lookup, this method follows the full deformer
        chain — if another deformer (e.g. blendShape, skinCluster) sits between this
        plugin and the final mesh, it continues traversing until it reaches the actual
        visible mesh shape, skipping intermediate objects.

        Traversal rules:
            - Mesh shape (non-intermediate) → record transform, stop.
            - Geometry filter (deformer) → follow its outputGeometry at same logical index.
            - Anything else → stop.
            - Visited set prevents infinite loops.

        Returns:
            list[str]: Full DAG path names of base mesh transforms. Empty if none found.
        """
        return get_base_mesh(self._getPlug)

    def getTargetMesh(self, attrName: str) -> list[str]:
        """
        Retrieve the target mesh transform(s) connected to the given target attribute.

        Args:
            attrName (str): Alias name of the target.

        Returns:
            list[str]: List of target mesh transform names.
        """
        return get_target_mesh(
            self._inputTargetPlug,
            self._attrInputTargetGroup,
            self._attrInputTargetItem,
            self.fnNode,
            self.getTargetIndex,
            self.getDagPathFromPlug,
            attrName,
        )

    def getTargetMeshesForItem(self, attrName: str, targetItemId: int) -> list[str]:
        """
        Retrieve connected target mesh transform(s) for a specific target item id.

        Args:
            attrName (str): Alias name of the target group.
            targetItemId (int): Logical index of the target item (for example 6000
                for the main target or 5000+ for inbetweens).

        Returns:
            list[str]: Full DAG paths for each matching connected target shape.
        """
        return get_target_meshes_for_item(
            self._inputTargetPlug,
            self._attrInputTargetGroup,
            self._attrInputTargetItem,
            self.fnNode,
            self.getTargetIndex,
            self.getDagPathFromPlug,
            attrName,
            targetItemId,
        )

    def getLastElementIndex(self, arrayPlug: om.MPlug) -> int:
        """
        Find the highest logical index currently used in an array plug.

        Args:
            arrayPlug (MPlug): A Maya MPlug representing an array (multi) attribute.

        Returns:
            int: The highest logical index, or -1 if the array has no elements.
        """
        return get_last_element_index(arrayPlug)

    # ─────────────────────────────────────────────
    # Weight Setters
    # ─────────────────────────────────────────────

    def setTargetWeight(self, targetName: str, value: float = 1.0) -> bool:
        """
        Set the blend shape weight on release, wrapped in a single undo chunk.

        Args:
            targetName (str): The alias name of the target.
            value (float): The weight value to set. Defaults to 1.0.

        Returns:
            bool: True if successful, False if the attribute does not exist.
        """
        attrFullName = f"{self.node}.{targetName}"
        if cmds.objExists(attrFullName):
            cmds.undoInfo(openChunk=True)
            try:
                cmds.setAttr(attrFullName, value)
            finally:
                cmds.undoInfo(closeChunk=True)
            return True
        logger.warning(f"Attribute '{attrFullName}' does not exist.")
        return False

    def setEnvelopeValue(self, value: float) -> bool:
        """
        Set the envelope value on release, wrapped in a single undo chunk.

        Args:
            value (float): The envelope value to set.

        Returns:
            bool: True if successful, False if the attribute does not exist.
        """
        attrFullName = f"{self.node}.envelope"
        if cmds.objExists(attrFullName):
            cmds.undoInfo(openChunk=True)
            try:
                cmds.setAttr(attrFullName, value)
            finally:
                cmds.undoInfo(closeChunk=True)
            return True
        logger.warning(f"Attribute '{attrFullName}' does not exist.")
        return False

    def setTargetWeightLive(self, targetName: str, value: float) -> bool:
        """
        Live-update a target weight during drag using MPlug — bypasses the undo queue.

        Args:
            targetName (str): The alias name of the target.
            value (float): The weight value to set.

        Returns:
            bool: True if successful, False otherwise.
        """
        index = self.getTargetIndex(targetName)
        if index is None:
            return False
        try:
            self._weightPlug.elementByLogicalIndex(index).setFloat(value)
            return True
        except Exception as e:
            logger.warning(f"[setTargetWeightLive] Failed: {e}")
            return False

    def setEnvelopeLive(self, value: float) -> bool:
        """
        Live-update the envelope value during drag using MPlug — bypasses the undo queue.

        Args:
            value (float): The envelope value to set.

        Returns:
            bool: True if successful, False otherwise.
        """
        try:
            self.fnNode.findPlug("envelope", False).setFloat(value)
            return True
        except Exception as e:
            logger.warning(f"[setEnvelopeLive] Failed: {e}")
            return False

    # ─────────────────────────────────────────────
    # Target Management
    # ─────────────────────────────────────────────

    def addTarget(self, parentItem, targetIds=None) -> list:
        """
        Add new mesh targets to the node and update the UI model.

        If targetIds are provided, they are used directly. Otherwise, uses the
        current Maya selection to determine which meshes to add.

        Args:
            parentItem (InterpBlendShapeItem): The parent model item to attach new children to.
            targetIds (int or list[int], optional): Target logical indices to use directly.
                If None, target meshes are determined from the current selection.

        Returns:
            list[InterpBlendShapeItem]: List of newly created child items.
        """
        newTargetIds = []

        if targetIds is not None:
            if isinstance(targetIds, int):
                if targetIds == -1:
                    logger.debug("Skipping index -1 (reserved for root or parent items)")
                    return []
                newTargetIds = [targetIds]
            elif isinstance(targetIds, list):
                newTargetIds = [i for i in targetIds if isinstance(i, int) and i != -1]
                if not newTargetIds:
                    logger.debug("All provided indices are -1 or invalid.")
                    return []
            else:
                logger.warning("Invalid targetIds format. Must be an int or list of ints.")
                return []
        else:
            inputGeometry = self.getInputMesh()
            if not inputGeometry:
                logger.warning(f"Cannot add a target because inputGeometry is not connected on {self.node}.")
                return []

            lastIndex    = self.getLastElementIndex(self._weightPlug)
            targetMeshes = []
            selection    = om.MGlobal.getActiveSelectionList()

            for i in range(selection.length()):
                try:
                    dagPath = selection.getDagPath(i)
                    targetMeshes.append(dagPath.fullPathName())
                except RuntimeError:
                    logger.warning("Skipping non-DAG path in selection.")
                    continue

            for mesh in targetMeshes:
                targetId = lastIndex + 1 + len(newTargetIds)
                try:
                    cmds.interpBlendShape(self.node, e=True, t=[inputGeometry, targetId, mesh, 1])
                    newTargetIds.append(targetId)
                except Exception as e:
                    logger.warning(f"Failed to add target {mesh}: {e}")

        childrenItems = []
        if newTargetIds:
            self.refreshAliasCache()
            inverse = {v: k for k, v in self.aliasDictCache.items()}
            for targetId in newTargetIds:
                aliasAttr = f'weight[{targetId}]'
                aliasName = inverse.get(aliasAttr, aliasAttr)
                childrenItems.append(self.addChildItem(aliasName, parentItem.builder()))
        return childrenItems

    def addInbetweenTarget(self, childItem, weight: float, modelOnly: bool = False) -> list:
        """
        Add a new in-between target to the specified child item.

        The weight must be strictly between 0 and 1 (exclusive).

        Args:
            childItem (InterpBlendShapeItem): The target item to attach inbetweens to.
            weight (float): Weight for the in-between target.
            modelOnly (bool): If True, only updates the UI model without modifying Maya.

        Returns:
            list[InterpBlendShapeItem]: Newly added in-between items, or empty list on failure.
        """
        inbetweenItems = []
        weight = self._normalizeInbetweenWeight(weight)

        if modelOnly:
            inbetweenIndex = self._inbetweenItemId(weight)
            name = f"{childItem.name()}_{weight:.3f}"
            if not self.isInbetweenIndexValid(childItem.targetIndex(), inbetweenIndex):
                return []
            item = InterpBlendShapeItem([name, weight], ItemType.INBETWEEN, childItem.builder(), inbetweenIndex)
            childItem.addPosition(weight)
            return [item]

        baseMesh     = self.getBaseMesh()
        selection    = om.MGlobal.getActiveSelectionList()
        targetMeshes = []

        if not baseMesh:
            logger.warning(f"[Inbetween] No base geometry found on {self.node}.")
            return []

        for i in range(selection.length()):
            try:
                targetMeshes.append(selection.getDagPath(i).fullPathName())
            except RuntimeError:
                logger.warning("Skipping invalid DAG path in selection.")
                continue

        if not targetMeshes:
            logger.warning("[Inbetween] No valid target meshes selected.")
            return []

        for i, mesh in enumerate(targetMeshes):
            w = self._normalizeInbetweenWeight(weight + weight * i)
            if w >= 1.0:
                logger.warning(f"[Inbetween] Skipping weight {w:.3f}: it must be less than 1.0.")
                continue
            try:
                cmds.interpBlendShape(
                    self.node, ib=True, e=True,
                    t=[baseMesh[0], childItem.targetIndex(), mesh, w]
                )
            except Exception as e:
                logger.warning(f"[Inbetween] Failed to add target at weight {w:.3f}: {e}")
                continue

            itemId = self._inbetweenItemId(w)
            item   = InterpBlendShapeItem(
                [f"{childItem.name()}_{w:.3f}", w],
                ItemType.INBETWEEN,
                childItem.parent().builder(),
                itemId
            )
            childItem.addPosition(w)
            inbetweenItems.append(item)

        if inbetweenItems and not self.setTargetValueLive(childItem.name(), AttrName.TARGET_REBIND, True):
            logger.warning(f"[Inbetween] Added targets but failed to mark '{childItem.name()}' for rebind.")

        return inbetweenItems

    def updateInbetweenTarget(self, targetName: str, value: float,
                              prevInbetweenWeight: float, inbetweenTargetName: str) -> str | bool:
        """
        Replace an existing inbetween target with a new one at a different weight.

        Removes the previous inbetween at prevInbetweenWeight and adds a new one at value.

        Args:
            targetName (str): Alias of the main blend shape target.
            value (float): New inbetween weight (0-1).
            prevInbetweenWeight (float): Weight of the inbetween to remove.
            inbetweenTargetName (str): Display name for the new inbetween.

        Returns:
            str | bool: True if successful, False otherwise.
        """
        index = self.getTargetIndex(targetName)
        if index is None:
            logger.warning(f"Target '{targetName}' not found.")
            return False

        value = self._normalizeInbetweenWeight(value)
        prevInbetweenWeight = self._normalizeInbetweenWeight(prevInbetweenWeight)
        prevItemId = self._inbetweenItemId(prevInbetweenWeight)
        try:
            outputGeomPlug = self._getPlug("outputGeometry")
            targetMeshes   = {}
            baseMeshes     = {}

            for i in range(self._inputTargetPlug.numElements()):
                elementPlug  = self._inputTargetPlug.elementByPhysicalIndex(i)
                logicalIndex = elementPlug.logicalIndex()
                try:
                    groupPlug    = elementPlug.child(self._attrInputTargetGroup)
                    groupElem    = groupPlug.elementByLogicalIndex(index)
                    itemPlug     = groupElem.child(self._attrInputTargetItem)
                    inbetweenPlug = itemPlug.elementByLogicalIndex(prevItemId)
                    geomPlug     = inbetweenPlug.child(self.fnNode.attribute("inputGeomTarget"))
                    connections  = geomPlug.connectedTo(True, False)
                    if connections:
                        targetMeshes[logicalIndex] = om.MFnDagNode(connections[0].node()).fullPathName()
                except RuntimeError:
                    continue

            for i in range(outputGeomPlug.numElements()):
                elementPlug  = outputGeomPlug.elementByPhysicalIndex(i)
                logicalIndex = elementPlug.logicalIndex()
                connections  = elementPlug.connectedTo(False, True)
                if connections:
                    baseMeshes[logicalIndex] = om.MFnDagNode(connections[0].node()).fullPathName()

            for logicalIndex, baseMesh in baseMeshes.items():
                targetMesh = targetMeshes.get(logicalIndex)
                if not targetMesh:
                    continue
                cmds.interpBlendShape(
                    self.node, e=True, ib=True,
                    removeTarget=[targetName, prevInbetweenWeight],
                    target=[baseMesh, index, targetMesh, value]
                )
            return True

        except Exception as e:
            logger.warning(f"Failed to update inbetween target '{targetName}': {e}")
            return False

    def setInbetweenTargetName(self, targetName: str, value: float, name: str) -> str | bool:
        """
        Set the display name of a specific inbetween shape for a given target.

        Args:
            targetName (str): The alias name of the blend shape target.
            value (float): The weight value of the inbetween shape.
            name (str): The name to assign to the inbetween shape.

        Returns:
            str: The assigned name if successful, False otherwise.
        """
        index = self.getTargetIndex(targetName)
        if index is None:
            logger.warning(f"Target '{targetName}' not found.")
            return False
        itemId = self._inbetweenItemId(value)
        try:
            groupPlug   = self._getPlug("inbetweenInfoGroup").elementByLogicalIndex(index)
            infoPlug    = groupPlug.child(self._attrInbetweenInfo)
            elementPlug = infoPlug.elementByLogicalIndex(itemId)
            if elementPlug.isNull:
                return False
            namePlug = elementPlug.child(self._attrInbetweenTargetName)
            cmds.setAttr(namePlug.name(), name, type="string")
            return name
        except Exception as e:
            logger.warning(f"Failed to set inbetween name for '{targetName}': {e}")
            return False

    def deleteInterpBlendShape(self) -> bool:
        """
        Delete the entire interpBlendShape node in Maya.

        Returns:
            bool: True if the node was deleted, False if it did not exist.
        """
        if cmds.objExists(self.node):
            try:
                cmds.delete(self.node)
                return True
            except Exception as e:
                logger.warning(f"Failed to delete node '{self.node}': {e}")
                return False
        return False

    def deleteTarget(self, targetName: str) -> bool:
        """
        Delete a target shape under the node.

        Args:
            targetName (str): The alias name of the target to delete.

        Returns:
            bool: True if successful, False otherwise.
        """
        if targetName in self.aliasDictCache:
            try:
                cmds.interpBlendShape(self.node, e=True, removeTarget=[targetName, 1])
                self.aliasDictCache.pop(targetName, None)
                return True
            except Exception as e:
                logger.warning(f"Failed to delete target '{targetName}': {e}")
        else:
            logger.warning(f"Target alias '{targetName}' not found in cache.")
        return False

    def deleteInbetween(self, targetName: str, weight: float) -> bool:
        """
        Delete an inbetween shape at the specified weight.

        Args:
            targetName (str): The alias of the parent target.
            weight (float): The weight value of the inbetween to delete.

        Returns:
            bool: True if successful, False otherwise.
        """
        weight = self._normalizeInbetweenWeight(weight)
        try:
            cmds.interpBlendShape(self.node, e=True, ib=True, removeTarget=[targetName, weight])
            if not self.setTargetValueLive(targetName, AttrName.TARGET_REBIND, True):
                logger.warning(
                    f"[Inbetween] Deleted target at weight {weight:.3f} but failed to mark '{targetName}' for rebind."
                )
            return True
        except Exception as e:
            logger.warning(f"Failed to delete inbetween for '{targetName}' at weight {weight}: {e}")
            return False

    # ─────────────────────────────────────────────
    # Surface Management
    # ─────────────────────────────────────────────

    def getDagPathFromPlug(self, plug: om.MPlug) -> str | None:
        """
        Retrieve the transform node name for the shape connected to the given plug.

        Args:
            plug (MPlug): A plug representing a shape node.

        Returns:
            str | None: The shortest unique DAG path to the transform, or None on failure.
        """
        return get_dag_path_from_plug(plug)

    def getSurfaceDriver(self, targetName: str) -> str | None:
        """
        Retrieve the name of the surface driver connected to the given target.

        Returns the surface name regardless of whether UV blend is enabled or not.
        The UV blend toggle controls whether the surface drives the target,
        but the surface assignment itself is always shown.

        Args:
            targetName (str): The alias name of the target.

        Returns:
            str | None: Transform name of the connected surface, or None if not connected.
        """
        try:
            index = self.getTargetIndex(targetName)
            if index is None:
                return None
            inputTargetPlug = self._inputTargetPlug.elementByLogicalIndex(0)
            inputTargetGroupPlug = inputTargetPlug.child(self._attrInputTargetGroup)
            groupElement = inputTargetGroupPlug.elementByLogicalIndex(index)
            surfaceId = groupElement.child(self._attrTargetSurfaceId).asInt()
            return self.getInputTargetSurface(surfaceId)
        except Exception:
            return None

    def getInputTargetSurface(self, index: int) -> str | None:
        """
        Retrieve the transform node connected to inputSurface at the specified logical index.

        Args:
            index (int): The logical index of the inputSurface element.

        Returns:
            str | None: The transform name, or None if not connected.
        """
        return get_input_target_surface(
            self._inputSurfacePlug,
            self._attrInputTargetSurface,
            self.getDagPathFromPlug,
            index,
        )

    def getAllInputTargetSurfaces(self) -> dict:
        """
        Gather all connected input surface transforms mapped to their logical indices.

        Returns:
            dict: Mapping of transform names to logical indices,
                  e.g. {"pSphere1": 0, "pCube1": 1}. Returns {"NONE": 0} if none found.
        """
        return get_all_input_target_surfaces(
            self._inputSurfacePlug,
            self._attrInputTargetSurface,
            self.getDagPathFromPlug,
            getUniqueName,
        )

    def getSurfaceSelection(self) -> list:
        """
        Retrieve MDagPath instances for all selected NURBS surfaces.

        Returns:
            list[MDagPath]: Selected NURBS surface dag paths.
        """
        selection       = om.MGlobal.getActiveSelectionList()
        surfaceDagPaths = []
        for i in range(selection.length()):
            dagPath = selection.getDagPath(i)
            if dagPath.node().hasFn(om.MFn.kTransform):
                try:
                    dagPath.extendToShape()
                except RuntimeError:
                    continue
            if dagPath.node().hasFn(om.MFn.kNurbsSurface):
                surfaceDagPaths.append(dagPath)
        return surfaceDagPaths

    def cleanupInputSurfacePlug(self, arrayPlug: om.MPlug) -> None:
        """
        Remove unconnected elements from the input surface array plug.

        Args:
            arrayPlug (MPlug): The array plug representing input surfaces.
        """
        numElements = arrayPlug.numElements()
        if numElements == 0:
            return
        toRemove = []
        for i in range(numElements):
            try:
                elementPlug = arrayPlug.elementByPhysicalIndex(i)
                childPlug   = elementPlug.child(self._attrInputTargetSurface)
                if not childPlug.isConnected:
                    toRemove.append(elementPlug.name())
            except Exception as e:
                logger.info(f"Failed to check plug at index {i}: {e}")
        for plugPath in toRemove:
            try:
                cmds.removeMultiInstance(plugPath, b=True)
            except Exception as e:
                logger.warning(f"Failed to remove {plugPath}: {e}")

    def addSurface(self, multiSurface: bool = True) -> tuple[int, str] | None:
        """
        Connect selected NURBS surfaces to this node's inputSurface multi-attribute.

        Args:
            multiSurface (bool): If True, connect all selected surfaces;
                                 if False, only the last selected. Defaults to True.

        Returns:
            tuple[int, str] | None: (logical index, surface name) of the last connected
                                     surface, or None if no surfaces were connected.
        """
        self.cleanupInputSurfacePlug(self._inputSurfacePlug)
        lastUsedIndex = self.getLastElementIndex(self._inputSurfacePlug)
        surfaceList   = self.getSurfaceSelection()

        if not surfaceList:
            logger.warning("No valid surfaces selected.")
            return None

        if not multiSurface:
            surfaceList = [surfaceList[-1]]

        currentIndex       = lastUsedIndex + 1
        lastConnectedIndex = None
        lastSurfaceName    = None

        try:
            cmds.undoInfo(openChunk=True)
            for dagPath in surfaceList:
                surfaceNode = om.MFnDependencyNode(dagPath.node())
                try:
                    srcPlug = surfaceNode.findPlug("worldSpace", False).elementByLogicalIndex(0)
                except Exception as e:
                    logger.warning(f"Failed to access worldSpace[0] on {dagPath.fullPathName()}: {e}")
                    continue

                alreadyConnected = False
                for i in range(self._inputSurfacePlug.numElements()):
                    elem       = self._inputSurfacePlug.elementByPhysicalIndex(i)
                    targetPlug = elem.child(self._attrInputTargetSurface)
                    if targetPlug.isConnected and any(p == srcPlug for p in targetPlug.connectedTo(True, False)):
                        logger.warning(f"Skipping {srcPlug.name()}: already connected.")
                        alreadyConnected = True
                        break
                if alreadyConnected:
                    continue

                destElem = self._inputSurfacePlug.elementByLogicalIndex(currentIndex)
                destPlug = destElem.child(self._attrInputTargetSurface)
                try:
                    attrPathName = f"{dagPath.fullPathName()}.{srcPlug.partialName(useFullAttributePath=True)}"
                    cmds.connectAttr(attrPathName, destPlug.name(), force=True)
                    lastConnectedIndex = currentIndex
                    lastSurfaceName    = self.getDagPathFromPlug(srcPlug)
                    currentIndex      += 1
                except Exception as e:
                    logger.warning(f"Failed to connect {attrPathName} to {destPlug.name()}: {e}")
        finally:
            cmds.undoInfo(closeChunk=True)

        if lastConnectedIndex is not None:
            logger.info(f"Connected surface at index {lastConnectedIndex}: {lastSurfaceName}")

        return (lastConnectedIndex, lastSurfaceName) if lastConnectedIndex is not None else None

    def replaceSurface(self, surfaceId: int) -> str | bool:
        """
        Replace the connection at the given surfaceId with the last selected surface.

        Args:
            surfaceId (int): Logical index of the surface to replace.

        Returns:
            str: The new surface DAG path name if successful, False otherwise.
        """
        surfaceList = self.getSurfaceSelection()
        if not surfaceList:
            logger.warning("No valid surfaces selected.")
            return False

        dagPath = surfaceList[-1]
        depNode = om.MFnDependencyNode(dagPath.node())
        srcPlug = depNode.findPlug("worldSpace", False).elementByLogicalIndex(0)

        for i in range(self._inputSurfacePlug.numElements()):
            elem       = self._inputSurfacePlug.elementByPhysicalIndex(i)
            targetPlug = elem.child(self._attrInputTargetSurface)
            if targetPlug.isConnected and any(p == srcPlug for p in targetPlug.connectedTo(True, False)):
                logger.warning(f"Skipping {srcPlug.name()}: already connected.")
                return False

        try:
            elem       = self._inputSurfacePlug.elementByLogicalIndex(surfaceId)
            targetPlug = elem.child(self._attrInputTargetSurface)
        except Exception as e:
            logger.warning(f"Invalid surfaceId {surfaceId}: {e}")
            return False

        if not self.removeSurface(surfaceId):
            logger.warning(f"Could not remove existing connections for ID {surfaceId}.")
            return False

        surfaceName = self.getDagPathFromPlug(srcPlug)

        def _reconnect():
            try:
                cmds.connectAttr(srcPlug.name(), targetPlug.name(), force=True)
            except Exception as e:
                logger.warning(f"Failed to reconnect surface {dagPath.fullPathName()}: {e}")

        cmds.evalDeferred(_reconnect)
        return surfaceName

    def removeSurface(self, surfaceId: int) -> bool:
        """
        Remove the connection into the inputTargetSurface plug at the given index.

        Args:
            surfaceId (int): Logical index of the surface to remove.

        Returns:
            bool: True if the connection was removed or was already disconnected.
        """
        try:
            elem       = self._inputSurfacePlug.elementByLogicalIndex(surfaceId)
            targetPlug = elem.child(self._attrInputTargetSurface)
        except Exception as e:
            logger.warning(f"Invalid surfaceId {surfaceId}: {e}")
            return False

        if not targetPlug.isConnected:
            return True

        for srcPlug in targetPlug.connectedTo(True, False):
            try:
                cmds.disconnectAttr(srcPlug.name(), targetPlug.name())
            except Exception as e:
                logger.warning(f"Failed to disconnect {srcPlug.name()} → {targetPlug.name()}: {e}")
                return False
        return True

    # ─────────────────────────────────────────────
    # Attribute Operations
    # ─────────────────────────────────────────────

    def renameNode(self, name: str) -> str | bool:
        """
        Rename the current node.

        Args:
            name (str): The desired new name for the node.

        Returns:
            str: The new name if successful, False otherwise.
        """
        try:
            newName    = cmds.rename(self.node, name)
            self.node  = newName
            return newName
        except Exception as e:
            logger.warning(f"Failed to rename '{self.node}' to '{name}': {e}")
            return False

    def keyActions(self, attrName: str, actionId=ActionID.KEYCURRENT) -> bool:
        """
        Perform a keyframe action on a specific attribute.

        Args:
            attrName (str): The attribute name (without node prefix).
            actionId (ActionID): Action to perform — KEYCURRENT, KEYZERO, KEYONE, RESET, REMOVEKEY.

        Returns:
            bool: True if successful, False otherwise.
        """
        attr = f"{self.node}.{attrName}"
        if not cmds.objExists(attr):
            return False

        if actionId == ActionID.KEYCURRENT:
            return self.keyCurrentAction(attr)

        elif actionId in (ActionID.KEYZERO, ActionID.RESET):
            try:
                cmds.setAttr(attr, 0)
            except Exception:
                return False
            if actionId == ActionID.RESET:
                return True
            return self.keyCurrentAction(attr)

        elif actionId == ActionID.KEYONE:
            cmds.setAttr(attr, 1)
            return self.keyCurrentAction(attr)

        elif actionId == ActionID.REMOVEKEY:
            currentFrame = cmds.currentTime(query=True)
            return cmds.cutKey(self.node, time=(currentFrame, currentFrame), attribute=attrName)

        return False

    def keyCurrentAction(self, attr: str) -> bool:
        """
        Set a keyframe on the specified attribute at the current time.

        Args:
            attr (str): The full attribute path (e.g. "myNode.weight[0]").

        Returns:
            bool: True if the keyframe was set successfully.
        """
        return cmds.setKeyframe(attr)

    def lockAttr(self, targetName: str, lock: bool) -> None:
        """
        Lock or unlock an attribute.

        Args:
            targetName (str): The attribute name (without node prefix).
            lock (bool): True to lock, False to unlock.
        """
        cmds.setAttr(f"{self.node}.{targetName}", lock=lock)

    def disconnectAttr(self, targetName: str) -> None:
        """
        Disconnect the input connection from the given attribute.

        Args:
            targetName (str): The attribute name (without node prefix).
        """
        attr       = f"{self.node}.{targetName}"
        sourcePlug = cmds.listConnections(attr, p=True, d=False, s=True)
        if sourcePlug:
            cmds.disconnectAttr(sourcePlug[0], attr)

    def rebindAll(self) -> None:
        """Rebind all targets by setting the rebind attribute."""
        cmds.setAttr(f"{self.node}.rebind", 1)

    # ─────────────────────────────────────────────
    # Vertex Weight Operations
    # ─────────────────────────────────────────────

    def getBaseWeights(self, vertexId: int, geomIndex: int) -> float | None:
        """
        Retrieve the base weight for a given vertex on a specific geometry.

        Args:
            vertexId (int): The vertex ID.
            geomIndex (int): The logical geometry index.

        Returns:
            float | None: The base weight value, or None on failure.
        """
        return get_base_weight(self._inputTargetPlug, self.fnNode, vertexId, geomIndex)

    def getTargetVertexWeights(self, targetName: str, vertexId: int, geomIndex: int) -> float | None:
        """
        Retrieve the target weight for a specific vertex on a given target and geometry.

        Args:
            targetName (str): The alias name of the target.
            vertexId (int): The vertex ID.
            geomIndex (int): The logical geometry index.

        Returns:
            float | None: The weight value, or None on failure.
        """
        return get_target_vertex_weight(
            self._inputTargetPlug,
            self._attrInputTargetGroup,
            self.fnNode,
            self.getTargetIndex,
            targetName,
            vertexId,
            geomIndex,
        )

    def setBaseWeight(self, vertexId: int, geomIndex: int, value: float) -> bool:
        """
        Set the base weight for a given vertex on a specific geometry.

        Args:
            vertexId (int): The vertex ID.
            geomIndex (int): The logical geometry index.
            value (float): The weight value to assign.

        Returns:
            bool: True if successful, False otherwise.
        """
        return set_base_weight(self._inputTargetPlug, self.fnNode, vertexId, geomIndex, value)

    def setTargetVertexWeight(self, targetName: str, vertexId: int,
                              geomIndex: int, value: float, normalize: bool = False) -> bool:
        """
        Set the weight for a specific vertex on a target, with optional normalization.

        Args:
            targetName (str): Name of the target shape.
            vertexId (int): Index of the vertex.
            geomIndex (int): Geometry index in the interpBlendShape.
            value (float): Weight value to assign.
            normalize (bool): If True, normalize sibling weights. Defaults to False.

        Returns:
            bool: True on success, False on failure.
        """
        return set_target_vertex_weight(
            self._inputTargetPlug,
            self._attrInputTargetGroup,
            self.fnNode,
            self.getTargetIndex,
            targetName,
            vertexId,
            geomIndex,
            value,
            normalize=normalize,
        )

    def normalizeTargetWeight(self, vertexId: int, paintIndex: int,
                              paintedWeight: float, inputTargetGroupPlug: om.MPlug) -> bool:
        """
        Normalize target weights for a given vertex after a weight has been painted.

        Redistributes the remaining weight (1.0 - paintedWeight - locked weights)
        across all other targets with normalization enabled, excluding locked targets.

        Args:
            vertexId (int): The index of the vertex being painted.
            paintIndex (int): Logical index of the target that was painted.
            paintedWeight (float): The weight value that was just painted.
            inputTargetGroupPlug (MPlug): Plug for inputTarget[geomIndex].inputTargetGroup.

        Returns:
            bool: True if normalization was performed, False if no normalization group found.
        """
        return normalize_target_weight(self.fnNode, vertexId, paintIndex, paintedWeight, inputTargetGroupPlug)

    # ─────────────────────────────────────────────
    # Paint Operations
    # ─────────────────────────────────────────────

    def selectPaintableBaseMesh(self) -> bool:
        """
        Select base meshes eligible for painting.

        If any currently selected objects match the base mesh list, selects only those.
        Otherwise selects all base meshes. NURBS curves are filtered out.

        Returns:
            bool: True if a valid paintable selection was made, False otherwise.
        """
        return select_paintable_base_mesh(self.getBaseMesh())

    def paintBaseWeight(self) -> None:
        """
        Activate the Artisan tool for painting base weights on the selected base mesh.
        """
        paint_base_weight(self.node, self.getBaseMesh())

    def paintTargetWeight(self, index: int) -> None:
        """
        Activate the Artisan tool for painting target weights.

        Args:
            index (int): Index of the target shape to paint weights for.
        """
        paint_target_weight(self.node, index, self.getBaseMesh())

    def copyWeight(self, sourceTarget: int, destinationTarget: int, surfaceAssociation: int) -> None:
        """
        Copy weights from one target to another.

        Args:
            sourceTarget (int): Source target index.
            destinationTarget (int): Destination target index.
            surfaceAssociation (int): Surface association mode.
        """
        copy_weight(self.node, sourceTarget, destinationTarget, surfaceAssociation)

    def mirrorWeight(self, destinationTarget: int, mirrorMode: int,
                     surfaceAssociation: int, mirrorInverse: bool) -> None:
        """
        Mirror weights to a destination target.

        Args:
            destinationTarget (int): Destination target index.
            mirrorMode (int): Mirror mode.
            surfaceAssociation (int): Surface association mode.
            mirrorInverse (bool): Whether to invert the mirrored weights.
        """
        mirror_weight(self.node, destinationTarget, mirrorMode, surfaceAssociation, mirrorInverse)

    def flipWeight(self, destinationTarget: int, mirrorMode: int, surfaceAssociation: int) -> None:
        """
        Flip weights on a destination target.

        Args:
            destinationTarget (int): Destination target index.
            mirrorMode (int): Mirror mode.
            surfaceAssociation (int): Surface association mode.
        """
        flip_weight(self.node, destinationTarget, mirrorMode, surfaceAssociation)

    def editTargetShape(self, destinationShapes: str | list[str], mirrorMode: str = "YZ",
                        surfaceAssociation: str = "closestPoint",
                        mirrorInverse: bool = False, flipTarget: bool = False) -> bool:
        """
        Mirror or flip connected target geometry using the interpBlendShapeEdit command.

        Args:
            destinationShapes (str | list[str]): Target alias or one or more connected
                target DAG paths to edit.
            mirrorMode (str): One of "XY", "YZ", or "XZ".
            surfaceAssociation (str): Matching mode for mirrored lookup.
                Valid values are "closestComponent", "closestPoint",
                "closestUVGlobal", and "closestUVShellCenter".
            mirrorInverse (bool): If True, mirror from negative to positive.
            flipTarget (bool): If True, flip both sides instead of mirroring one side.

        Returns:
            bool: True if at least one command succeeded, False otherwise.
        """
        return edit_target_shape(
            self.node,
            destinationShapes,
            mirror_mode=mirrorMode,
            surface_association=surfaceAssociation,
            mirror_inverse=mirrorInverse,
            flip_target=flipTarget,
        )


