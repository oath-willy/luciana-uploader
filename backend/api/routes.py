from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Response
from pydantic import BaseModel
from azure.storage.blob.aio import BlobServiceClient
from dotenv import load_dotenv
from services.storage import ( upload_to_blob, list_blobs_in_container, delete_blob, rename_blob )

import os

router = APIRouter()

# ************************************
#           STORAGE BROWSER
# ************************************
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
AZURE_CONTAINER_NAME = os.getenv("AZURE_CONTAINER_NAME", "bronze")

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

# Download file
@router.get("/download")
async def download_file(path: str):
    try:
        blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
        container_client = blob_service_client.get_container_client(AZURE_CONTAINER_NAME)
        blob_client = container_client.get_blob_client(path)

        if not await blob_client.exists():
            raise HTTPException(status_code=404, detail="File non trovato")

        stream = await blob_client.download_blob()
        data = await stream.readall()

        return Response(
            content=data,
            media_type='application/octet-stream',
            headers={'Content-Disposition': f'attachment; filename="{path.split("/")[-1]}"'}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore durante il download: {str(e)}")