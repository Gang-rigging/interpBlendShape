from PySide2 import QtCore


SETTINGS_ORG = "interpBlendShape"
SETTINGS_APP = "InterpBlendShapeUI"

WINDOW_TITLE = "InterpBlendShape Editor"
WINDOW_OBJECT_NAME = "interpBlendShapeEditor"

SHAPE_EDIT_GROUP = "shapeEdit"
SHAPE_EDIT_MIRROR_INVERSE_KEY = f"{SHAPE_EDIT_GROUP}/mirrorInverse"
SHAPE_EDIT_MIRROR_MODE_KEY = f"{SHAPE_EDIT_GROUP}/mirrorMode"
SHAPE_EDIT_SURFACE_ASSOCIATION_KEY = f"{SHAPE_EDIT_GROUP}/surfaceAssociation"

SHAPE_EDIT_DEFAULTS = {
    "mirrorInverse": False,
    "mirrorMode": "YZ",
    "surfaceAssociation": "closestPoint",
}

SCENE_GROUP_EXPANDED_STATE = "ExpandedState"
SCENE_GROUP_NODE_ORDER = "NodeOrder"


def ui_settings():
    return QtCore.QSettings(SETTINGS_ORG, SETTINGS_APP)


def shape_edit_options():
    settings = ui_settings()
    return {
        "mirrorInverse": settings.value(
            SHAPE_EDIT_MIRROR_INVERSE_KEY,
            SHAPE_EDIT_DEFAULTS["mirrorInverse"],
            type=bool,
        ),
        "mirrorMode": settings.value(
            SHAPE_EDIT_MIRROR_MODE_KEY,
            SHAPE_EDIT_DEFAULTS["mirrorMode"],
            type=str,
        ),
        "surfaceAssociation": settings.value(
            SHAPE_EDIT_SURFACE_ASSOCIATION_KEY,
            SHAPE_EDIT_DEFAULTS["surfaceAssociation"],
            type=str,
        ),
    }


def save_shape_edit_options(options):
    settings = ui_settings()
    settings.setValue(SHAPE_EDIT_MIRROR_INVERSE_KEY, options["mirrorInverse"])
    settings.setValue(SHAPE_EDIT_MIRROR_MODE_KEY, options["mirrorMode"])
    settings.setValue(SHAPE_EDIT_SURFACE_ASSOCIATION_KEY, options["surfaceAssociation"])


def scene_group(scene_key, group_name):
    return f"{scene_key}/{group_name}"
