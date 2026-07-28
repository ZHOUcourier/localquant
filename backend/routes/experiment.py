from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from backend.models.experiment import ExperimentCreate, ExperimentCompareRequest
from backend.services.experiment_service import experiment_service

router = APIRouter()


@router.get("/")
async def list_experiments(source: Optional[str] = None, limit: int = 50, offset: int = 0):
    return await experiment_service.list_experiments(source=source, limit=limit, offset=offset)


@router.post("/")
async def create_experiment(req: ExperimentCreate):
    return await experiment_service.create(req)


@router.get("/{experiment_id}")
async def get_experiment(experiment_id: str):
    exp = await experiment_service.get_experiment(experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return exp


@router.post("/compare")
async def compare_experiments(req: ExperimentCompareRequest):
    return await experiment_service.compare(req.experiment_ids)


@router.post("/{experiment_id}/note")
async def add_note(experiment_id: str, req: dict):
    note = req.get("note", "")
    success = await experiment_service.add_note(experiment_id, note)
    return {"updated": success}


@router.post("/search")
async def search_experiments(req: dict):
    tags = req.get("tags")
    metric_min = req.get("metric_min")
    limit = req.get("limit", 50)
    return await experiment_service.search(tags=tags, metric_min=metric_min, limit=limit)
