"""LangGraph StateGraph for the v2 data analysis agent.

Graph topology:
  [START] → planner → tool_executor ⇄ tools → synthesizer → follow_up_gen → [END]

One CompiledStateGraph is built per request via build_graph(context), ensuring
tools are bound to a request-scoped AnalysisContext with no shared mutable globals.
"""

from typing import Any, Literal, cast

from pydantic import SecretStr
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
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


_EXECUTOR_SYSTEM = """You are a data analyst executing a pre-approved analysis plan step by step.
You are a tool-execution engine — your ONLY job is to call the tool you are instructed to call.
Do NOT write prose answers, explore data, or call tools other than the one specified for each step.
The synthesizer will generate the final answer after you call finish_analysis.

Rules:
- Call EXACTLY the tool named in each step instruction — no substitutions, no extra calls
- Use execute_python for all pandas/numpy operations — use print() to see output
- Do NOT use import statements inside execute_python — pd and np are pre-injected into the namespace
- Do NOT use matplotlib, seaborn, or any plotting library inside execute_python — use create_visualization instead
- Before filtering on categorical columns, print unique values first to verify exact strings
- Variables persist across execute_python calls — build incrementally, do not repeat setup
- Call set_working_df(result_df) inside execute_python BEFORE calling create_visualization
- create_visualization uses whatever was passed to set_working_df — it cannot see your local variables

Error hints:
{hints_block}"""


def _build_executor_system(state: AgentState) -> str:
    hints = state.get("error_hints", [])
    hints_block = "\n".join(f"- {h}" for h in hints) if hints else "None."
    return _EXECUTOR_SYSTEM.format(hints_block=hints_block)


def _tool_message_has_error(content) -> bool:
    """Heuristic: does a ToolMessage content indicate a failure?"""
    if isinstance(content, str):
        lowered = content.lower()
        return any(tok in lowered for tok in ("error", "exception", "traceback"))
    if isinstance(content, list):
        joined = " ".join(str(block) for block in content).lower()
        return any(tok in joined for tok in ("error", "exception", "traceback"))
    return False


