"""Tools for data analysis operations."""

import pandas as pd
import json
from langchain.tools import Tool
from typing import Dict, Any
from app.tools.dataset_tools import dataset_context


def analyze_data_func(input_str: str) -> str:
    """
    Perform data analysis operations.
    
    Input format (JSON string):
    {
        "operation": "group_by" | "aggregate" | "sort",
        "column": "column_name",
        "agg_func": "sum" | "mean" | "count" | "max" | "min",
        "value_column": "column_to_aggregate" (optional)
    }
    
    Args:
        input_str: JSON string with operation parameters
        
    Returns:
        Analysis results as string
    """
    try:
        df = dataset_context.get_dataframe()
        params = json.loads(input_str)
        
        operation = params.get("operation")
        
        if operation == "group_by":
            column = params["column"]
            agg_func = params.get("agg_func", "count")
            value_col = params.get("value_column")

            if value_col:
                result = df.groupby(column)[value_col].agg(agg_func).reset_index()
            else:
                result = df.groupby(column).size().reset_index(name='count')

            dataset_context.set_working_dataframe(result)
            return f"Group by results:\n{result.to_string()}"

        elif operation == "aggregate":
            column = params["column"]
            agg_func = params.get("agg_func", "sum")

            result = df[column].agg(agg_func)
            return f"{agg_func.capitalize()} of {column}: {result}"

        elif operation == "sort":
            column = params["column"]
            ascending = params.get("ascending", False)
            n = params.get("n", 10)

            result = df.sort_values(column, ascending=ascending).head(n)
            dataset_context.set_working_dataframe(result)
            return f"Top {n} rows sorted by {column}:\n{result.to_string()}"
        
        else:
            return f"Unknown operation: {operation}"
    
    except Exception as e:
        return f"Error in analysis: {str(e)}"


def get_statistics_func(input_str: str) -> str:
    """
    Get statistical summary of columns.
    
    Input format (JSON string):
    {
        "columns": ["col1", "col2"] or "all"
    }
    
    Args:
        input_str: JSON string with columns to analyze
        
    Returns:
        Statistical summary
    """
    try:
        df = dataset_context.get_dataframe()
        params = json.loads(input_str)
        
        columns = params.get("columns", "all")
        
        if columns == "all":
            result = df.describe()
        else:
            result = df[columns].describe()
        
        return f"Statistical Summary:\n{result.to_string()}"
    
    except Exception as e:
        return f"Error getting statistics: {str(e)}"


def filter_data_func(input_str: str) -> str:
    """
    Filter dataset based on conditions.
    
    Input format (JSON string):
    {
        "column": "column_name",
        "operator": "==" | ">" | "<" | ">=" | "<=",
        "value": value_to_compare
    }
    
    Args:
        input_str: JSON string with filter parameters
        
    Returns:
        Filtered data summary
    """
    try:
        df = dataset_context.get_dataframe()
        params = json.loads(input_str)
        
        column = params["column"]
        operator = params["operator"]
        value = params["value"]
        
        # Apply filter
        if operator == "==":
            filtered_df = df[df[column] == value]
        elif operator == ">":
            filtered_df = df[df[column] > value]
        elif operator == "<":
            filtered_df = df[df[column] < value]
        elif operator == ">=":
            filtered_df = df[df[column] >= value]
        elif operator == "<=":
            filtered_df = df[df[column] <= value]
        else:
            return f"Unknown operator: {operator}"
        
        dataset_context.set_working_dataframe(filtered_df)
        return f"Filtered results ({len(filtered_df)} rows):\n{filtered_df.head(10).to_string()}"
    
    except Exception as e:
        return f"Error filtering data: {str(e)}"


# Create LangChain tools
analyze_data_tool = Tool(
    name="analyze_data",
    description="""Perform data analysis operations like grouping, aggregation, and sorting.
    Input must be a JSON string with operation parameters.
    
    Examples:
    - Group by: {"operation": "group_by", "column": "region", "agg_func": "sum", "value_column": "revenue"}
    - Aggregate: {"operation": "aggregate", "column": "sales", "agg_func": "mean"}
    - Sort: {"operation": "sort", "column": "revenue", "ascending": false, "n": 10}""",
    func=analyze_data_func
)

get_statistics_tool = Tool(
    name="get_statistics",
    description="""Get statistical summary (mean, std, min, max, etc.) for columns.
    Input must be a JSON string.
    
    Examples:
    - All columns: {"columns": "all"}
    - Specific columns: {"columns": ["revenue", "sales"]}""",
    func=get_statistics_func
)

filter_data_tool = Tool(
    name="filter_data",
    description="""Filter the dataset based on conditions.
    Input must be a JSON string with filter parameters.
    
    Examples:
    - Equal: {"column": "region", "operator": "==", "value": "North"}
    - Greater than: {"column": "revenue", "operator": ">", "value": 1000000}""",
    func=filter_data_func
)
