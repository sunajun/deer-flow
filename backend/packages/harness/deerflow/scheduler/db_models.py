from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from deerflow.persistence.base import Base


class ScheduledTaskRow(Base):
    __tablename__ = "scheduled_tasks"

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    description: Mapped[str] = mapped_column(Text, default="")
    prompt: Mapped[str] = mapped_column(Text)
    trigger_config: Mapped[str] = mapped_column(Text)
    notification_config: Mapped[str] = mapped_column(Text, default="{}")
    use_orchestration: Mapped[bool] = mapped_column(Boolean, default=False)
    reuse_thread: Mapped[bool] = mapped_column(Boolean, default=False)
    thread_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=3600)
    status: Mapped[str] = mapped_column(String(16), default="active")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    run_count: Mapped[int] = mapped_column(Integer, default=0)
    last_fired_cron_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class ScheduleRunRow(Base):
    __tablename__ = "schedule_runs"

    run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(64), index=True)
    thread_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    started_at: Mapped[datetime] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
