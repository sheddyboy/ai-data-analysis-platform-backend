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
from langchain_core.tools import tool
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
from loguru import logger


_EXECUTOR_SYSTEM = """You are a data analyst executing a pre-approved analysis plan.
You are a tool-execution engine — your ONLY job is to call tools. Do NOT write prose answers.
The synthesizer will generate the final answer after you finish. You signal completion by calling finish_analysis.

{plan_block}

Rules:
- Always call load_dataset first, then execute ONLY the steps listed in the plan above — no extra exploration
- Do NOT print exploratory summaries, distributions, or counts unless the plan explicitly lists them
- The plan has {plan_step_count} steps (excluding load_dataset). Call finish_analysis after exactly those steps are done
- Use execute_python for all pandas/numpy operations — use print() to see output
- Do NOT use import statements inside execute_python — pd and np are pre-injected into the namespace
- Do NOT use matplotlib, seaborn, or any plotting library inside execute_python — use create_visualization instead
- Before filtering on categorical columns, print unique values first to verify exact strings
- Variables persist across execute_python calls — build incrementally, don't repeat setup
- Call set_working_df(result_df) inside execute_python BEFORE calling create_visualization
- create_visualization uses whatever was passed to set_working_df — it cannot see your variables
- Call finish_analysis ONLY after you have completed every step in the plan

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

    return _EXECUTOR_SYSTEM.format(
        plan_block=plan_block,
        plan_step_count=len(steps),
        hints_block=hints_block,
    )


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

    # ── Terminal tool — agent must call this to signal it is done ────────────
    @tool
    def finish_analysis(summary: str = "") -> str:  # noqa: ARG001
        """Call this when you have completed ALL steps in the analysis plan.
        Only call this after all execute_python and create_visualization steps are done.
        """
        return "Analysis complete. Handing off to synthesizer."

    # ── Build request-scoped tools ───────────────────────────────────────────
    tools = [
        build_load_dataset_tool(context),
        build_execute_python_tool(context),
        build_create_visualization_tool(context),
        finish_analysis,
    ]
    tool_node = ToolNode(tools)

    # tool_choice="required" forces the LLM to always call a tool — it cannot
    # return plain text and stop early. The agent signals completion via finish_analysis.
    executor_llm = ChatOpenAI(
        model=settings.EXECUTOR_MODEL,
        temperature=0.0,
        api_key=SecretStr(settings.OPENAI_API_KEY),
    ).bind_tools(tools, tool_choice="required")

    # ── Node: tool_executor ──────────────────────────────────────────────────
    async def tool_executor_node(state: AgentState) -> dict[str, Any]:
        """
        Drives the tool-calling loop. On first call seeds messages with the system
        prompt + question. On subsequent calls the ToolNode has already appended
        ToolMessages so we just call the LLM again.
        """
        messages = list(state.get("messages", []))
        turn = (
            sum(
                1
                for s in state.get("agent_steps", [])
                if s.get("node") == "tool_executor"
            )
            + 1
        )

        # First call: seed the conversation
        if not messages:
            system_content = _build_executor_system(state)
            logger.info("[executor turn {}] system prompt:\n{}", turn, system_content)
            messages = [
                SystemMessage(content=system_content),
                HumanMessage(content=state["question"]),
            ]

        logger.info(
            "[executor turn {}] calling LLM ({})", turn, settings.EXECUTOR_MODEL
        )
        response = cast(AIMessage, await executor_llm.ainvoke(messages))

        tool_calls = getattr(response, "tool_calls", None) or []
        tool_names = [tc.get("name") for tc in tool_calls]
        logger.info(
            "[executor turn {}] LLM chose tools: {}", turn, tool_names or "(none)"
        )

        # Collect tool output text for the synthesizer transcript
        tool_outputs = list(state.get("tool_outputs", []))

        # Sync visualizations from context (tools appended there directly)
        visualizations = context.get_visualizations()

        step_info: dict[str, Any] = {"node": "tool_executor"}
        if tool_names:
            step_info["tool_calls"] = tool_names

        return {
            "messages": [response],
            "tool_outputs": tool_outputs,
            "visualizations": visualizations,
            "agent_steps": state.get("agent_steps", []) + [step_info],
        }

    # ── Edge condition ───────────────────────────────────────────────────────
    def should_continue(state: AgentState) -> Literal["tools", "synthesizer"]:
        """Route to synthesizer when finish_analysis is called or max iterations hit."""
        messages = state.get("messages", [])
        if not messages:
            return "synthesizer"
        last = messages[-1]
        if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
            # finish_analysis signals the agent is done
            if any(tc.get("name") == "finish_analysis" for tc in last.tool_calls):
                logger.info(
                    "[executor] finish_analysis called — routing to synthesizer"
                )
                return "synthesizer"
            # Respect max iterations guard
            iterations = sum(
                1
                for s in state.get("agent_steps", [])
                if s.get("node") == "tool_executor"
            )
            if iterations < _get_max_iterations(state):
                return "tools"
        logger.info(
            "[executor] no tool calls / max iterations — routing to synthesizer"
        )
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
