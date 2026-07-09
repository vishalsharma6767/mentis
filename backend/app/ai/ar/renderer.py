"""AR renderer: generates board action sequences for the frontend canvas."""

from typing import Optional


class ARRenderer:
    """Builds board action JSON for the AR pen canvas."""

    def write(self, text: str, color: Optional[str] = None) -> dict:
        return {'write': text, 'color': color}

    def writeln(self, text: str, color: Optional[str] = None) -> dict:
        return {'writeln': text, 'color': color}

    def line(self, x1, y1, x2, y2, color=None) -> dict:
        return {'line': {'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2, 'color': color}}

    def arrow(self, x1, y1, x2, y2, color=None) -> dict:
        return {'arrow': {'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2, 'color': color}}

    def circle(self, x, y, r, color=None) -> dict:
        return {'circle': {'x': x, 'y': y, 'radius': r, 'color': color}}

    def underline(self, y, w, color=None) -> dict:
        return {'underline': {'y': y, 'width': w, 'color': color}}

    def clear(self) -> dict:
        return {'clear': True}
