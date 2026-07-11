"""Shared JSON extraction utility.

Provides a single ``extract_json()`` function used by all agents and
services. Replaces the 4 duplicate implementations that previously lived
in planner.py, teacher.py, gateway.py, and reasoner.py.

Usage::

    from app.utils.json_utils import extract_json

    data = extract_json(llm_response.text)
    if data is None:
        # fallback or error
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional


def extract_json(text: str) -> Optional[dict[str, Any]]:
    """Extract the first JSON object from a string.

    Tries in order:
      1. Direct ``json.loads`` if text is ``{...}``.
      2. Content inside ```json ... ``` fences.
      3. First balanced ``{...}`` block found via brace-depth scan.

    Returns the parsed dict or ``None`` if no valid JSON is found.
    """
    text = text.strip()
    if text.startswith('{') and text.endswith('}'):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start >= 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    pass
    return None
