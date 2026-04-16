"""
Public UI launcher for InterpBlendShape.
"""

import datetime

from maya_utils import getMayaMainWindow
from main_window import InterpBlendShapeEditor

_interpEditorWin = None


def getUI():
    return _interpEditorWin


def closeUI():
    global _interpEditorWin
    if _interpEditorWin is not None:
        try:
            _interpEditorWin.close()
        finally:
            _interpEditorWin = None


def showUI():
    """Launch or bring to front the InterpBlendShape Editor window."""
    global _interpEditorWin
    if _interpEditorWin is not None:
        if _interpEditorWin.isVisible():
            _interpEditorWin.raise_()
            _interpEditorWin.activateWindow()
            return _interpEditorWin
        else:
            # Clean up closed window before creating new one
            try:
                _interpEditorWin.close()
            except Exception:
                pass
            _interpEditorWin = None

    start_time       = datetime.datetime.now()
    _interpEditorWin = InterpBlendShapeEditor(getMayaMainWindow())
    _interpEditorWin._startOpenTime = start_time
    _interpEditorWin.show()
    return _interpEditorWin


launch = showUI
