"""
Compatibility wrapper for delegate imports.

The concrete delegate implementations live in smaller modules so each
responsibility is easier to navigate and maintain:
- `delegates_weight.py`
- `delegates_state.py`
- `delegates_popup.py`
"""

from .delegate_common import ReturnKeyCommitFilter
from .delegates_popup import LineEditDelegate, ListPopupDelegate, SliderPopupDelegate
from .delegates_state import CheckBoxDelegate, NoFocusDelegate, ToggleButtonDelegate
from .delegates_weight import SliderWeightDelegate

__all__ = [
    "ReturnKeyCommitFilter",
    "SliderWeightDelegate",
    "ToggleButtonDelegate",
    "CheckBoxDelegate",
    "LineEditDelegate",
    "SliderPopupDelegate",
    "NoFocusDelegate",
    "ListPopupDelegate",
]
