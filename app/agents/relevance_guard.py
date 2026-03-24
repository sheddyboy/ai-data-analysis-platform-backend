"""LLM-based relevance guard — v2: uses ChatOpenAI with structured output."""

from typing import Dict, List, cast

from pydantic import SecretStr
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from loguru import logger

from app.config import settings
from app.schemas.agent import RelevanceResult
from app.utils.error_handlers import IrrelevantQuestionError


_SYSTEM_PROMPT = """You are a data relevance validator. Determine if a user's question
can be meaningfully answered using the provided dataset.

A question is RELEVANT if it:
- References any column name or value type that exists in the dataset
- Asks to filter, rank, sort, or aggregate records by any column
- Requests analysis, statistics, trends, comparisons, or patterns
- Requests visualizations of the data
- Uses synonyms or natural language for column concepts

A question is IRRELEVANT if it is completely unrelated to any column or value
in the dataset (e.g. asking about the weather or a recipe), or is a greeting/
casual conversation with no connection to the data.

When in doubt, mark as relevant — it is better to attempt answering a borderline
question than to wrongly reject a valid one."""


class RelevanceGuard:
    """Validates whether a query is relevant to a dataset using structured LLM output."""

    def __init__(self):
        self._llm = ChatOpenAI(
            model=settings.OPENAI_MODEL,
            temperature=0.0,
            api_key=SecretStr(settings.OPENAI_API_KEY),
        )
        self._structured_llm = self._llm.with_structured_output(RelevanceResult)

    async def validate_query(
        self,
        question: str,
        column_names: List[str],
        column_types: Dict[str, str],
        sample_data: List[Dict],
    ) -> bool:
        """
        Validate if a question is relevant to the dataset.

        Returns True if relevant, raises IrrelevantQuestionError if not.
        Falls back to permissive (True) on LLM failure.
        """
        dataset_info = self._build_dataset_context(
            column_names, column_types, sample_data
        )
        prompt = (
            f"Dataset:\n{dataset_info}\n\n"
            f'User question: "{question}"\n\n'
            f"Is this question relevant to the dataset?"
        )

        try:
            result = cast(
                RelevanceResult,
                await self._structured_llm.ainvoke(
                    [
                        SystemMessage(content=_SYSTEM_PROMPT),
                        HumanMessage(content=prompt),
                    ]
                ),
            )

            logger.debug("Relevance validation result: {}", result)

            if not result.is_relevant:
                raise IrrelevantQuestionError(
                    f"This question does not relate to the uploaded dataset. "
                    f"Reason: {result.reason}. "
                    f"Available columns: {', '.join(column_names)}"
                )

            return True

        except IrrelevantQuestionError:
            raise
        except Exception as e:
            # Permissive fallback: if LLM fails, allow the query
            logger.warning("Relevance guard error (allowing query): {}", e)
            return True

    def _build_dataset_context(
        self,
        column_names: List[str],
        column_types: Dict[str, str],
        sample_data: List[Dict],
    ) -> str:
        lines = ["Columns:"]
        for col in column_names:
            lines.append(f"  - {col} ({column_types.get(col, 'unknown')})")

        if sample_data:
            lines.append("\nSample Data (first 3 rows):")
            for i, row in enumerate(sample_data[:3], 1):
                lines.append(f"  Row {i}:")
                for key, value in row.items():
                    lines.append(f"    {key}: {value}")

        return "\n".join(lines)
