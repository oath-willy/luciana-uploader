import os
import urllib.parse
from typing import Any, Dict, Literal, Tuple

from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


router = APIRouter()

DictionaryStatus = Literal["all", "validated", "non_validated", "id_country_null"]

PAGE_SIZE_OPTIONS = {25, 50, 100, 500}
DEFAULT_PAGE_SIZE = 100
DICTIONARY_DATABASE = os.getenv("SQL_DICTIONARY_DATABASE", "luciana_db")

FILTER_FIELDS = {
    "ID",
    "COUNTRY RAW",
    "COUNTRY ISO",
    "USER NAME",
    "VALIDATED",
}


class CountriesDictionarySearchRequest(BaseModel):
    page: int = 0
    page_size: int = DEFAULT_PAGE_SIZE
    status: DictionaryStatus = "all"
    search: str = ""
    filters: Dict[str, Any] = Field(default_factory=dict)


class CountriesDictionaryValidateItem(BaseModel):
    id_country_dictionary: int
    id_country: int


class CountriesDictionaryValidateRequest(BaseModel):
    items: list[CountriesDictionaryValidateItem]


def _engine():
    params = urllib.parse.quote_plus(
        f"Driver={{ODBC Driver 17 for SQL Server}};"
        f"Server=tcp:{os.getenv('SQL_SERVER')},1433;"
        f"Database={DICTIONARY_DATABASE};"
        f"Uid={os.getenv('SQL_USER')};"
        f"Pwd={os.getenv('SQL_PASSWORD')};"
        "Encrypt=yes;"
        "TrustServerCertificate=no;"
        "Connection Timeout=30;"
    )
    return create_engine(
        f"mssql+pyodbc:///?odbc_connect={params}",
        pool_pre_ping=True,
    )


DictionarySessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=_engine(),
)


BASE_QUERY = """
    SELECT
        cd.id_country_dictionary AS [ID],
        cd.country_raw AS [COUNTRY RAW],
        c.country_name AS [COUNTRY ISO],
        cd.user_name AS [USER NAME],
        cd.validated AS [VALIDATED],
        cd.id_country
    FROM dbo.countries_dictionary AS cd
    LEFT JOIN dbo.countries AS c
        ON cd.id_country = c.id_country
"""


def _filter_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _build_filter_clause(
    request: CountriesDictionarySearchRequest,
) -> Tuple[str, Dict[str, Any]]:
    conditions = []
    params: Dict[str, Any] = {}

    if request.status == "validated":
        conditions.append("[VALIDATED] = 1")
    elif request.status == "non_validated":
        conditions.append("([VALIDATED] = 0 OR [VALIDATED] IS NULL)")
    elif request.status == "id_country_null":
        conditions.append("[id_country] IS NULL")

    search = _filter_value(request.search)
    if search:
        conditions.append(
            "("
            "COALESCE(CONVERT(NVARCHAR(4000), [ID]), '') LIKE :search "
            "OR COALESCE(CONVERT(NVARCHAR(4000), [COUNTRY RAW]), '') LIKE :search "
            "OR COALESCE(CONVERT(NVARCHAR(4000), [COUNTRY ISO]), '') LIKE :search "
            "OR COALESCE(CONVERT(NVARCHAR(4000), [USER NAME]), '') LIKE :search "
            "OR COALESCE(CONVERT(NVARCHAR(4000), [VALIDATED]), '') LIKE :search"
            ")"
        )
        params["search"] = f"%{search}%"

    for field, raw_value in request.filters.items():
        if field not in FILTER_FIELDS:
            continue

        value = _filter_value(raw_value)
        if not value:
            continue

        param_name = f"filter_{field.replace(' ', '_').lower()}"
        conditions.append(
            f"COALESCE(CONVERT(NVARCHAR(4000), [{field}]), '') LIKE :{param_name}"
        )
        params[param_name] = f"%{value}%"

    if not conditions:
        return "", params

    return "WHERE " + " AND ".join(conditions), params


def _count_query(filter_clause: str):
    return text(
        f"""
        WITH dictionary_base AS (
            {BASE_QUERY}
        )
        SELECT COUNT(*) AS total
        FROM dictionary_base
        {filter_clause}
        """
    )


def _rows_query(filter_clause: str):
    return text(
        f"""
        WITH dictionary_base AS (
            {BASE_QUERY}
        )
        SELECT *
        FROM dictionary_base
        {filter_clause}
        ORDER BY [ID]
        OFFSET :offset ROWS FETCH NEXT :page_size ROWS ONLY
        """
    )


@router.post("/countries-dictionary/search")
def search_countries_dictionary(request: CountriesDictionarySearchRequest):
    if request.page < 0:
        raise HTTPException(status_code=400, detail="page non puo essere negativa")
    if request.page_size not in PAGE_SIZE_OPTIONS:
        raise HTTPException(
            status_code=400,
            detail="page_size deve essere uno tra 25, 50, 100, 500",
        )

    filter_clause, params = _build_filter_clause(request)
    query_params = {
        **params,
        "offset": request.page * request.page_size,
        "page_size": request.page_size,
    }

    db = DictionarySessionLocal()
    try:
        total = db.execute(_count_query(filter_clause), params).scalar() or 0
        rows = db.execute(_rows_query(filter_clause), query_params).fetchall()
        return jsonable_encoder(
            {
                "rows": [dict(row._mapping) for row in rows],
                "total": total,
                "page": request.page,
                "page_size": request.page_size,
            }
        )
    finally:
        db.close()


@router.get("/countries-dictionary/countries")
def get_countries(q: str = "", limit: int = 50):
    safe_limit = min(max(limit, 1), 100)
    query = text(
        f"""
        SELECT TOP ({safe_limit})
            id_country,
            country_name
        FROM dbo.countries
        WHERE
            :q = ''
            OR COALESCE(CONVERT(NVARCHAR(4000), country_name), '') LIKE :q_like
            OR COALESCE(CONVERT(NVARCHAR(4000), id_country), '') LIKE :q_like
        ORDER BY country_name
        """
    )

    db = DictionarySessionLocal()
    try:
        rows = db.execute(query, {"q": q.strip(), "q_like": f"%{q.strip()}%"}).fetchall()
        return jsonable_encoder([dict(row._mapping) for row in rows])
    finally:
        db.close()


@router.post("/countries-dictionary/validate")
def validate_countries_dictionary(request: CountriesDictionaryValidateRequest):
    if not request.items:
        raise HTTPException(status_code=400, detail="Seleziona almeno una riga")

    db = DictionarySessionLocal()
    try:
        with db.begin():
            for item in request.items:
                if item.id_country_dictionary <= 0 or item.id_country <= 0:
                    raise HTTPException(
                        status_code=400,
                        detail="ID dictionary o country non valido",
                    )

                db.execute(
                    text(
                        """
                        UPDATE dbo.countries_dictionary
                        SET
                            id_country = :id_country,
                            validated = 1
                        WHERE id_country_dictionary = :id_country_dictionary
                        """
                    ),
                    {
                        "id_country": item.id_country,
                        "id_country_dictionary": item.id_country_dictionary,
                    },
                )

        return jsonable_encoder({"updated": len(request.items)})
    finally:
        db.close()
