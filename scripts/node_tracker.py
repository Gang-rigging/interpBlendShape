from contextlib import contextmanager

import maya.api.OpenMaya as om
import maya.api.OpenMayaAnim as oma
import maya.cmds as cmds
from PySide2 import QtCore

from enums import AttrName, CallbackType
from logger import getLogger
from maya_utils import deferRemoveMultiInstance, isInterpBlendShape

logger = getLogger("InterpBlendShape")

class CallbackSuppressor:
    """Temporarily suppress time or dirty-plug callbacks for a single event cycle."""

    def __init__(self):
        self.suppressTimeCallback = False
        self.suppressDirtyPlug    = False

    def temporarilySuppressTime(self):
        self.suppressTimeCallback = True
        QtCore.QTimer.singleShot(200, self.clearTimeSuppression)

    def clearTimeSuppression(self):
        self.suppressTimeCallback = False

    def temporarilySuppressDirtyPlug(self):
        self.suppressDirtyPlug = True
        QtCore.QTimer.singleShot(0, self.clearDirtyPlugSuppression)

    def clearDirtyPlugSuppression(self):
        self.suppressDirtyPlug = False

class NodeTracker:
    """
    Track a single Maya node, registering callbacks for attribute changes,
    name changes, and dirty-plug events, dispatching them to a user-provided function.
    """

    def __init__(self, nodeName, callbackFn, suppressor=None):
        self.nodeName                 = nodeName
        self.callbackFn               = callbackFn
        self.suppressor               = suppressor
        self._suppressAttrSetOrRename = False
        self.paused                   = False
        self.callbackId               = None
        self.nameChangedCallbackId    = None
        self.dirtyPlugCallbackId      = None
        self._registerCallbacks()

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def unregister(self):
        for cbId in (self.callbackId, self.nameChangedCallbackId, self.dirtyPlugCallbackId):
            if cbId is not None:
                try:
                    om.MMessage.removeCallback(cbId)
                except Exception:
                    pass
        self.callbackId            = None
        self.nameChangedCallbackId = None
        self.dirtyPlugCallbackId   = None

    def _clearSuppression(self):
        self._suppressAttrSetOrRename = False

    def _getMObject(self):
        sel = om.MSelectionList()
        sel.add(self.nodeName)
        return sel.getDependNode(0)

    def _registerCallbacks(self):
        try:
            mobj = self._getMObject()
        except Exception as e:
            logger.warning(f"[NodeTracker] Cannot find node '{self.nodeName}': {e}")
            return

        self.callbackId = om.MNodeMessage.addAttributeChangedCallback(
            mobj, self._attributeChanged
        )
        self.nameChangedCallbackId = om.MNodeMessage.addNameChangedCallback(
            mobj, self._onNodeNameChanged
        )
        self.dirtyPlugCallbackId = om.MNodeMessage.addNodeDirtyPlugCallback(
            mobj, self._onPlugDirty
        )

    def _attributeChanged(self, msg, plug, sourcePlug, clientData):
        if self.paused:
            return

        dispatch = {
            om.MNodeMessage.kAttributeArrayAdded:   (self._onAttributeAdded,            (plug,)),
            om.MNodeMessage.kAttributeArrayRemoved: (self._onAttributeRemoved,           (plug,)),
            om.MNodeMessage.kAttributeRenamed:      (self._onAttributeRenamed,           (plug,)),
            om.MNodeMessage.kAttributeSet:          (self._onAttributeSet,               (plug,)),
            om.MNodeMessage.kAttributeLocked:       (self._onAttributeLockStatusChanged, (plug,)),
            om.MNodeMessage.kAttributeUnlocked:     (self._onAttributeLockStatusChanged, (plug,)),
            om.MNodeMessage.kConnectionMade:        (self._onAttributeConnectionChanged, (plug, sourcePlug)),
            om.MNodeMessage.kConnectionBroken:      (self._onAttributeConnectionChanged, (plug, sourcePlug)),
        }

        for flag, (handler, args) in dispatch.items():
            if msg & flag:
                try:
                    handler(*args)
                except Exception as e:
                    logger.error(f"Exception in attributeChanged callback: {e}")

    def _onAttributeLockStatusChanged(self, plug):
        if self._suppressAttrSetOrRename:
            return
        attrName = om.MFnAttribute(plug.attribute()).name
        if attrName not in (AttrName.WEIGHT, AttrName.ENVELOPE):
            return
        logicIndex = plug.logicalIndex() if attrName == AttrName.WEIGHT else -1
        self.callbackFn(attrName, logicIndex, type=CallbackType.ATTRIBUTE_LOCK, value=plug.isLocked)

    def _onAttributeAdded(self, plug):
        attrName   = om.MFnAttribute(plug.attribute()).name
        logicIndex = plug.logicalIndex()

        self._suppressAttrSetOrRename = True
        QtCore.QTimer.singleShot(0, self._clearSuppression)

        if attrName == AttrName.WEIGHT:
            self.callbackFn(attrName, logicIndex, type=CallbackType.ATTRIBUTE_ARRAYADD)
            return

        if attrName == AttrName.INBETWEEN_INFO and plug.isElement:
            arrayPlug = plug.array()
            if arrayPlug.isChild:
                self.callbackFn(
                    attrName, arrayPlug.parent().logicalIndex(),
                    type=CallbackType.ATTRIBUTE_ARRAYADD,
                    value=plug.logicalIndex()
                )

    def _onAttributeRemoved(self, plug):
        attrName   = om.MFnAttribute(plug.attribute()).name
        logicIndex = plug.logicalIndex()

        self._suppressAttrSetOrRename = True
        QtCore.QTimer.singleShot(0, self._clearSuppression)

        def emit(idx, **kw):
            self.callbackFn(attrName, idx, type=CallbackType.ATTRIBUTE_ARRAYREMOVED, **kw)

        if attrName == AttrName.WEIGHT:
            emit(logicIndex)
        elif attrName == AttrName.INBETWEEN_INFO and plug.isElement:
            arrayPlug = plug.array()
            if arrayPlug.isChild:
                emit(arrayPlug.parent().logicalIndex(), value=plug.logicalIndex())

    def _onAttributeRenamed(self, plug):
        if self._suppressAttrSetOrRename:
            return
        attrName = om.MFnAttribute(plug.attribute()).name
        if attrName == AttrName.WEIGHT:
            self.callbackFn(
                attrName, plug.logicalIndex(),
                type=CallbackType.ATTRIBUTE_RENAMED,
                newName=plug.partialName(useAlias=True)
            )

    def _onAttributeSet(self, plug):
        if self._suppressAttrSetOrRename:
            return

        attrName = om.MFnAttribute(plug.attribute()).name

        def emit(idx, **kw):
            self.callbackFn(attrName, idx, type=CallbackType.ATTRIBUTE_SET, **kw)

        if attrName == AttrName.WEIGHT:
            emit(plug.logicalIndex(), value=plug.asDouble())

        elif attrName == AttrName.ENVELOPE:
            emit(-1, value=plug.asDouble())

        elif attrName == AttrName.INBETWEEN_TARGET_NAME:
            parent      = plug.parent()
            arrayParent = parent.array()
            if parent.isElement and arrayParent.isChild:
                emit(
                    arrayParent.parent().logicalIndex(),
                    value=parent.logicalIndex(),
                    newName=plug.asString()
                )

        elif plug.isChild and AttrName.isTargetAttr(attrName):
            readerMap = {
                AttrName.TARGET_SURFACE_ID:   plug.asInt,
                AttrName.TARGET_BLEND_UV:     plug.asBool,
                AttrName.TARGET_BLEND_BEZIER: plug.asBool,
                AttrName.TARGET_BLEND_LIVE:   plug.asBool,
                AttrName.TARGET_CACHED:       plug.asBool,
            }
            emit(plug.parent().logicalIndex(), value=readerMap.get(attrName, plug.asDouble)())

        elif AttrName.isPaintAttr(attrName):
            emit(plug.parent().logicalIndex(), value=plug.asBool())

    def _onAttributeConnectionChanged(self, plug, sourcePlug):
        if self.suppressor:
            self.suppressor.temporarilySuppressTime()

        attrName    = om.MFnAttribute(plug.attribute()).name
        isConnected = plug.isConnected
        inputConns  = plug.connectedTo(True, False) if isConnected else []
        safePlug    = om.MPlug(plug)

        cbType        = CallbackType.ATTRIBUTE_DISCONNECT
        isUserConnect = False
        payload       = {"value": None, "keyframes": []}

        for ip in inputConns:
            node = ip.node()
            if not (node.hasFn(om.MFn.kAnimCurve) or node.hasFn(om.MFn.kBlendWeighted)):
                payload["value"] = ip.asDouble()
                isUserConnect    = True
                cbType           = CallbackType.ATTRIBUTE_CONNECT
                break

        if attrName in (AttrName.WEIGHT, AttrName.ENVELOPE):
            logicIndex = plug.logicalIndex() if attrName == AttrName.WEIGHT else -1

            if isConnected and not isUserConnect:
                def _restoreKeyFromAnimCurve():
                    keyframes = []
                    hasSDK    = False
                    if safePlug.isNull:
                        logger.warning("plug is invalid inside evalDeferred")
                        return
                    for animNode in oma.MAnimUtil.findAnimation(safePlug):
                        anim = oma.MFnAnimCurve(animNode)
                        if anim.isTimeInput:
                            for i in range(anim.numKeys):
                                v = anim.input(i).value
                                if v not in keyframes:
                                    keyframes.append(v)
                        elif anim.isUnitlessInput:
                            hasSDK = anim.numKeys > 0
                    payload["hasSDK"]    = hasSDK
                    payload["keyframes"] = keyframes
                    self.callbackFn(attrName, logicIndex, cbType, **payload)
                cmds.evalDeferred(_restoreKeyFromAnimCurve)
            else:
                self.callbackFn(attrName, logicIndex, cbType, **payload)

        elif attrName == AttrName.INPUT_TARGET_SURFACE:
            try:
                logicIndex             = plug.parent().logicalIndex()
                payload["surfaceName"] = om.MFnDagNode(sourcePlug.node()).getPath().pop().partialPathName()
            except Exception:
                logicIndex             = -1
                payload["surfaceName"] = ""

            self.callbackFn(attrName, logicIndex, cbType, **payload)

            if not isUserConnect:
                deferRemoveMultiInstance(plug.parent().name())

    def _onNodeNameChanged(self, obj, oldName, clientData):
        self.callbackFn(
            "DUMMY", -1,
            type=CallbackType.NODE_RENAMED,
            oldName=oldName,
            newName=om.MFnDependencyNode(obj).name()
        )

    def _onPlugDirty(self, node, dirtyPlug, clientData):
        if self._suppressAttrSetOrRename:
            return
        if self.suppressor:
            if self.suppressor.suppressTimeCallback or self.suppressor.suppressDirtyPlug:
                return
        if not dirtyPlug.isConnected:
            return

        attrName = om.MFnAttribute(dirtyPlug.attribute()).name
        if not AttrName.isWeightOrEnvelopeAttr(attrName):
            return

        index     = dirtyPlug.logicalIndex() if attrName == AttrName.WEIGHT else -1
        keyframes = []
        for animNode in oma.MAnimUtil.findAnimation(dirtyPlug):
            animCurve = oma.MFnAnimCurve(animNode)
            if animCurve.isTimeInput:
                keyframes.extend(
                    v for v in (animCurve.input(i).value for i in range(animCurve.numKeys))
                    if v not in keyframes
                )

        self.callbackFn(attrName, index, type=CallbackType.ATTRIBUTE_DIRTYPLUG, keyframes=keyframes)

