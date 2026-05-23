from pydantic import BaseModel, ConfigDict, Field


class SchedulerConfig(BaseModel):
    """Configuration for the scheduler service."""

    model_config = ConfigDict(extra="allow")

    enabled: bool = Field(default=False, description="Enable the scheduler service")
    tick_interval: int = Field(default=60, description="Tick interval in seconds")
    max_concurrent_runs: int = Field(default=5, description="Maximum concurrent scheduled runs")
    default_timeout: int = Field(default=3600, description="Default timeout in seconds for scheduled runs")
    persist_to_db: bool = Field(default=True, description="Persist scheduled tasks to database")
