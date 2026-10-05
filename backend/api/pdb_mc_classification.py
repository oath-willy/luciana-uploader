from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.mc_code_local_store import SnapshotUnavailable
from services.pdb_mc_classification import (
    classification_metadata,
    create_classification_record,
    search_classification,
    update_classification_record,
)


router = APIRouter(
    prefix="/pdb/mc-classification",
    tags=["PDB MC Classification"],
)


class ClassificationSearchRequest(BaseModel):
    page: int = Field(default=0, ge=0)
    page_size: int = 100
    search: str = Field(default="", max_length=2000)
    filters: dict[str, str] = Field(default_factory=dict)
    family: str = Field(default="", max_length=1000)
    subfamily: str = Field(default="", max_length=1000)


class ClassificationUpdateRequest(BaseModel):
    record_key: str = Field(min_length=1, max_length=1000)
    values: dict[str, Any]


class ClassificationCreateRequest(BaseModel):
    values: dict[str, Any]


def _call(callback, *args):
    try:
        return callback(*args)
    except SnapshotUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/metadata")
def metadata():
    return _call(classification_metadata)


@router.post("/search")
def search(payload: ClassificationSearchRequest):
    return _call(
        search_classification,
        payload.page,
        payload.page_size,
        payload.search,
        payload.filters,
        payload.family,
        payload.subfamily,
    )


@router.patch("/records")
def update_record(payload: ClassificationUpdateRequest):
    return _call(
        update_classification_record,
        payload.record_key,
        payload.values,
    )


@router.post("/records", status_code=201)
def create_record(payload: ClassificationCreateRequest):
    return _call(create_classification_record, payload.values)
