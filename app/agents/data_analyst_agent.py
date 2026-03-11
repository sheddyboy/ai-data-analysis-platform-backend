"""Data analyst agent using LangChain with ReAct pattern."""

import pandas as pd
from typing import Dict, Any, List
from langchain.agents import AgentExecutor, create_react_agent
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate

from app.config import settings
from app.tools import (
    load_dataset_tool,
    execute_python_tool,
    create_visualization_tool,
    generate_insights_tool,
)
from app.tools.dataset_tools import dataset_context
from app.tools.visualization_tools import viz_storage
from app.tools.insight_tools import insight_storage, generate_insights_async
from app.services.error_memory import ErrorMemoryService
from app.utils.error_handlers import AgentExecutionError


# ReAct prompt template
REACT_PROMPT = """You are a data analyst AI agent. Your job is to answer questions about datasets using the tools available to you.

You have access to the following tools:

{tools}

You MUST use EXACTLY this format for every action — never skip a line:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action (always required — use {{}} if no input needed)
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

CRITICAL RULES:
- After every "Action:" line you MUST immediately write "Action Input:" on the next line. Never skip it.
- For execute_python: Action Input is the raw Python code to run (not JSON). Example:
    Action: execute_python
    Action Input: print(df[df['country'] == 'United Kingdom'].groupby('artist_name').size().nlargest(10))
- For create_visualization and generate_insights: Action Input MUST be a raw JSON object using double quotes only. Never use Python single-quote dict syntax. Example:
    Action: create_visualization
    Action Input: {{"chart_type": "bar", "x": "artist_name", "y": "stream_count", "title": "Top Artists"}}
- Never write "Action:" without immediately following it with "Action Input:"

VARIABLE PERSISTENCE:
- Variables you define in execute_python persist across ALL subsequent execute_python calls in this session.
- Example: define `top_artists` in call 1, use it directly in call 2 without redefining it.
- You do NOT need to repeat setup code — build incrementally on previous results.

CATEGORICAL FILTER SAFETY:
- Before filtering on any text/categorical column (country, genre, label, etc.), ALWAYS verify the exact values first:
    print(df['country'].unique())
- Never assume the format (e.g., 'United Kingdom' not 'UK', 'United States' not 'US').

WORKFLOW:
1. Always start with load_dataset to understand the schema and column names
2. Check unique values of categorical columns before filtering
3. Use execute_python to analyze data — write precise pandas expressions and use print() to output results
4. ALWAYS call set_working_df(result_df) inside execute_python BEFORE using create_visualization. The visualization tool ONLY sees whatever was passed to set_working_df — it cannot access variables like top_artists, uk_df, etc. You must build a single flat DataFrame and call set_working_df() on it. For grouped comparisons, use long format:
   combined = pd.concat([series_a.reset_index().assign(group='A'), series_b.reset_index().assign(group='B')])
   set_working_df(combined)
5. Call create_visualization whenever the result contains numerical, categorical, or time-series data that can be meaningfully plotted — you do NOT need to be explicitly asked. Skip only when the answer is purely text (e.g. a single value, a yes/no, or a list lookup with no quantitative dimension).
6. ALWAYS call generate_insights after any data analysis. Pass a concise summary of what you found as analysis_results. Skip only for trivial lookups with no analytical finding.
7. Be concise but thorough in your final answer

{error_hints}

Begin!

Question: {input}
Thought: {agent_scratchpad}"""


class DataAnalystAgent:
    """
    AI agent that analyzes datasets and answers questions using LangChain.
    """

    def __init__(self):
        """Initialize the data analyst agent."""
        # Initialize LLM
        self.llm = ChatOpenAI(
            model=settings.OPENAI_MODEL,
            temperature=settings.LLM_TEMPERATURE,
            api_key=settings.OPENAI_API_KEY,
        )

        # Define tools
        self.tools = [
            load_dataset_tool,
            execute_python_tool,
            create_visualization_tool,
            generate_insights_tool,
        ]

        # Create prompt
        self.prompt = PromptTemplate.from_template(REACT_PROMPT)

        # Create agent
        self.agent = create_react_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=self.prompt,
        )

        # Create agent executor
        self.agent_executor = AgentExecutor(
            agent=self.agent,  # type: ignore[arg-type]
            tools=self.tools,
            verbose=settings.AGENT_VERBOSE,
            max_iterations=settings.AGENT_MAX_ITERATIONS,
            handle_parsing_errors=True,
        )

        # Error memory for injecting lessons into future prompts
        self.error_memory = ErrorMemoryService(data_dir=settings.DATA_DIR)

    async def analyze(
        self, question: str, df: pd.DataFrame, metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Analyze a dataset and answer a question.

        Args:
            question: User's question
            df: Pandas DataFrame with dataset
            metadata: Dataset metadata

        Returns:
            Dictionary with answer, visualizations, and insights

        Raises:
            AgentExecutionError: If agent execution fails
        """
        try:
            # Load dataset into context (also resets exec namespace)
            dataset_context.load_dataset(df, metadata)

            # Clear previous visualizations and insights
            viz_storage.clear()
            insight_storage.clear()

            # Build error hints block for prompt injection
            raw_hints = self.error_memory.get_hints(question)
            if raw_hints:
                hints_block = (
                    "LESSONS FROM PREVIOUS RUNS (apply these to avoid known mistakes):\n"
                    + "\n".join(f"- {h}" for h in raw_hints)
                )
            else:
                hints_block = ""

            # Run agent
            result = await self.agent_executor.ainvoke(
                {"input": question, "error_hints": hints_block}
            )

            # Extract answer
            answer = result.get("output", "Unable to generate answer")

            # Get visualizations
            visualizations = viz_storage.get_visualizations()

            # Generate insights if requested by agent
            insights = None
            pending_insights = insight_storage.get_insights()
            if pending_insights and pending_insights.get("status") == "pending":
                insights = await generate_insights_async(
                    pending_insights.get("analysis_results", answer), question
                )

            agent_steps = self._extract_agent_steps(result)

            # Auto-record any error patterns observed in this run
            self.error_memory.scan_steps_and_record(agent_steps)

            return {
                "answer": answer,
                "visualizations": visualizations,
                "insights": insights,
                "agent_steps": agent_steps,
            }

        except Exception as e:
            raise AgentExecutionError(f"Agent execution failed: {str(e)}")

    def _extract_agent_steps(self, result: Dict[str, Any]) -> List[Dict[str, str]]:
        """
        Extract agent reasoning steps from result.

        Args:
            result: Agent execution result

        Returns:
            List of step dictionaries
        """
        steps = []

        # Extract intermediate steps if available
        intermediate_steps = result.get("intermediate_steps", [])

        for step in intermediate_steps:
            if len(step) >= 2:
                action = step[0]
                observation = step[1]

                steps.append(
                    {
                        "action": action.tool
                        if hasattr(action, "tool")
                        else str(action),
                        "input": action.tool_input
                        if hasattr(action, "tool_input")
                        else "",
                        "observation": str(observation)[
                            :200
                        ],  # Truncate long observations
                    }
                )

        return steps
