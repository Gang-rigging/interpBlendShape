"""
maya_utils.py

Utility functions for Maya UI integration, e.g., getting Maya main window as a QWidget,
plugin loading helper functions, etc.
"""
from PySide2 import QtWidgets
from enums import NodeTypeID
import maya.OpenMayaUI as omui
import maya.api.OpenMayaAnim as oma
import maya.api.OpenMaya as om
import shiboken2
import platform
import maya.cmds as cmds
import re

from logger import getLogger
logger = getLogger("InterpBlendShape")

def getMayaMainWindow():
    """
    Return Maya's main window as a QWidget instance.
    """
    ptr = omui.MQtUtil.mainWindow()
    return shiboken2.wrapInstance(int(ptr), QtWidgets.QWidget)


def getPluginExtension():
    """
    Return the platform-specific plugin file extension.
    """
    system = platform.system()
    if system == "Windows":
        return ".mll"
    elif system == "Darwin":
        return ".bundle"
    elif system == "Linux":
        return ".so"
    else:
        return ""


def loadPlugin(pluginBaseName):
    """
    Load a plugin by base name with correct platform extension.

    Args:
        pluginBaseName (str): Plugin name without extension.

    Returns:
        bool: True if plugin is already loaded or successfully loaded, False otherwise.
    """
    pluginExt = getPluginExtension()
    pluginFile = pluginBaseName + pluginExt

    if cmds.pluginInfo(pluginBaseName, query=True, loaded=True):
        logger.info(f"Plugin '{pluginBaseName}' is already loaded.")
        return True

    try:
        cmds.loadPlugin(pluginFile)
        logger.info(f"Successfully loaded plugin '{pluginFile}'.")
        return True
    except RuntimeError as e:
        logger.error(f"Failed to load plugin '{pluginFile}': {e}.")
        return False

def getUniqueName(base, existingDict):
    """
    Generate a unique name by appending or incrementing a numeric suffix.

    Args:
        base (str): The desired base name.
        existingDict (dict or set): Existing names to avoid.

    Returns:
        str: A unique name not present in existingDict.
    """
    if isinstance(existingDict, dict):
        existing = set(existingDict.keys())
    else:
        existing = set(existingDict)

    match = re.match(r"^(.*?)(?:[_-]?(\d+))?$", base)
    if match:
        prefix = match.group(1)
        start_num = int(match.group(2)) if match.group(2) else 1
    else:
        prefix = base
        start_num = 1

    new_name = base
    while new_name in existing:
        new_name = f"{prefix}_{start_num}"
        start_num += 1

    return new_name


def normalizeName(name):
    """
    Normalize a name string by replacing one or more spaces with a single underscore.

    If the name already contains underscores, it is returned unchanged (except for leading/trailing spaces).

    Args:
        name (str): The input string to normalize.

    Returns:
        str: The normalized name with spaces replaced by underscores.
    """
    if '_' in name:
        return name.strip()
    return re.sub(r'\s+', '_', name.strip())

def getTransformFromSelection():
    """
    Get full path names of transform nodes from the current selection in Maya.

    If a selected object is a shape node (e.g., mesh or NURBS curve), the function returns
    its parent transform node instead.

    Returns:
        list[str]: List of full path names of transform nodes.
    """
    selection = om.MGlobal.getActiveSelectionList()
    transformNames = []

    for i in range(selection.length()):
        obj = selection.getDependNode(i)
        if not obj.hasFn(om.MFn.kDagNode):
            logger.warning(f"Selection item: {obj.name()} is not a DAG node, skipping.")
            continue
        dagPath = selection.getDagPath(i)

        # If it's a shape node, go up to its parent transform
        if dagPath.apiType() in [om.MFn.kMesh, om.MFn.kNurbsCurve]:
            dagPath.pop()

        transformNames.append(dagPath.fullPathName())

    return transformNames

def deferRemoveMultiInstance(plugPath):
    """
    Safely remove a disconnected multi-attribute element using Maya's evalDeferred,
    to avoid crashes when called during undo or DG callbacks.

    Args:
        plugPath (str): The full plug name (e.g., 'myNode.inputSurface[2]')
    """

    def _remove():
        if cmds.objExists(plugPath):
            try:
                cmds.removeMultiInstance(plugPath, b=True)
                logger.info(f"[deferRemoveMultiInstance] Removed: {plugPath}")
            except Exception as e:
                logger.info(f"[deferRemoveMultiInstance] Failed: {plugPath} | Error: {e}")

    cmds.evalDeferred(_remove)

def getCurrentFrame() -> float:
    """
    Retrieve the current time/frame from Maya.

    Returns:
        float: The current frame value as a floating‑point number.
    """
    return oma.MAnimControl.currentTime().value

def isInterpBlendShape(depNode):
    """
    Check whether the given dependency node is an InterpBlendShape node.

    Args:
        depNode (om.MFnDependencyNode): The dependency node to check.

    Returns:
        bool: True if the node's type ID matches the InterpBlendShape node type, False otherwise.
    """
    return depNode.typeId.id() == NodeTypeID.INTERP_BLENDSHAPE

def getNodeFromSelection():
    """
    Retrieve the first 'interpBlendShape' node connected to the first selected DAG object in Maya.
    If the selected object *is* an interpBlendShape node itself, return it directly.

    Returns:
        str or None: The name of the found interpBlendShape node, or None if not found.
    """
    sel = om.MGlobal.getActiveSelectionList()
    if sel.length() == 0:
        om.MGlobal.displayWarning("No object selected.")
        return None

    mobj = sel.getDependNode(0)
    # Check if selected node itself is interpBlendShape
    depNodeFn = om.MFnDependencyNode(mobj)
    if isInterpBlendShape(depNodeFn):
        return depNodeFn.name()

    # If selected node is not interpBlendShape, check its history
    if not mobj.hasFn(om.MFn.kDagNode):
        return None

    dagPath = sel.getDagPath(0)
    history = cmds.listHistory(dagPath.fullPathName(), pruneDagObjects=True) or []

    for node in history:
        if cmds.nodeType(node) == "interpBlendShape":
            return node

    return None
