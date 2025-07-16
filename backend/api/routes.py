from fastapi import APIRouter, UploadFile, File, HTTPException
from services.storage import upload_to_blob, list_blobs_in_container

router = APIRouter()

@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        url = await upload_to_blob(file)
        return {"status": "success", "url": url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/container")
async def list_container_blobs():
    files = await list_blobs_in_container()
    return {"files": files}
