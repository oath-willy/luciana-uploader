import os
import urllib.parse
from datetime import datetime
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


class CountriesCurrenciesSearchRequest(TableSearchRequest):
    year: int
    month: int


class CountriesCurrencyItem(BaseModel):
    id: int | None = None
    year: int
    month: int
    id_country: int
    id_currency: int


class CountriesCurrencyUpdateRequest(BaseModel):
    items: list[CountriesCurrencyItem]


class CountriesCurrencyCreateRequest(BaseModel):
    item: CountriesCurrencyItem


class CountriesCurrencyDeleteRequest(BaseModel):
    ids: list[int]


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

COUNTRIES_CURRENCIES_FIELDS = [
    "id",
    "id_time",
    "year",
    "month",
    "id_country",
    "country_name",
    "id_currency",
    "currency_code",
    "currency_name",
    "uic_code",
]


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


def _table_columns(db, table_name: str) -> set[str]:
    rows = db.execute(
        text(
            """
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = 'dbo'
                AND TABLE_NAME = :table_name
            """
        ),
        {"table_name": table_name},
    ).fetchall()
    return {row.COLUMN_NAME for row in rows}


def _preferred_column(columns: set[str], preferred: str, fallback: str = "id") -> str:
    if preferred in columns:
        return preferred
    if fallback in columns:
        return fallback
    raise HTTPException(
        status_code=500,
        detail=f"Colonna richiesta non trovata: {preferred}",
    )


def _countries_currencies_columns(db) -> tuple[str, str, str, str]:
    cc_id_col = _preferred_column(
        _table_columns(db, "countries_currencies"),
        "id_country_currency",
    )
    time_id_col = _preferred_column(_table_columns(db, "times"), "id_time")
    country_id_col = _preferred_column(_table_columns(db, "countries"), "id_country")
    currency_id_col = _preferred_column(_table_columns(db, "currencies"), "id_currency")
    return cc_id_col, time_id_col, country_id_col, currency_id_col


def _countries_currencies_base_query(db) -> str:
    cc_id_col, time_id_col, country_id_col, currency_id_col = _countries_currencies_columns(db)
    return f"""
        SELECT
            cc.[{cc_id_col}] AS id,
            cc.id_time,
            t.[year],
            t.[month],
            cc.id_country,
            c.country_name,
            cc.id_currency,
            cur.currency_code,
            cur.currency_name,
            cur.uic_code
        FROM dbo.countries_currencies AS cc
        JOIN dbo.times AS t
            ON t.[{time_id_col}] = cc.id_time
        LEFT JOIN dbo.countries AS c
            ON c.[{country_id_col}] = cc.id_country
        LEFT JOIN dbo.currencies AS cur
            ON cur.[{currency_id_col}] = cc.id_currency
    """


def _validate_year_month(year: int, month: int):
    current_year = datetime.now().year
    if year < 2015 or year > current_year:
        raise HTTPException(
            status_code=400,
            detail=f"Anno non valido: usa un valore tra 2015 e {current_year}",
        )
    if month < 1 or month > 12:
        raise HTTPException(status_code=400, detail="Mese non valido")


def _get_time_id(db, year: int, month: int) -> int:
    _validate_year_month(year, month)
    _, time_id_col, _, _ = _countries_currencies_columns(db)
    row = db.execute(
        text(
            f"""
            SELECT TOP 1 [{time_id_col}] AS id_time
            FROM dbo.times
            WHERE [year] = :year
                AND [month] = :month
            ORDER BY [{time_id_col}]
            """
        ),
        {"year": year, "month": month},
    ).fetchone()

    if not row:
        raise HTTPException(
            status_code=400,
            detail=f"Nessun id_time trovato per {year}-{month:02d}",
        )

    return int(row.id_time)


def _validate_countries_currency_item(item: CountriesCurrencyItem):
    _validate_year_month(item.year, item.month)
    if item.id_country <= 0:
        raise HTTPException(status_code=400, detail="id_country non valido")
    if item.id_currency <= 0:
        raise HTTPException(status_code=400, detail="id_currency non valido")


