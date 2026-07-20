"""
Monitoring schema: one row per question asked, plus the thumbs up/down on it.

These tables deliberately sit on their OWN DeclarativeBase. create_schema() in
cinevec/ingestion/db/build_rag_db.py calls Base.metadata.drop_all() when
rebuild=True, which would wipe every table registered on the movies Base.
Monitoring history has to outlive a dataset rebuild, so it lives in a separate
MetaData -- same database, same container, only the registry differs.
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class MonitoringBase(DeclarativeBase):
    pass


class Conversation(MonitoringBase):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)

    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)

    # Which tools the agent chose, in order, e.g.
    # {get_movie_details,search_movies:hybrid}. The mode suffix matters: it says
    # whether the vector index is actually being used.
    tool_calls: Mapped[int] = mapped_column(Integer, default=0)
    tools_used: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)

    response_time: Mapped[float] = mapped_column(Float)   # seconds
    cost: Mapped[float] = mapped_column(Float, default=0.0)  # USD

    # timezone=True -> TIMESTAMPTZ, which Grafana's $__timeFilter() needs to
    # avoid time-shifting. Postgres now() keeps one clock for every row.
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class Feedback(MonitoringBase):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    # Signed: +1 up, -1 down. Lets the dashboard count both in one SUM(CASE).
    score: Mapped[int] = mapped_column(Integer)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
