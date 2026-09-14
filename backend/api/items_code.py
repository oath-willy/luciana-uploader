from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services.items_code import Dataset, dataset_metadata, search_dataset
from services.mc_code_local_store import SnapshotUnavailable


router = APIRouter(prefix="/items-code", tags=["Items Code"])
PAGE_SIZES = {25, 50, 100, 250, 500, 1000}


class DatasetSearch(BaseModel):
    company: str = Field(default="", max_length=255)
    page: int = Field(default=0, ge=0)
    page_size: int = 100
    search: str = Field(default="", max_length=2000)
    filters: dict[str, str] = Field(default_factory=dict)


@router.get("/{dataset}/metadata")
def metadata(dataset: Dataset, company: str = Query(default="", max_length=255)):
    try:
        return dataset_metadata(dataset, company)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{dataset}/search")
def search(dataset: Dataset, payload: DatasetSearch):
    if payload.page_size not in PAGE_SIZES:
        raise HTTPException(status_code=400, detail="Rows per page non valido")
    try:
        return search_dataset(dataset, payload.company, payload.page, payload.page_size, payload.search, payload.filters)
    except SnapshotUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
