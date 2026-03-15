"""LangGraph StateGraph for the v2 data analysis agent.

Graph topology:
  [START] → planner → tool_executor ⇄ tools → synthesizer → follow_up_gen → [END]

One CompiledStateGraph is built per request via build_graph(context), ensuring
tools are bound to a request-scoped AnalysisContext with no shared mutable globals.
"""

from typing import Any, Literal, cast

from pydantic import SecretStr
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode

from app.agents.context import AnalysisContext
from app.agents.state import AgentState
from app.agents.planner import planner_node
from app.agents.synthesizer import synthesizer_node, follow_up_node
from app.tools import (
    build_load_dataset_tool,
    build_execute_python_tool,
    build_create_visualization_tool,
)
from app.config import settings


_EXECUTOR_SYSTEM = """You are a data analyst executing a pre-approved analysis plan.
Follow the steps in order. Adapt only if you encounter a data issue requiring it.

{plan_block}

Rules:
- Always call load_dataset first
- Use execute_python for all pandas/numpy operations — use print() to see output
- Before filtering on categorical columns, print unique values first to verify exact strings
- Variables persist across execute_python calls — build incrementally, don't repeat setup
- Call set_working_df(result_df) inside execute_python BEFORE calling create_visualization
- create_visualization uses whatever was passed to set_working_df — it cannot see your variables

Error hints:
{hints_block}"""


def _build_executor_system(state: AgentState) -> str:
    plan = state.get("analysis_plan") or {}
    steps = plan.get("steps", [])
    if steps:
        step_lines = "\n".join(
            f"  Step {s['step_number']}: [{s['tool_to_use']}] {s['description']}"
            for s in steps
        )
        plan_block = f"Analysis plan:\n{step_lines}"
    else:
        plan_block = "No pre-computed plan available — use your best judgment."

    hints = state.get("error_hints", [])
    hints_block = "\n".join(f"- {h}" for h in hints) if hints else "None."

    return _EXECUTOR_SYSTEM.format(plan_block=plan_block, hints_block=hints_block)


def _get_max_iterations(state: AgentState) -> int:
    complexity = (state.get("analysis_plan") or {}).get(
        "estimated_complexity", "moderate"
    )
    return {
        "simple": settings.AGENT_MAX_ITERATIONS_SIMPLE,
        "moderate": settings.AGENT_MAX_ITERATIONS_MODERATE,
        "complex": settings.AGENT_MAX_ITERATIONS_COMPLEX,
    }.get(complexity, settings.AGENT_MAX_ITERATIONS_MODERATE)


def build_graph(context: AnalysisContext):
    """
    Build and compile a fresh StateGraph bound to a request-scoped AnalysisContext.

    This must be called once per request so tools close over isolated state.
    """
    # ── Build request-scoped tools ───────────────────────────────────────────
    tools = [
        build_load_dataset_tool(context),
        build_execute_python_tool(context),
        build_create_visualization_tool(context),
    ]
    tool_node = ToolNode(tools)

    executor_llm = ChatOpenAI(
        model=settings.EXECUTOR_MODEL,
        temperature=0.0,
        api_key=SecretStr(settings.OPENAI_API_KEY),
    ).bind_tools(tools)

    # ── Node: tool_executor ──────────────────────────────────────────────────
    async def tool_executor_node(state: AgentState) -> dict[str, Any]:
        """
        Drives the tool-calling loop. On first call seeds messages with the system
        prompt + question. On subsequent calls the ToolNode has already appended
        ToolMessages so we just call the LLM again.
        """
        messages = list(state.get("messages", []))

        # First call: seed the conversation
        if not messages:
            system_content = _build_executor_system(state)
            messages = [
                SystemMessage(content=system_content),
                HumanMessage(content=state["question"]),
            ]

        response = cast(AIMessage, await executor_llm.ainvoke(messages))

        # Collect tool output text for the synthesizer transcript
        tool_outputs = list(state.get("tool_outputs", []))
        visualizations = list(state.get("visualizations", []))

        # Sync visualizations from context (tools appended there directly)
        visualizations = context.get_visualizations()

        step_info: dict[str, Any] = {"node": "tool_executor"}
        if hasattr(response, "tool_calls") and response.tool_calls:
            step_info["tool_calls"] = [tc.get("name") for tc in response.tool_calls]

        return {
            "messages": [response],
            "tool_outputs": tool_outputs,
            "visualizations": visualizations,
            "agent_steps": state.get("agent_steps", []) + [step_info],
        }

    # ── Edge condition ───────────────────────────────────────────────────────
    def should_continue(state: AgentState) -> Literal["tools", "synthesizer"]:
        """Route to tools if the LLM requested tool calls, else to synthesizer."""
        messages = state.get("messages", [])
        if not messages:
            return "synthesizer"
        last = messages[-1]
        if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
            # Respect max iterations guard
            iterations = sum(
                1
                for s in state.get("agent_steps", [])
                if s.get("node") == "tool_executor"
            )
            if iterations < _get_max_iterations(state):
                return "tools"
        return "synthesizer"

    # ── Wire graph ───────────────────────────────────────────────────────────
    builder = StateGraph(AgentState)

    builder.add_node("planner", planner_node)
    builder.add_node("tool_executor", tool_executor_node)
    builder.add_node("tools", tool_node)
    builder.add_node("synthesizer", synthesizer_node)
    builder.add_node("follow_up_gen", follow_up_node)

    builder.add_edge(START, "planner")
    builder.add_edge("planner", "tool_executor")
    builder.add_conditional_edges(
        "tool_executor",
        should_continue,
        {"tools": "tools", "synthesizer": "synthesizer"},
    )
    builder.add_edge("tools", "tool_executor")
    builder.add_edge("synthesizer", "follow_up_gen")
    builder.add_edge("follow_up_gen", END)

    return builder.compile()
