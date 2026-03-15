"""Tool factory for loading and describing the current dataset."""

from langchain_core.tools import tool
from app.agents.context import AnalysisContext


def build_load_dataset_tool(context: AnalysisContext):
    """Return a load_dataset tool bound to the given request-scoped context."""

    @tool
    def load_dataset(query: str = "") -> str:  # noqa: ARG001
        """Load and describe the dataset. Call this first to understand available columns and data types.

        Returns column names, types, row count, and the first 3 rows.
        """
        try:
            df = context.get_dataframe()
            metadata = context.metadata

            description = (
                f"Dataset loaded successfully:\n"
                f"- Rows: {len(df)}\n"
                f"- Columns: {len(df.columns)}\n"
                f"- Column Names: {', '.join(df.columns.tolist())}\n\n"
                f"Column Types:\n"
            )
            for col, dtype in zip(df.columns, df.dtypes):
                description += f"  - {col}: {dtype}\n"

            description += f"\nFirst 3 rows:\n{df.head(3).to_string()}\n"

            if metadata.get("summary_statistics"):
                description += "\nNumeric column statistics available (call execute_python for details).\n"

            return description

        except Exception as e:
            return f"Error loading dataset: {str(e)}"

    return load_dataset
