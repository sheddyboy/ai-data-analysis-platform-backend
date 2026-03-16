"""Planner node — produces a structured AnalysisPlan before any tools are called."""

import json
from typing import Any, cast

from pydantic import SecretStr
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.state import AgentState
from app.schemas.agent import AnalysisPlan
from app.config import settings
from loguru import logger


_PLANNER_SYSTEM = """You are a senior data analyst. Your sole job is to create a step-by-step
analysis plan BEFORE any code is written. You do NOT have access to tools — only reason about approach.

Given the dataset schema, user question, and any error hints, produce a structured plan that:
- Identifies which columns are relevant
- Lists exact steps in execution order (load_dataset always first)
- Decides whether a visualization or narrative insights are warranted
- Estimates complexity: simple (1-2 steps), moderate (3-5), complex (6+)

Do NOT write actual code. Think carefully about what pandas operations are needed and flag
any data quality considerations (potential nulls, categorical value ambiguity, date parsing)."""


def _build_planner_prompt(state: AgentState) -> str:
    metadata = state["dataset_metadata"]
    columns = metadata.get("columns", [])
    column_types = metadata.get("column_types", {})
    row_count = metadata.get("row_count", "unknown")

    col_lines = "\n".join(
        f"  - {col} ({column_types.get(col, 'unknown')})" for col in columns
    )

    hints_block = ""
    if state.get("error_hints"):
        hints_block = "\nKnown pitfalls to avoid:\n" + "\n".join(
            f"- {h}" for h in state["error_hints"]
        )

    parent_block = ""
    if state.get("conversation_history"):
        parent_block = f"\n{state['conversation_history']}"

    return (
        f"Dataset: {row_count} rows\n"
        f"Columns:\n{col_lines}\n"
        f"{hints_block}"
        f"{parent_block}\n\n"
        f'Question: "{state["question"]}"'
    )


async def planner_node(state: AgentState) -> dict[str, Any]:
    """
    Planner node: calls the LLM with structured output to produce an AnalysisPlan.
    Adds the plan to state and records the planning step in agent_steps.
    """
    llm = ChatOpenAI(
        model=settings.PLANNER_MODEL,
        temperature=0.0,
        api_key=SecretStr(settings.OPENAI_API_KEY),
    )
    structured_llm = llm.with_structured_output(AnalysisPlan)

    prompt = _build_planner_prompt(state)
    logger.info("Sending request to planner:\n{}", prompt)
    messages = [
        SystemMessage(content=_PLANNER_SYSTEM),
        HumanMessage(content=prompt),
    ]

    plan = cast(AnalysisPlan, await structured_llm.ainvoke(messages))
    logger.info("Generated analysis plan: {}", plan.steps)

    return {
        "analysis_plan": plan.model_dump(),
        "agent_steps": state.get("agent_steps", [])
        + [
            {
                "node": "planner",
                "plan_steps": len(plan.steps),
                "complexity": plan.estimated_complexity,
                "needs_visualization": plan.needs_visualization,
            }
        ],
    }
