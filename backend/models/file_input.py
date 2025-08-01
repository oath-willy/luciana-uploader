from pydantic import BaseModel

class FileMetadata(BaseModel):
    filename: str
    uploader: str
    upload_time: str
