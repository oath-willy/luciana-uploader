from typing import Any, Dict, Literal, Tuple

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.db import get_db


router = APIRouter()

CompanyRole = Literal["dealer", "manufacturer", "any"]

PAGE_SIZE_OPTIONS = {25, 50, 100, 250, 500, 1000}
DEFAULT_PAGE_SIZE = 100

PRODUCT_FIELDS = {
    "id_prod_version",
    "id_prod",
    "company_item_code",
    "version",
    "is_current",
    "valid_from",
    "valid_to",
    "prod_version_data_creation",
    "description",
    "prod_version_notes",
    "id_dealer",
    "dealer_company_name",
    "dealer_company_code",
    "id_manufacturer",
    "manufacturer_company_name",
    "manufacturer_company_code",
    "id_prefix_encoding",
    "prefix_encoding",
    "id_prefix_code",
    "prefix_code",
    "id_father_name",
    "father_name",
    "id_mc",
    "id_mc_lvl1",
    "mc_lvl1_code",
    "mc_lvl1_desc",
    "mc_lvl1_status_code",
    "id_mc_lvl2",
    "mc_lvl2_code",
    "mc_lvl2_desc",
    "mc_lvl2_status_code",
    "id_mc_lvl3",
    "mc_lvl3_code",
    "mc_lvl3_desc",
    "mc_lvl3_status_code",
    "id_pack",
    "pack",
    "id_pack_qty",
    "pack_qty_raw",
    "inner_count",
    "inner_qty",
    "is_composite_pack",
    "id_pack_measure_unit",
    "pack_measure_unit",
    "pack_qty_notes",
    "id_feature",
    "feature",
    "id_measure",
    "measure",
    "id_split",
    "id_parent_prod",
    "parent_company_item_code",
    "split_percentage",
    "id_user",
    "user_nome",
    "user_cognome",
}


class ProductSearchRequest(BaseModel):
    id_company: int
    company_role: CompanyRole = "any"
    page: int = 0
    page_size: int = DEFAULT_PAGE_SIZE
    full: bool = False
    search: str = ""
    filters: Dict[str, Any] = Field(default_factory=dict)


PRODUCT_LOOKUP_QUERIES = {
    "companies": """
        SELECT id, company_name AS label, company_code AS code
        FROM dbo.companies
        ORDER BY company_name
    """,
    "prefix_encodings": """
        SELECT id, prefix_encoding AS label
        FROM dbo.prods_prefix_encodings
        ORDER BY prefix_encoding
    """,
    "prefix_codes": """
        SELECT id, prefix_code AS label
        FROM dbo.prods_prefix_codes
        ORDER BY prefix_code
    """,
    "father_names": """
        SELECT id, father_name AS label
        FROM dbo.prods_father_names
        ORDER BY father_name
    """,
    "master_codes": """
        SELECT
            mc.id,
            CONCAT(
                COALESCE(mc1.code, ''),
                CASE WHEN mc2.code IS NULL THEN '' ELSE CONCAT(' / ', mc2.code) END,
                CASE WHEN mc3.code IS NULL THEN '' ELSE CONCAT(' / ', mc3.code) END
            ) AS label
        FROM dbo.master_code AS mc
        LEFT JOIN dbo.mc_lvl1 AS mc1 ON mc1.id = mc.id_mc_lvl1
        LEFT JOIN dbo.mc_lvl2 AS mc2 ON mc2.id = mc.id_mc_lvl2
        LEFT JOIN dbo.mc_lvl3 AS mc3 ON mc3.id = mc.id_mc_lvl3
        ORDER BY label
    """,
    "packs": """
        SELECT id, pack AS label
        FROM dbo.prods_pack
        ORDER BY pack
    """,
    "pack_measure_units": """
        SELECT id, measure_unit AS label
        FROM dbo.prods_pack_measure_units
        ORDER BY measure_unit
    """,
    "features": """
        SELECT id, feature AS label
        FROM dbo.prods_features
        ORDER BY feature
    """,
    "measures": """
        SELECT id, measure AS label
        FROM dbo.prods_measures
        ORDER BY measure
    """,
    "products": """
        SELECT TOP (5000) id, company_item_code AS label
        FROM dbo.prods
        ORDER BY company_item_code
    """,
    "users": """
        SELECT id, CONCAT(COALESCE(nome, ''), ' ', COALESCE(cognome, '')) AS label
        FROM dbo.users
        ORDER BY label
    """,
}


