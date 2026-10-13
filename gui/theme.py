"""Visual styling and theme system for SCTRL GUI.

Modern, high-contrast dark theme with curated accents, glassmorphic card
surfaces, and support tier badge styles.
"""

from __future__ import annotations

# Palette definitions
BG_DARK = "#0d1117"
BG_SURFACE = "#161b22"
BG_CARD = "#1f242c"
BG_CARD_HOVER = "#272e38"
BORDER_SUBTLE = "#30363d"
BORDER_FOCUS = "#58a6ff"

TEXT_PRIMARY = "#f0f6fc"
TEXT_SECONDARY = "#8b949e"
TEXT_MUTED = "#6e7681"

ACCENT_CYAN = "#00e5ff"
ACCENT_GREEN = "#2ea043"
ACCENT_AMBER = "#d29922"
ACCENT_RED = "#f85149"
ACCENT_PURPLE = "#a371f7"

# Tier color mappings
TIER_COLORS = {
    "verified": ("#2ea043", "#0d2b14"),    # green text, dark green bg
    "community": ("#d29922", "#2e2107"),   # amber text, dark amber bg
    "detected": ("#58a6ff", "#0c213b"),    # blue text, dark blue bg
    "unsupported": ("#f85149", "#360c0c"), # red text, dark red bg
}


def get_stylesheet() -> str:
    """Return application-wide Qt stylesheet."""
    return f"""
    QMainWindow, QDialog {{
        background-color: {BG_DARK};
        color: {TEXT_PRIMARY};
        font-family: 'Segoe UI', 'Ubuntu', 'Inter', sans-serif;
    }}

    QWidget {{
        color: {TEXT_PRIMARY};
        font-size: 13px;
    }}

    QFrame.card {{
        background-color: {BG_CARD};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 10px;
        padding: 12px;
    }}

    QFrame.card:hover {{
        border: 1px solid {BORDER_FOCUS};
    }}

    QFrame.nav-sidebar {{
        background-color: {BG_SURFACE};
        border-right: 1px solid {BORDER_SUBTLE};
    }}

    QPushButton.nav-btn {{
        background-color: transparent;
        color: {TEXT_SECONDARY};
        text-align: left;
        padding: 10px 16px;
        border: none;
        border-radius: 6px;
        font-weight: 500;
        font-size: 13px;
    }}

    QPushButton.nav-btn:hover {{
        background-color: {BG_CARD};
        color: {TEXT_PRIMARY};
    }}

    QPushButton.nav-btn:checked {{
        background-color: #1a2736;
        color: {ACCENT_CYAN};
        font-weight: bold;
        border-left: 3px solid {ACCENT_CYAN};
    }}

    QPushButton.primary-btn {{
        background-color: #1f6feb;
        color: #ffffff;
        border: none;
        border-radius: 6px;
        padding: 8px 18px;
        font-weight: 600;
    }}

    QPushButton.primary-btn:hover {{
        background-color: #388bfd;
    }}

    QPushButton.primary-btn:pressed {{
        background-color: #1158c7;
    }}

    QPushButton.danger-btn {{
        background-color: #da3633;
        color: #ffffff;
        border: none;
        border-radius: 6px;
        padding: 8px 18px;
        font-weight: 600;
    }}

    QPushButton.danger-btn:hover {{
        background-color: #f85149;
    }}

    QSlider::groove:horizontal {{
        height: 6px;
        background: {BORDER_SUBTLE};
        border-radius: 3px;
    }}

    QSlider::sub-page:horizontal {{
        background: {ACCENT_CYAN};
        border-radius: 3px;
    }}

    QSlider::handle:horizontal {{
        background: #ffffff;
        border: 2px solid {ACCENT_CYAN};
        width: 16px;
        height: 16px;
        margin: -5px 0;
        border-radius: 8px;
    }}

    QProgressBar {{
        background-color: {BG_SURFACE};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 4px;
        text-align: center;
        color: {TEXT_PRIMARY};
        font-weight: bold;
    }}

    QProgressBar::chunk {{
        background-color: {ACCENT_CYAN};
        border-radius: 3px;
    }}

    QComboBox {{
        background-color: {BG_SURFACE};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 6px;
        padding: 6px 12px;
        color: {TEXT_PRIMARY};
    }}

    QComboBox:hover {{
        border: 1px solid {BORDER_FOCUS};
    }}

    QComboBox::drop-down {{
        border: none;
    }}

    QLabel.title {{
        font-size: 18px;
        font-weight: bold;
        color: {TEXT_PRIMARY};
    }}

    QLabel.subtitle {{
        font-size: 12px;
        color: {TEXT_SECONDARY};
    }}

    QLabel.metric-val {{
        font-size: 26px;
        font-weight: bold;
        color: {TEXT_PRIMARY};
    }}

    QScrollArea {{
        border: none;
        background: transparent;
    }}

    QScrollBar:vertical {{
        background: {BG_DARK};
        width: 8px;
        margin: 0;
    }}

    QScrollBar::handle:vertical {{
        background: {BORDER_SUBTLE};
        min-height: 20px;
        border-radius: 4px;
    }}

    QScrollBar::handle:vertical:hover {{
        background: {TEXT_MUTED};
    }}
    """
