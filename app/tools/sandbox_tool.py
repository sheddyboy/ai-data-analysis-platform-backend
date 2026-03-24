"""Tool factory for sandboxed Python execution against the dataset."""

import io
import re
import concurrent.futures
import contextlib
import traceback
import pandas as pd
import numpy as np
from langchain_core.tools import tool

from loguru import logger

from app.agents.context import AnalysisContext
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


def _strip_code_fences(code: str) -> str:
    """Remove markdown code fences (``` or ```python) from code strings."""
    return re.sub(r"^```(?:\w+)?\n?", "", re.sub(r"\n?```$", "", code.strip()))


def build_execute_python_tool(context: AnalysisContext):
    """Return an execute_python tool bound to the given request-scoped context."""

    def _run_code(code: str) -> str:
        namespace = context.get_or_create_namespace(pd, np, _SAFE_BUILTINS)
        # Refresh df each call so agent always sees the canonical dataset
        namespace["df"] = context.get_dataframe().copy()
        # Re-assert trusted bindings
        namespace["pd"] = pd
        namespace["np"] = np
        namespace["set_working_df"] = context.set_working_dataframe
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

    @tool
    def execute_python(code: str) -> str:  # noqa: RUF029
        """Execute Python/pandas code against the loaded dataset.

        Available variables:
        - `df`: the full dataset as a pandas DataFrame (refreshed each call)
        - `pd`: pandas
        - `np`: numpy
        - `set_working_df(result_df)`: save a DataFrame for use by create_visualization

        Variables you define persist across ALL execute_python calls in this session.
        Use print() to output results — only printed output is returned.
        Output is capped at 3000 characters.

        Examples:
          print(df.groupby('artist')['streams'].sum().nlargest(10))
          print(df['country'].unique())  # always check exact values before filtering
          uk = df[df['country'] == 'United Kingdom']; set_working_df(uk); print(uk.head())
        """
        clean_code = _strip_code_fences(code)
        preview = clean_code[:120].replace("\n", " ")
        logger.debug("[tool:execute_python] running: {}{}", preview, "..." if len(clean_code) > 120 else "")
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_run_code, clean_code)
            try:
                result = future.result(timeout=settings.SANDBOX_TIMEOUT)
                logger.debug("[tool:execute_python] output: {}", result[:200].replace("\n", " "))
                return result
            except concurrent.futures.TimeoutError:
                future.cancel()
                logger.warning("[tool:execute_python] timed out after {}s", settings.SANDBOX_TIMEOUT)
                return f"Error: Code execution timed out after {settings.SANDBOX_TIMEOUT} seconds."
            except Exception as e:
                logger.error("[tool:execute_python] error: {}", e)
                return f"Error: {str(e)}"

    return execute_python
