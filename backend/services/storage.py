
import os
from azure.storage.blob.aio import BlobServiceClient
from azure.storage.filedatalake.aio import DataLakeServiceClient
from fastapi import HTTPException, UploadFile

def is_adls_container(container_key: str):
    return container_key.lower() == "silver"

# ==== UTILS COMMON ====
def get_blob_container_client(container_key: str = "bronze"):
    key_upper = container_key.upper()
    conn_str = os.getenv(f"AZURE_{key_upper}_CONNECTION_STRING")
    container_name = os.getenv(f"AZURE_{key_upper}_CONTAINER_NAME")
    if not conn_str or not container_name:
        raise HTTPException(status_code=500, detail=f"Variabili mancanti per {container_key}")
    client = BlobServiceClient.from_connection_string(conn_str)
    return client.get_container_client(container_name)

def get_adls_filesystem(container_key: str = "silver"):
    key_upper = container_key.upper()
    conn_str = os.getenv(f"AZURE_{key_upper}_CONNECTION_STRING")
    container_name = os.getenv(f"AZURE_{key_upper}_CONTAINER_NAME")
    if not conn_str or not container_name:
        raise HTTPException(status_code=500, detail="Connessione ADLS mancante")
    client = DataLakeServiceClient.from_connection_string(conn_str)
    return client.get_file_system_client(container_name)

# ==== UPLOAD ====

async def upload_to_blob(file: UploadFile, path: str, container: str = "bronze"):
    container_client = get_blob_container_client(container)
    full_path = f"{path}/{file.filename}" if path else file.filename
    blob_client = container_client.get_blob_client(full_path)
    await blob_client.upload_blob(await file.read(), overwrite=True)
    return blob_client.url

# ==== LIST ====

async def list_blobs_in_container(prefix: str = "", container: str = "bronze"):
    container_client = get_blob_container_client(container)
    blobs = []
    folders = set()

    async for blob in container_client.list_blobs(name_starts_with=prefix):
        full_path = blob.name
        relative_path = full_path[len(prefix)+1:] if prefix else full_path
        parts = relative_path.split("/")

        if len(parts) == 1:
            blobs.append({
                "name": parts[0],
                "type": "file",
                "last_modified": blob.last_modified.isoformat() if blob.last_modified else None
            })
        elif len(parts) > 1:
            folders.add(parts[0])

    return [
        *[{"name": name, "type": "folder", "last_modified": None} for name in sorted(folders)],
        *blobs
    ]

async def list_adls_paths(container: str = "silver", prefix: str = ""):
    fs_client = get_adls_filesystem(container)
    result = []
    async for path in fs_client.get_paths(path=prefix or "", recursive=False):
        relative = path.name[len(prefix):] if prefix and path.name.startswith(prefix) else path.name
        relative = relative.strip("/")
        if "/" in relative:
            continue
        result.append({
            "name": relative,
            "type": "folder" if path.is_directory else "file",
            "last_modified": path.last_modified.isoformat() if path.last_modified else None
        })
    return result

# ==== CREATE FOLDER ====

async def create_folder(path: str, container: str = "bronze"):
    clean_path = path.rstrip("/")
    if is_adls_container(container):
        fs = get_adls_filesystem(container)
        await fs.create_directory(clean_path)
    else:
        container_client = get_blob_container_client(container)
        dummy_blob_name = f"{clean_path}/.folder-placeholder"
        blob_client = container_client.get_blob_client(dummy_blob_name)
        await blob_client.upload_blob(b"", overwrite=True)

# ==== DELETE ====

async def delete_blob(path: str, container: str = "bronze"):
    container_client = get_blob_container_client(container)
    blob_client = container_client.get_blob_client(path)
    await blob_client.delete_blob()

async def delete_folder(prefix: str, container: str = "bronze"):
    if is_adls_container(container):
        fs_client = get_adls_filesystem(container)
        if not prefix.endswith("/"):
            prefix += "/"
        to_delete = []
        async for path in fs_client.get_paths(path=prefix, recursive=True):
            to_delete.append(path.name)
        for p in sorted(to_delete, reverse=True):
            try:
                await fs_client.get_file_client(p).delete_file()
            except Exception as e:
                print(f"⚠️ Errore eliminando {p}: {e}")
        try:
            await fs_client.get_directory_client(prefix.rstrip("/")).delete_directory()
        except Exception as e:
            print(f"⚠️ Impossibile eliminare directory {prefix}: {e}")
    else:
        container_client = get_blob_container_client(container)
        async for blob in container_client.list_blobs(name_starts_with=prefix):
            blob_client = container_client.get_blob_client(blob.name)
            await blob_client.delete_blob()

