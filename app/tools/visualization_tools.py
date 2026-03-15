"""Tool factory for creating data visualizations."""

import json
from typing import Literal, Optional

import plotly.express as px
from langchain_core.tools import tool
from app.agents.context import AnalysisContext


def build_create_visualization_tool(context: AnalysisContext):
    """Return a create_visualization tool bound to the given request-scoped context."""

    @tool
    def create_visualization(
        chart_type: Literal["bar", "line", "scatter", "pie", "histogram"],
        x: str,
        y: Optional[str] = None,
        title: str = "Chart",
        color: Optional[str] = None,
    ) -> str:
        """Create a data visualization from the working DataFrame.

        IMPORTANT: You must call set_working_df(result_df) inside execute_python
        before calling this tool. The tool uses whatever DataFrame was passed to
        set_working_df — it cannot access variables in the execution namespace.

        Supported chart types: bar, line, scatter, pie, histogram.
        """
        try:
            df = context.get_working_dataframe()

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
                return f"Unknown chart type: {chart_type}. Use one of: bar, line, scatter, pie, histogram."

            fig_json = json.loads(fig.to_json() or "{}")
            viz_data = {
                "type": chart_type,
                "title": title,
                "data": fig_json["data"],
                "layout": fig_json["layout"],
            }
            context.add_visualization(viz_data)
            return f"Created {chart_type} chart: '{title}'"

        except Exception as e:
            return f"Error creating visualization: {str(e)}"

    return create_visualization
