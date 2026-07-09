"""Animation specs for board actions: cursor speed, wobble, colors, easing.

All timing values are in milliseconds. These constants control how the
frontend AR canvas renders the teacher's board actions — handwriting
speed, pen wobble, colour scheme, and line spacing.
"""

# ── Pen / Cursor ────────────────────────────────────────────────────────

CURSOR_SPEED_MS = 25
PEN_WOBBLE = 1.2
DEFAULT_COLOR = '#00D4FF'
HIGHLIGHT_COLOR = '#FFD700'
ERROR_COLOR = '#FF6B6B'
CORRECT_COLOR = '#51CF66'
FORMULA_COLOR = '#FFD700'

# ── Board layout ────────────────────────────────────────────────────────

LINE_HEIGHT = 42
CHAR_WIDTH = 14
MARGIN_X = 40
MARGIN_Y = 60
MAX_LINES_PER_PAGE = 12

# ── Animation timing ────────────────────────────────────────────────────

DRAW_DURATION_MS = 500
FADE_DURATION_MS = 300
PULSE_DURATION_MS = 800
GLOW_DURATION_MS = 1000
WRITE_CHAR_MS = 80
ERASE_DURATION_MS = 400

# ── Easing functions ────────────────────────────────────────────────────

EASE_IN_OUT = 'cubic-bezier(0.42, 0.0, 0.58, 1.0)'
EASE_OUT = 'cubic-bezier(0.0, 0.0, 0.58, 1.0)'
LINEAR = 'linear'

# ── Priority levels ─────────────────────────────────────────────────────

PRIORITY_HIGH = 0
PRIORITY_MEDIUM = 5
PRIORITY_LOW = 10


def write_duration(text_length: int) -> int:
    """Estimate how long it takes to hand-write a text string."""
    return max(DRAW_DURATION_MS, text_length * WRITE_CHAR_MS)


def line_y_position(line_number: int) -> int:
    """Calculate the Y position for a given line number on the board."""
    return MARGIN_Y + line_number * LINE_HEIGHT
