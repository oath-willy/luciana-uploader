import os
import urllib.parse
from typing import Any, Dict, Literal, Tuple

from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


router = APIRouter()

PAGE_SIZE_OPTIONS = {25, 50, 100, 500}
DEFAULT_PAGE_SIZE = 50
DATABASE_NAME = os.getenv("SQL_DICTIONARY_DATABASE", "luciana_db")


class TableSearchRequest(BaseModel):
    page: int = 0
    page_size: int = DEFAULT_PAGE_SIZE
    search: str = ""
    filters: Dict[str, Any] = Field(default_factory=dict)


class CompanyUpdateItem(BaseModel):
    id_company: int
    company: str
    manufacturer: bool = False
    dealer: bool = False


class CompanyUpdateRequest(BaseModel):
    items: list[CompanyUpdateItem]


TableKey = Literal["companies", "countries", "currencies", "father-names"]


TABLE_CONFIGS = {
    "companies": {
        "base": """
            SELECT
                c.id_company,
                c.company,
                c.manufacturer,
                c.dealer
            FROM dbo.companies AS c
        """,
        "fields": ["id_company", "company", "manufacturer", "dealer"],
        "order": "[company], [id_company]",
    },
    "countries": {
        "base": """
            SELECT
                c.id_country,
                c.country_name
            FROM dbo.countries AS c
        """,
        "fields": ["id_country", "country_name"],
        "order": "[country_name], [id_country]",
    },
    "currencies": {
        "base": """
            SELECT
                c.id_currency,
                c.currency_code,
                c.currency_name,
                c.uic_code
            FROM dbo.currencies AS c
        """,
        "fields": ["id_currency", "currency_code", "currency_name", "uic_code"],
        "order": "[currency_code], [id_currency]",
    },
    "father-names": {
        "base": """
            SELECT
                fn.id_father_name,
                fn.father_name,
                COUNT(p.id_product) AS product_count
            FROM dbo.products_father_names AS fn
            LEFT JOIN dbo.products AS p
                ON p.id_father_name = fn.id_father_name
            GROUP BY
                fn.id_father_name,
                fn.father_name
        """,
        "fields": ["id_father_name", "father_name", "product_count"],
        "order": "[father_name], [id_father_name]",
    },
}

FATHER_PRODUCTS_FIELDS = [
    "id_product",
    "company_item_code",
    "item_description",
    "id_company_dealer",
    "id_prefix_encoding",
    "id_prefix_code",
    "id_father_name",
    "id_packaging",
    "id_packaging_quantity",
    "id_packaging_unit",
    "id_feature",
    "id_measure",
    "id_user",
    "creation_date",
]

FATHER_PRODUCTS_BASE = """
    SELECT
        p.id_product,
        p.company_item_code,
        p.item_description,
        p.id_company_dealer,
        p.id_prefix_encoding,
        p.id_prefix_code,
        p.id_father_name,
        p.id_packaging,
        p.id_packaging_quantity,
        p.id_packaging_unit,
        p.id_feature,
        p.id_measure,
        p.id_user,
        p.creation_date
    FROM dbo.products AS p
    WHERE p.id_father_name = :id_father_name
"""


def _engine():
    params = urllib.parse.quote_plus(
        f"Driver={{ODBC Driver 17 for SQL Server}};"
        f"Server=tcp:{os.getenv('SQL_SERVER')},1433;"
        f"Database={DATABASE_NAME};"
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


DatabaseSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=_engine(),
)


def _filter_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _build_filter_clause(
    request: TableSearchRequest,
    fields: list[str],
    base_params: Dict[str, Any] | None = None,
) -> Tuple[str, Dict[str, Any]]:
    params: Dict[str, Any] = dict(base_params or {})
    conditions = []

    search = _filter_value(request.search)
    if search:
        search_conditions = [
            f"COALESCE(CONVERT(NVARCHAR(4000), [{field}]), '') LIKE :search"
            for field in fields
        ]
        conditions.append("(" + " OR ".join(search_conditions) + ")")
        params["search"] = f"%{search}%"

    for field, raw_value in request.filters.items():
        if field not in fields:
            continue

        value = _filter_value(raw_value)
        if not value:
            continue

        param_name = f"filter_{field}"
        conditions.append(
            f"COALESCE(CONVERT(NVARCHAR(4000), [{field}]), '') LIKE :{param_name}"
        )
        params[param_name] = f"%{value}%"

    if not conditions:
        return "", params

    return "WHERE " + " AND ".join(conditions), params


def _count_query(base_query: str, filter_clause: str):
    return text(
        f"""
        WITH table_base AS (
            {base_query}
        )
        SELECT COUNT(*) AS total
        FROM table_base
        {filter_clause}
        """
    )


def _rows_query(base_query: str, filter_clause: str, order_by: str):
    return text(
        f"""
        WITH table_base AS (
            {base_query}
        )
        SELECT *
        FROM table_base
        {filter_clause}
        ORDER BY {order_by}
        OFFSET :offset ROWS FETCH NEXT :page_size ROWS ONLY
        """
    )


def _search(base_query: str, fields: list[str], order_by: str, request: TableSearchRequest, base_params=None):
    if request.page < 0:
        raise HTTPException(status_code=400, detail="page non puo essere negativa")
    if request.page_size not in PAGE_SIZE_OPTIONS:
        raise HTTPException(
            status_code=400,
            detail="page_size deve essere uno tra 25, 50, 100, 500",
        )

    filter_clause, params = _build_filter_clause(request, fields, base_params)
    query_params = {
        **params,
        "offset": request.page * request.page_size,
        "page_size": request.page_size,
    }

    db = DatabaseSessionLocal()
    try:
        total = db.execute(_count_query(base_query, filter_clause), params).scalar() or 0
        rows = db.execute(_rows_query(base_query, filter_clause, order_by), query_params).fetchall()
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


@router.post("/database/{table_key}/search")
def search_database_table(table_key: TableKey, request: TableSearchRequest):
    config = TABLE_CONFIGS[table_key]
    return _search(config["base"], config["fields"], config["order"], request)


@router.post("/database/father-names/{id_father_name}/products/search")
def search_father_name_products(id_father_name: int, request: TableSearchRequest):
    if id_father_name <= 0:
        raise HTTPException(status_code=400, detail="id_father_name non valido")

    return _search(
        FATHER_PRODUCTS_BASE,
        FATHER_PRODUCTS_FIELDS,
        "[company_item_code], [id_product]",
        request,
        {"id_father_name": id_father_name},
    )


@router.post("/database/companies/update")
def update_companies(request: CompanyUpdateRequest):
    if not request.items:
        raise HTTPException(status_code=400, detail="Nessuna company da aggiornare")

    db = DatabaseSessionLocal()
    try:
        with db.begin():
            for item in request.items:
                if item.id_company <= 0:
                    raise HTTPException(status_code=400, detail="id_company non valido")
                company = item.company.strip()
                if not company:
                    raise HTTPException(status_code=400, detail="company non puo essere vuota")

                db.execute(
                    text(
                        """
                        UPDATE dbo.companies
                        SET
                            company = :company,
                            manufacturer = :manufacturer,
                            dealer = :dealer
                        WHERE id_company = :id_company
                        """
                    ),
                    {
                        "id_company": item.id_company,
                        "company": company,
                        "manufacturer": item.manufacturer,
                        "dealer": item.dealer,
                    },
                )

        return jsonable_encoder({"updated": len(request.items)})
    finally:
        db.close()