def _ensure_unique_country_currency(
    db,
    id_time: int,
    id_country: int,
    id_currency: int,
    exclude_id: int | None = None,
):
    cc_id_col, _, _, _ = _countries_currencies_columns(db)
    row = db.execute(
        text(
            f"""
            SELECT TOP 1 [{cc_id_col}] AS id
            FROM dbo.countries_currencies
            WHERE id_time = :id_time
                AND id_country = :id_country
                AND id_currency = :id_currency
                AND (:exclude_id IS NULL OR [{cc_id_col}] <> :exclude_id)
            """
        ),
        {
            "id_time": id_time,
            "id_country": id_country,
            "id_currency": id_currency,
            "exclude_id": exclude_id,
        },
    ).fetchone()

    if row:
        raise HTTPException(
            status_code=409,
            detail=(
                "Associazione country/currency gia presente "
                "per lo stesso periodo"
            ),
        )


def _assert_no_duplicate_payload(items: list[CountriesCurrencyItem]):
    seen: set[tuple[int, int, int]] = set()
    for item in items:
        key = (item.year, item.month, item.id_country, item.id_currency)
        if key in seen:
            raise HTTPException(
                status_code=400,
                detail="Il payload contiene associazioni duplicate nello stesso periodo",
            )
        seen.add(key)


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


@router.post("/database/countries-currencies/search")
def search_countries_currencies(request: CountriesCurrenciesSearchRequest):
    if request.page < 0:
        raise HTTPException(status_code=400, detail="page non puo essere negativa")
    if request.page_size not in PAGE_SIZE_OPTIONS:
        raise HTTPException(
            status_code=400,
            detail="page_size deve essere uno tra 25, 50, 100, 500",
        )

    _validate_year_month(request.year, request.month)

    db = DatabaseSessionLocal()
    try:
        base_query = _countries_currencies_base_query(db)
        filter_clause, params = _build_filter_clause(
            request,
            COUNTRIES_CURRENCIES_FIELDS,
            {"year": request.year, "month": request.month},
        )
        period_condition = "[year] = :year AND [month] = :month"
        if filter_clause:
            filter_clause = "WHERE " + period_condition + " AND " + filter_clause[6:]
        else:
            filter_clause = "WHERE " + period_condition

        query_params = {
            **params,
            "offset": request.page * request.page_size,
            "page_size": request.page_size,
        }
        total = db.execute(_count_query(base_query, filter_clause), params).scalar() or 0
        rows = db.execute(
            _rows_query(base_query, filter_clause, "[country_name], [currency_code], [id]"),
            query_params,
        ).fetchall()
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


@router.get("/database/countries-currencies/countries")
def search_countries_for_currencies(q: str = "", limit: int = 50):
    safe_limit = min(max(limit, 1), 100)
    db = DatabaseSessionLocal()
    try:
        _, _, country_id_col, _ = _countries_currencies_columns(db)
        rows = db.execute(
            text(
                f"""
                SELECT TOP ({safe_limit})
                    [{country_id_col}] AS id_country,
                    country_name
                FROM dbo.countries
                WHERE
                    :q = ''
                    OR COALESCE(CONVERT(NVARCHAR(4000), country_name), '') LIKE :q_like
                    OR COALESCE(CONVERT(NVARCHAR(4000), [{country_id_col}]), '') LIKE :q_like
                ORDER BY country_name
                """
            ),
            {"q": q.strip(), "q_like": f"%{q.strip()}%"},
        ).fetchall()
        return jsonable_encoder([dict(row._mapping) for row in rows])
    finally:
        db.close()


