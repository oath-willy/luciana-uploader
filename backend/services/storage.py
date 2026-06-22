import os
from urllib.parse import quote

from azure.storage.blob.aio import BlobServiceClient
from azure.storage.filedatalake.aio import DataLakeServiceClient
from fastapi import HTTPException, UploadFile


DEFAULT_STORAGE_TYPES = {
    "bronze": "adls",
    "silver": "adls",
    "gold": "adls",
}


def normalize_container_key(container_key: str = "bronze") -> str:
    key = (container_key or "bronze").strip().lower()
    if not key:
        raise HTTPException(status_code=400, detail="Container non valido")
    return key


def normalize_path(path: str = "") -> str:
    return (path or "").strip().strip("/")


def get_storage_type(container_key: str = "bronze") -> str:
    key = normalize_container_key(container_key)
    configured_type = os.getenv(f"AZURE_{key.upper()}_STORAGE_TYPE")
    storage_type = (configured_type or DEFAULT_STORAGE_TYPES.get(key, "blob")).strip().lower()
    if storage_type not in {"blob", "adls"}:
        raise HTTPException(
            status_code=500,
            detail=f"Tipo storage non valido per {key}: {storage_type}",
        )
    return storage_type


def is_adls_container(container_key: str) -> bool:
    return get_storage_type(container_key) == "adls"


def get_storage_settings(container_key: str):
    key = normalize_container_key(container_key)
    key_upper = key.upper()
    conn_str = os.getenv(f"AZURE_{key_upper}_CONNECTION_STRING")
    container_name = os.getenv(f"AZURE_{key_upper}_CONTAINER_NAME")

    if not conn_str or not container_name:
        raise HTTPException(
            status_code=500,
            detail=f"Variabili mancanti per il container {key}",
        )

    return conn_str, container_name


def get_blob_container_client(container_key: str = "bronze"):
    conn_str, container_name = get_storage_settings(container_key)
    client = BlobServiceClient.from_connection_string(conn_str)
    return client.get_container_client(container_name)


def get_adls_filesystem(container_key: str = "silver"):
    conn_str, container_name = get_storage_settings(container_key)
    client = DataLakeServiceClient.from_connection_string(conn_str)
    return client.get_file_system_client(container_name)


def build_full_path(path: str, filename: str) -> str:
    clean_path = normalize_path(path)
    clean_filename = (filename or "").strip().strip("/")
    if not clean_filename:
        raise HTTPException(status_code=400, detail="Nome file non valido")
    return f"{clean_path}/{clean_filename}" if clean_path else clean_filename


def as_download_headers(path: str):
    filename = normalize_path(path).split("/")[-1] or "download"
    return {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
    }


async def upload_file(file: UploadFile, path: str, container: str = "bronze"):
    full_path = build_full_path(path, file.filename)

    if is_adls_container(container):
        file_client = get_adls_filesystem(container).get_file_client(full_path)
        await file_client.upload_data(await file.read(), overwrite=True)
        return file_client.url

    blob_client = get_blob_container_client(container).get_blob_client(full_path)
    await blob_client.upload_blob(await file.read(), overwrite=True)
    return blob_client.url


async def list_paths(prefix: str = "", container: str = "bronze"):
    if is_adls_container(container):
        return await list_adls_paths(container=container, prefix=prefix)
    return await list_blob_paths(prefix=prefix, container=container)


async def list_blob_paths(prefix: str = "", container: str = "bronze"):
    container_client = get_blob_container_client(container)
    blobs = []
    folders = set()

    clean_prefix = normalize_path(prefix)
    blob_prefix = f"{clean_prefix}/" if clean_prefix else ""

    async for blob in container_client.list_blobs(name_starts_with=blob_prefix):
        relative_path = blob.name[len(blob_prefix) :]
        parts = relative_path.split("/")

        if len(parts) == 1:
            if parts[0] != ".folder-placeholder":
                blobs.append(
                    {
                        "name": parts[0],
                        "type": "file",
                        "last_modified": blob.last_modified.isoformat()
                        if blob.last_modified
                        else None,
                    }
                )
        elif len(parts) > 1 and parts[0]:
            folders.add(parts[0])

    return [
        *[
            {"name": name, "type": "folder", "last_modified": None}
            for name in sorted(folders)
        ],
        *blobs,
    ]


async def list_adls_paths(container: str = "silver", prefix: str = ""):
    fs_client = get_adls_filesystem(container)
    clean_prefix = normalize_path(prefix)
    result = []

    async for path in fs_client.get_paths(path=clean_prefix or None, recursive=False):
        path_name = normalize_path(path.name)
        if not path_name or path_name == clean_prefix:
            continue

        if clean_prefix:
            prefix_with_slash = f"{clean_prefix}/"
            if not path_name.startswith(prefix_with_slash):
                continue
            relative = path_name[len(prefix_with_slash) :]
        else:
            relative = path_name

        relative = relative.strip("/")
        if not relative or "/" in relative:
            continue

        result.append(
            {
                "name": relative,
                "type": "folder" if path.is_directory else "file",
                "last_modified": path.last_modified.isoformat()
                if path.last_modified
                else None,
            }
        )

    return sorted(result, key=lambda item: (item["type"] != "folder", item["name"].lower()))


