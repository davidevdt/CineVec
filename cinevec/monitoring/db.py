"""
Reads and writes for the monitoring tables. Every call opens its own
`with Session(engine) as s:`, matching the rest of the codebase.
"""

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from cinevec.logging import logger
from cinevec.monitoring.metrics import ConversationRecord
from cinevec.monitoring.models import Conversation, Feedback, MonitoringBase


def create_monitoring_schema(engine: Engine) -> None:
    """Create the monitoring tables if they are missing. Never drops: this is
    history. Kept out of create_schema(), whose rebuild path drops everything
    registered on the movies Base."""
    MonitoringBase.metadata.create_all(engine)
    logger.info("Monitoring schema ready (conversations, feedback).")


def save_conversation(engine: Engine, record: ConversationRecord) -> int:
    """Insert one conversation and return its new id."""
    with Session(engine) as s:
        row = Conversation(
            question=record.question,
            answer=record.answer,
            model=record.model,
            input_tokens=record.input_tokens,
            output_tokens=record.output_tokens,
            total_tokens=record.total_tokens,
            tool_calls=record.tool_calls,
            tools_used=record.tools_used or None,
            response_time=record.response_time,
            cost=record.cost,
        )
        s.add(row)
        s.flush()          # INSERT ... RETURNING id
        new_id = row.id    # read before commit expires the attribute
        s.commit()
        return new_id


def conversation_exists(engine: Engine, conversation_id: int) -> bool:
    with Session(engine) as s:
        found = s.execute(
            select(Conversation.id).where(Conversation.id == conversation_id)
        ).first()
    return found is not None


def save_feedback(engine: Engine, conversation_id: int, score: int) -> int:
    """Record a +1 / -1 vote against a conversation."""
    with Session(engine) as s:
        row = Feedback(conversation_id=conversation_id, score=score)
        s.add(row)
        s.flush()
        new_id = row.id
        s.commit()
        return new_id
