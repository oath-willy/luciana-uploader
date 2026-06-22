from typing import Optional

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from services.storage import (
    as_download_headers,
    create_folder,
    delete_file,
    delete_folder,
    download_file,
    list_adls_paths,
    list_paths,
    rename_file,
    rename_folder,
    upload_file as upload_file_to_storage,
)


router = APIRouter()


class UploadRequest(BaseModel):
    path: Optional[str] = ""
    container: str = "bronze"


class RenameRequest(BaseModel):
    oldPath: str
    newPath: str
    container: str


class RenameFolderRequest(BaseModel):
    oldPath: str
    newPath: str
    container: str


@router.get("/container")
async def list_container(prefix: str = "", container: str = "bronze"):
    return {"files": await list_paths(prefix=prefix, container=container)}


@router.get("/container-adls")
async def list_container_adls(prefix: str = "", container: str = "silver"):
    return {"files": await list_adls_paths(container=container, prefix=prefix)}


@router.post("/upload")
async def upload(path: str = "", container: str = "bronze", file: UploadFile = File(...)):
    return {"url": await upload_file_to_storage(file, path, container=container)}


@router.post("/create-folder")
async def create(path: str = "", container: str = "bronze"):
    await create_folder(path, container=container)
    return {"message": "Cartella creata"}


@router.delete("/delete")
async def delete(path: str = "", container: str = "bronze"):
    await delete_file(path, container=container)
    return {"message": "File eliminato"}


@router.delete("/delete-folder")
async def api_delete_folder(path: str = "", container: str = "bronze"):
    await delete_folder(path, container=container)
    return {"message": "Cartella eliminata"}


@router.post("/rename")
async def rename(request: RenameRequest):
    await rename_file(request.oldPath, request.newPath, container=request.container)
    return {"message": "Rinominato"}


@router.post("/rename-folder")
async def api_rename_folder(request: RenameFolderRequest):
    await rename_folder(request.oldPath, request.newPath, container=request.container)
    return {"message": "Cartella rinominata"}


@router.get("/download")
async def download(path: str = "", container: str = "bronze"):
    content = await download_file(path, container=container)
    return Response(
        content,
        media_type="application/octet-stream",
        headers=as_download_headers(path),
    )
