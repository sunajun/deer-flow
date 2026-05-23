from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ScheduleStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"


class ScheduleTrigger(BaseModel):
    cron: str = ""
    timezone: str = "Asia/Shanghai"
    interval_seconds: int | None = None


class ScheduleNotification(BaseModel):
    enabled: bool = False
    channel: str = "feishu"
    target: str = ""
    include_summary: bool = True
    include_full_output: bool = False


class ScheduledTask(BaseModel):
    task_id: str
    name: str
    description: str = ""
    prompt: str
    trigger: ScheduleTrigger = Field(default_factory=ScheduleTrigger)
    notification: ScheduleNotification = Field(default_factory=ScheduleNotification)
    use_orchestration: bool = False
    reuse_thread: bool = False
    thread_id: str | None = None
    timeout_seconds: int = 3600
    status: ScheduleStatus = ScheduleStatus.ACTIVE
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    run_count: int = 0
    last_fired_cron_time: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class ScheduleRun(BaseModel):
    run_id: str
    task_id: str
    thread_id: str
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    result_summary: str | None = None
    error: str | None = None
