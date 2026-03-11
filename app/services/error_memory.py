"""
Lightweight error pattern memory service.

Persists agent error patterns to a JSON file so future runs can avoid
repeating the same mistakes. Pre-seeded with patterns observed in real
execution logs.
"""

import json
import re
from pathlib import Path
from typing import Dict, List


# Pre-seeded patterns derived from observed agent execution logs.
# These are ALWAYS injected into the prompt regardless of what's in the file.
KNOWN_PATTERNS: Dict[str, str] = {
    "empty_filter_country": (
        "Before filtering on country/region, check exact values first: "
        "print(df['country'].unique()) — names often differ from common "
        "abbreviations (e.g., 'United Kingdom' not 'UK', 'United States' not 'US')."
    ),
    "empty_filter_category": (
        "Before filtering on any categorical column (genre, label, etc.), "
        "always verify exact values: print(df['column'].unique())"
    ),
    "nameerror_variable": (
        "Variables defined in execute_python persist across calls in this session. "
        "If you get a NameError, the variable was never defined — redefine it in "
        "the current call."
    ),
    "json_tool_input": (
        "For create_visualization and generate_insights, Action Input must be "
        "a raw JSON object using double quotes only — never Python dict syntax "
        "with single quotes and never wrap in an outer string."
    ),
}

# Regexes to detect error patterns in agent step observations
_ERROR_DETECTORS: Dict[str, re.Pattern] = {
    "empty_filter_country": re.compile(
        r"Empty DataFrame.{0,80}(country|region|nation)|"
        r"(country|region|nation).{0,80}Empty DataFrame",
        re.IGNORECASE,
    ),
    "empty_filter_category": re.compile(r"Empty DataFrame", re.IGNORECASE),
    "nameerror_variable": re.compile(
        r"NameError: name '[\w]+' is not defined", re.IGNORECASE
    ),
    "json_tool_input": re.compile(
        r"Expecting property name enclosed in double quotes", re.IGNORECASE
    ),
}


class ErrorMemoryService:
    """
    Persists error patterns and provides relevant hints for future agent runs.

    Patterns are stored in a JSON file. Pre-seeded KNOWN_PATTERNS are always
    returned by get_hints(); dynamically discovered patterns accumulate over time.
    """

    def __init__(self, data_dir: str):
        self._path = Path(data_dir) / "error_memory.json"
        self._ensure_file()

    def _ensure_file(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._write({})

    def _read(self) -> Dict[str, dict]:
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def _write(self, data: Dict[str, dict]) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def record_error(self, pattern_key: str, hint: str) -> None:
        """Record or increment an error pattern in persistent storage.

        Args:
            pattern_key: Short identifier (e.g., 'empty_filter_country')
            hint: Human-readable hint to inject into future prompts
        """
        data = self._read()
        if pattern_key in data:
            data[pattern_key]["count"] = data[pattern_key].get("count", 0) + 1
        else:
            data[pattern_key] = {"hint": hint, "count": 1}
        self._write(data)

    def get_hints(self, question: str = "") -> List[str]:
        """Return hint strings to inject into the agent prompt.

        Always includes all KNOWN_PATTERNS hints. Appends any dynamically
        discovered patterns from the JSON file not already covered.

        Args:
            question: Reserved for future keyword-based filtering.

        Returns:
            List of hint strings, deduplicated.
        """
        hints = list(KNOWN_PATTERNS.values())

        data = self._read()
        known_keys = set(KNOWN_PATTERNS.keys())
        for key, entry in data.items():
            if key not in known_keys and "hint" in entry:
                hints.append(entry["hint"])

        return hints

    def scan_steps_and_record(self, agent_steps: list) -> None:
        """Scan completed agent steps for error observations and record patterns.

        Called after agent.analyze() completes. Detects known error patterns
        in step observations and persists them for analytics/future use.

        Args:
            agent_steps: List of step dicts with keys 'action', 'input', 'observation'
        """
        for step in agent_steps:
            obs = step.get("observation", "")
            for pattern_key, regex in _ERROR_DETECTORS.items():
                if regex.search(obs):
                    hint = KNOWN_PATTERNS.get(pattern_key, obs[:120])
                    self.record_error(pattern_key, hint)