PRODUCTS_BASE_QUERY = """
    SELECT
        pv.id AS id_prod_version,
        pv.id_prod,
        p.company_item_code,

        pv.[version],
        pv.is_current,
        pv.valid_from,
        pv.valid_to,
        pv.data_creation AS prod_version_data_creation,

        pv.description,
        pv.notes AS prod_version_notes,

        pv.id_dealer,
        dealer.company_name AS dealer_company_name,
        dealer.company_code AS dealer_company_code,

        pv.id_manufacturer,
        manufacturer.company_name AS manufacturer_company_name,
        manufacturer.company_code AS manufacturer_company_code,

        pv.id_prefix_encoding,
        pe.prefix_encoding,

        pv.id_prefix_code,
        pc.prefix_code,

        pv.id_father_name,
        fn.father_name,

        pv.id_mc,
        mc.id_mc_lvl1,
        mc1.code AS mc_lvl1_code,
        mc1.[desc] AS mc_lvl1_desc,
        mc1_status.code AS mc_lvl1_status_code,

        mc.id_mc_lvl2,
        mc2.code AS mc_lvl2_code,
        mc2.[desc] AS mc_lvl2_desc,
        mc2_status.code AS mc_lvl2_status_code,

        mc.id_mc_lvl3,
        mc3.code AS mc_lvl3_code,
        mc3.[desc] AS mc_lvl3_desc,
        mc3_status.code AS mc_lvl3_status_code,

        pv.id_pack,
        pack.pack,

        pq.id AS id_pack_qty,
        pq.raw AS pack_qty_raw,
        pq.inner_count,
        pq.inner_qty,
        pq.is_composite_pack,
        pq.id_pack_measure_unit,
        pmu.measure_unit AS pack_measure_unit,
        pq.notes AS pack_qty_notes,

        pv.id_feature,
        feat.feature,

        pv.id_measure,
        meas.measure,

        ps.id AS id_split,
        ps.id_parent_prod,
        parent_prod.company_item_code AS parent_company_item_code,
        ps.percentage AS split_percentage,

        pv.id_user,
        u.nome AS user_nome,
        u.cognome AS user_cognome

    FROM dbo.prods_versions AS pv
    JOIN dbo.prods AS p
        ON p.id = pv.id_prod

    LEFT JOIN dbo.companies AS dealer
        ON dealer.id = pv.id_dealer

    LEFT JOIN dbo.companies AS manufacturer
        ON manufacturer.id = pv.id_manufacturer

    LEFT JOIN dbo.prods_prefix_encodings AS pe
        ON pe.id = pv.id_prefix_encoding

    LEFT JOIN dbo.prods_prefix_codes AS pc
        ON pc.id = pv.id_prefix_code

    LEFT JOIN dbo.prods_father_names AS fn
        ON fn.id = pv.id_father_name

    LEFT JOIN dbo.master_code AS mc
        ON mc.id = pv.id_mc

    LEFT JOIN dbo.mc_lvl1 AS mc1
        ON mc1.id = mc.id_mc_lvl1

    LEFT JOIN dbo.mc_status AS mc1_status
        ON mc1_status.id = mc1.id_mc_status

    LEFT JOIN dbo.mc_lvl2 AS mc2
        ON mc2.id = mc.id_mc_lvl2

    LEFT JOIN dbo.mc_status AS mc2_status
        ON mc2_status.id = mc2.id_mc_status

    LEFT JOIN dbo.mc_lvl3 AS mc3
        ON mc3.id = mc.id_mc_lvl3

    LEFT JOIN dbo.mc_status AS mc3_status
        ON mc3_status.id = mc3.id_mc_status

    LEFT JOIN dbo.prods_pack AS pack
        ON pack.id = pv.id_pack

    LEFT JOIN dbo.prods_pack_qty AS pq
        ON pq.id_prod_version = pv.id

    LEFT JOIN dbo.prods_pack_measure_units AS pmu
        ON pmu.id = pq.id_pack_measure_unit

    LEFT JOIN dbo.prods_features AS feat
        ON feat.id = pv.id_feature

    LEFT JOIN dbo.prods_measures AS meas
        ON meas.id = pv.id_measure

    LEFT JOIN dbo.prods_splits AS ps
        ON ps.id_prod = p.id

    LEFT JOIN dbo.prods AS parent_prod
        ON parent_prod.id = ps.id_parent_prod

    LEFT JOIN dbo.users AS u
        ON u.id = pv.id_user

    WHERE {company_filter}
"""

