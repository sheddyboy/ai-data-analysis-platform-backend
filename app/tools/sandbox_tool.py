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
    """Execute code synchronously in a restricted namespace and capture stdout."""
    df = dataset_context.get_dataframe().copy()

    namespace = {
        "df": df,
        "pd": pd,
        "np": np,
        "set_working_df": dataset_context.set_working_dataframe,
        "__builtins__": _SAFE_BUILTINS,
    }

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
- `df`: the full dataset as a pandas DataFrame (read-only copy)
- `pd`: pandas
- `np`: numpy
- `set_working_df(result_df)`: save a DataFrame for use by create_visualization

Use print() to output results — only printed output is returned.
Output is capped at 3000 characters.

Examples:
  print(df.groupby('artist')['streams'].sum().nlargest(10))
  print(df[df['country'] == 'UK'].groupby('artist').size().nlargest(20))
  print(df.describe()[['streams', 'popularity']])
  uk = df[df['country'] == 'UK']; set_working_df(uk); print(uk.head())""",
    func=execute_python_func,
)
