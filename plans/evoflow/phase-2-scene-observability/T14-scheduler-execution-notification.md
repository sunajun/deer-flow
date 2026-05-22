# T14 - 定时任务执行触发与 IM 推送

## 元信息
- **任务ID**: T14
- **阶段**: 第2期 - 场景与观测
- **优先级**: P2
- **预估工期**: 3 天
- **依赖任务**: T13
- **关联差距**: 差距4 - 定时任务

## 目标
实现定时任务执行触发、IM 推送通知、API 路由，以及与 Gateway lifespan 上下文管理器集成。

## 详细实现步骤

### 步骤1: 实现 _execute 执行触发
- **文件**: `backend/packages/harness/deerflow/scheduler/service.py`
- **操作**: 续写
- **内容**: 触发执行
```python
    async def _execute(self, task: ScheduledTask) -> None:
        now = datetime.now(timezone.utc)
        run = ScheduleRun(
            run_id=f"run_{task.task_id}_{int(now.timestamp())}",
            task_id=task.task_id,
            thread_id="",
            status="running",
            started_at=now,
        )

        if task.reuse_thread and task.thread_id:
            run.thread_id = task.thread_id
        else:
            run.thread_id = await self._create_thread(task.prompt)

        await self._send_message(run.thread_id, task.prompt)

        task.last_run_at = now
        task.last_fired_cron_time = now
        task.run_count += 1
        self.runs.append(run)

        asyncio.create_task(self._wait_and_notify(task, run))
```
- **验收**: 触发后创建线程并发送消息

### 步骤2: 实现 _create_thread 和 _send_message
- **文件**: `backend/packages/harness/deerflow/scheduler/service.py`
- **操作**: 续写
- **内容**: 复用 Gateway 的线程和消息 API
```python
    async def _create_thread(self, prompt: str) -> str:
        """调用 Gateway API 创建线程"""
        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "http://localhost:8000/api/threads",
                json={},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("thread_id", "")

    async def _send_message(self, thread_id: str, prompt: str) -> None:
        """调用 Gateway API 发送消息"""
        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"http://localhost:8000/api/threads/{thread_id}/runs",
                json={"input": {"messages": [{"type": "human", "content": prompt}]}},
            )
            resp.raise_for_status()
```
- **验收**: 线程创建和消息发送成功

### 步骤3: 实现 _wait_and_notify
- **文件**: `backend/packages/harness/deerflow/scheduler/service.py`
- **操作**: 续写
- **内容**: 等待执行完成并推送通知
```python
    async def _wait_and_notify(self, task: ScheduledTask, run: ScheduleRun) -> None:
        """等待执行完成并推送通知"""
        import time

        timeout = task.timeout_seconds
        start = time.time()
        while time.time() - start < timeout:
            status = await self._check_thread_status(run.thread_id)
            if status in ("completed", "failed", "cancelled"):
                run.status = status
                run.completed_at = datetime.now(timezone.utc)
                break
            await asyncio.sleep(10)
        else:
            run.status = "failed"
            run.error = "执行超时"

        if task.notification.enabled:
            await self._send_notification(task, run)

    async def _check_thread_status(self, thread_id: str) -> str:
        """检查线程执行状态"""
        import httpx

        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(
                    f"http://localhost:8000/api/threads/{thread_id}/runs",
                )
                resp.raise_for_status()
                runs = resp.json()
                if runs:
                    return runs[-1].get("status", "running")
            except Exception:
                pass
        return "running"
```
- **验收**: 等待完成或超时，超时后推送通知

