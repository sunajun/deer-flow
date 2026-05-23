from fastapi import APIRouter, Query, Response

from app.gateway.services.task_center_service import get_task_center_service

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("/")
async def list_tasks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = None,
    task_type: str | None = None,
):
    service = get_task_center_service()
    tasks = await service.list_tasks(page, page_size, status, task_type)
    return {
        "tasks": [t.model_dump(mode="json") for t in tasks],
        "page": page,
        "page_size": page_size,
    }


@router.get("/{task_id}")
async def get_task_detail(task_id: str):
    service = get_task_center_service()
    task = await service.get_task_detail(task_id)
    if task is None:
        return {"error": f"Task {task_id} not found"}
    return task.model_dump(mode="json")


@router.get("/{task_id}/logs")
async def get_task_logs(task_id: str):
    service = get_task_center_service()
    logs = await service.get_task_logs(task_id)
    return {"task_id": task_id, "logs": logs}


@router.post("/{task_id}/retry")
async def retry_task(task_id: str):
    service = get_task_center_service()
    try:
        task = await service.retry_task(task_id)
        return task.model_dump(mode="json")
    except ValueError as e:
        return {"error": str(e)}


@router.post("/{task_id}/rerun")
async def rerun_task(task_id: str, use_new_thread: bool = False):
    service = get_task_center_service()
    try:
        task = await service.rerun_task(task_id, use_new_thread=use_new_thread)
        return task.model_dump(mode="json")
    except ValueError as e:
        return {"error": str(e)}


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str):
    service = get_task_center_service()
    try:
        task = await service.cancel_task(task_id)
        return task.model_dump(mode="json")
    except ValueError as e:
        return {"error": str(e)}


@router.get("/{task_id}/export")
async def export_audit(task_id: str):
    service = get_task_center_service()
    try:
        report = await service.export_task_audit(task_id)
        return Response(content=report, media_type="application/json")
    except ValueError as e:
        return {"error": str(e)}
