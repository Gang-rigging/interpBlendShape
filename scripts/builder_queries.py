from __future__ import annotations

import maya.api.OpenMaya as om
import maya.api.OpenMayaAnim as oma

from enums import AttrName
from logger import getLogger

logger = getLogger("InterpBlendShape")


def get_base_weight(input_target_plug, fn_node, vertex_id: int, geom_index: int) -> float | None:
    """Return the base weight for one vertex on one geometry index."""
    try:
        input_target = input_target_plug.elementByLogicalIndex(geom_index)
        weight_plug = input_target.child(fn_node.attribute(AttrName.BASE_WEIGHTS))
        return weight_plug.elementByLogicalIndex(vertex_id).asDouble()
    except Exception:
        return None


def get_target_vertex_weight(input_target_plug, attr_input_target_group, fn_node,
                             get_target_index, target_name: str,
                             vertex_id: int, geom_index: int) -> float | None:
    """Return the painted target weight for one vertex on one target/geometry pair."""
    try:
        index = get_target_index(target_name)
        if index is None:
            return None
        input_target = input_target_plug.elementByLogicalIndex(geom_index)
        input_target_group = input_target.child(attr_input_target_group)
        group_element = input_target_group.elementByLogicalIndex(index)
        weight_plug = group_element.child(fn_node.attribute(AttrName.TARGET_WEIGHTS))
        return weight_plug.elementByLogicalIndex(vertex_id).asDouble()
    except Exception:
        return None


def is_locked(get_plug, attr_name: str, weight_plug: bool = False) -> bool:
    """Check whether a resolved plug is locked."""
    try:
        plug = get_plug(attr_name, weight_plug)
        return plug.isLocked if plug else False
    except Exception:
        return False


def is_connected(get_plug, attr_name: str, weight_plug: bool = False) -> bool:
    """Check whether a resolved plug is connected to any non-animCurve node."""
    try:
        plug = get_plug(attr_name, weight_plug)
        if not plug:
            return False
        return any(
            not inp.node().hasFn(om.MFn.kAnimCurve)
            for inp in plug.connectedTo(True, False)
        )
    except Exception:
        return False


def get_keyframes(get_plug, attr_name: str, weight_plug: bool = False) -> tuple[list[float], bool]:
    """Return keyframe times and SDK presence for a plug."""
    plug = get_plug(attr_name, weight_plug)
    if not plug or plug.isNull or not plug.isDestination:
        return [], False

    keyframes = []
    has_sdk = False
    for anim_node in oma.MAnimUtil.findAnimation(plug):
        anim = oma.MFnAnimCurve(anim_node)
        if anim.isTimeInput:
            keyframes += [
                anim.input(i).value
                for i in range(anim.numKeys)
                if anim.input(i).value not in keyframes
            ]
        elif anim.isUnitlessInput and not has_sdk:
            has_sdk = anim.numKeys > 0
    return keyframes, has_sdk


def is_inbetween_index_valid(input_target_plug, attr_input_target_group, attr_input_target_item,
                             target_index: int, inbetween_index: int) -> bool:
    """Check whether an inbetween logical index exists for the given target."""
    if target_index is None or inbetween_index is None:
        return False

    input_target = input_target_plug.elementByLogicalIndex(0)
    input_target_group = input_target.child(attr_input_target_group)
    group_element = input_target_group.elementByLogicalIndex(target_index)
    input_target_item = group_element.child(attr_input_target_item)
    for i in range(input_target_item.numElements()):
        if input_target_item.elementByPhysicalIndex(i).logicalIndex() == inbetween_index:
            return True
    return False


def get_inbetween_targets(get_plug, attr_inbetween_info, attr_inbetween_target_name,
                          get_target_index, is_inbetween_index_valid_fn,
                          target_name: str) -> tuple[list[str], list[float]]:
    """Return inbetween names and weights for a main target alias."""
    inbetween_info = []
    inbetween_weight = []
    index = get_target_index(target_name)
    if index is None:
        return inbetween_info, inbetween_weight

    inbetween_info_group = get_plug("inbetweenInfoGroup").elementByLogicalIndex(index)
    inbetween_info_plug = inbetween_info_group.child(attr_inbetween_info)
    for i in range(inbetween_info_plug.numElements()):
        info_item = inbetween_info_plug.elementByPhysicalIndex(i)
        logical_index = info_item.logicalIndex()
        if is_inbetween_index_valid_fn(index, logical_index):
            weight = (logical_index - 5000) / 1000.0
            if weight != 0 and weight != 1:
                inbetween_weight.append(weight)
            inbetween_info.append(info_item.child(attr_inbetween_target_name).asString())
    return inbetween_info, inbetween_weight


