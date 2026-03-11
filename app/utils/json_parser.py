"""Shared utility for robust JSON parsing of LLM tool inputs."""

import ast
import json
from typing import Any


def _parse_json_input(input_str: Any) -> dict:
    """Parse LLM tool input that should be a JSON object/dict.

    Handles four cases in order:
    1. Already a dict (passthrough — LangChain sometimes passes parsed objects)
    2. Valid JSON string: '{"key": "value"}'
    3. String-wrapped JSON (double-encoded): '"{\\"key\\": \\"value\\"}"'
    4. Python single-quote dict syntax: "{'key': 'value'}" via ast.literal_eval

    Args:
        input_str: Raw tool input, may be str or dict.

    Returns:
        Parsed dict.

    Raises:
        ValueError: If none of the parsing strategies succeed.
    """
    # Case 1: already a dict
    if isinstance(input_str, dict):
        return input_str

    if not isinstance(input_str, str):
        raise ValueError(f"Expected str or dict, got {type(input_str)}")

    stripped = input_str.strip()

    # Case 2 & 3: try JSON parse first
    try:
        result = json.loads(stripped)
        if isinstance(result, dict):
            return result
        # Case 3: double-encoded — json.loads returned a string which is itself JSON
        if isinstance(result, str):
            inner = json.loads(result)
            if isinstance(inner, dict):
                return inner
    except json.JSONDecodeError:
        pass

    # Case 4: Python single-quote dict syntax (safe — only handles literals)
    try:
        result = ast.literal_eval(stripped)
        if isinstance(result, dict):
            return result
    except (ValueError, SyntaxError):
        pass

    raise ValueError(
        f"Could not parse tool input as JSON object. Raw input: {input_str!r}"
    )