@router.get("/database/countries-currencies/currencies")
def search_currencies_for_countries(q: str = "", limit: int = 50):
    safe_limit = min(max(limit, 1), 100)
    db = DatabaseSessionLocal()
    try:
        _, _, _, currency_id_col = _countries_currencies_columns(db)
        rows = db.execute(
            text(
                f"""
                SELECT TOP ({safe_limit})
                    [{currency_id_col}] AS id_currency,
                    currency_code,
                    currency_name,
                    uic_code
                FROM dbo.currencies
                WHERE
                    :q = ''
                    OR COALESCE(CONVERT(NVARCHAR(4000), currency_code), '') LIKE :q_like
                    OR COALESCE(CONVERT(NVARCHAR(4000), currency_name), '') LIKE :q_like
                    OR COALESCE(CONVERT(NVARCHAR(4000), uic_code), '') LIKE :q_like
                    OR COALESCE(CONVERT(NVARCHAR(4000), [{currency_id_col}]), '') LIKE :q_like
                ORDER BY currency_code, currency_name
                """
            ),
            {"q": q.strip(), "q_like": f"%{q.strip()}%"},
        ).fetchall()
        return jsonable_encoder([dict(row._mapping) for row in rows])
    finally:
        db.close()


@router.post("/database/countries-currencies/create")
def create_countries_currency(request: CountriesCurrencyCreateRequest):
    item = request.item
    _validate_countries_currency_item(item)

    db = DatabaseSessionLocal()
    try:
        with db.begin():
            cc_id_col, _, _, _ = _countries_currencies_columns(db)
            id_time = _get_time_id(db, item.year, item.month)
            _ensure_unique_country_currency(
                db,
                id_time,
                item.id_country,
                item.id_currency,
            )
            result = db.execute(
                text(
                    f"""
                    INSERT INTO dbo.countries_currencies (
                        id_time,
                        id_country,
                        id_currency
                    )
                    OUTPUT INSERTED.[{cc_id_col}]
                    VALUES (
                        :id_time,
                        :id_country,
                        :id_currency
                    )
                    """
                ),
                {
                    "id_time": id_time,
                    "id_country": item.id_country,
                    "id_currency": item.id_currency,
                },
            )
            new_id = result.scalar()

        return jsonable_encoder({"created": 1, "id": new_id})
    finally:
        db.close()


@router.post("/database/countries-currencies/update")
def update_countries_currencies(request: CountriesCurrencyUpdateRequest):
    if not request.items:
        raise HTTPException(status_code=400, detail="Nessuna riga da aggiornare")
    _assert_no_duplicate_payload(request.items)

    db = DatabaseSessionLocal()
    try:
        with db.begin():
            cc_id_col, _, _, _ = _countries_currencies_columns(db)
            for item in request.items:
                if not item.id or item.id <= 0:
                    raise HTTPException(status_code=400, detail="id non valido")
                _validate_countries_currency_item(item)
                id_time = _get_time_id(db, item.year, item.month)
                _ensure_unique_country_currency(
                    db,
                    id_time,
                    item.id_country,
                    item.id_currency,
                    item.id,
                )
                result = db.execute(
                    text(
                        f"""
                        UPDATE dbo.countries_currencies
                        SET
                            id_time = :id_time,
                            id_country = :id_country,
                            id_currency = :id_currency
                        WHERE [{cc_id_col}] = :id
                        """
                    ),
                    {
                        "id": item.id,
                        "id_time": id_time,
                        "id_country": item.id_country,
                        "id_currency": item.id_currency,
                    },
                )
                if result.rowcount == 0:
                    raise HTTPException(status_code=404, detail=f"Riga {item.id} non trovata")

        return jsonable_encoder({"updated": len(request.items)})
    finally:
        db.close()


@router.post("/database/countries-currencies/delete")
def delete_countries_currencies(request: CountriesCurrencyDeleteRequest):
    ids = sorted({int(row_id) for row_id in request.ids if int(row_id) > 0})
    if not ids:
        raise HTTPException(status_code=400, detail="Seleziona almeno una riga")

    params = {f"id_{index}": row_id for index, row_id in enumerate(ids)}
    placeholders = ", ".join(f":{key}" for key in params)

    db = DatabaseSessionLocal()
    try:
        with db.begin():
            cc_id_col, _, _, _ = _countries_currencies_columns(db)
            result = db.execute(
                text(
                    f"""
                    DELETE FROM dbo.countries_currencies
                    WHERE [{cc_id_col}] IN ({placeholders})
                    """
                ),
                params,
            )

        return jsonable_encoder({"deleted": result.rowcount})
    finally:
        db.close()


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