def get_dag_path_from_plug(plug: om.MPlug) -> str | None:
    """Return the shortest unique transform path for a shape plug connection."""
    try:
        shape_obj = plug.node()
        dag_node = om.MFnDagNode(shape_obj)
        if dag_node.parentCount() > 0:
            return om.MFnDagNode(dag_node.parent(0)).partialPathName()
        return dag_node.partialPathName()
    except Exception as err:
        logger.warning(f"[getDagPathFromPlug] Error: {err}")
        return None


def get_input_mesh(get_plug, index: int = 0) -> str | None:
    """Traverse upstream from inputGeometry to find the first supported input shape."""
    try:
        input_geom_plug = get_plug("inputGeometry")
        if input_geom_plug.isArray:
            input_geom_plug = input_geom_plug.elementByLogicalIndex(index)

        iterator = om.MItDependencyGraph(
            input_geom_plug,
            om.MFn.kShape,
            om.MItDependencyGraph.kUpstream,
            om.MItDependencyGraph.kDepthFirst,
            om.MItDependencyGraph.kPlugLevel,
        )

        while not iterator.isDone():
            shape_node = iterator.currentNode()
            if shape_node.hasFn(om.MFn.kMesh) or shape_node.hasFn(om.MFn.kNurbsCurve):
                dag_path = om.MDagPath.getAPathTo(shape_node)
                dag_path.pop()
                return dag_path.fullPathName()
            iterator.next()
        return None
    except Exception as err:
        logger.warning(f"[getInputMesh] Failed: {err}")
        return None


def get_base_mesh(get_plug) -> list[str]:
    """
    Resolve base mesh transforms for the deformer.

    Prefer the visible downstream geometry reached from `outputGeometry`.
    If that traversal cannot find a visible result, fall back to the upstream
    `inputGeometry` transform so UI actions can still target the owning object.
    """
    output_geom_plug = get_plug("outputGeometry")
    base_mesh_paths = []
    seen_paths = set()

    def append_path(path: str | None) -> None:
        if path and path not in seen_paths:
            seen_paths.add(path)
            base_mesh_paths.append(path)

    for i in range(output_geom_plug.numElements()):
        element_plug = output_geom_plug.elementByPhysicalIndex(i)
        connections = element_plug.connectedTo(False, True)
        if not connections:
            continue

        current_plug = connections[0]
        visited = set()
        while True:
            node = current_plug.node()
            node_id = om.MObjectHandle(node).hashCode()
            if node_id in visited:
                break
            visited.add(node_id)

            if node.hasFn(om.MFn.kMesh) or node.hasFn(om.MFn.kNurbsCurve):
                try:
                    dag_path = om.MDagPath.getAPathTo(node)
                    if not om.MFnDagNode(dag_path).isIntermediateObject:
                        dag_path.pop()
                        append_path(dag_path.fullPathName())
                except Exception as err:
                    logger.warning(f"[getBaseMesh] Failed to get geometry path: {err}")
                break

            if node.hasFn(om.MFn.kGeometryFilt):
                try:
                    fn_node = om.MFnDependencyNode(node)
                    dest_logical_index = current_plug.logicalIndex() if current_plug.isElement else 0
                    out_plug = fn_node.findPlug("outputGeometry", False)
                    next_plug = out_plug.elementByLogicalIndex(dest_logical_index)
                    next_connections = next_plug.connectedTo(False, True)
                    if next_connections:
                        current_plug = next_connections[0]
                        continue
                except Exception as err:
                    logger.warning(f"[getBaseMesh] Deformer traversal failed: {err}")
                break

            break

    if base_mesh_paths:
        return base_mesh_paths

    try:
        input_geom_plug = get_plug("inputGeometry")
        if input_geom_plug.isArray:
            for i in range(input_geom_plug.numElements()):
                logical_index = input_geom_plug.elementByPhysicalIndex(i).logicalIndex()
                append_path(get_input_mesh(get_plug, logical_index))
        else:
            append_path(get_input_mesh(get_plug, 0))
    except Exception as err:
        logger.warning(f"[getBaseMesh] Input fallback failed: {err}")

    return base_mesh_paths


