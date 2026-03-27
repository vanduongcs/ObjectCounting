"""Color palette and stylesheet theme settings."""

# Global colors
APP_BG = "#f6f7fb"
APP_TEXT = "#222222"
SURFACE_BG = "#ffffff"
SURFACE_BORDER = "#dde3ea"
SURFACE_HOVER_BORDER = "#c8d2dd"
TITLE_TEXT = "#1f1f1f"
BODY_TEXT = "#333333"
VALUE_TEXT = "#111111"
MUTED_TEXT = "#666666"
SECONDARY_TEXT = "#64748b"
ACCENT_TEXT = "#334155"
SECTION_HEADER_TEXT = "#444444"

# Inputs and controls
INPUT_BG = "#ffffff"
INPUT_BORDER = "#c8c8c8"
INPUT_ACTIVE_BORDER = "#9a9a9a"
INPUT_TEXT = "#222222"
INPUT_SEPARATOR = "#d6d6d6"
INPUT_DIVIDER = "#e8e8e8"
INPUT_HOVER_BG = "#f7f7f7"

CHECKBOX_BG = "#ffffff"
CHECKBOX_BORDER = "#bdbdbd"
CHECKBOX_CHECKED_BG = "#3b82f6"
CHECKBOX_CHECKED_BORDER = "#3b82f6"

BUTTON_BG = "#ffffff"
BUTTON_BORDER = "#bdbdbd"
BUTTON_TEXT = "#222222"
BUTTON_HOVER_BG = "#f7f7f7"
BUTTON_HOVER_BORDER = "#9f9f9f"

PRIMARY_BUTTON_BG = "#3b82f6"
PRIMARY_BUTTON_BORDER = "#3b82f6"
PRIMARY_BUTTON_TEXT = "#ffffff"
PRIMARY_BUTTON_HOVER_BG = "#2563eb"
PRIMARY_BUTTON_HOVER_BORDER = "#2563eb"

DANGER_BUTTON_BG = "#fff5f5"
DANGER_BUTTON_BORDER = "#e5a6a6"
DANGER_BUTTON_TEXT = "#b42318"
DANGER_BUTTON_HOVER_BG = "#ffeaea"
DANGER_BUTTON_HOVER_BORDER = "#d98b8b"

DRAWER_BUTTON_BG = "#ffffff"
DRAWER_BUTTON_BORDER = "#d9d9d9"
DRAWER_BUTTON_TEXT = "#333333"
DRAWER_BUTTON_HOVER_BG = "#f7f7f7"
DRAWER_BUTTON_HOVER_BORDER = "#bfbfbf"

DISABLED_BUTTON_BG = "#f0f0f0"
DISABLED_BUTTON_BORDER = "#dddddd"
DISABLED_BUTTON_TEXT = "#9a9a9a"

# Table and scroll areas
TABLE_GRID = "#ececec"
TABLE_ALT_BG = "#fafafa"
TABLE_TEXT = "#334155"
TABLE_MUTED_TEXT = "#94a3b8"
TABLE_SELECTION_BG = "#eef4ff"
TABLE_SELECTION_TEXT = "#1f2937"
TABLE_HEADER_BG = "#f8fafc"
TABLE_HEADER_TEXT = "#444444"
TABLE_HEADER_BORDER = "#e5eaf0"

SCROLLBAR_TRACK = "#eef2f6"
SCROLLBAR_HANDLE = "#c4cfdb"
SCROLLBAR_HANDLE_HOVER = "#a8b6c7"
SPLITTER_HANDLE = "#dde3ea"
SPLITTER_HANDLE_HOVER = "#c7d0da"

# Preview and overlays
VIDEO_CANVAS_BG = "#fbfcfe"
VIDEO_CANVAS_BORDER = "#d7dde5"
VIDEO_CANVAS_TEXT = "#666666"
TOGGLE_TRACK_ON_COLOR = "#2563eb"
TOGGLE_TRACK_OFF_COLOR = "#cbd5e1"
TOGGLE_TEXT_ON_COLOR = "#ffffff"
TOGGLE_TEXT_OFF_COLOR = "#475569"
TOGGLE_THUMB_COLOR = "#ffffff"
VIRTUAL_LINE_COLOR = (0, 0, 255)
LINE_ENTER_COLOR = (0, 200, 0)
LINE_EXIT_COLOR = (200, 0, 200)
TIMESTAMP_ROI_COLOR = (0, 255, 255)
DETECTION_LABEL_TEXT_COLOR = (255, 255, 255)
CLASS_COLOR_PALETTE = [
    (255, 56, 56), (255, 157, 151), (255, 112, 31), (255, 178, 29),
    (207, 210, 49), (72, 249, 10), (146, 204, 23), (61, 219, 134),
    (26, 147, 52), (0, 212, 187), (44, 153, 168), (0, 194, 255),
    (52, 69, 147), (100, 115, 255), (0, 24, 236), (132, 56, 255),
    (82, 0, 133), (203, 56, 255), (255, 149, 200), (255, 55, 199),
]

