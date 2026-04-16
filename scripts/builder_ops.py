from __future__ import annotations

import maya.api.OpenMaya as om
import maya.cmds as cmds
import maya.mel as mel

from enums import AttrName
from logger import getLogger

logger = getLogger("InterpBlendShape")


def set_base_weight(input_target_plug, fn_node, vertex_id: int, geom_index: int, value: float) -> bool:
    """Set the base weight for one vertex on one geometry index."""
    try:
        input_target = input_target_plug.elementByLogicalIndex(geom_index)
        weight_plug = input_target.child(fn_node.attribute(AttrName.BASE_WEIGHTS))
        weight_plug.elementByLogicalIndex(vertex_id).setDouble(value)
        return True
    except Exception:
        return False


def normalize_target_weight(fn_node, vertex_id: int, paint_index: int,
                            painted_weight: float, input_target_group_plug: om.MPlug) -> bool:
    """
    Normalize target weights for a vertex after one target value changes.

    Remaining weight is distributed across other normalized, unlocked targets.
    """
    normalization_group = []
    normalization_unlocked_group = []

    for i in range(input_target_group_plug.numElements()):
        elem_plug = input_target_group_plug.elementByPhysicalIndex(i)
        logical_idx = elem_plug.logicalIndex()
        is_locked = elem_plug.child(fn_node.attribute(AttrName.TARGET_WEIGHT_LOCKED)).asBool()
        is_norm = elem_plug.child(fn_node.attribute(AttrName.TARGET_WEIGHT_NORMALIZATION)).asBool()
        if is_norm and logical_idx != paint_index:
            normalization_group.append(logical_idx)
            if not is_locked:
                normalization_unlocked_group.append(logical_idx)

    if not normalization_group:
        return False

    sum_locked = 0.0
    sum_unlocked = 0.0
    target_weights = {}

    for target_idx in normalization_group:
        elem_plug = input_target_group_plug.elementByLogicalIndex(target_idx)
        is_locked = elem_plug.child(fn_node.attribute(AttrName.TARGET_WEIGHT_LOCKED)).asBool()
        weight_plug = elem_plug.child(fn_node.attribute(AttrName.TARGET_WEIGHTS))
        weight_value = weight_plug.elementByLogicalIndex(vertex_id).asDouble()
        if is_locked:
            sum_locked += weight_value
        else:
            sum_unlocked += weight_value
            target_weights[target_idx] = weight_value

    max_paint = 1.0 - sum_locked
    new_paint = max(0.0, min(painted_weight, max_paint))
    leftover = 1.0 - (new_paint + sum_locked)

    if abs(painted_weight - new_paint) > 1e-8:
        paint_elem_plug = input_target_group_plug.elementByLogicalIndex(paint_index)
        paint_weight_plug = paint_elem_plug.child(fn_node.attribute(AttrName.TARGET_WEIGHTS))
        paint_weight_plug.elementByLogicalIndex(vertex_id).setDouble(new_paint)

    proportional = sum_unlocked > 1e-8
    for target_idx in normalization_unlocked_group:
        elem_plug = input_target_group_plug.elementByLogicalIndex(target_idx)
        weight_plug = elem_plug.child(fn_node.attribute(AttrName.TARGET_WEIGHTS))
        vertex_plug = weight_plug.elementByLogicalIndex(vertex_id)
        if leftover > 1e-5:
            if proportional:
                new_weight = leftover * target_weights.get(target_idx, 0.0) / sum_unlocked
            else:
                new_weight = leftover / len(normalization_group)
        else:
            new_weight = 0.0
        vertex_plug.setDouble(new_weight)

    return True


def set_target_vertex_weight(input_target_plug, attr_input_target_group, fn_node,
                             get_target_index, target_name: str, vertex_id: int,
                             geom_index: int, value: float, normalize: bool = False) -> bool:
    """Set a target vertex weight and optionally normalize sibling targets."""
    try:
        index = get_target_index(target_name)
        if index is None:
            logger.error(f"Target '{target_name}' not found")
            return False

        input_target = input_target_plug.elementByLogicalIndex(geom_index)
        input_target_group = input_target.child(attr_input_target_group)
        target_elem = input_target_group.elementByLogicalIndex(index)
        weight_plug = target_elem.child(fn_node.attribute(AttrName.TARGET_WEIGHTS))
        weight_plug.elementByLogicalIndex(vertex_id).setDouble(value)

        if normalize:
            return bool(normalize_target_weight(fn_node, vertex_id, index, value, input_target_group))
        return True
    except Exception as err:
        logger.error(f"Error in setTargetVertexWeight: {err}")
        return False


