from __future__ import annotations

import os

from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from azure.storage.blob import BlobClient


ACCOUNT_NAME = "stkeystoneresearchdev"
CONTAINER_NAME = "pdb"


def blob_client(file_name: str, connection_env: str, secret_env: str) -> BlobClient:
    connection_string = os.getenv(connection_env, "").strip()
    if connection_string:
        return BlobClient.from_connection_string(connection_string, CONTAINER_NAME, file_name)

    credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
    secret_name = os.getenv(secret_env, "").strip()
    if secret_name:
        with SecretClient(
            vault_url=f"https://{os.getenv('KEY_VAULT_NAME', 'luciana-project')}.vault.azure.net/",
            credential=credential,
        ) as secrets:
            connection_string = secrets.get_secret(secret_name).value
        if not connection_string:
            raise RuntimeError(f"Secret di accesso a {file_name} vuoto")
        return BlobClient.from_connection_string(connection_string, CONTAINER_NAME, file_name)

    return BlobClient(
        account_url=f"https://{ACCOUNT_NAME}.blob.core.windows.net",
        container_name=CONTAINER_NAME,
        blob_name=file_name,
        credential=credential,
    )
