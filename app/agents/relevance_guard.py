"""LLM-based relevance guard for validating query relevance."""

from openai import AsyncOpenAI
from typing import Dict, List
from app.config import settings
from app.utils.error_handlers import IrrelevantQuestionError


class RelevanceGuard:
    """
    LLM-based guard that validates whether a query is relevant to a dataset.
    """

    def __init__(self):
        """Initialize the relevance guard with OpenAI client."""
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.OPENAI_MODEL

    async def validate_query(
        self,
        question: str,
        column_names: List[str],
        column_types: Dict[str, str],
        sample_data: List[Dict],
    ) -> bool:
        """
        Validate if a question is relevant to the dataset.

        Args:
            question: User's question
            column_names: List of column names
            column_types: Dictionary of column types
            sample_data: Sample rows from dataset

        Returns:
            True if question is relevant

        Raises:
            IrrelevantQuestionError: If question is not relevant
        """
        # Build context about the dataset
        dataset_info = self._build_dataset_context(
            column_names, column_types, sample_data
        )

        # Create prompt for LLM
        prompt = f"""You are a relevance validator. Your job is to determine if a user's question can be answered using the provided dataset.

Dataset Information:
{dataset_info}

User Question: "{question}"

Analyze whether this question can be meaningfully answered using the dataset columns and data above.

A question is RELEVANT if:
- It references any column name or a value type that exists in the columns
- It asks to filter, rank, sort, or aggregate records by any column (e.g. "top 10 by popularity", "most streamed", "songs in the US")
- It requests analysis, statistics, trends, comparisons, or patterns about the data
- It requests visualizations of the data
- It uses synonyms or natural language for column concepts (e.g. "popular" → popularity column, "country" → country column)

A question is IRRELEVANT if:
- It is completely unrelated to any column or value in the dataset (e.g. asking about the weather or a recipe)
- It is a greeting, casual conversation, or off-topic request with no connection to the data

When in doubt, answer YES — it is better to attempt answering a borderline question than to wrongly reject a valid one.

Respond with ONLY one word: "YES" if relevant, "NO" if irrelevant."""

        try:
            # Call OpenAI API
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a data relevance validator.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
                max_tokens=10,
            )

            # Parse response
            answer = (response.choices[0].message.content or "").strip().upper()

            if answer == "NO":
                raise IrrelevantQuestionError(
                    f"This question does not relate to the uploaded dataset. "
                    f"Please ask a question about the data columns: {', '.join(column_names)}"
                )

            return True

        except IrrelevantQuestionError:
            raise
        except Exception as e:
            # If LLM fails, be permissive and allow the query
            print(f"Relevance guard error: {e}")
            return True

    def _build_dataset_context(
        self,
        column_names: List[str],
        column_types: Dict[str, str],
        sample_data: List[Dict],
    ) -> str:
        """
        Build a text description of the dataset for the LLM.

        Args:
            column_names: List of column names
            column_types: Dictionary of column types
            sample_data: Sample rows

        Returns:
            Formatted dataset description
        """
        context_parts = []

        # Column information
        context_parts.append("Columns:")
        for col in column_names:
            col_type = column_types.get(col, "unknown")
            context_parts.append(f"  - {col} ({col_type})")

        # Sample data
        if sample_data:
            context_parts.append("\nSample Data (first 3 rows):")
            for i, row in enumerate(sample_data[:3], 1):
                context_parts.append(f"  Row {i}:")
                for key, value in row.items():
                    context_parts.append(f"    {key}: {value}")

        return "\n".join(context_parts)
