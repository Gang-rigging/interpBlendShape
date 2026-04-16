from collections import OrderedDict
from enum import IntEnum, auto
from typing import List, Mapping


VERSION_NUMBER = "1.0.0"


class HeaderColumn(IntEnum):
    """
    Enum representing the column indices in the TreeView model.
    """

    NAME = 0
    WEIGHT = auto()
    SURFACE = auto()
    UV = auto()
    BEZIER = auto()
    LIVE = auto()
    OFFSET = auto()
    CURVATURE = auto()
    PRECISION = auto()
    CACHE = auto()
    KEY = auto()

    @classmethod
    def headers(cls) -> List[str]:
        """
        Returns:
            List[str]: Display header text for each column, in enum order.
        """
        return [HEADERS_MAP[col] for col in cls]

    @classmethod
    def tooltips(cls) -> List[str]:
        """
        Returns:
            List[str]: Tooltip string for each column, in enum order.
        """
        return [TOOLTIPS_MAP[col] for col in cls]

    @classmethod
    def widths(cls) -> List[int]:
        """
        Returns:
            List[int]: Default pixel widths for each column, in enum order.
        """
        return [WIDTHS_MAP[col] for col in cls]


HEADERS_MAP: Mapping[HeaderColumn, str] = OrderedDict([
    (HeaderColumn.NAME, "Name"),
    (HeaderColumn.WEIGHT, "Weight"),
    (HeaderColumn.SURFACE, "Drivers"),
    (HeaderColumn.UV, "UV"),
    (HeaderColumn.BEZIER, "Bezier"),
    (HeaderColumn.LIVE, "Live"),
    (HeaderColumn.OFFSET, "Offset"),
    (HeaderColumn.CURVATURE, "Curva"),
    (HeaderColumn.PRECISION, "Preci"),
    (HeaderColumn.CACHE, "Cache"),
    (HeaderColumn.KEY, "Key"),
])

TOOLTIPS_MAP = {
    HeaderColumn.NAME: "Display name of the interpBlendShape node.",
    HeaderColumn.WEIGHT: "Blend weight applied to the target.",
    HeaderColumn.SURFACE: "Surface driving the target in UV blend mode.",
    HeaderColumn.UV: "Enable UV-based interpolation.",
    HeaderColumn.BEZIER: "Enable Bezier-based interpolation.",
    HeaderColumn.LIVE: "Enable live updates for this target.",
    HeaderColumn.OFFSET: "Offset target position to match surface in UV mode.",
    HeaderColumn.CURVATURE: "Curvature control for Bezier interpolation.",
    HeaderColumn.PRECISION: "Precision value used to cache target vertices.",
    HeaderColumn.CACHE: "Enable target caching for better performance.",
    HeaderColumn.KEY: "Control keying behavior for animation.",
}

WIDTHS_MAP = {
    HeaderColumn.NAME: 140,
    HeaderColumn.WEIGHT: 160,
    HeaderColumn.SURFACE: 60,
    HeaderColumn.UV: 30,
    HeaderColumn.BEZIER: 30,
    HeaderColumn.LIVE: 30,
    HeaderColumn.OFFSET: 30,
    HeaderColumn.CURVATURE: 30,
    HeaderColumn.PRECISION: 30,
    HeaderColumn.CACHE: 30,
    HeaderColumn.KEY: 30,
}


class NodeTypeID:
    INTERP_BLENDSHAPE = 0x00140541


class AttrName:
    """Centralized attribute name definitions for InterpBlendShape node tracking."""

    WEIGHT = "weight"
    ENVELOPE = "envelope"
    INPUT_TARGET_SURFACE = "inputTargetSurface"

    INBETWEEN_INFO = "inbetweenInfo"
    INBETWEEN_TARGET_NAME = "inbetweenTargetName"

    TARGET_SURFACE_ID = "targetSurfaceId"
    TARGET_BLEND_UV = "targetBlendUV"
    TARGET_BLEND_BEZIER = "targetBlendBezier"
    TARGET_BLEND_LIVE = "targetBlendLive"
    TARGET_CACHED = "targetCached"
    TARGET_OFFSET = "targetOffset"
    TARGET_CURVATURE = "targetCurvature"
    TARGET_PRECISION = "targetPrecision"
    TARGET_REBIND = "targetRebind"

    TARGET_WEIGHT_NORMALIZATION = "targetWeightNormalization"
    TARGET_WEIGHT_LOCKED = "targetWeightLock"
    TARGET_WEIGHTS = "targetWeights"
    BASE_WEIGHTS = "baseWeights"

    @classmethod
    def all(cls):
        """Return a list of all attribute names."""
        return [value for key, value in cls.__dict__.items() if not key.startswith("_") and isinstance(value, str)]

    @classmethod
    def isTargetAttr(cls, name):
        return name in {
            cls.TARGET_SURFACE_ID,
            cls.TARGET_BLEND_UV,
            cls.TARGET_BLEND_BEZIER,
            cls.TARGET_BLEND_LIVE,
            cls.TARGET_CACHED,
            cls.TARGET_OFFSET,
            cls.TARGET_CURVATURE,
            cls.TARGET_PRECISION,
        }

    @classmethod
    def isInbetweenAttr(cls, name):
        return name in {
            cls.INBETWEEN_INFO,
            cls.INBETWEEN_TARGET_NAME,
        }

    @classmethod
    def isPaintAttr(cls, name):
        return name in {
            cls.TARGET_WEIGHT_NORMALIZATION,
            cls.TARGET_WEIGHT_LOCKED,
        }

    @classmethod
    def isWeightOrEnvelopeAttr(cls, name):
        return name in {cls.WEIGHT, cls.ENVELOPE}


class ItemType(IntEnum):
    """
    Enum representing the type of item in the blend shape hierarchy.

    Members:
        ROOT - The root node of the hierarchy.
        PARENT - A top-level target node.
        CHILD - A blend shape target.
        INBETWEEN - An inbetween target of a blend shape.
    """

    ROOT = 0
    PARENT = auto()
    CHILD = auto()
    INBETWEEN = auto()


class ActionID(IntEnum):
    """
    Enum representing keyframe actions for blend shape attributes.

    Members:
        KEYCURRENT - Set a key at the current time.
        KEYZERO - Set the weight to 0 and key it.
        KEYONE - Set the weight to 1 and key it.
        REMOVEKEY - Remove the key at the current time.
    """

    KEYCURRENT = auto()
    KEYZERO = auto()
    KEYONE = auto()
    REMOVEKEY = auto()
    RESET = auto()


class CallbackType(IntEnum):
    """
    Enum representing different callback types or IDs.
    """

    ATTRIBUTE_SET = auto()
    ATTRIBUTE_ARRAYADD = auto()
    ATTRIBUTE_ARRAYREMOVED = auto()
    ATTRIBUTE_RENAMED = auto()
    ATTRIBUTE_LOCK = auto()
    ATTRIBUTE_CONNECT = auto()
    ATTRIBUTE_DISCONNECT = auto()
    ATTRIBUTE_DIRTYPLUG = auto()

    KEYFRAME_NORMAL = auto()
    KEYFRAME_SDK = auto()

    NODE_RENAMED = auto()