COMPANY_FILTERS = {
    "dealer": "pv.id_dealer = :id_company",
    "manufacturer": "pv.id_manufacturer = :id_company",
    "any": "(pv.id_dealer = :id_company OR pv.id_manufacturer = :id_company)",
}


def _filter_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _build_filter_clause(request: ProductSearchRequest) -> Tuple[str, Dict[str, Any]]:
    conditions = []
    params: Dict[str, Any] = {"id_company": request.id_company}

    search = _filter_value(request.search)
    if search:
        conditions.append("COALESCE(CONVERT(NVARCHAR(4000), [description]), '') LIKE :search")
        params["search"] = f"%{search}%"

    for field, raw_value in request.filters.items():
        if field not in PRODUCT_FIELDS:
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


def _products_cte(company_role: CompanyRole) -> str:
    return PRODUCTS_BASE_QUERY.format(company_filter=COMPANY_FILTERS[company_role])


def _count_query(company_role: CompanyRole, filter_clause: str):
    return text(
        f"""
        WITH products_base AS (
            {_products_cte(company_role)}
        )
        SELECT COUNT(*) AS total
        FROM products_base
        {filter_clause}
        """
    )


def _rows_query(company_role: CompanyRole, filter_clause: str, full: bool):
    pagination_clause = ""
    if not full:
        pagination_clause = "OFFSET :offset ROWS FETCH NEXT :page_size ROWS ONLY"

    return text(
        f"""
        WITH products_base AS (
            {_products_cte(company_role)}
        )
        SELECT *
        FROM products_base
        {filter_clause}
        ORDER BY [company_item_code], [version], [id_prod_version]
        {pagination_clause}
        """
    )


@router.get("/products/companies")
def get_product_companies(db: Session = Depends(get_db)):
    rows = db.execute(
        text(
            """
            SELECT DISTINCT
                c.id,
                c.company_name,
                c.company_code
            FROM dbo.companies AS c
            WHERE EXISTS (
                SELECT 1
                FROM dbo.prods_versions AS pv
                WHERE pv.id_dealer = c.id
                   OR pv.id_manufacturer = c.id
            )
            ORDER BY c.company_name
            """
        )
    ).fetchall()

    return jsonable_encoder([dict(row._mapping) for row in rows])


@router.get("/products/lookups")
def get_product_lookups(db: Session = Depends(get_db)):
    lookups = {}
    for key, query in PRODUCT_LOOKUP_QUERIES.items():
        rows = db.execute(text(query)).fetchall()
        lookups[key] = [dict(row._mapping) for row in rows]

    return jsonable_encoder(lookups)


@router.post("/products/search")
def search_products(request: ProductSearchRequest, db: Session = Depends(get_db)):
    if request.id_company <= 0:
        raise HTTPException(status_code=400, detail="Company non valida")
    if request.page < 0:
        raise HTTPException(status_code=400, detail="page non puo essere negativa")
    if not request.full and request.page_size not in PAGE_SIZE_OPTIONS:
        raise HTTPException(
            status_code=400,
            detail="page_size deve essere uno tra 25, 50, 100, 250, 500, 1000",
        )

    filter_clause, params = _build_filter_clause(request)
    total = (
        db.execute(_count_query(request.company_role, filter_clause), params).scalar()
        or 0
    )

    query_params = dict(params)
    if not request.full:
        query_params["offset"] = request.page * request.page_size
        query_params["page_size"] = request.page_size

    rows = db.execute(
        _rows_query(request.company_role, filter_clause, request.full),
        query_params,
    ).fetchall()

    return jsonable_encoder(
        {
            "rows": [dict(row._mapping) for row in rows],
            "total": total,
            "page": 0 if request.full else request.page,
            "page_size": None if request.full else request.page_size,
            "full": request.full,
        }
    )


@router.get("/products")
def get_products(db: Session = Depends(get_db)):
    rows = db.execute(text("SELECT * FROM dbo.v_products_all")).fetchall()
    return jsonable_encoder([dict(row._mapping) for row in rows])