async def create_folder(path: str, container: str = "bronze"):
    clean_path = normalize_path(path)
    if not clean_path:
        raise HTTPException(status_code=400, detail="Path cartella non valido")

    if is_adls_container(container):
        await get_adls_filesystem(container).create_directory(clean_path)
        return

    blob_client = get_blob_container_client(container).get_blob_client(
        f"{clean_path}/.folder-placeholder"
    )
    await blob_client.upload_blob(b"", overwrite=True)


async def delete_file(path: str, container: str = "bronze"):
    clean_path = normalize_path(path)
    if not clean_path:
        raise HTTPException(status_code=400, detail="Path file non valido")

    if is_adls_container(container):
        await get_adls_filesystem(container).get_file_client(clean_path).delete_file()
        return

    await get_blob_container_client(container).get_blob_client(clean_path).delete_blob()


async def delete_folder(prefix: str, container: str = "bronze"):
    clean_prefix = normalize_path(prefix)
    if not clean_prefix:
        raise HTTPException(status_code=400, detail="Path cartella non valido")

    if is_adls_container(container):
        fs_client = get_adls_filesystem(container)
        paths_to_delete = []

        async for path in fs_client.get_paths(path=clean_prefix, recursive=True):
            path_name = normalize_path(path.name)
            if path_name != clean_prefix:
                paths_to_delete.append((path_name, path.is_directory))

        for path_name, is_directory in sorted(paths_to_delete, reverse=True):
            try:
                if is_directory:
                    await fs_client.get_directory_client(path_name).delete_directory()
                else:
                    await fs_client.get_file_client(path_name).delete_file()
            except Exception as exc:
                print(f"Errore eliminando {path_name}: {exc}")

        await fs_client.get_directory_client(clean_prefix).delete_directory()
        return

    container_client = get_blob_container_client(container)
    blob_prefix = f"{clean_prefix}/"
    async for blob in container_client.list_blobs(name_starts_with=blob_prefix):
        await container_client.get_blob_client(blob.name).delete_blob()


async def rename_file(old_path: str, new_path: str, container: str = "bronze"):
    clean_old_path = normalize_path(old_path)
    clean_new_path = normalize_path(new_path)
    if not clean_old_path or not clean_new_path:
        raise HTTPException(status_code=400, detail="Path non valido")

    if is_adls_container(container):
        fs_client = get_adls_filesystem(container)
        target = fs_client.get_file_client(clean_new_path)
        if await target.exists():
            raise HTTPException(status_code=400, detail="Esiste gia un file con questo nome.")

        file_client = fs_client.get_file_client(clean_old_path)
        await file_client.rename_file(f"{fs_client.file_system_name}/{clean_new_path}")
        return

    container_client = get_blob_container_client(container)
    new_blob = container_client.get_blob_client(clean_new_path)
    if await new_blob.exists():
        raise HTTPException(status_code=400, detail="Esiste gia un file con questo nome.")

    old_blob = container_client.get_blob_client(clean_old_path)
    await new_blob.start_copy_from_url(old_blob.url)
    await old_blob.delete_blob()


async def rename_folder(old_prefix: str, new_prefix: str, container: str = "bronze"):
    clean_old_prefix = normalize_path(old_prefix)
    clean_new_prefix = normalize_path(new_prefix)
    if not clean_old_prefix or not clean_new_prefix:
        raise HTTPException(status_code=400, detail="Path cartella non valido")

    if is_adls_container(container):
        fs_client = get_adls_filesystem(container)
        target = fs_client.get_directory_client(clean_new_prefix)
        if await target.exists():
            raise HTTPException(status_code=400, detail="Esiste gia una cartella con questo nome.")

        directory_client = fs_client.get_directory_client(clean_old_prefix)
        await directory_client.rename_directory(
            f"{fs_client.file_system_name}/{clean_new_prefix}"
        )
        return

    container_client = get_blob_container_client(container)
    old_blob_prefix = f"{clean_old_prefix}/"
    new_blob_prefix = f"{clean_new_prefix}/"

    async for blob in container_client.list_blobs(name_starts_with=new_blob_prefix):
        if blob.name:
            raise HTTPException(status_code=400, detail="Esiste gia una cartella con questo nome.")

    async for blob in container_client.list_blobs(name_starts_with=old_blob_prefix):
        new_name = blob.name.replace(old_blob_prefix, new_blob_prefix, 1)
        old_blob = container_client.get_blob_client(blob.name)
        new_blob = container_client.get_blob_client(new_name)
        await new_blob.start_copy_from_url(old_blob.url)
        await old_blob.delete_blob()


async def download_file(path: str, container: str = "bronze"):
    clean_path = normalize_path(path)
    if not clean_path:
        raise HTTPException(status_code=400, detail="Path file non valido")

    if is_adls_container(container):
        downloader = await get_adls_filesystem(container).get_file_client(clean_path).download_file()
        return await downloader.readall()

    downloader = await get_blob_container_client(container).get_blob_client(clean_path).download_blob()
    return await downloader.readall()


# Backward-compatible names used by older routes/components.
upload_to_blob = upload_file
list_blobs_in_container = list_blob_paths
delete_blob = delete_file
rename_blob = rename_file
rename_folder_adls = rename_folder
delete_folder_adls = delete_folder
