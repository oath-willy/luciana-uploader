from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.mc_code_local_store import SnapshotUnavailable
from services.pdb_brands import (
    create_brand_raw,
    search_brand_raw,
    search_brands,
    update_brand_raw,
)


router = APIRouter(prefix="/pdb/brands", tags=["PDB Brands"])


class BrandsSearchRequest(BaseModel):
    page: int = Field(default=0, ge=0)
    page_size: int = 50
    search: str = Field(default="", max_length=2000)
    filters: dict[str, str] = Field(default_factory=dict)


class BrandRawSearchRequest(BrandsSearchRequest):
    brand: str = Field(min_length=1, max_length=1000)


class BrandRawCreateRequest(BaseModel):
    brand: str = Field(min_length=1, max_length=1000)
    brand_raw: str = Field(min_length=1, max_length=1000)


class BrandRawUpdateRequest(BrandRawCreateRequest):
    record_key: str = Field(min_length=1, max_length=1000)


def _handle_search(callback, *args):
    try:
        return callback(*args)
    except SnapshotUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/search")
def brands_search(payload: BrandsSearchRequest):
    return _handle_search(
        search_brands,
        payload.page,
        payload.page_size,
        payload.search,
        payload.filters,
    )


@router.post("/raw/search")
def brand_raw_search(payload: BrandRawSearchRequest):
    return _handle_search(
        search_brand_raw,
        payload.brand,
        payload.page,
        payload.page_size,
        payload.search,
        payload.filters,
    )


@router.post("/raw/records")
def brand_raw_create(payload: BrandRawCreateRequest):
    return _handle_search(create_brand_raw, payload.brand, payload.brand_raw)


@router.patch("/raw/records")
def brand_raw_update(payload: BrandRawUpdateRequest):
    return _handle_search(
        update_brand_raw,
        payload.record_key,
        payload.brand,
        payload.brand_raw,
    )
