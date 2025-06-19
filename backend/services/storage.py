import os
from azure.storage.blob.aio import BlobServiceClient
from azure.storage.blob import ContentSettings
from fastapi import UploadFile

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
