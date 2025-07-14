from azure.storage.blob import BlobServiceClient
import os

conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
client = BlobServiceClient.from_connection_string(conn_str)

print("✅ Connessione riuscita. Container disponibili:")
for c in client.list_containers():
    print("-", c.name)