### 步骤4: 实现 IM 推送
- **文件**: `backend/packages/harness/deerflow/scheduler/service.py`
- **操作**: 续写
- **内容**: 通过 ChannelService 推送
```python
    async def _send_notification(self, task: ScheduledTask, run: ScheduleRun) -> None:
        """通过 ChannelService 推送通知。

        使用 get_channel_service() 从 app.channels.service 获取
        ChannelService 单例，而非不存在的 get_channel_manager。
        """
        from app.channels.service import get_channel_service

        channel_service = get_channel_service()
        if channel_service is None:
            logger.warning("ChannelService not available, skipping notification for task %s", task.task_id)
            return

        channel = channel_service.get_channel(task.notification.channel)
        if channel is None:
            logger.warning("Channel %s not available", task.notification.channel)
            return

        message = run.result_summary or "任务执行完成"
        if task.notification.include_summary and run.result_summary:
            message = f"【定时任务】{task.name}\n状态: {run.status}\n摘要: {run.result_summary}"

        try:
            if hasattr(channel, "send_message"):
                await channel.send_message(task.notification.target, message)
        except Exception:
            logger.exception("Failed to send notification via %s", task.notification.channel)
```
- **关键修正**: 原方案使用 `from deerflow.channels import get_channel_manager`，但代码库中不存在此函数。正确方式是使用 `get_channel_service()` 从 `app.channels.service` 获取 ChannelService 单例，然后通过 `channel_service.get_channel(name)` 获取具体 channel 实例。
- **验收**: 推送到指定 IM 渠道

### 步骤5: 创建 API 路由
- **文件**: `backend/app/gateway/routers/schedules.py`
- **操作**: 新建
- **内容**: 9 个 API 端点
```python
from fastapi import APIRouter

from deerflow.scheduler.models import ScheduleTrigger, ScheduledTask
from deerflow.scheduler.service import get_scheduler_service

router = APIRouter(prefix="/api/schedules", tags=["schedules"])


@router.post("/")
async def create_schedule(task: ScheduledTask):
    service = get_scheduler_service()
    result = await service.create_task(task)
    return result.model_dump(mode="json")


@router.get("/")
async def list_schedules():
    service = get_scheduler_service()
    tasks = await service.list_tasks()
    return {"tasks": [t.model_dump(mode="json") for t in tasks]}


@router.get("/{task_id}")
async def get_schedule(task_id: str):
    service = get_scheduler_service()
    tasks = await service.list_tasks()
    task = next((t for t in tasks if t.task_id == task_id), None)
    if task is None:
        return {"error": f"Task {task_id} not found"}
    return task.model_dump(mode="json")


@router.put("/{task_id}")
async def update_schedule(task_id: str, updates: dict):
    service = get_scheduler_service()
    try:
        task = await service.update_task(task_id, updates)
        return task.model_dump(mode="json")
    except ValueError as e:
        return {"error": str(e)}


@router.delete("/{task_id}")
async def delete_schedule(task_id: str):
    service = get_scheduler_service()
    await service.delete_task(task_id)
    return {"deleted": task_id}


@router.post("/{task_id}/pause")
async def pause_schedule(task_id: str):
    service = get_scheduler_service()
    await service.pause_task(task_id)
    return {"status": "paused"}


@router.post("/{task_id}/resume")
async def resume_schedule(task_id: str):
    service = get_scheduler_service()
    await service.resume_task(task_id)
    return {"status": "active"}


@router.post("/{task_id}/trigger")
async def trigger_schedule(task_id: str):
    service = get_scheduler_service()
    tasks = await service.list_tasks()
    task = next((t for t in tasks if t.task_id == task_id), None)
    if task is None:
        return {"error": f"Task {task_id} not found"}
    await service._execute(task)
    return {"triggered": task_id}


@router.get("/{task_id}/runs")
async def get_schedule_runs(task_id: str):
    service = get_scheduler_service()
    runs = await service.get_runs(task_id)
    return {"runs": [r.model_dump(mode="json") for r in runs]}
```
- **验收**: API 端点可访问

