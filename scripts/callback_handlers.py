from enums import HeaderColumn, CallbackType, AttrName
from logger import getLogger

logger = getLogger("InterpBlendShape")
def handleSet(view, parentItem, attr, idx, ctype, kw):
    value = kw.get("value")
    logger.debug("handleSet called for attr=%s, idx=%s, value=%s", attr, idx, value)

    if attr == AttrName.ENVELOPE:
        view.model.updateColumnData(parentItem, HeaderColumn.WEIGHT, value)
        _refreshWeightWidget(view, parentItem, value)
        return

    child = view.model.getChildItem(parentItem, idx)
    if not child:
        return

    colMap = {
        AttrName.WEIGHT:              HeaderColumn.WEIGHT,
        AttrName.TARGET_BLEND_UV:     HeaderColumn.UV,
        AttrName.TARGET_BLEND_BEZIER: HeaderColumn.BEZIER,
        AttrName.TARGET_BLEND_LIVE:   HeaderColumn.LIVE,
        AttrName.TARGET_CACHED:       HeaderColumn.CACHE,
        AttrName.TARGET_OFFSET:       HeaderColumn.OFFSET,
        AttrName.TARGET_CURVATURE:    HeaderColumn.CURVATURE,
        AttrName.TARGET_PRECISION:    HeaderColumn.PRECISION,
        AttrName.TARGET_SURFACE_ID:   HeaderColumn.SURFACE,
    }

    if attr == AttrName.TARGET_SURFACE_ID:
        surfaces = parentItem.getAllSurfaces()
        value = next((k for k, v in surfaces.items() if v == value and k != "NONE"), "NONE")

    column = colMap.get(attr)
    if column is not None:
        view.model.updateColumnData(child, column, value)
        # Directly update the weight widget for undo support
        if column == HeaderColumn.WEIGHT:
            _refreshWeightWidget(view, child, value)

    if attr == AttrName.INBETWEEN_TARGET_NAME:
        newName = kw.get("newName")
        ibItem = view.model.getChildItem(child, value)
        if ibItem and newName:
            view.model.updateColumnData(ibItem, HeaderColumn.NAME, newName)

    elif AttrName.isPaintAttr(attr):
        if attr == AttrName.TARGET_WEIGHT_LOCKED:
            child.weightLocked = value
        elif attr == AttrName.TARGET_WEIGHT_NORMALIZATION:
            child.weightNormalization = value

        paintUI = view.paintToolWidget
        if not paintUI:
            return

        listWidget = paintUI.listWidget
        count = listWidget.count()
        if count <= 1:
            return

        firstWidget = listWidget.itemWidget(listWidget.item(0))
        if not firstWidget or firstWidget.label.text() != parentItem.name():
            return

        for i in range(1, count):
            widget = listWidget.itemWidget(listWidget.item(i))
            if not widget:
                continue
            if widget.label.text() == child.name():
                widget.updateStates(child.weightLocked, child.weightNormalization)
                break


def _refreshWeightWidget(view, item, value):
    """Directly update the persistent SliderWeightWidget for this item."""
    if getattr(view, '_sliderDragging', False):
        return
    currentData = item.data(HeaderColumn.WEIGHT)
    if currentData is not None and abs(float(value) - float(currentData)) > 1e-4:
        return
    proxyIndex = view.getProxyIndex(item, HeaderColumn.WEIGHT)
    if not proxyIndex.isValid():
        return
    widget = view.indexWidget(proxyIndex)
    if widget and hasattr(widget, 'setValue'):
        widget.setValue(value)

def handleAttrRenamed(view, parentItem, attr, idx, ctype, kw):
    """
    Handle attribute rename events.
    Updates internal alias cache and column data for a renamed attribute.

    :param view: The InterpBlendShapeView instance.
    :param parentItem: The parent tree item in the model.
    :param attr: The attribute name that was renamed.
    :param idx: The index for array attributes (unused here).
    :param ctype: The callback type (should be CallbackType.ATTRIBUTE_RENAME).
    :param kw: A dict containing additional keyword data (e.g., newName).
    """
    newName = kw.get("newName")
    child = view.model.getChildItem(parentItem, idx)
    if child:
        oldAlias = child.name()
        child.builder().updateAliasDictCache(oldAlias, newName)
        view.model.updateColumnData(child, HeaderColumn.NAME, newName)


