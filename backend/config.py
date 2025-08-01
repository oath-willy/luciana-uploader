import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    AZURE_STORAGE_CONNECTION_STRING: str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    AZURE_CONTAINER_NAME: str = os.getenv("AZURE_CONTAINER_NAME", "bronze")

settings = Settings()