class NodeTrackerManager:
    """Manage NodeTracker instances and their associated UI items for multiple Maya nodes."""

    def __init__(self, suppressor=None):
        self._trackers  = {}
        self._items     = {}
        self.suppressor = suppressor

    def register(self, nodeName, item, onAttrChangedCallback):
        tracker      = NodeTracker(nodeName, None, self.suppressor)
        tracker.item = item

        def callbackWrapper(attrName, index, type=None, **payload):
            onAttrChangedCallback(tracker.nodeName, attrName, index, type, payload)

        tracker.callbackFn       = callbackWrapper
        self._trackers[nodeName] = tracker
        self._items[nodeName]    = item

    def unregister(self, nodeName):
        tracker = self._trackers.pop(nodeName, None)
        if tracker:
            tracker.unregister()
        self._items.pop(nodeName, None)

    def getItem(self, nodeName):
        return self._items.get(nodeName)

    def getAllItems(self):
        return self._items.values()

    def renameItem(self, oldName, newName, item):
        self._items.pop(oldName, None)
        self._items[newName] = item
        if oldName in self._trackers:
            tracker          = self._trackers.pop(oldName)
            tracker.nodeName = newName
            self._trackers[newName] = tracker

    def pause(self, nodeName=None):
        targets = [self._trackers[nodeName]] if nodeName else self._trackers.values()
        for tracker in targets:
            tracker.pause()

    def resume(self, nodeName=None):
        targets = [self._trackers[nodeName]] if nodeName else self._trackers.values()
        for tracker in targets:
            tracker.resume()

    @contextmanager
    def suspended(self, nodeName=None):
        """Context manager — temporarily suspend callbacks for one or all nodes."""
        self.pause(nodeName)
        try:
            yield
        finally:
            self.resume(nodeName)

    def clear(self):
        for tracker in self._trackers.values():
            tracker.unregister()
        self._trackers.clear()
        self._items.clear()