def handleNodeRenamed(view, parentItem, attr, idx, ctype, kw):
    """
    Handle node rename events.
    Updates the tree item's displayed name and builder node reference.

    :param view: The InterpBlendShapeView instance.
    :param parentItem: The tree item representing the node.
    :param attr: The attribute associated (unused here).
    :param idx: The index (unused here).
    :param ctype: The callback type (should be CallbackType.NODE_RENAME).
    :param kw: A dict containing additional keyword data (e.g., newName).
    """
    newName = kw.get("newName")
    view.model.updateColumnData(parentItem, HeaderColumn.NAME, newName)
    parentItem.builder().node = newName


def handleArrayAdd(view, parentItem, attr, idx, ctype, kw):
    """
    Handle array add events.
    Inserts new target or inbetween items into the model when an array attribute grows.

    :param view: The InterpBlendShapeView instance.
    :param parentItem: The parent tree item in the model.
    :param attr: The array attribute name.
    :param idx: The index at which the element was added.
    :param ctype: The callback type (should be CallbackType.ATTRIBUTE_ARRAY_ADDED).
    :param kw: A dict containing additional keyword data (e.g., value).
    """
    logger.debug("handleArrayAdd called for attr=%s, idx=%s", attr, idx)

    if attr == AttrName.WEIGHT:
        newTargets = parentItem.builder().addTarget(parentItem, idx)
        if newTargets:
            view.model.insertItem(parentItem, newTargets)

    elif attr == AttrName.INBETWEEN_INFO:
        ibIdx = kw.get("value")
        weight = (ibIdx - 5000) / 1000.0
        child = view.model.getChildItem(parentItem, idx)
        if child:
            newIbs = child.builder().addInbetweenTarget(child, weight, modelOnly=True)
            if newIbs:
                view.model.insertItem(child, newIbs)


def handleArrayRemoved(view, parentItem, attr, idx, ctype, kw):
    """
    Handle array remove events.
    Removes target or inbetween items from the model when an array attribute shrinks.

    :param view: The InterpBlendShapeView instance.
    :param parentItem: The parent tree item in the model.
    :param attr: The array attribute name.
    :param idx: The index at which the element was removed.
    :param ctype: The callback type (should be CallbackType.ATTRIBUTE_ARRAY_REMOVED).
    :param kw: A dict containing additional keyword data (e.g., value).
    """
    logger.debug("handleArrayRemoved called for attr=%s, idx=%s", attr, idx)

    if attr == AttrName.INBETWEEN_INFO:
        child = view.model.getChildItem(parentItem, idx)
        ibIdx = kw.get("value")
        ibItem = view.model.getChildItem(child, ibIdx) if child else None
        if ibItem:
            view.model.removeItems(ibItem, modelOnly=True)
    else:
        child = view.model.getChildItem(parentItem, idx)
        if child:
            view.model.removeItems(child, modelOnly=True)


def handleLock(view, parentItem, attr, idx, ctype, kw):
    """
    Handle lock toggle events.
    Locks or unlocks sliders and editors based on the lock state.

    :param view: The InterpBlendShapeView instance.
    :param parentItem: The tree item associated with the lock.
    :param attr: The attribute name (usually WEIGHT).
    :param idx: The element index for array attributes.
    :param ctype: The callback type (should be CallbackType.ATTRIBUTE_LOCK).
    :param kw: A dict containing additional keyword data (e.g., value).
    """
    locked = kw.get("value", False)
    item = (view.model.getChildItem(parentItem, idx)
            if attr == AttrName.WEIGHT else parentItem)

    if not item:
        return

    item.setLocked(locked)
    pIdx = view.getProxyIndex(item, HeaderColumn.WEIGHT)
    editor = view.indexWidget(pIdx)
    if editor:
        # editor.lineEdit.setLocked(locked)
        # editor.slider.setActive(locked, item.isConnected())
        editor.setLockStatus(item.isLocked(), item.isConnected())
        if item.hasSDK() and item.isConnected():
            # enable widget when sdk and keyframe model
            editor.slider.setActive(item.isLocked())
        editor.lineEdit.refreshStyle()

