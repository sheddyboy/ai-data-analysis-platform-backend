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
    Action Input: print(df[df['country'] == 'UK'].groupby('artist_name').size().nlargest(10))
- For all other tools: Action Input must be a valid JSON string, even if empty: {{}}
- Never write "Action:" without immediately following it with "Action Input:"

WORKFLOW:
1. Always start with load_dataset to understand the schema and column names
2. Use execute_python to analyze data — write precise pandas expressions and use print() to output results
3. Call set_working_df(result_df) inside execute_python before using create_visualization if you need to visualize a subset
4. If a visualization was requested, call create_visualization after setting the working df
5. Generate insights at the end if helpful
6. Be concise but thorough in your final answer

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
            # Load dataset into context
            dataset_context.load_dataset(df, metadata)

            # Clear previous visualizations and insights
            viz_storage.clear()
            insight_storage.clear()

            # Run agent
            result = await self.agent_executor.ainvoke({"input": question})

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

            return {
                "answer": answer,
                "visualizations": visualizations,
                "insights": insights,
                "agent_steps": self._extract_agent_steps(result),
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
