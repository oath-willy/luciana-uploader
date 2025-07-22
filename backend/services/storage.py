import os
from azure.storage.blob.aio import BlobServiceClient
from azure.storage.blob import ContentSettings
from fastapi import UploadFile
from fastapi import HTTPException
from dotenv import load_dotenv

load_dotenv()

AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
AZURE_CONTAINER_NAME = os.getenv("AZURE_CONTAINER_NAME", "bronze")

async def upload_to_blob(file: UploadFile):
    blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
    container_client = blob_service_client.get_container_client(AZURE_CONTAINER_NAME)
    blob_client = container_client.get_blob_client(file.filename)

    content = await file.read()
    await blob_client.upload_blob(
        content,
        overwrite=True,
        content_settings=ContentSettings(content_type=file.content_type),
    )
    return blob_client.url

# async def list_blobs_in_container(prefix: str = ""):
#     AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
#     AZURE_CONTAINER_NAME = os.getenv("AZURE_CONTAINER_NAME", "bronze")

#     blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
#     container_client = blob_service_client.get_container_client(AZURE_CONTAINER_NAME)

#     blob_list = []
#     async for blob in container_client.list_blobs(name_starts_with=prefix):
#         blob_list.append(blob.name)

#     return blob_list

async def list_blobs_in_container(prefix: str = ""):
    blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
    container_client = blob_service_client.get_container_client(AZURE_CONTAINER_NAME)

    blob_list = []
    async for blob in container_client.list_blobs(name_starts_with=prefix):
        blob_list.append({
            "name": blob.name,
            "last_modified": blob.last_modified.isoformat() if blob.last_modified else None
        })

    return blob_list

async def delete_blob(path: str):
    blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
    container_client = blob_service_client.get_container_client(AZURE_CONTAINER_NAME)
    blob_client = container_client.get_blob_client(path)

    try:
        await blob_client.delete_blob()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore eliminazione: {str(e)}")
    
async def rename_blob(old_path: str, new_path: str):
    print("🔁 RENAME:", old_path, "→", new_path)

    try:
        blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
        container_client = blob_service_client.get_container_client(AZURE_CONTAINER_NAME)

        source_blob = container_client.get_blob_client(old_path)
        dest_blob = container_client.get_blob_client(new_path)

        print("📦 Verifico esistenza blob:", old_path)
        source_exists = await source_blob.exists()
        if not source_exists:
            raise HTTPException(status_code=404, detail=f"Blob {old_path} non trovato")

        print("⬇️ Download blob...")
        download_stream = await source_blob.download_blob()
        content = await download_stream.readall()

        print("⬆️ Upload nuovo blob:", new_path)
        await dest_blob.upload_blob(content, overwrite=True)

        print("❌ Elimino blob originale:", old_path)
        await source_blob.delete_blob()

        print("✅ Rinominato con successo")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print("❌ Errore durante la rinomina:", str(e))
        raise HTTPException(status_code=500, detail=f"Errore rinomina: {str(e)}")
