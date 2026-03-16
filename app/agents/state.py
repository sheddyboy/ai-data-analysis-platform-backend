"""LangGraph agent state definition for the v2 analysis graph."""

from typing import Annotated, Any, Optional
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """
    Shared state passed through every node of the analysis graph.

    Fields are populated progressively as the graph executes:
      - question, dataset_metadata, error_hints   → set at entry
      - analysis_plan                             → set by planner node
      - messages                                  → accumulated by tool_executor + ToolNode
      - tool_outputs                              → accumulated by tool_executor
      - visualizations                            → accumulated by tools
      - answer, key_findings, data_quality_notes, confidence → set by synthesizer
      - follow_up_questions                       → set by follow_up_gen node
      - agent_steps                               → accumulated throughout
    """

    # ── Immutable inputs (set once at graph entry) ───────────────────────────
    question: str
    dataset_metadata: dict[str, Any]
    error_hints: list[str]
    conversation_history: Optional[str]  # summarized multi-turn history from session

    # ── Planner output ───────────────────────────────────────────────────────
    analysis_plan: Optional[dict[str, Any]]  # serialized AnalysisPlan

    # ── Tool-calling executor loop ───────────────────────────────────────────
    # add_messages reducer appends incoming messages rather than overwriting
    messages: Annotated[list[BaseMessage], add_messages]
    tool_outputs: list[str]       # raw text outputs from each tool invocation
    current_step_index: int       # which plan step to execute next (0-based)

    # ── Accumulated tool results ─────────────────────────────────────────────
    visualizations: list[dict[str, Any]]

    # ── Synthesizer output ───────────────────────────────────────────────────
    answer: Optional[str]
    key_findings: list[str]
    data_quality_notes: list[str]
    confidence: Optional[str]

    # ── Follow-up questions ──────────────────────────────────────────────────
    follow_up_questions: Optional[list[dict[str, str]]]  # [{question, rationale}]

    # ── Debug / persistence ──────────────────────────────────────────────────
    agent_steps: list[dict[str, Any]]
