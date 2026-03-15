"""Per-request analysis context — replaces module-level singletons from v1."""

from typing import Any, Optional
import pandas as pd


class AnalysisContext:
    """
    Request-scoped container for all mutable state shared between tools.

    One instance is created per query execution and injected into tool closures
    via build_tools(). This eliminates the v1 concurrency bug where module-level
    globals could be overwritten by concurrent requests.
    """

    def __init__(self, df: pd.DataFrame, metadata: dict[str, Any]) -> None:
        self.df: pd.DataFrame = df
        self.metadata: dict[str, Any] = metadata
        self.working_df: Optional[pd.DataFrame] = None
        self.exec_namespace: Optional[dict[str, Any]] = None
        self.visualizations: list[dict[str, Any]] = []

    # ── DataFrame helpers ────────────────────────────────────────────────────

    def get_dataframe(self) -> pd.DataFrame:
        return self.df

    def set_working_dataframe(self, df: pd.DataFrame) -> None:
        self.working_df = df

    def get_working_dataframe(self) -> pd.DataFrame:
        """Return the working (filtered/grouped) df or the full df as fallback."""
        return self.working_df if self.working_df is not None else self.df

    # ── Persistent execution namespace ───────────────────────────────────────

    def get_or_create_namespace(
        self, pd_module: Any, np_module: Any, safe_builtins: dict
    ) -> dict[str, Any]:
        """Return the persistent exec namespace, creating it on first call."""
        if self.exec_namespace is None:
            self.exec_namespace = {
                "df": self.df.copy(),
                "pd": pd_module,
                "np": np_module,
                "set_working_df": self.set_working_dataframe,
                "__builtins__": safe_builtins,
            }
        return self.exec_namespace

    # ── Visualization storage ────────────────────────────────────────────────

    def add_visualization(self, viz: dict[str, Any]) -> None:
        self.visualizations.append(viz)

    def get_visualizations(self) -> list[dict[str, Any]]:
        return self.visualizations
