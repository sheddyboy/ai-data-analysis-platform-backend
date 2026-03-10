"""Tools for loading and accessing datasets."""

import pandas as pd
from langchain.tools import Tool
from typing import Dict, Any, Optional


class DatasetContext:
    """Context object to hold the current dataset during agent execution."""

    def __init__(self):
        self.df: Optional[pd.DataFrame] = None
        self.working_df: Optional[pd.DataFrame] = None
        self.metadata: Dict[str, Any] = {}

    def load_dataset(self, df: pd.DataFrame, metadata: Dict[str, Any]):
        """Load a dataset into the context."""
        self.df = df
        self.working_df = None
        self.metadata = metadata

    def get_dataframe(self) -> pd.DataFrame:
        """Get the current dataframe."""
        if self.df is None:
            raise ValueError("No dataset loaded")
        return self.df

    def set_working_dataframe(self, df: pd.DataFrame):
        """Set a filtered/sorted working dataframe for subsequent operations."""
        self.working_df = df

    def get_working_dataframe(self) -> pd.DataFrame:
        """Get the working dataframe if set, otherwise the full dataframe."""
        if self.working_df is not None:
            return self.working_df
        if self.df is None:
            raise ValueError("No dataset loaded")
        return self.df

    def get_metadata(self) -> Dict[str, Any]:
        """Get dataset metadata."""
        return self.metadata


# Global context for the current dataset
dataset_context = DatasetContext()


def load_dataset_func(input_str: str) -> str:
    """
    Load and describe the dataset.
    
    Args:
        input_str: Not used (tool requires no input)
        
    Returns:
        Description of the loaded dataset
    """
    try:
        df = dataset_context.get_dataframe()
        metadata = dataset_context.get_metadata()
        
        # Build description
        description = f"""Dataset loaded successfully:
- Rows: {len(df)}
- Columns: {len(df.columns)}
- Column Names: {', '.join(df.columns.tolist())}

Column Types:
"""
        for col, dtype in zip(df.columns, df.dtypes):
            description += f"  - {col}: {dtype}\n"
        
        # Add sample data
        description += f"\nFirst 3 rows:\n{df.head(3).to_string()}\n"
        
        return description
        
    except Exception as e:
        return f"Error loading dataset: {str(e)}"


# Create the LangChain tool
load_dataset_tool = Tool(
    name="load_dataset",
    description="""Use this tool to load and examine the dataset. 
    This should typically be your first step to understand what data is available.
    The tool will show you the column names, types, and sample data.""",
    func=load_dataset_func
)
