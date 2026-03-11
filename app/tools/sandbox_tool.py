"""Sandboxed Python execution tool for data analysis."""

import io
import concurrent.futures
import contextlib
import traceback
import pandas as pd
import numpy as np
from langchain.tools import Tool

from app.tools.dataset_tools import dataset_context
from app.config import settings


_SAFE_BUILTINS = {
    "print": print,
    "len": len,
    "range": range,
    "list": list,
    "dict": dict,
    "set": set,
    "tuple": tuple,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "round": round,
    "sorted": sorted,
    "sum": sum,
    "min": min,
    "max": max,
    "abs": abs,
    "enumerate": enumerate,
    "zip": zip,
    "isinstance": isinstance,
    "type": type,
    "repr": repr,
    "True": True,
    "False": False,
    "None": None,
}


def _run_code(code: str) -> str:
    """Execute code synchronously in a persistent namespace and capture stdout.

    Variables defined in previous calls within the same session are available.
    The full dataset df is refreshed each call; all user-defined vars persist.
    """
    namespace = dataset_context.get_or_create_namespace(pd, np, _SAFE_BUILTINS)
    # Refresh df so agent always sees the canonical dataset
    namespace["df"] = dataset_context.get_dataframe().copy()
    # Re-assert trusted bindings in case agent code accidentally overwrote them
    namespace["pd"] = pd
    namespace["np"] = np
    namespace["set_working_df"] = dataset_context.set_working_dataframe
    namespace["__builtins__"] = _SAFE_BUILTINS

    stdout_capture = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout_capture):
            exec(code, namespace)  # noqa: S102
    except Exception:
        return f"Error:\n{traceback.format_exc()}"

    output = stdout_capture.getvalue()
    if not output:
        return "Code executed successfully (no output printed)."

    max_chars = settings.SANDBOX_MAX_OUTPUT
    if len(output) > max_chars:
        output = output[:max_chars] + f"\n... [output truncated at {max_chars} chars]"

    return output


def _strip_code_fences(code: str) -> str:
    """Remove markdown code fences (``` or ```python) from code strings."""
    import re
    return re.sub(r"^```(?:\w+)?\n?", "", re.sub(r"\n?```$", "", code.strip()))


def execute_python_func(code: str) -> str:
    """
    Execute Python code against the loaded dataset.

    Args:
        code: Python code string to execute

    Returns:
        Captured stdout output, truncated to SANDBOX_MAX_OUTPUT chars
    """
    code = _strip_code_fences(code)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_run_code, code)
        try:
            return future.result(timeout=settings.SANDBOX_TIMEOUT)
        except concurrent.futures.TimeoutError:
            future.cancel()
            return f"Error: Code execution timed out after {settings.SANDBOX_TIMEOUT} seconds."
        except Exception as e:
            return f"Error: {str(e)}"


execute_python_tool = Tool(
    name="execute_python",
    description="""Execute Python code to analyze the dataset.

Available variables:
- `df`: the full dataset as a pandas DataFrame (refreshed each call)
- `pd`: pandas
- `np`: numpy
- `set_working_df(result_df)`: save a DataFrame for use by create_visualization

Variables you define persist across ALL execute_python calls in this session.
Example: define `top_artists` in call 1, use it directly in call 2.

Use print() to output results — only printed output is returned.
Output is capped at 3000 characters.

Examples:
  print(df.groupby('artist')['streams'].sum().nlargest(10))
  print(df['country'].unique())  # always check exact values before filtering
  print(df.describe()[['streams', 'popularity']])
  uk = df[df['country'] == 'United Kingdom']; set_working_df(uk); print(uk.head())""",
    func=execute_python_func,
)