### 步骤6: 集成到 Gateway lifespan 上下文管理器
- **文件**: `backend/app/gateway/app.py`
- **操作**: 改造
- **内容**: 在 `lifespan` 上下文管理器中管理 SchedulerService，NOT `@app.on_event("startup")`
```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # ... 现有启动逻辑 ...

    # Start SchedulerService
    scheduler_task = None
    try:
        from deerflow.scheduler.service import get_scheduler_service

        scheduler = get_scheduler_service()
        scheduler_config = getattr(startup_config, "scheduler", None)
        if scheduler_config and getattr(scheduler_config, "enabled", False):
            scheduler_task = asyncio.create_task(scheduler.start())
            logger.info("SchedulerService started")
    except Exception:
        logger.exception("Failed to start SchedulerService")

    yield

    # Stop SchedulerService
    if scheduler_task is not None:
        try:
            from deerflow.scheduler.service import get_scheduler_service

            scheduler = get_scheduler_service()
            await asyncio.wait_for(
                scheduler.stop(),
                timeout=_SHUTDOWN_HOOK_TIMEOUT_SECONDS,
            )
            scheduler_task.cancel()
        except TimeoutError:
            logger.warning("SchedulerService shutdown exceeded %.1fs", _SHUTDOWN_HOOK_TIMEOUT_SECONDS)
        except Exception:
            logger.exception("Failed to stop SchedulerService")

    # ... 现有关闭逻辑 ...
```

同时在 `create_app()` 中注册 schedules router：
```python
from app.gateway.routers import (
    # ... 现有导入 ...
    schedules,
)

def create_app() -> FastAPI:
    # ... 现有逻辑 ...

    # Schedules API is mounted at /api/schedules
    app.include_router(schedules.router)

    # ... 后续路由注册 ...
```
- **关键修正**: 原方案使用 `@app.on_event("startup")` 和 `@app.on_event("shutdown")`，但 DeerFlow Gateway 使用 `lifespan` 上下文管理器（`@asynccontextmanager`）。SchedulerService 必须在 `lifespan` 函数的 yield 之前启动，yield 之后停止，与 ChannelService 的管理模式一致。
- **验收**: Gateway 启动后调度服务自动运行

### 步骤7: 添加 SchedulerService 单例访问
- **文件**: `backend/packages/harness/deerflow/scheduler/service.py`
- **操作**: 续写
- **内容**: 添加单例访问函数
```python
_scheduler_service: SchedulerService | None = None


def get_scheduler_service() -> SchedulerService:
    """获取全局 SchedulerService 单例"""
    global _scheduler_service
    if _scheduler_service is None:
        _scheduler_service = SchedulerService()
    return _scheduler_service


def reset_scheduler_service() -> None:
    """重置单例（用于测试）"""
    global _scheduler_service
    _scheduler_service = None
```
- **验收**: 单例访问正确

## 验收标准
- [ ] _execute 触发执行，创建线程/发送消息
- [ ] _wait_and_notify 等待完成或超时
- [ ] IM 推送使用 `get_channel_service()` 从 `app.channels.service`
- [ ] 9 个 API 端点可访问
- [ ] schedules router 在 `create_app()` 中注册
- [ ] SchedulerService 在 `lifespan` 上下文管理器中启动/停止

## 测试计划
| 测试类型 | 测试用例 | 预期结果 |
|---------|---------|---------|
| 单元测试 | _execute 创建线程 | run 记录生成 |
| 单元测试 | _wait_and_notify 完成 | run.status=completed |
| 单元测试 | _wait_and_notify 超时 | run.status=failed, error="执行超时" |
| 单元测试 | _send_notification | 调用 ChannelService |
| 单元测试 | ChannelService 不可用 | 跳过推送，记录警告 |
| 集成测试 | POST /api/schedules | 返回 task_id |
| 集成测试 | POST /api/schedules/{id}/pause | status=paused |
| 集成测试 | POST /api/schedules/{id}/trigger | 手动触发执行 |
| 集成测试 | Gateway 启动 | 调度服务运行 |

## 风险与缓解
| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| ChannelService 未初始化 | 中 | 推送前检查 channel_service 是否为 None |
| 并发执行数过多 | 中 | 限制 max_concurrent_runs |
| Gateway 重启丢任务 | 低 | 持久化到 DB（T15） |

## 参考文档
- EVOFLOW_IMPLEMENTATION_PLAN.md 第4节
- ChannelService 单例: `backend/app/channels/service.py`（`get_channel_service()` / `start_channel_service()` / `stop_channel_service()`）
- Gateway lifespan: `backend/app/gateway/app.py`（`@asynccontextmanager async def lifespan(app)`）
