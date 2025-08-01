
from fastapi import APIRouter, UploadFile, File, Query, HTTPException
from pydantic import BaseModel
from typing import Optional

from services.storage import (
    upload_to_blob,
    list_blobs_in_container,
    create_folder,
    delete_blob,
    delete_folder,
    rename_blob,
    rename_folder,
    rename_folder_adls,
    delete_folder_adls,
    list_adls_paths
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
    return {"files": await list_blobs_in_container(prefix=prefix, container=container)}

@router.get("/container-adls")
async def list_container_adls(prefix: str = "", container: str = "silver"):
    print(f"📂 ADLS: container={container}, prefix={prefix}")
    return {"files": await list_adls_paths(container, prefix)}

@router.post("/upload")
async def upload_file(path: str = "", container: str = "bronze", file: UploadFile = File(...)):
    return {"url": await upload_to_blob(file, path, container=container)}

@router.post("/create-folder")
async def create(path: str = "", container: str = "bronze"):
    await create_folder(path, container=container)
    return {"message": "Cartella creata"}

@router.delete("/delete")
async def delete(path: str = "", container: str = "bronze"):
    await delete_blob(path, container=container)
    return {"message": "File eliminato"}

@router.delete("/delete-folder")
async def api_delete_folder(path: str = "", container: str = "bronze"):
    if container.lower() == "silver":
        await delete_folder_adls(path, container=container)
    else:
        await delete_folder(path, container=container)
    return {"message": "Cartella eliminata"}

@router.post("/rename")
async def rename(request: RenameRequest):
    await rename_blob(request.oldPath, request.newPath, container=request.container)
    return {"message": "Rinominato"}

@router.post("/rename-folder")
async def api_rename_folder(request: RenameFolderRequest):
    print(f"🔁 Rinomina cartella {request.oldPath} → {request.newPath} in {request.container}")
    if request.container.lower() == "silver":
        await rename_folder_adls(request.oldPath, request.newPath, container=request.container)
    else:
        await rename_folder(request.oldPath, request.newPath, container=request.container)
    return {"message": "Cartella rinominata"}
