"""
Lightweight Maya smoke test for the InterpBlendShape UI and core workflows.

Run inside Maya's Script Editor:

    from smoke_test_interpblendshape import run_smoke_test
    run_smoke_test()
"""

import time

from PySide2 import QtCore, QtWidgets

import maya.cmds as cmds

from interpBlendShape_ui import closeUI, showUI


def _require(condition, message):
    if not condition:
        raise RuntimeError(message)


def _deform_duplicate(mesh_name, duplicate_name, vertex_index, offset_x):
    duplicate = cmds.duplicate(mesh_name, name=duplicate_name)[0]
    cmds.move(offset_x, 0.0, 0.0, f"{duplicate}.vtx[{vertex_index}]", r=True)
    return duplicate


def _pump_events(duration_ms=50):
    app = QtWidgets.QApplication.instance()
    if app is None:
        return

    deadline = time.monotonic() + max(0.0, duration_ms) / 1000.0
    while time.monotonic() < deadline:
        app.processEvents(QtCore.QEventLoop.AllEvents, 25)
        QtCore.QThread.msleep(5)


def _wait_for_signal(signal, timeout_ms=5000):
    triggered = {"done": False}

    def _mark_done(*args, **kwargs):
        triggered["done"] = True

    signal.connect(_mark_done)
    try:
        deadline = time.monotonic() + max(0.0, timeout_ms) / 1000.0
        while not triggered["done"] and time.monotonic() < deadline:
            _pump_events(25)
        return triggered["done"]
    finally:
        try:
            signal.disconnect(_mark_done)
        except (RuntimeError, TypeError):
            pass


def run_smoke_test(close_ui_on_finish=True):
    """
    Exercise the main happy-path UI flows on a simple mesh setup.

    Returns:
        dict: Summary with per-step status details.
    """
    results = []

    def step(name, callback):
        try:
            value = callback()
            results.append({"step": name, "success": True})
            return value
        except Exception as exc:
            results.append({"step": name, "success": False, "error": str(exc)})
            raise

    try:
        step("new_scene", lambda: cmds.file(new=True, force=True))
        base_mesh = step("create_base_mesh", lambda: cmds.polySphere(name="ibs_smoke_base", sx=12, sy=12)[0])
        target_mesh = step(
            "create_target_mesh",
            lambda: _deform_duplicate(base_mesh, "ibs_smoke_target", 0, 0.35),
        )
        inbetween_mesh = step(
            "create_inbetween_mesh",
            lambda: _deform_duplicate(base_mesh, "ibs_smoke_inbetween", 1, 0.18),
        )

        def show_ui():
            win = showUI()
            _require(win is not None, "UI did not return a window instance.")
            _require(
                _wait_for_signal(win.tree.modelLoadFinished, timeout_ms=5000),
                "UI model load did not finish within the timeout.",
            )
            return win

        window = step("show_ui", show_ui)
        _pump_events(50)

        def create_node():
            cmds.select(base_mesh, r=True)
            parent_item = window.tree.model.addNewInterpBlendShapeNode()
            _require(parent_item, "Failed to create interpBlendShape node from the UI model.")
            return parent_item

        parent_item = step("create_deformer_node", create_node)
        builder = parent_item.builder()
        _require(builder is not None, "New parent item does not have a valid builder.")
        _pump_events(50)

        def add_target():
            cmds.select(target_mesh, r=True)
            children = builder.addTarget(parent_item)
            _require(children, "Failed to add a target mesh.")
            window.tree.model.insertItem(parent_item, children)
            return children[0]

        child_item = step("add_target", add_target)
        _pump_events(50)

        def add_inbetween():
            cmds.select(inbetween_mesh, r=True)
            inbetweens = builder.addInbetweenTarget(child_item, 0.5)
            _require(inbetweens, "Failed to add an inbetween target.")
            window.tree.model.insertItem(child_item, inbetweens)
            return inbetweens[0]

        step("add_inbetween", add_inbetween)
        _pump_events(50)

        def open_shape_options():
            anchor = window.mapToGlobal(QtCore.QPoint(40, 72))
            window.showShapeEditOptions(anchor)
            _require(window._shapeOptionsPopup is not None, "Shape options popup was not created.")
            _require(window._shapeOptionsPopup.isVisible(), "Shape options popup is not visible.")
            window._shapeOptionsPopup.hide()

        step("open_shape_options", open_shape_options)
        _pump_events(50)

        def mirror_target():
            success = builder.editTargetShape(
                child_item.name(),
                mirrorMode="YZ",
                surfaceAssociation="closestComponent",
                mirrorInverse=False,
                flipTarget=False,
            )
            _require(success, "Mirror target command returned failure.")

        step("mirror_target", mirror_target)
        _pump_events(100)

        return {"success": True, "results": results}

    except Exception:
        return {"success": False, "results": results}

    finally:
        if close_ui_on_finish:
            try:
                closeUI()
            except Exception:
                pass