# ==== RENAME ====

async def rename_blob(old_path: str, new_path: str, container: str = "bronze"):
    container_client = get_blob_container_client(container)
    old_blob = container_client.get_blob_client(old_path)
    new_blob = container_client.get_blob_client(new_path)
    await new_blob.start_copy_from_url(old_blob.url)
    await old_blob.delete_blob()

async def rename_folder(old_prefix: str, new_prefix: str, container: str = "bronze"):
    if is_adls_container(container):
        fs_client = get_adls_filesystem(container)
        if not old_prefix.endswith("/"):
            old_prefix += "/"
        if not new_prefix.endswith("/"):
            new_prefix += "/"
        try:
            await fs_client.create_directory(new_prefix)
        except Exception:
            pass
        paths = []
        async for path in fs_client.get_paths(path=old_prefix, recursive=True):
            paths.append(path.name)
        for src_path in sorted(paths, reverse=True):
            relative = src_path[len(old_prefix):].lstrip("/")
            dest_path = f"{new_prefix}{relative}".replace("//", "/")
            file_client = fs_client.get_file_client(src_path)
            try:
                await file_client.rename_file(f"{fs_client.file_system_name}/{dest_path}")
            except Exception as e:
                print(f"❌ Errore rename {src_path} → {dest_path}: {e}")
                raise HTTPException(status_code=500, detail=f"Errore rename {src_path}: {str(e)}")
        try:
            await fs_client.get_directory_client(old_prefix.rstrip("/")).delete_directory()
        except Exception as e:
            print(f"⚠️ Impossibile eliminare directory {old_prefix}: {e}")
    else:
        container_client = get_blob_container_client(container)
        async for blob in container_client.list_blobs(name_starts_with=old_prefix):
            old_blob = container_client.get_blob_client(blob.name)
            new_name = blob.name.replace(old_prefix, new_prefix, 1)
            new_blob = container_client.get_blob_client(new_name)
            await new_blob.start_copy_from_url(old_blob.url)
            await old_blob.delete_blob()


def get_adls_filesystem(container_key: str = "silver"):
    key_upper = container_key.upper()
    conn_str = os.getenv(f"AZURE_{key_upper}_CONNECTION_STRING")
    container_name = os.getenv(f"AZURE_{key_upper}_CONTAINER_NAME")

    if not conn_str or not container_name:
        raise HTTPException(status_code=500, detail="Connessione ADLS mancante")

    client = DataLakeServiceClient.from_connection_string(conn_str)
    return client.get_file_system_client(container_name)

async def rename_folder_adls(old_prefix: str, new_prefix: str, container: str = "silver"):
    fs_client = get_adls_filesystem(container)

    if not old_prefix.endswith("/"):
        old_prefix += "/"
    if not new_prefix.endswith("/"):
        new_prefix += "/"

    try:
        await fs_client.create_directory(new_prefix)
    except Exception:
        pass

    paths = []
    async for path in fs_client.get_paths(path=old_prefix, recursive=True):
        paths.append(path.name)

    for src_path in sorted(paths, reverse=True):
        relative = src_path[len(old_prefix):].lstrip("/")
        dest_path = f"{new_prefix}{relative}"
        dest_path = dest_path.replace("//", "/")
        file_client = fs_client.get_file_client(src_path)
        try:
            await file_client.rename_file(f"{fs_client.file_system_name}/{dest_path}")
        except Exception as e:
            print(f"❌ Errore rename {src_path} → {dest_path}: {e}")
            raise HTTPException(status_code=500, detail=f"Errore rename {src_path}: {str(e)}")
    
    # Elimina la cartella vecchia se vuota
    try:
        await fs_client.get_directory_client(old_prefix.rstrip("/")).delete_directory()
    except Exception as e:
        print(f"⚠️ Impossibile eliminare directory {old_prefix}: {e}")

async def delete_folder_adls(prefix: str, container: str = "silver"):
    fs_client = get_adls_filesystem(container)

    if not prefix.endswith("/"):
        prefix += "/"

    to_delete = []
    async for path in fs_client.get_paths(path=prefix, recursive=True):
        to_delete.append(path.name)

    # Elimina prima i file
    for p in sorted(to_delete, reverse=True):
        try:
            await fs_client.get_file_client(p).delete_file()
        except Exception as e:
            print(f"⚠️ Errore eliminando {p}: {e}")

    # Poi elimina la directory principale
    try:
        await fs_client.get_directory_client(prefix.rstrip("/")).delete_directory()
    except Exception as e:
        print(f"⚠️ Impossibile eliminare directory {prefix}: {e}")