def handleConnection(view, parentItem, attr, idx, ctype, kw):
    """
    Handle connection and disconnection events on attributes.
    Updates connection state, clears or sets keyframes, and refreshes view.

    :param view: The InterpBlendShapeView instance.
    :param parentItem: The parent tree item in the model.
    :param attr: The attribute name that changed connection.
    :param idx: The index for array attributes (e.g., weight index).
    :param ctype: The callback type (CONNECT or DISCONNECT).
    :param kw: A dict containing additional keyword data (e.g., value, keyframes, hasSDK).
    """
    logger.debug("handleConnection called for attr=%s, idx=%s, type=%s", attr, idx, ctype)

    value     = kw.get("value")
    keyframes = kw.get("keyframes", [])
    hasSDK    = kw.get("hasSDK", False)

    if AttrName.isWeightOrEnvelopeAttr(attr):
        item = (view.model.getChildItem(parentItem, idx)
                if attr == AttrName.WEIGHT else parentItem)
        if not item:
            return

        if ctype == CallbackType.ATTRIBUTE_CONNECT:
            item.setConnected(True)
            item.clearKeyframes()
            item.setHasSDK(False)

        elif ctype == CallbackType.ATTRIBUTE_DISCONNECT:
            item.setConnected(False)
            item.setKeyframes(keyframes)
            item.setHasSDK(hasSDK)

        view._refreshItemFromCallback(item, value, ctype)

    elif attr == AttrName.INPUT_TARGET_SURFACE:
        if ctype == CallbackType.ATTRIBUTE_CONNECT:
            parentItem.addSurface(kw.get("surfaceName"), idx)
        elif ctype == CallbackType.ATTRIBUTE_DISCONNECT:
            parentItem.removeSurface(idx)


def handleDirtyPlug(view, parentItem, attr, idx, ctype, kw):
    """
    Handle dirty plug events when an attribute's plug is dirtied.
    Triggers a view refresh for weight or envelope attributes.

    :param view: The InterpBlendShapeView instance.
    :param parentItem: The parent tree item in the model.
    :param attr: The attribute name whose plug was dirtied.
    :param idx: The index for array attributes (unused here).
    :param ctype: The callback type (should be CallbackType.ATTRIBUTE_DIRTYPLUG).
    :param kw: A dict containing additional keyword data.
    """
    logger.debug("handleDirtyPlug called for attr=%s, idx=%s", attr, idx)

    if not AttrName.isWeightOrEnvelopeAttr(attr):
        return

    keyframes = kw.get("keyframes", [])
    item = (view.model.getChildItem(parentItem, idx)
            if attr == AttrName.WEIGHT else parentItem)
    if not item:
        return

    item.setKeyframes(keyframes)
    view._refreshItemFromCallback(item, ctype=CallbackType.ATTRIBUTE_DIRTYPLUG)

def handleKeyframeEdit(view, parentItem, attrName, logicIndex, keyType, hasSDK, keyframesList):

    if attrName == AttrName.ENVELOPE:
        item = parentItem
    elif attrName == AttrName.WEIGHT:
        item = view.model.getChildItem(parentItem, logicIndex)
        if not item:
            return
    else:
        return

    if keyType == CallbackType.KEYFRAME_NORMAL:
        if keyframesList:
            item.setKeyframes(keyframesList)
        else:
            item.clearKeyframes()
    elif keyType == CallbackType.KEYFRAME_SDK:
        item.setHasSDK(hasSDK)

    if keyframesList and not hasSDK:
        view._refreshItemFromCallback(item)
