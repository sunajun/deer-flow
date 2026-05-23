from __future__ import annotations

from fastapi import APIRouter, HTTPException

from deerflow.scheduler.models import ScheduledTask
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
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task.model_dump(mode="json")


@router.put("/{task_id}")
async def update_schedule(task_id: str, updates: dict):
    service = get_scheduler_service()
    try:
        task = await service.update_task(task_id, updates)
        return task.model_dump(mode="json")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete("/{task_id}")
async def delete_schedule(task_id: str):
    service = get_scheduler_service()
    await service.delete_task(task_id)
    return {"deleted": task_id}


@router.post("/{task_id}/pause")
async def pause_schedule(task_id: str):
    service = get_scheduler_service()
    try:
        await service.pause_task(task_id)
        return {"status": "paused"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/{task_id}/resume")
async def resume_schedule(task_id: str):
    service = get_scheduler_service()
    try:
        await service.resume_task(task_id)
        return {"status": "active"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/{task_id}/trigger")
async def trigger_schedule(task_id: str):
    service = get_scheduler_service()
    tasks = await service.list_tasks()
    task = next((t for t in tasks if t.task_id == task_id), None)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    await service._execute(task)
    return {"triggered": task_id}


@router.get("/{task_id}/runs")
async def get_schedule_runs(task_id: str):
    service = get_scheduler_service()
    runs = await service.get_runs(task_id)
    return {"runs": [r.model_dump(mode="json") for r in runs]}
