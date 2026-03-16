"""Service for managing chat sessions and building conversation context."""

from uuid import UUID
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.session import Session
from app.models.dataset import Query
from app.services.dataset_service import DatasetService


class SessionService:
    """Service for session CRUD and conversation context building."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.dataset_service = DatasetService(db)

    async def create_session(self, dataset_id: UUID, title: Optional[str] = None) -> Session:
        """Create a new session tied to a dataset."""
        # Verify dataset exists
        await self.dataset_service.get_dataset(dataset_id)

        session = Session(
            dataset_id=dataset_id,
            title=title or "New session",
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def get_session(self, session_id: UUID) -> Session:
        """Fetch a session by ID, raising 404 if not found."""
        result = await self.db.execute(select(Session).where(Session.id == session_id))
        session = result.scalar_one_or_none()
        if not session:
            from app.utils.error_handlers import DatasetNotFoundError
            raise DatasetNotFoundError(f"Session {session_id} not found")
        return session

    async def list_sessions(
        self, dataset_id: UUID, skip: int = 0, limit: int = 50
    ) -> tuple[list[Session], int]:
        """List sessions for a dataset, most recent first."""
        count_result = await self.db.execute(
            select(func.count(Session.id)).where(Session.dataset_id == dataset_id)
        )
        total = count_result.scalar_one()

        result = await self.db.execute(
            select(Session)
            .where(Session.dataset_id == dataset_id)
            .order_by(Session.updated_at.desc())
            .offset(skip)
            .limit(limit)
        )
        sessions = result.scalars().all()
        return list(sessions), total

    async def delete_session(self, session_id: UUID) -> None:
        """Delete a session (queries get session_id nullified via SET NULL FK)."""
        session = await self.get_session(session_id)
        await self.db.delete(session)
        await self.db.commit()

    async def get_session_queries(self, session_id: UUID) -> list[Query]:
        """Return all queries in a session, ordered oldest → newest."""
        result = await self.db.execute(
            select(Query)
            .where(Query.session_id == session_id)
            .order_by(Query.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_message_count(self, session_id: UUID) -> int:
        """Return number of completed queries in a session."""
        result = await self.db.execute(
            select(func.count(Query.id)).where(Query.session_id == session_id)
        )
        return result.scalar_one()

    async def auto_update_title(self, session: Session, first_question: str) -> None:
        """Set session title from the first question (max 80 chars) if still default."""
        if session.title == "New session":
            session.title = first_question[:80]
            await self.db.commit()

    @staticmethod
    def build_conversation_context(
        queries: list[Query],
        max_full: int = 2,
        max_total: int = 7,
    ) -> Optional[str]:
        """
        Build a summarized conversation history string for the planner.

        Strategy:
        - Take up to max_total most recent completed queries (oldest → newest)
        - Last max_full turns: include full question + answer[:400]
        - Earlier turns: include question + key_findings only (cheaper)

        Returns None if there are no prior queries.
        """
        if not queries:
            return None

        # Trim to max window
        window = queries[-max_total:]
        total = len(window)
        full_start_idx = max(0, total - max_full)

        parts = []
        for i, q in enumerate(window):
            turn_label = f"Turn {i + 1}"
            if i >= full_start_idx:
                answer_excerpt = (q.answer or "No answer")[:400]
                parts.append(f"{turn_label}:\n  Q: {q.question}\n  A: {answer_excerpt}")
            else:
                if q.key_findings:
                    findings_str = "; ".join(q.key_findings[:3])
                else:
                    findings_str = "No findings recorded"
                parts.append(f"{turn_label}:\n  Q: {q.question}\n  Findings: {findings_str}")

        return "Conversation history (build on this when relevant):\n" + "\n\n".join(parts)