_MAIN_WINDOW_STYLESHEET_TEMPLATE = """
QMainWindow,
QWidget#root {
    background: __APP_BG__;
    color: __APP_TEXT__;
    font-family: "Segoe UI";
    font-size: 12px;
}
QFrame#videoStageCard,
QFrame#historyDrawerBody {
    background: __SURFACE_BG__;
    border: 1px solid __SURFACE_BORDER__;
    border-radius: 14px;
}
QScrollArea#sidePanelScroll,
QScrollArea#historyScroll,
QWidget#sidePanelViewport,
QWidget#sidePanelContent,
QWidget#historySidebar,
QWidget#historyViewport,
QWidget#historyListWidget {
    background: transparent;
    border: none;
}
QLabel#sectionTitle,
QLabel#historyHeaderTitle {
    color: __TITLE_TEXT__;
    font-size: 14px;
    font-weight: 600;
}
QLabel#sectionHint,
QLabel#historyCardMeta,
QLabel#historyCardCounts {
    color: __MUTED_TEXT__;
    font-size: 11px;
}
QLabel#videoCanvas {
    background: __VIDEO_CANVAS_BG__;
    border: 1px solid __VIDEO_CANVAS_BORDER__;
    border-radius: 12px;
    color: __VIDEO_CANVAS_TEXT__;
    font-size: 15px;
    padding: 16px;
}
QFrame#sessionCard,
QFrame#emptyHistoryCard {
    background: __SURFACE_BG__;
    border: 1px solid __SESSION_CARD_BORDER__;
    border-radius: 12px;
}
QFrame#sessionCard:hover {
    border-color: __SURFACE_HOVER_BORDER__;
}
QLabel#overviewItem {
    color: __BODY_TEXT__;
    font-weight: 600;
}
QLabel#overviewValue {
    color: __VALUE_TEXT__;
}
QLabel#fpsValue {
    color: __VALUE_TEXT__;
}
QGroupBox {
    background: __SURFACE_BG__;
    border: 1px solid __SURFACE_BORDER__;
    border-radius: 14px;
    margin-top: 0px;
    padding: 0;
    color: __TABLE_SELECTION_TEXT__;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: padding;
    subcontrol-position: top left;
    left: 14px;
    padding: 0;
    background: transparent;
    color: __ACCENT_TEXT__;
}
QLabel {
    color: __BODY_TEXT__;
}
QLabel#fieldLabel,
QLabel#historyCardTitle {
    color: __BODY_TEXT__;
    font-weight: 600;
}
QComboBox,
QDoubleSpinBox {
    background: __INPUT_BG__;
    border: 1px solid __INPUT_BORDER__;
    border-radius: 8px;
    padding: 6px 8px;
    min-height: 18px;
    color: __INPUT_TEXT__;
}
QDoubleSpinBox {
    padding-right: 28px;
}
QComboBox:hover,
QDoubleSpinBox:hover,
QComboBox:focus,
QDoubleSpinBox:focus {
    border-color: __INPUT_ACTIVE_BORDER__;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QDoubleSpinBox::up-button,
QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    width: 18px;
    background: __INPUT_BG__;
    border-left: 1px solid __INPUT_SEPARATOR__;
}
QDoubleSpinBox::up-button {
    subcontrol-position: top right;
    border-top-right-radius: 8px;
    border-bottom: 1px solid __INPUT_DIVIDER__;
}
QDoubleSpinBox::down-button {
    subcontrol-position: bottom right;
    border-bottom-right-radius: 8px;
}
QDoubleSpinBox::up-button:hover,
QDoubleSpinBox::down-button:hover {
    background: __INPUT_HOVER_BG__;
}
QDoubleSpinBox::up-arrow,
QDoubleSpinBox::down-arrow {
    width: 8px;
    height: 8px;
}
QCheckBox {
    color: __INPUT_TEXT__;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid __CHECKBOX_BORDER__;
    border-radius: 4px;
    background: __CHECKBOX_BG__;
}
QCheckBox::indicator:checked {
    background: __CHECKBOX_CHECKED_BG__;
    border-color: __CHECKBOX_CHECKED_BORDER__;
}
QPushButton {
    border-radius: 8px;
    border: 1px solid __BUTTON_BORDER__;
    background: __BUTTON_BG__;
    color: __BUTTON_TEXT__;
    font-size: 12px;
    font-weight: 500;
    padding: 8px 10px;
}
QPushButton:hover {
    background: __BUTTON_HOVER_BG__;
    border-color: __BUTTON_HOVER_BORDER__;
}
QPushButton[variant="icon"] {
    padding: 0;
    min-width: 0;
}
QPushButton[variant="primary"] {
    background: __PRIMARY_BUTTON_BG__;
    border-color: __PRIMARY_BUTTON_BORDER__;
    color: __PRIMARY_BUTTON_TEXT__;
}
QPushButton[variant="primary"]:hover {
    background: __PRIMARY_BUTTON_HOVER_BG__;
    border-color: __PRIMARY_BUTTON_HOVER_BORDER__;
}
QPushButton[variant="danger"] {
    background: __DANGER_BUTTON_BG__;
    border-color: __DANGER_BUTTON_BORDER__;
    color: __DANGER_BUTTON_TEXT__;
}
QPushButton[variant="danger"]:hover {
    background: __DANGER_BUTTON_HOVER_BG__;
    border-color: __DANGER_BUTTON_HOVER_BORDER__;
}
QPushButton[variant="drawer"] {
    background: __DRAWER_BUTTON_BG__;
    border: 1px solid __DRAWER_BUTTON_BORDER__;
    border-radius: 8px;
    color: __DRAWER_BUTTON_TEXT__;
    font-size: 14px;
    font-weight: 600;
    padding: 0;
}
QPushButton[variant="drawer"]:hover {
    background: __DRAWER_BUTTON_HOVER_BG__;
    border-color: __DRAWER_BUTTON_HOVER_BORDER__;
}
QPushButton:disabled {
    background: __DISABLED_BUTTON_BG__;
    border-color: __DISABLED_BUTTON_BORDER__;
    color: __DISABLED_BUTTON_TEXT__;
}
QFrame#resultTableCard {
    background: __SURFACE_BG__;
    border: 1px solid __SURFACE_BORDER__;
    border-radius: 12px;
}
QWidget#resultTableStackHost,
QWidget#resultTableViewport,
QTableWidget#resultTable {
    background: transparent;
    border: none;
}
QTableWidget#resultTable {
    gridline-color: __TABLE_GRID__;
    alternate-background-color: __TABLE_ALT_BG__;
    color: __TABLE_TEXT__;
    selection-background-color: __TABLE_SELECTION_BG__;
    selection-color: __TABLE_SELECTION_TEXT__;
}
QTableWidget#resultTable::item {
    color: __TABLE_TEXT__;
    padding: 6px;
}
QHeaderView::section {
    background: __TABLE_HEADER_BG__;
    color: __TABLE_HEADER_TEXT__;
    border: none;
    border-bottom: 1px solid __TABLE_HEADER_BORDER__;
    padding: 7px;
    font-weight: 600;
}
QTableCornerButton::section {
    background: __TABLE_HEADER_BG__;
    border: none;
    border-bottom: 1px solid __TABLE_HEADER_BORDER__;
}
QLabel#emptyStateLabel {
    background: transparent;
    color: __SECONDARY_TEXT__;
    border: none;
    padding: 16px;
    line-height: 1.4;
}
QScrollBar:vertical {
    background: __SCROLLBAR_TRACK__;
    border-radius: 4px;
    width: 8px;
    margin: 8px 0 8px 0;
}
QScrollBar::handle:vertical {
    background: __SCROLLBAR_HANDLE__;
    border-radius: 4px;
    min-height: 36px;
}
QScrollBar::handle:vertical:hover {
    background: __SCROLLBAR_HANDLE_HOVER__;
}
QScrollBar:horizontal {
    background: __SCROLLBAR_TRACK__;
    border-radius: 4px;
    height: 8px;
    margin: 0 8px 0 8px;
}
QScrollBar::handle:horizontal {
    background: __SCROLLBAR_HANDLE__;
    border-radius: 4px;
    min-width: 36px;
}
QScrollBar::handle:horizontal:hover {
    background: __SCROLLBAR_HANDLE_HOVER__;
}
QScrollBar::add-line,
QScrollBar::sub-line,
QScrollBar::add-page,
QScrollBar::sub-page {
    background: transparent;
    border: none;
    width: 0px;
    height: 0px;
}
QSplitter::handle {
    background: transparent;
}
QSplitter::handle:horizontal {
    background: __SPLITTER_HANDLE__;
    border-radius: 999px;
    margin: 14px 4px;
}
QSplitter::handle:horizontal:hover {
    background: __SPLITTER_HANDLE_HOVER__;
}
"""

