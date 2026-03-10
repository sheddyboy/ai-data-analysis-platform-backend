"""Tools for creating data visualizations."""

import plotly.express as px
import plotly.graph_objects as go
import json
from langchain.tools import Tool
from typing import Dict, Any
from app.tools.dataset_tools import dataset_context


class VisualizationStorage:
    """Storage for visualizations created during agent execution."""
    
    def __init__(self):
        self.visualizations = []
    
    def add_visualization(self, viz: Dict[str, Any]):
        """Add a visualization to storage."""
        self.visualizations.append(viz)
    
    def get_visualizations(self):
        """Get all visualizations."""
        return self.visualizations
    
    def clear(self):
        """Clear all visualizations."""
        self.visualizations = []


# Global visualization storage
viz_storage = VisualizationStorage()


def create_visualization_func(input_str: str) -> str:
    """
    Create a visualization from the dataset.
    
    Input format (JSON string):
    {
        "chart_type": "bar" | "line" | "scatter" | "pie" | "histogram",
        "x": "x_column",
        "y": "y_column",
        "title": "Chart Title" (optional),
        "color": "color_column" (optional)
    }
    
    Args:
        input_str: JSON string with visualization parameters
        
    Returns:
        Confirmation message
    """
    try:
        df = dataset_context.get_working_dataframe()
        params = json.loads(input_str)
        
        chart_type = params["chart_type"]
        x = params.get("x")
        y = params.get("y")
        title = params.get("title", f"{chart_type.capitalize()} Chart")
        color = params.get("color")
        
        # Create visualization based on type
        if chart_type == "bar":
            fig = px.bar(df, x=x, y=y, title=title, color=color)
        
        elif chart_type == "line":
            fig = px.line(df, x=x, y=y, title=title, color=color)
        
        elif chart_type == "scatter":
            fig = px.scatter(df, x=x, y=y, title=title, color=color)
        
        elif chart_type == "pie":
            fig = px.pie(df, names=x, values=y, title=title)
        
        elif chart_type == "histogram":
            fig = px.histogram(df, x=x, title=title, color=color)
        
        else:
            return f"Unknown chart type: {chart_type}"
        
        # Convert to JSON-serializable format
        fig_json = json.loads(fig.to_json() or "{}")
        viz_data = {
            "type": chart_type,
            "title": title,
            "data": fig_json["data"],
            "layout": fig_json["layout"]
        }
        
        # Store visualization
        viz_storage.add_visualization(viz_data)
        
        return f"Created {chart_type} chart: '{title}'"
    
    except Exception as e:
        return f"Error creating visualization: {str(e)}"


# Create LangChain tool
create_visualization_tool = Tool(
    name="create_visualization",
    description="""Create data visualizations (charts) from the dataset.
    Input must be a JSON string with visualization parameters.
    
    Supported chart types: bar, line, scatter, pie, histogram
    
    Examples:
    - Bar chart: {"chart_type": "bar", "x": "region", "y": "revenue", "title": "Revenue by Region"}
    - Line chart: {"chart_type": "line", "x": "date", "y": "sales", "title": "Sales Over Time"}
    - Pie chart: {"chart_type": "pie", "x": "category", "y": "count", "title": "Distribution"}
    - Scatter: {"chart_type": "scatter", "x": "age", "y": "income", "color": "gender"}""",
    func=create_visualization_func
)