def select_paintable_base_mesh(base_mesh_list: list[str]) -> bool:
    """Select paintable base meshes, filtering out NURBS curves."""
    sel_list = om.MGlobal.getActiveSelectionList()
    matching = []

    for i in range(sel_list.length()):
        obj = sel_list.getDependNode(i)
        if not obj.hasFn(om.MFn.kDagNode):
            continue
        full_path = sel_list.getDagPath(i).fullPathName()
        if full_path in base_mesh_list:
            matching.append(full_path)

    new_sel_list = om.MSelectionList()
    for obj_path in matching if matching else base_mesh_list:
        try:
            new_sel_list.add(obj_path)
        except Exception:
            logger.debug(f"Object not found: {obj_path}")

    indices_to_remove = []
    for i in range(new_sel_list.length()):
        obj_path = new_sel_list.getDagPath(i)
        for j in range(obj_path.childCount()):
            if obj_path.child(j).hasFn(om.MFn.kNurbsCurve):
                cmds.warning("NURBS curves are not paintable. Use the weight edit tool instead.")
                indices_to_remove.append(i)
                break

    for index in sorted(indices_to_remove, reverse=True):
        new_sel_list.remove(index)

    om.MGlobal.setActiveSelectionList(new_sel_list, om.MGlobal.kReplaceList)
    return not new_sel_list.isEmpty()


def paint_base_weight(node: str, base_mesh_list: list[str]) -> None:
    """Activate Artisan painting for base weights."""
    cmds.makePaintable("interpBlendShape", "baseWeights", attrType="multiDouble", sm="deformer")
    if not select_paintable_base_mesh(base_mesh_list):
        return
    mel.eval(f'artSetToolAndSelectAttr("artAttrCtx", "interpBlendShape.{node}.baseWeights");')


def paint_target_weight(node: str, index: int, base_mesh_list: list[str]) -> None:
    """Activate Artisan painting for target weights."""
    if not select_paintable_base_mesh(base_mesh_list):
        return

    cmds.setAttr(f"{node}.paintTargetWeightsIndex", index)
    current_ctx = cmds.currentCtx()
    should_switch = True
    if current_ctx == "artAttrContext":
        painted_attr = cmds.artAttrCtx("artAttrContext", query=True, attrSelected=True)
        if "." in painted_attr and painted_attr.split(".")[-1] != "baseWeights":
            should_switch = False

    if should_switch:
        cmds.makePaintable("interpBlendShape", "paintTargetWeights", attrType="multiDouble", sm="deformer")
        mel.eval(f'artSetToolAndSelectAttr("artAttrCtx", "interpBlendShape.{node}.paintTargetWeights");')


def copy_weight(node: str, source_target: int, destination_target: int, surface_association: int) -> None:
    """Copy weights from one target index to another on the same node."""
    cmds.copyInterpBlendWeights(
        ss=source_target,
        sd=node,
        ds=destination_target,
        dd=node,
        sa=surface_association,
        noMirror=True,
    )


def mirror_weight(node: str, destination_target: int, mirror_mode: int,
                  surface_association: int, mirror_inverse: bool) -> None:
    """Mirror weights into a destination target on the same node."""
    cmds.copyInterpBlendWeights(
        ds=destination_target,
        dd=node,
        mirrorMode=mirror_mode,
        sa=surface_association,
        mirrorInverse=mirror_inverse,
    )


def flip_weight(node: str, destination_target: int, mirror_mode: int, surface_association: int) -> None:
    """Flip weights in place on a destination target."""
    cmds.copyInterpBlendWeights(
        ds=destination_target,
        dd=node,
        mirrorMode=mirror_mode,
        sa=surface_association,
        flipWeights=True,
    )


def edit_target_shape(node: str, destination_shapes: str | list[str], mirror_mode: str = "YZ",
                      surface_association: str = "closestPoint",
                      mirror_inverse: bool = False, flip_target: bool = False) -> bool:
    """Mirror or flip connected target geometry using the interpBlendShapeEdit command."""
    if isinstance(destination_shapes, str):
        shape_targets = [destination_shapes]
    else:
        shape_targets = [shape for shape in destination_shapes if shape]

    if not shape_targets:
        logger.warning("[ShapeEdit] No destination target shapes found.")
        return False

    succeeded = False
    cmds.undoInfo(openChunk=True)
    try:
        for destination_shape in shape_targets:
            kwargs = {
                "dd": node,
                "ds": destination_shape,
                "mm": mirror_mode,
                "sa": surface_association,
            }
            if mirror_inverse:
                kwargs["mi"] = True
            if flip_target:
                kwargs["ft"] = True

            try:
                cmds.interpBlendShapeEdit(**kwargs)
                succeeded = True
            except Exception as err:
                logger.warning(f"[ShapeEdit] Failed on '{destination_shape}': {err}")
    finally:
        cmds.undoInfo(closeChunk=True)

    return succeeded