class SceneNodeMonitor(QtCore.QObject):
    """
    Monitor scene-level Maya events and specific node lifecycle for a given node type.

    Emits signals for node addition/removal, scene open/save, time changes, and keyframe edits.
    """
    nodeAdded        = QtCore.Signal(str)
    nodeRemoved      = QtCore.Signal(str)
    sceneOpened      = QtCore.Signal()
    sceneSaved       = QtCore.Signal()
    timeChanged      = QtCore.Signal(float)
    keyframeEdit     = QtCore.Signal(str, str, int, int, bool, list)
    selectionChanged = QtCore.Signal(list)

    def __init__(self, nodeType, trackerManager=None, suppressor=None):
        super().__init__()
        self.nodeType        = nodeType
        self.trackerManager  = trackerManager
        self.suppressor      = suppressor
        self._suppress       = False
        self._callbacks      = []
        self.selectionCallbackId = None

        self._registerNodeCallbacks()
        self._registerSceneCallbacks()
        self._registerTimeCallback()
        self._registerAnimCurveCallback()

    def _registerNodeCallbacks(self):
        for fn, handler in (
            (om.MDGMessage.addNodeAddedCallback,   self._onNodeAdded),
            (om.MDGMessage.addNodeRemovedCallback, self._onNodeRemoved),
        ):
            try:
                self._callbacks.append(fn(handler, self.nodeType))
            except Exception as e:
                logger.debug(f"[SceneNodeMonitor] Failed to register node callback: {e}")

    def _registerSceneCallbacks(self):
        msgs = (
            om.MSceneMessage.kBeforeOpen,
            om.MSceneMessage.kBeforeImport,
            om.MSceneMessage.kBeforeReference,
            om.MSceneMessage.kBeforeNew,
            om.MSceneMessage.kAfterOpen,
            om.MSceneMessage.kAfterImport,
            om.MSceneMessage.kAfterReference,
            om.MSceneMessage.kAfterNew,
        )
        handlers = {
            **dict.fromkeys(msgs[:4], self._onBeforeSceneChange),
            **dict.fromkeys(msgs[4:], self._onAfterSceneChange),
        }
        for msg, handler in handlers.items():
            try:
                self._callbacks.append(om.MSceneMessage.addCallback(msg, handler))
            except Exception as e:
                logger.debug(f"[SceneNodeMonitor] Failed to register scene callback: {e}")

        try:
            self._callbacks.append(
                om.MSceneMessage.addCallback(om.MSceneMessage.kBeforeSave, self._onBeforeSave)
            )
        except Exception as e:
            logger.debug(f"[SceneNodeMonitor] Failed to register save callback: {e}")

    def _registerTimeCallback(self):
        try:
            self._callbacks.append(
                om.MDGMessage.addTimeChangeCallback(self._onDGTimeChanged, None)
            )
        except Exception as e:
            logger.debug(f"[SceneNodeMonitor] Failed to register time callback: {e}")

    def _registerAnimCurveCallback(self):
        try:
            self._callbacks.append(
                oma.MAnimMessage.addAnimCurveEditedCallback(self._onAnimKeyframeEdit)
            )
        except Exception as e:
            logger.debug(f"[SceneNodeMonitor] Failed to register animCurve callback: {e}")

    def registerSelectionCallback(self):
        if not self.selectionCallbackId:
            self.selectionCallbackId = om.MEventMessage.addEventCallback(
                "SelectionChanged", lambda *args: self.selectionChangedCallback(*args)
            )

    def clearSelectionCallback(self):
        if self.selectionCallbackId:
            om.MMessage.removeCallback(self.selectionCallbackId)
            self.selectionCallbackId = None

    def _onBeforeSceneChange(self, *args):
        self._suppress = True

    def _onAfterSceneChange(self, *args):
        self._suppress = False
        self.sceneOpened.emit()

    def _onBeforeSave(self, *args):
        self.sceneSaved.emit()

    def _onNodeAdded(self, mobject, *args):
        if self._suppress:
            return
        if mobject.hasFn(om.MFn.kDependencyNode):
            depFn = om.MFnDependencyNode(mobject)
            if isInterpBlendShape(depFn):
                self.nodeAdded.emit(depFn.name())

    def _onNodeRemoved(self, mobject, *args):
        self.nodeRemoved.emit(om.MFnDependencyNode(mobject).name())

    def _onDGTimeChanged(self, currentTime, *_):
        if self.suppressor:
            self.suppressor.temporarilySuppressDirtyPlug()
        if self.suppressor and self.suppressor.suppressTimeCallback:
            return
        try:
            if not oma.MAnimControl.isPlaying():
                self.timeChanged.emit(currentTime.value)
        except Exception as e:
            logger.debug(f"[SceneNodeMonitor] DG timeChange error: {e}")

    def _onAnimKeyframeEdit(self, objArray, clientData):
        if self.suppressor and self.suppressor.suppressTimeCallback:
            return

        for mobj in objArray:
            if not mobj.hasFn(om.MFn.kAnimCurve):
                continue

            anim      = oma.MFnAnimCurve(mobj)
            outPlug   = anim.findPlug("output", True)
            destPlugs = outPlug.connectedTo(False, True)

            if len(destPlugs) > 1:
                logger.warning(f"{outPlug.name()}.output can't connect to multiple plugs.")

            for destPlug in destPlugs:
                destNode = destPlug.node()
                depNode  = om.MFnDependencyNode(destNode)

                if destNode.hasFn(om.MFn.kPluginDeformerNode) and isInterpBlendShape(depNode):
                    attrName   = om.MFnAttribute(destPlug.attribute()).name
                    nodeName   = depNode.name()
                    logicIndex = destPlug.logicalIndex() if attrName == AttrName.WEIGHT else -1

                elif destNode.hasFn(om.MFn.kBlendWeighted):
                    bwOut   = om.MFnDependencyNode(destNode).findPlug("output", True)
                    bwDests = bwOut.connectedTo(False, True)
                    if len(bwDests) != 1:
                        if len(bwDests) > 1:
                            logger.warning(f"{bwOut.name()}.output can't connect to multiple plugs.")
                        continue
                    bwPlug    = bwDests[0]
                    bwNode    = bwPlug.node()
                    bwDepNode = om.MFnDependencyNode(bwNode)
                    if not (bwNode.hasFn(om.MFn.kPluginDeformerNode) and isInterpBlendShape(bwDepNode)):
                        continue
                    attrName   = om.MFnAttribute(bwPlug.attribute()).name
                    nodeName   = bwDepNode.name()
                    logicIndex = bwPlug.logicalIndex() if attrName == AttrName.WEIGHT else -1
                else:
                    continue

                numKeys = anim.numKeys
                if anim.isTimeInput:
                    keyType       = CallbackType.KEYFRAME_NORMAL
                    keyframesList = [anim.input(i).value for i in range(numKeys)]
                    hasSDK        = False
                elif anim.isUnitlessInput:
                    keyType       = CallbackType.KEYFRAME_SDK
                    keyframesList = []
                    hasSDK        = numKeys > 0
                else:
                    return

                if attrName == AttrName.ENVELOPE:
                    logicIndex = -1

                self.keyframeEdit.emit(nodeName, attrName, keyType, logicIndex, hasSDK, keyframesList)
                return

    def selectionChangedCallback(self, *args):
        selList            = om.MGlobal.getActiveSelectionList()
        iterSel            = om.MItSelectionList(selList, om.MFn.kComponent)
        selectedComponents = []

        while not iterSel.isDone():
            dagPath, component = iterSel.getComponent()

            if component.apiType() in (om.MFn.kMeshVertComponent, om.MFn.kCurveCVComponent):
                try:
                    inMeshPlug = om.MFnDependencyNode(dagPath.node()).findPlug("inMesh", False)
                except RuntimeError:
                    iterSel.next()
                    continue

                if not inMeshPlug.isConnected:
                    iterSel.next()
                    continue

                depNodes = []
                for plug in inMeshPlug.connectedTo(True, False):
                    geomIndex  = plug.logicalIndex()
                    destNodeFn = om.MFnDependencyNode(plug.node())
                    if isInterpBlendShape(destNodeFn):
                        depNodes.append(destNodeFn)

                if depNodes:
                    indices = om.MFnSingleIndexedComponent(component).getElements()
                    selectedComponents.append(
                        (dagPath.partialPathName(), geomIndex, [indices, depNodes])
                    )

            iterSel.next()

        self.selectionChanged.emit(selectedComponents)

    def clear(self):
        for cb in self._callbacks:
            try:
                om.MMessage.removeCallback(cb)
            except Exception:
                pass
        self._callbacks.clear()