def _last_of_type(messages: list, msg_type):
    """Return the most recent message of the given type, or None."""
    for m in reversed(messages):
        if isinstance(m, msg_type):
            return m
    return None


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

    # base_llm is unbound — tool_choice is set per-step inside tool_executor_node
    # to force the exact tool the plan requires.
    base_llm = ChatOpenAI(
        model=settings.EXECUTOR_MODEL,
        temperature=0.0,
        api_key=SecretStr(settings.OPENAI_API_KEY),
    )
    available_tool_names = {t.name for t in tools}

    # ── Node: tool_executor ──────────────────────────────────────────────────
    async def tool_executor_node(state: AgentState) -> dict[str, Any]:
        """
        Drives the tool-calling loop. Each turn injects a step-specific HumanMessage
        and forces the correct tool via tool_choice, so the LLM cannot deviate from
        the plan. Step index advances only on successful tool execution.
        """
        messages = list(state.get("messages", []))
        step_idx = state.get("current_step_index", 0)

        plan = state.get("analysis_plan") or {}
        raw_steps = plan.get("steps", [])
        # load_dataset is a pre-step handled separately — exclude it from plan steps
        steps = [s for s in raw_steps if s.get("tool_to_use") != "load_dataset"]
        total_steps = len(steps)

        turn = (
            sum(
                1
                for s in state.get("agent_steps", [])
                if s.get("node") == "tool_executor"
            )
            + 1
        )

        # ── Advance step_idx based on last tool result ───────────────────────
        # On every turn after the first, inspect what the previous AIMessage called
        # and whether the ToolMessage it produced indicates success or failure.
        # Only advance if the step succeeded — errors keep the same index so the
        # LLM retries the same step with the same forced tool_choice.
        if messages:
            last_ai = _last_of_type(messages, AIMessage)
            last_tool_msg = _last_of_type(messages, ToolMessage)

            if last_ai is not None:
                last_tool_calls = getattr(last_ai, "tool_calls", None) or []
                last_called = (
                    last_tool_calls[0].get("name") if last_tool_calls else None
                )

                # load_dataset is a pre-step (not counted in plan steps); finish_analysis
                # is a terminal signal — neither should advance the plan index.
                if last_called and last_called not in (
                    "load_dataset",
                    "finish_analysis",
                ):
                    has_error = (
                        _tool_message_has_error(last_tool_msg.content)
                        if last_tool_msg is not None
                        else False
                    )
                    if not has_error:
                        step_idx += 1
                        logger.info(
                            "[executor turn {}] step succeeded — advancing to step_idx={}",
                            turn,
                            step_idx,
                        )
                    else:
                        # Keep step_idx unchanged so the same step is retried next turn
                        logger.warning(
                            "[executor turn {}] step '{}' errored — retrying (step_idx={})",
                            turn,
                            last_called,
                            step_idx,
                        )

        # ── Determine which tool to force this turn ──────────────────────────
        # Priority order:
        #   1. load_dataset hasn't been called yet → always force it first
        #   2. All plan steps done → force finish_analysis to hand off to synthesizer
        #   3. Otherwise → force the tool specified by the current plan step
        #
        # tool_choice is an OpenAI API-level constraint, not a prompt instruction,
        # so the LLM physically cannot call a different tool.
        load_dataset_done = any(
            isinstance(m, AIMessage)
            and any(
                tc.get("name") == "load_dataset"
                for tc in (getattr(m, "tool_calls", None) or [])
            )
            for m in messages
        )

        if not messages or not load_dataset_done:
            # First turn ever, or load_dataset somehow wasn't called — force it now
            forced_tool = "load_dataset"
            tool_choice: Any = {
                "type": "function",
                "function": {"name": "load_dataset"},
            }
            step_label = (
                f"[STEP 0/{total_steps}] Load the dataset first. Call load_dataset now."
            )
        elif step_idx >= total_steps:
            # Every plan step has been executed successfully — signal completion
            forced_tool = "finish_analysis"
            tool_choice = {"type": "function", "function": {"name": "finish_analysis"}}
            step_label = "All analysis steps are complete. Call finish_analysis now."
        else:
            # Normal case: execute the next plan step
            current_step = steps[step_idx]
            tool_name = current_step.get("tool_to_use", "")
            if tool_name in available_tool_names:
                forced_tool = tool_name
                tool_choice = {"type": "function", "function": {"name": tool_name}}
            else:
                # Planner named a tool that isn't registered (e.g. generate_insights) —
                # fall back to "required" so execution doesn't hard-fail; the injected
                # step_label still gives the LLM a strong hint about what to call.
                logger.warning(
                    "[executor turn {}] step tool '{}' not in available tools — falling back to required",
                    turn,
                    tool_name,
                )
                forced_tool = None
                tool_choice = "required"
            # The injected message tells the LLM exactly what step it's on, what tool
            # to call, and what output is expected — leaving only the implementation
            # details (e.g. the pandas code) up to the LLM.
            step_label = (
                f"[STEP {step_idx + 1}/{total_steps}] Execute: [{tool_name}] "
                f"{current_step.get('description', '')}. "
                f"Expected output: {current_step.get('expected_output', '')}. "
                f"Call {tool_name} now."
            )

        # This message is appended to the conversation each turn so the LLM always
        # knows exactly what it should do next, regardless of prior context.
        injected_msg = HumanMessage(content=step_label)

        # ── Seed or extend messages ──────────────────────────────────────────
        # First turn: bootstrap with system prompt + original question + first step.
        # Subsequent turns: the ToolNode has already appended ToolMessages from the
        # last tool call, so we just append the next step instruction on top.
        if not messages:
            system_content = _build_executor_system(state)
            full_messages = [
                SystemMessage(content=system_content),
                HumanMessage(content=state["question"]),
                injected_msg,
            ]
            logger.info(
                "[executor turn {}] initial messages:\n{}",
                turn,
                "\n".join(f"{type(m).__name__}: {m.content}" for m in full_messages),
            )
        else:
            full_messages = messages + [injected_msg]
            logger.info(
                "[executor turn {}] appended step instruction:\n{}",
                turn,
                injected_msg.content,
            )

        # ── Bind tool_choice for this step and invoke ────────────────────────
        # Re-bind on every turn so the forced tool matches the current step.
        bound_llm = base_llm.bind_tools(tools, tool_choice=tool_choice)
        logger.info(
            "[executor turn {}] calling LLM ({}) forcing tool: {}",
            turn,
            settings.EXECUTOR_MODEL,
            forced_tool or "(required)",
        )
        response = cast(AIMessage, await bound_llm.ainvoke(full_messages))
        logger.info(
            "[executor turn {}] LLM response\ncontent: {}\ntool_calls: {}",
            turn,
            response.content,
            getattr(response, "tool_calls", None),
        )
        tool_calls = getattr(response, "tool_calls", None) or []
        tool_names = [tc.get("name") for tc in tool_calls]
        logger.info(
            "[executor turn {}] LLM chose tools: {}", turn, tool_names or "(none)"
        )

        tool_outputs = list(state.get("tool_outputs", []))
        # Sync visualizations produced by tools (tools write directly to context)
        visualizations = context.get_visualizations()

        step_info: dict[str, Any] = {"node": "tool_executor", "step_idx": step_idx}
        if tool_names:
            step_info["tool_calls"] = tool_names

        return {
            "messages": [injected_msg, response],
            "tool_outputs": tool_outputs,
            "visualizations": visualizations,
            "current_step_index": step_idx,
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