_STYLE_TOKENS = {
    "APP_BG": APP_BG,
    "APP_TEXT": APP_TEXT,
    "SURFACE_BG": SURFACE_BG,
    "SURFACE_BORDER": SURFACE_BORDER,
    "SURFACE_HOVER_BORDER": SURFACE_HOVER_BORDER,
    "TITLE_TEXT": TITLE_TEXT,
    "BODY_TEXT": BODY_TEXT,
    "VALUE_TEXT": VALUE_TEXT,
    "MUTED_TEXT": MUTED_TEXT,
    "SECONDARY_TEXT": SECONDARY_TEXT,
    "ACCENT_TEXT": ACCENT_TEXT,
    "INPUT_BG": INPUT_BG,
    "INPUT_BORDER": INPUT_BORDER,
    "INPUT_ACTIVE_BORDER": INPUT_ACTIVE_BORDER,
    "INPUT_TEXT": INPUT_TEXT,
    "INPUT_SEPARATOR": INPUT_SEPARATOR,
    "INPUT_DIVIDER": INPUT_DIVIDER,
    "INPUT_HOVER_BG": INPUT_HOVER_BG,
    "CHECKBOX_BG": CHECKBOX_BG,
    "CHECKBOX_BORDER": CHECKBOX_BORDER,
    "CHECKBOX_CHECKED_BG": CHECKBOX_CHECKED_BG,
    "CHECKBOX_CHECKED_BORDER": CHECKBOX_CHECKED_BORDER,
    "BUTTON_BG": BUTTON_BG,
    "BUTTON_BORDER": BUTTON_BORDER,
    "BUTTON_TEXT": BUTTON_TEXT,
    "BUTTON_HOVER_BG": BUTTON_HOVER_BG,
    "BUTTON_HOVER_BORDER": BUTTON_HOVER_BORDER,
    "PRIMARY_BUTTON_BG": PRIMARY_BUTTON_BG,
    "PRIMARY_BUTTON_BORDER": PRIMARY_BUTTON_BORDER,
    "PRIMARY_BUTTON_TEXT": PRIMARY_BUTTON_TEXT,
    "PRIMARY_BUTTON_HOVER_BG": PRIMARY_BUTTON_HOVER_BG,
    "PRIMARY_BUTTON_HOVER_BORDER": PRIMARY_BUTTON_HOVER_BORDER,
    "DANGER_BUTTON_BG": DANGER_BUTTON_BG,
    "DANGER_BUTTON_BORDER": DANGER_BUTTON_BORDER,
    "DANGER_BUTTON_TEXT": DANGER_BUTTON_TEXT,
    "DANGER_BUTTON_HOVER_BG": DANGER_BUTTON_HOVER_BG,
    "DANGER_BUTTON_HOVER_BORDER": DANGER_BUTTON_HOVER_BORDER,
    "DRAWER_BUTTON_BG": DRAWER_BUTTON_BG,
    "DRAWER_BUTTON_BORDER": DRAWER_BUTTON_BORDER,
    "DRAWER_BUTTON_TEXT": DRAWER_BUTTON_TEXT,
    "DRAWER_BUTTON_HOVER_BG": DRAWER_BUTTON_HOVER_BG,
    "DRAWER_BUTTON_HOVER_BORDER": DRAWER_BUTTON_HOVER_BORDER,
    "DISABLED_BUTTON_BG": DISABLED_BUTTON_BG,
    "DISABLED_BUTTON_BORDER": DISABLED_BUTTON_BORDER,
    "DISABLED_BUTTON_TEXT": DISABLED_BUTTON_TEXT,
    "TABLE_GRID": TABLE_GRID,
    "TABLE_ALT_BG": TABLE_ALT_BG,
    "TABLE_TEXT": TABLE_TEXT,
    "TABLE_SELECTION_BG": TABLE_SELECTION_BG,
    "TABLE_SELECTION_TEXT": TABLE_SELECTION_TEXT,
    "TABLE_HEADER_BG": TABLE_HEADER_BG,
    "TABLE_HEADER_TEXT": TABLE_HEADER_TEXT,
    "TABLE_HEADER_BORDER": TABLE_HEADER_BORDER,
    "VIDEO_CANVAS_BG": VIDEO_CANVAS_BG,
    "VIDEO_CANVAS_BORDER": VIDEO_CANVAS_BORDER,
    "VIDEO_CANVAS_TEXT": VIDEO_CANVAS_TEXT,
    "SESSION_CARD_BORDER": SURFACE_BORDER,
    "SCROLLBAR_TRACK": SCROLLBAR_TRACK,
    "SCROLLBAR_HANDLE": SCROLLBAR_HANDLE,
    "SCROLLBAR_HANDLE_HOVER": SCROLLBAR_HANDLE_HOVER,
    "SPLITTER_HANDLE": SPLITTER_HANDLE,
    "SPLITTER_HANDLE_HOVER": SPLITTER_HANDLE_HOVER,
}

MAIN_WINDOW_STYLESHEET = _MAIN_WINDOW_STYLESHEET_TEMPLATE
for _token, _value in _STYLE_TOKENS.items():
    MAIN_WINDOW_STYLESHEET = MAIN_WINDOW_STYLESHEET.replace(f"__{_token}__", _value)
