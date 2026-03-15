"""Pydantic models for structured LLM output across the v2 agent graph."""

from typing import Literal, Optional
from pydantic import BaseModel, Field


class AnalysisStep(BaseModel):
    """A single step in the analysis plan."""

    step_number: int = Field(description="Sequential step number starting at 1")
    description: str = Field(description="What this step does and why")
    tool_to_use: Literal["load_dataset", "execute_python", "create_visualization"] = Field(
        description="Which tool to call in this step"
    )
    expected_output: str = Field(description="What this step should produce")


class AnalysisPlan(BaseModel):
    """Structured analysis plan produced by the planner node before any tools are called."""

    reasoning: str = Field(
        description="Chain-of-thought reasoning about the question and dataset"
    )
    steps: list[AnalysisStep] = Field(description="Ordered list of analysis steps")
    needs_visualization: bool = Field(
        description="True if the answer would benefit from a chart"
    )
    needs_insights: bool = Field(
        description="True if narrative key findings should be synthesized"
    )
    estimated_complexity: Literal["simple", "moderate", "complex"] = Field(
        description="Complexity estimate: simple=1-2 tools, moderate=3-5, complex=6+"
    )


class AnalysisResult(BaseModel):
    """Structured final answer produced by the synthesizer node."""

    answer: str = Field(description="Complete natural language answer to the question")
    key_findings: list[str] = Field(
        description="Bullet-point key findings extracted from the analysis"
    )
    data_quality_notes: list[str] = Field(
        default_factory=list,
        description="Any data quality issues noticed (nulls, outliers, unexpected values)",
    )
    confidence: Literal["high", "medium", "low"] = Field(
        description="Confidence level in the answer based on data quality and completeness"
    )


class FollowUpQuestion(BaseModel):
    """A single suggested follow-up question."""

    question: str = Field(description="The follow-up question text")
    rationale: str = Field(
        description="Why this question is a useful next step given what was found"
    )


class FollowUpQuestions(BaseModel):
    """Set of follow-up questions generated after analysis completes."""

    questions: list[FollowUpQuestion] = Field(
        min_length=3,
        max_length=5,
        description="3–5 follow-up questions ranked by relevance",
    )


class RelevanceResult(BaseModel):
    """Structured output from the relevance guard."""

    is_relevant: bool = Field(
        description="True if the question can be answered with the dataset"
    )
    reason: str = Field(
        description="Brief explanation of the relevance determination"
    )
