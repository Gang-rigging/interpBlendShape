"""
Qt style sheets and icon paths for the InterpBlendShape UI.

Defines colors, styles, and icon file locations to keep the UI consistent
and match Maya's dark theme.

Use the `iconPath()` function to get icon file paths based on the project
folder structure.
"""

import os

# === Icons Helper ===
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))  # ...\plug-ins\scripts\widgets
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))  # two levels up: ...\plug-ins
ICONS_DIR = os.path.join(PROJECT_ROOT, "icons")

def iconPath(name):
    return os.path.join(ICONS_DIR, name)

# Icon file paths
ICON_CLOSE_DEFAULT = iconPath("closeDefault.svg")
ICON_CLOSE_HOVER = iconPath("closeHover.svg")
ICON_MINIMIZE = iconPath("minimize.svg")
ICON_MAXIMIZE = iconPath("maximize.svg")

# === Color Constants ===
TITLE_BAR_COLOR = "#586069"
MAIN_UI_COLOR   = "#444444"
BORDER_COLOR    = "#3C3C3C"
TEXT_COLOR      = "#E0E0E0"
ACCENT_COLOR = "#55AAC3"
ACCENT_HOVER_COLOR = "#62C3DF"
ACCENT_PRESSED_COLOR = "#4890A5"
FIELD_BORDER_COLOR = "#444444"
FIELD_FOCUS_COLOR = "#5285A6"
FIELD_BG_COLOR = "#3E3E3E"
POPUP_BG_RGBA = (51, 51, 51, 250)
POPUP_SOFT_BG_RGBA = (51, 51, 51, 230)
POPUP_BORDER_COLOR = "#555555"
POPUP_PANEL_COLOR = "#333333"
POPUP_FIELD_COLOR = "#444444"
POPUP_FIELD_HOVER_COLOR = "#4D4D4D"
POPUP_MUTED_TEXT_COLOR = "#888888"
POPUP_MUTED_TEXT_HOVER_COLOR = "#AAAAAA"
POPUP_ITEM_HOVER_COLOR = "rgba(90, 132, 255, 80)"
POPUP_ITEM_SELECTED_COLOR = "rgba(90, 132, 255, 140)"
POPUP_RADIUS = 8


def popup_rgba(alpha: int) -> str:
    return f"rgba({POPUP_BG_RGBA[0]}, {POPUP_BG_RGBA[1]}, {POPUP_BG_RGBA[2]}, {alpha})"


def popup_frame_style(selector: str = "QFrame#popupFrame", alpha: int = 250) -> str:
    return f"""
{selector} {{
    background-color: {popup_rgba(alpha)};
    border-radius: {POPUP_RADIUS}px;
    border: 1px solid {POPUP_BORDER_COLOR};
}}
"""


def line_edit_style(
    background: str = "transparent",
    border: str = FIELD_BORDER_COLOR,
    text: str = TEXT_COLOR,
    padding: str = "2px 4px",
    radius: int = 2,
    focus_border: str = FIELD_FOCUS_COLOR,
    placeholder: str = "#999999",
) -> str:
    return f"""
QLineEdit {{
    color: {text};
    background-color: {background};
    border: 1px solid {border};
    border-radius: {radius}px;
    padding: {padding};
    selection-background-color: {ACCENT_COLOR};
}}
QLineEdit:focus {{
    border: 1px solid {focus_border};
}}
QLineEdit[readOnly="true"] {{
    background-color: {background};
}}
QLineEdit::placeholder {{
    color: {placeholder};
}}
"""


POPUP_LIST_WIDGET_STYLE = f"""
QListWidget {{
    background: transparent;
    color: white;
    padding: 4px;
    border: none;
}}
QListWidget::item {{
    padding: 3px 8px 3px 4px;
}}
QListWidget::item:hover {{
    background-color: {POPUP_ITEM_HOVER_COLOR};
    border-radius: 4px;
}}
QListWidget::item:selected {{
    border-radius: 4px;
    color: white;
    background-color: {POPUP_ITEM_SELECTED_COLOR};
}}
"""

POPUP_MENU_STYLE = f"""
QMenu {{
    background-color: {popup_rgba(240)};
    color: {TEXT_COLOR};
    border: 1px solid {POPUP_BORDER_COLOR};
    padding: 4px;
}}
QMenu::item {{
    padding: 4px 18px 4px 10px;
    background-color: transparent;
}}
QMenu::item:selected {{
    background-color: {POPUP_ITEM_SELECTED_COLOR};
    border-radius: 4px;
}}
"""

# === Tree View Style ===
TREE_VIEW_STYLE = f"""
QTreeView {{
    background-color: {MAIN_UI_COLOR};
    border: 1px solid {BORDER_COLOR};
    show-decoration-selected: 1;
    outline: none;
    selection-color: white;
}}

QHeaderView::section {{
    background-color: #505558;
    border: 1px solid #444;
    color: {TEXT_COLOR};
}}

QHeaderView {{
    background-color: #505558;
}}


"""

# === Title Bar Style ===
TITLE_BAR_STYLE = f"""
#titleBar {{
    background-color: {TITLE_BAR_COLOR};
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
}}
"""

# === Tool Button Style ===
TOOL_BUTTON_STYLE = """
QPushButton {
    background-color: #5D5D5D;
    border: none;
    padding: 6px;
    border-radius: 4px;
}
QPushButton:hover {
    background-color: #707070;
}
QPushButton:pressed {
    background-color: #3F3F3F;
}
"""

# === Menu Bar Style ===
MENU_BAR_STYLE = f"""
QMenuBar {{
    background-color: {MAIN_UI_COLOR};
    color: {TEXT_COLOR};
    border: none;
    border-left: 1px solid rgb(80, 80, 80);  
    border-right: 1px solid rgb(80, 80, 80);
    
}}
QMenuBar::item {{
    background-color: transparent;
}}
QMenuBar::item:selected {{
    background-color: #5285A6;
}}
"""

# === Overlay Style ===
OVERLAY_STYLE = """
background-color: rgba(0, 0, 0, 80);
border-radius: 10px;
"""

# === Central Widget Style ===
CENTRAL_WIDGET_STYLE = f"""
#centralWidget {{ 
    background-color: {MAIN_UI_COLOR}; 
    border-radius: 10px; 
    border: 1px solid rgba(80, 80, 80); /* subtle border */
}}
"""

# Backward-compatible alias for older imports/usages.
CENTERAL_WIDGET_STYLE = CENTRAL_WIDGET_STYLE

# === Main UI Scrollbar Style ===
MAIN_UI_STYLE = """
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 2px 0 2px 0;
    border: none;
}

QScrollBar::handle:vertical {
    background: #666;
    border-radius: 4px;
    min-height: 40px;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    background: none;
    height: 0;
}

QScrollBar:horizontal {
    background: transparent;
    height: 8px;
    margin: 0 2px 0 2px;
    border: none;
}

QScrollBar::handle:horizontal {
    background: #666;
    border-radius: 4px;
    min-width: 20px;
}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {
    background: none;
    width: 0;
}
"""

# === Window Control Button Styles ===
CLOSE_BUTTON_STYLE = """
QPushButton {
    background: transparent;
    border-radius: 12px;
    color: white;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #e74c3c;
}
"""

MINMAX_BUTTON_STYLE = """
QPushButton {
    background: transparent;
    border-radius: 12px;
    color: white;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #6a8a8a;
}
"""

# === Icon Button Style ===
ICON_BUTTON_STYLE = """
QPushButton {
    background-color: transparent;
    border: none;
    padding: 0px;
}
QPushButton:hover {
    background-color: transparent;
}
"""
