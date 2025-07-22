import os
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import router
from dotenv import load_dotenv
from fastapi import HTTPException
load_dotenv()

app = FastAPI()

frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
print("🔐 AZURE_STORAGE_CONNECTION_STRING =", os.getenv("AZURE_STORAGE_CONNECTION_STRING"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin],  # <-- ora valore esplicito
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/ping")
def ping():
    return {"message": "stong"}

# Include tutte le rotte
app.include_router(router, prefix="/api")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8080)))


async def delete_blob(path: str):
    blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
    container_client = blob_service_client.get_container_client(AZURE_CONTAINER_NAME)
    blob_client = container_client.get_blob_client(path)
    try:
        await blob_client.delete_blob()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore eliminazione: {str(e)}")


async def rename_blob(old_path: str, new_path: str):
    blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
    container_client = blob_service_client.get_container_client(AZURE_CONTAINER_NAME)

    source_blob = container_client.get_blob_client(old_path)
    dest_blob = container_client.get_blob_client(new_path)

    try:
        await dest_blob.start_copy_from_url(source_blob.url)
        await source_blob.delete_blob()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore rinomina: {str(e)}")