"""Synthesizer and follow-up generator nodes."""

import json
from typing import Any, cast

from loguru import logger
from pydantic import SecretStr
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.state import AgentState
from app.agents.planner import _extract_usage, _merge_usage
from app.schemas.agent import AnalysisResult, FollowUpQuestions
from app.config import settings


# ── Synthesizer ──────────────────────────────────────────────────────────────

_SYNTHESIZER_SYSTEM = """You are a senior data analyst writing the final response to a user's question.

You have access to the full tool execution transcript. Synthesize the findings into:
- A clear, complete natural language answer
- Bullet-point key findings (specific numbers and facts, not vague statements)
- Any data quality notes (nulls, unexpected values, ambiguous categories)
- A confidence level: high (clean data, clear answer), medium (some gaps), low (data issues or ambiguous)

Be concise and precise. Reference specific values from the analysis."""


async def synthesizer_node(state: AgentState) -> dict[str, Any]:
    """
    Synthesizer node: produces structured AnalysisResult from the tool execution transcript.
    """
    llm = ChatOpenAI(
        model=settings.SYNTHESIZER_MODEL,
        temperature=0.0,
        api_key=SecretStr(settings.OPENAI_API_KEY),
        stream_usage=True,
    )

    # Build context from messages
    tool_transcript = _extract_transcript(state)

    context_block = ""
    if state.get("conversation_history"):
        context_block = f"Conversation context:\n{state['conversation_history']}\n\n"

    prompt = (
        f'Original question: "{state["question"]}"\n\n'
        f"{context_block}"
        f"Analysis transcript:\n{tool_transcript}\n\n"
        f"Produce a structured final answer."
    )

    raw_result = await llm.with_structured_output(
        AnalysisResult, include_raw=True
    ).ainvoke(
        [SystemMessage(content=_SYNTHESIZER_SYSTEM), HumanMessage(content=prompt)]
    )
    result = cast(AnalysisResult, raw_result["parsed"])
    usage = _extract_usage(raw_result.get("raw"))
    logger.info("Generated analysis result: {}", result.answer)

    prior = state.get("token_usage") or {}
    return {
        "answer": result.answer,
        "key_findings": result.key_findings,
        "data_quality_notes": result.data_quality_notes,
        "confidence": result.confidence,
        "token_usage": _merge_usage(prior, usage),
        "agent_steps": state.get("agent_steps", [])
        + [{"node": "synthesizer", "confidence": result.confidence}],
    }


# ── Follow-up question generator ─────────────────────────────────────────────

_FOLLOWUP_SYSTEM = """You are a data analyst suggesting follow-up questions after completing an analysis.

Generate 3–5 follow-up questions that:
- Dig deeper into findings from the analysis
- Explore related dimensions of the data not yet examined
- Could reveal actionable insights or context
- Are specific and answerable with the same dataset

For each question include a brief rationale explaining why it's a useful next exploration."""


async def follow_up_node(state: AgentState) -> dict[str, Any]:
    """
    Follow-up generator node: produces 3–5 suggested follow-up questions.
    """
    llm = ChatOpenAI(
        model=settings.SYNTHESIZER_MODEL,
        temperature=0.3,  # slight creativity for question variety
        api_key=SecretStr(settings.OPENAI_API_KEY),
        stream_usage=True,
    )

    metadata = state["dataset_metadata"]
    columns = metadata.get("columns", [])

    prompt = (
        f'Original question: "{state["question"]}"\n\n'
        f"Answer summary: {(state.get('answer') or '')[:500]}\n\n"
        f"Key findings: {json.dumps(state.get('key_findings', []))}\n\n"
        f"Available columns: {', '.join(columns)}\n\n"
        f"Suggest 3–5 follow-up questions."
    )

    raw_result = await llm.with_structured_output(
        FollowUpQuestions, include_raw=True
    ).ainvoke([SystemMessage(content=_FOLLOWUP_SYSTEM), HumanMessage(content=prompt)])
    result = cast(FollowUpQuestions, raw_result["parsed"])
    usage = _extract_usage(raw_result.get("raw"))
    logger.info("Generated follow-up questions: {}", result.questions)

    follow_ups = [q.model_dump() for q in result.questions]
    prior = state.get("token_usage") or {}

    logger.info("Token usage after follow-up generation: {}", state.get("token_usage"))
    logger.info(
        "Merged token usage with follow-up step: {}", _merge_usage(prior, usage)
    )

    return {
        "follow_up_questions": follow_ups,
        "token_usage": _merge_usage(prior, usage),
        "agent_steps": state.get("agent_steps", [])
        + [{"node": "follow_up_gen", "questions_generated": len(follow_ups)}],
    }


# ── Helpers ──────────────────────────────────────────────────────────────────


def _extract_transcript(state: AgentState) -> str:
    """Build a readable transcript from messages for the synthesizer prompt."""
    from langchain_core.messages import AIMessage, ToolMessage

    lines = []
    for msg in state.get("messages", []):
        if isinstance(msg, AIMessage):
            if msg.content:
                lines.append(f"Agent: {msg.content}")
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    args_str = json.dumps(tc.get("args", {}))[:300]
                    lines.append(f"Tool call: {tc.get('name')}({args_str})")
        elif isinstance(msg, ToolMessage):
            content = str(msg.content)[:500]
            lines.append(f"Tool result: {content}")

    return "\n".join(lines) if lines else "No tool transcript available."
