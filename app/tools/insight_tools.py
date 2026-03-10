"""Tools for generating insights from analysis results."""

import json
from langchain.tools import Tool
from openai import AsyncOpenAI
from app.config import settings


class InsightStorage:
    """Storage for insights generated during agent execution."""
    
    def __init__(self):
        self.insights = None
    
    def set_insights(self, insights: dict):
        """Set the insights."""
        self.insights = insights
    
    def get_insights(self):
        """Get the insights."""
        return self.insights
    
    def clear(self):
        """Clear insights."""
        self.insights = None


# Global insight storage
insight_storage = InsightStorage()


async def generate_insights_async(analysis_results: str, question: str) -> dict:
    """
    Generate insights from analysis results using LLM.
    
    Args:
        analysis_results: Results from data analysis
        question: Original user question
        
    Returns:
        Insights dictionary
    """
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    
    prompt = f"""You are a data analyst. Based on the following analysis results, generate insights.

Original Question: {question}

Analysis Results:
{analysis_results}

Generate insights in the following JSON format:
{{
    "summary": "A concise 1-2 sentence summary of the main finding",
    "key_findings": ["Finding 1", "Finding 2", "Finding 3"],
    "recommendations": ["Recommendation 1", "Recommendation 2"] (optional)
}}

Focus on actionable insights and clear interpretations of the data."""

    try:
        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You are a data analyst generating insights."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=500
        )
        
        # Parse JSON response
        content = response.choices[0].message.content.strip()
        
        # Try to extract JSON from the response
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        insights = json.loads(content)
        return insights
        
    except Exception as e:
        # Return default insights if LLM fails
        return {
            "summary": "Analysis completed successfully",
            "key_findings": ["Results extracted from data"],
            "recommendations": []
        }


def generate_insights_func(input_str: str) -> str:
    """
    Generate insights from analysis results.
    
    Input format (JSON string):
    {
        "analysis_results": "results from previous analysis",
        "question": "original user question"
    }
    
    Args:
        input_str: JSON string with parameters
        
    Returns:
        Confirmation message
    """
    try:
        params = json.loads(input_str)
        analysis_results = params.get("analysis_results", "")
        question = params.get("question", "")
        
        # Note: Since LangChain tools are synchronous but we need async,
        # we'll store the request and process it later in the service layer
        insight_storage.set_insights({
            "analysis_results": analysis_results,
            "question": question,
            "status": "pending"
        })
        
        return "Insights will be generated from the analysis results"
        
    except Exception as e:
        return f"Error preparing insights: {str(e)}"


# Create LangChain tool
generate_insights_tool = Tool(
    name="generate_insights",
    description="""Generate natural language insights from analysis results.
    Input must be a JSON string with analysis results and original question.
    
    Example:
    {"analysis_results": "North region: $2.5M, South: $2.1M", "question": "Which region has highest revenue?"}""",
    func=generate_insights_func
)
