import os
import urllib

SQL_SERVER   = "lucianasqlserver01.database.windows.net"
SQL_DATABASE = "luciana_db"
SQL_USERNAME = "il_tuo_utente_sql"
SQL_PASSWORD = "la_tua_password_sql"

connection_string = (
    f"Driver={{ODBC Driver 18 for SQL Server}};"
    f"Server=tcp:{SQL_SERVER},1433;"
    f"Database={SQL_DATABASE};"
    f"Uid={SQL_USERNAME};"
    f"Pwd={SQL_PASSWORD};"
    f"Encrypt=yes;"
    f"TrustServerCertificate=no;"
    f"Connection Timeout=30;"
)

params = urllib.parse.quote_plus(connection_string)
SQLALCHEMY_DATABASE_URL = f"mssql+pyodbc:///?odbc_connect={params}


from dotenv import load_dotenv

load_dotenv()

class Settings:
    AZURE_STORAGE_CONNECTION_STRING: str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    AZURE_CONTAINER_NAME: str = os.getenv("AZURE_CONTAINER_NAME", "bronze")

settings = Settings()