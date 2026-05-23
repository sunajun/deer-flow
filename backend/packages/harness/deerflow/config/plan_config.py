from pydantic import BaseModel, Field


class PlanConfig(BaseModel):
    enabled: bool = Field(default=False, description="是否启用 Plan DAG 编排")
    max_parallel_nodes: int = Field(default=3, description="最大并行节点数")
    default_timeout: int = Field(default=900, description="节点默认超时（秒）")
    auto_approve: bool = Field(default=False, description="是否自动确认 Plan")
    acceptance_verification: bool = Field(default=True, description="是否启用验收校验")
    reorchestrate_max_retries: int = Field(default=2, description="最大重编排次数")


_plan_config: PlanConfig = PlanConfig()


def load_plan_config_from_dict(data: dict | None) -> PlanConfig:
    global _plan_config
    if data is None:
        _plan_config = PlanConfig()
    else:
        _plan_config = PlanConfig.model_validate(data)
    return _plan_config


def get_plan_config() -> PlanConfig:
    return _plan_config


def reset_plan_config() -> None:
    global _plan_config
    _plan_config = PlanConfig()
