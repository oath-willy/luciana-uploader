from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from pydantic import BaseModel
from services.storage import (
    upload_to_blob,
    list_blobs_in_container,
    delete_blob,
    rename_blob
)

router = APIRouter()

# Upload file
@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        url = await upload_to_blob(file)
        return {"status": "success", "url": url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# List files in container
@router.get("/container")
async def list_container_blobs(prefix: str = ""):
    try:
        files = await list_blobs_in_container(prefix=prefix)
        return {"files": files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Delete file or folder
@router.delete("/delete")
async def api_delete(path: str = Query(..., description="Percorso del file o cartella da eliminare")):
    try:
        await delete_blob(path)
        return {"message": f"{path} eliminato con successo"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Rename file or folder
class RenameRequest(BaseModel):
    oldPath: str
    newPath: str

@router.post("/rename")
async def api_rename(request: RenameRequest):
    try:
        await rename_blob(request.oldPath, request.newPath)
        return {"message": f"Rinominato {request.oldPath} → {request.newPath}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