def get_target_mesh(input_target_plug, attr_input_target_group, attr_input_target_item,
                    fn_node, get_target_index, get_dag_path_from_plug_fn, attr_name: str) -> list[str]:
    """Return connected target transforms for a target alias across all geometries."""
    index = get_target_index(attr_name)
    if index == -1:
        logger.warning(f"Invalid attrName '{attr_name}'; no index found.")
        return []

    target_meshes = []
    try:
        for i in range(input_target_plug.numElements()):
            element_plug = input_target_plug.elementByPhysicalIndex(i)
            try:
                group_plug = element_plug.child(attr_input_target_group)
                group_elem = group_plug.elementByLogicalIndex(index)
                item_plug = group_elem.child(attr_input_target_item)
                for j in range(item_plug.numElements()):
                    item_elem_plug = item_plug.elementByPhysicalIndex(j)
                    geom_plug = item_elem_plug.child(fn_node.attribute("inputGeomTarget"))
                    connections = geom_plug.connectedTo(True, False)
                    if connections:
                        target_meshes.append(get_dag_path_from_plug_fn(connections[0]))
            except RuntimeError:
                continue
    except Exception as err:
        logger.warning(f"No target mesh found: {err}")
    return target_meshes


def get_target_meshes_for_item(input_target_plug, attr_input_target_group, attr_input_target_item,
                               fn_node, get_target_index, get_dag_path_from_plug_fn,
                               attr_name: str, target_item_id: int) -> list[str]:
    """Return connected target transforms for one target item id."""
    index = get_target_index(attr_name)
    if index in (-1, None):
        logger.warning(f"Invalid attrName '{attr_name}'; no index found.")
        return []

    target_meshes = []
    seen = set()
    try:
        for i in range(input_target_plug.numElements()):
            element_plug = input_target_plug.elementByPhysicalIndex(i)
            try:
                group_plug = element_plug.child(attr_input_target_group)
                group_elem = group_plug.elementByLogicalIndex(index)
                item_plug = group_elem.child(attr_input_target_item)
                item_elem_plug = item_plug.elementByLogicalIndex(target_item_id)
                geom_plug = item_elem_plug.child(fn_node.attribute("inputGeomTarget"))
                connections = geom_plug.connectedTo(True, False)
                if not connections:
                    continue

                dag_path = get_dag_path_from_plug_fn(connections[0])
                if dag_path and dag_path not in seen:
                    seen.add(dag_path)
                    target_meshes.append(dag_path)
            except RuntimeError:
                continue
    except Exception as err:
        logger.warning(f"Failed to resolve target mesh for '{attr_name}' [{target_item_id}]: {err}")
    return target_meshes


def get_last_element_index(array_plug: om.MPlug) -> int:
    """Return the highest logical index used by an array plug, or -1 if empty."""
    num_elements = array_plug.numElements()
    if num_elements > 0:
        return array_plug.elementByPhysicalIndex(num_elements - 1).logicalIndex()
    return -1


def get_input_target_surface(input_surface_plug, attr_input_target_surface,
                             get_dag_path_from_plug_fn, index: int) -> str | None:
    """Return the transform connected to one inputSurface element."""
    try:
        element_plug = input_surface_plug.elementByLogicalIndex(index)
        target_surface_plug = element_plug.child(attr_input_target_surface)
        if target_surface_plug.isDestination:
            connections = target_surface_plug.connectedTo(True, False)
            if connections:
                return get_dag_path_from_plug_fn(connections[0])
        return None
    except Exception as err:
        logger.warning(f"[getInputTargetSurface] Error: {err}")
        return None


def get_all_input_target_surfaces(input_surface_plug, attr_input_target_surface,
                                  get_dag_path_from_plug_fn, get_unique_name_fn) -> dict:
    """Return all connected input surfaces keyed by unique transform name."""
    transform_dict = {}
    try:
        for i in range(input_surface_plug.numElements()):
            element = input_surface_plug.elementByPhysicalIndex(i)
            logical_index = element.logicalIndex()
            target_surface_plug = element.child(attr_input_target_surface)
            if target_surface_plug.isDestination:
                connections = target_surface_plug.connectedTo(True, False)
                if connections:
                    dag_path = get_dag_path_from_plug_fn(connections[0])
                    if dag_path:
                        transform_dict[get_unique_name_fn(dag_path, transform_dict)] = logical_index
        return {"NONE": 0} if not transform_dict else transform_dict
    except Exception as err:
        logger.warning(f"[getAllInputTargetSurfaces] Error: {err}")
        return {"NONE": 0}
