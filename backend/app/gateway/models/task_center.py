from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class TaskRecord(BaseModel):
    task_id: str
    thread_id: str
    task_type: str
    name: str
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration: float | None = None
    result: dict | None = None
    error: str | None = None
    log_ids: list[str] = Field(default_factory=list)
    created_by: str = "default"
    parent_task_id: str | None = None

    def to_storage_dict(self) -> dict:
        data = self.model_dump(mode="json")
        return data

    @classmethod
    def from_storage_dict(cls, data: dict) -> "TaskRecord":
        return cls.model_validate(data)
