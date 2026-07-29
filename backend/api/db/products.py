from typing import Any, Dict, Literal, Tuple

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from services.db import get_db


router = APIRouter()

CompanyRole = Literal["dealer", "manufacturer", "any"]

PAGE_SIZE_OPTIONS = {25, 50, 100, 500}
DEFAULT_PAGE_SIZE = 50

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
    search: str = ""
    filters: Dict[str, Any] = Field(default_factory=dict)
    include_extra_attributes: bool = False


PRODUCT_LOOKUP_SOURCES = {
    "companies": """
        SELECT id, company_name AS label, NULL AS code
        FROM dbo.companies
    """,
    "prefix_encodings": """
        SELECT id, prefix_encoding AS label, NULL AS code
        FROM dbo.prods_prefix_encodings
    """,
    "prefix_codes": """
        SELECT id, prefix_code AS label, NULL AS code
        FROM dbo.prods_prefix_codes
    """,
    "father_names": """
        SELECT id, father_name AS label, NULL AS code
        FROM dbo.prods_father_names
    """,
    "master_codes": """
        SELECT
            mc.id,
            CONCAT(
                COALESCE(mc1.code, ''),
                CASE WHEN mc2.code IS NULL THEN '' ELSE CONCAT(' / ', mc2.code) END,
                CASE WHEN mc3.code IS NULL THEN '' ELSE CONCAT(' / ', mc3.code) END
            ) AS label,
            NULL AS code
        FROM dbo.master_code AS mc
        LEFT JOIN dbo.mc_lvl1 AS mc1 ON mc1.id = mc.id_mc_lvl1
        LEFT JOIN dbo.mc_lvl2 AS mc2 ON mc2.id = mc.id_mc_lvl2
        LEFT JOIN dbo.mc_lvl3 AS mc3 ON mc3.id = mc.id_mc_lvl3
    """,
    "packs": """
        SELECT id, pack AS label, NULL AS code
        FROM dbo.prods_pack
    """,
    "pack_measure_units": """
        SELECT id, measure_unit AS label, NULL AS code
        FROM dbo.prods_pack_measure_units
    """,
    "features": """
        SELECT id, feature AS label, NULL AS code
        FROM dbo.prods_features
    """,
    "measures": """
        SELECT id, measure AS label, NULL AS code
        FROM dbo.prods_measures
    """,
    "products": """
        SELECT id, company_item_code AS label, NULL AS code
        FROM dbo.prods
    """,
    "users": """
        SELECT id, CONCAT(COALESCE(nome, ''), ' ', COALESCE(cognome, '')) AS label, NULL AS code
        FROM dbo.users
    """,
    "mc_lvl1": """
        SELECT DISTINCT
            mc1.id,
            RIGHT(CONCAT('00', COALESCE(CONVERT(NVARCHAR(20), mc1.code), '')), 2) AS label,
            RIGHT(CONCAT('00', COALESCE(CONVERT(NVARCHAR(20), mc1.code), '')), 2) AS code
        FROM dbo.master_code AS mc
        JOIN dbo.mc_lvl1 AS mc1 ON mc1.id = mc.id_mc_lvl1
        WHERE LEN(LTRIM(RTRIM(COALESCE(CONVERT(NVARCHAR(20), mc1.code), '')))) > 0
    """,
    "mc_lvl2": """
        SELECT DISTINCT
            mc2.id,
            RIGHT(CONCAT('00', COALESCE(CONVERT(NVARCHAR(20), mc2.code), '')), 2) AS label,
            RIGHT(CONCAT('00', COALESCE(CONVERT(NVARCHAR(20), mc2.code), '')), 2) AS code,
            mc.id_mc_lvl1
        FROM dbo.master_code AS mc
        JOIN dbo.mc_lvl2 AS mc2 ON mc2.id = mc.id_mc_lvl2
        WHERE LEN(LTRIM(RTRIM(COALESCE(CONVERT(NVARCHAR(20), mc2.code), '')))) > 0
    """,
    "mc_lvl3": """
        SELECT DISTINCT
            mc3.id,
            RIGHT(CONCAT('00', COALESCE(CONVERT(NVARCHAR(20), mc3.code), '')), 2) AS label,
            RIGHT(CONCAT('00', COALESCE(CONVERT(NVARCHAR(20), mc3.code), '')), 2) AS code,
            mc.id_mc_lvl1,
            mc.id_mc_lvl2
        FROM dbo.master_code AS mc
        JOIN dbo.mc_lvl3 AS mc3 ON mc3.id = mc.id_mc_lvl3
        WHERE LEN(LTRIM(RTRIM(COALESCE(CONVERT(NVARCHAR(20), mc3.code), '')))) > 0
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
        NULL AS dealer_company_code,

        pv.id_brand AS id_manufacturer,
        manufacturer.company_name AS manufacturer_company_name,
        NULL AS manufacturer_company_code,

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
        ON manufacturer.id = pv.id_brand

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
    "manufacturer": "pv.id_brand = :id_company",
    "any": "(pv.id_dealer = :id_company OR pv.id_brand = :id_company)",
}


def _filter_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _extra_attribute_value_expression(alias: str = "ea", allowed_alias: str = "av") -> str:
    return f"""
        COALESCE(
            CONVERT(NVARCHAR(1000), {allowed_alias}.val_label),
            CONVERT(NVARCHAR(1000), {allowed_alias}.val_code),
            CONVERT(NVARCHAR(1000), {alias}.val_text),
            CONVERT(NVARCHAR(1000), {alias}.val_decimal),
            CONVERT(NVARCHAR(1000), {alias}.val_integer),
            CASE
                WHEN {alias}.val_boolean = 1 THEN N'true'
                WHEN {alias}.val_boolean = 0 THEN N'false'
                ELSE NULL
            END,
            CONVERT(NVARCHAR(1000), {alias}.val_date, 23),
            CONVERT(NVARCHAR(1000), {alias}.source_raw_val)
        )
    """


def _extra_attribute_key(field: Dict[str, Any]) -> str:
    code = _filter_value(field.get("field_code")) or str(field["id"])
    safe_code = "".join(char if char.isalnum() or char == "_" else "_" for char in code)
    return f"extra_attr_{safe_code.lower()}"


def _get_extra_attribute_fields(db: Session):
    rows = db.execute(
        text(
            """
            SELECT
                id,
                field_code,
                field_name,
                val_type,
                is_multi_val,
                is_active
            FROM dbo.prods_extra_attrib_fields
            WHERE is_active = 1
            ORDER BY id
            """
        )
    ).fetchall()

    fields = []
    for row in rows:
        field = dict(row._mapping)
        field["field_key"] = _extra_attribute_key(field)
        fields.append(field)
    return fields


def _build_filter_clause(
    request: ProductSearchRequest,
    extra_attribute_fields=None,
) -> Tuple[str, Dict[str, Any]]:
    conditions = []
    params: Dict[str, Any] = {"id_company": request.id_company}
    extra_field_by_key = {
        field["field_key"]: field for field in (extra_attribute_fields or [])
    }

    search = _filter_value(request.search)
    if search:
        conditions.append("COALESCE(CONVERT(NVARCHAR(4000), [description]), '') LIKE :search")
        params["search"] = f"%{search}%"

    for field, raw_value in request.filters.items():
        value = _filter_value(raw_value)
        if not value:
            continue

        if field in extra_field_by_key:
            param_name = f"extra_filter_{field}"
            field_param_name = f"extra_field_{field}"
            value_expression = _extra_attribute_value_expression()
            conditions.append(
                f"""
                EXISTS (
                    SELECT 1
                    FROM dbo.prods_extra_attrib AS ea
                    LEFT JOIN dbo.prods_extra_attrib_allowed_val AS av
                        ON av.id = ea.id_prod_extra_attrib_allowed_val
                    WHERE ea.id_prod_version = products_base.id_prod_version
                      AND ea.id_prod_extra_attrib_field = :{field_param_name}
                      AND COALESCE({value_expression}, N'') LIKE :{param_name}
                )
                """
            )
            params[field_param_name] = extra_field_by_key[field]["id"]
            params[param_name] = f"%{value}%"
            continue

        if field not in PRODUCT_FIELDS:
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


def _rows_query(company_role: CompanyRole, filter_clause: str):
    return text(
        f"""
        WITH products_base AS (
            {_products_cte(company_role)}
        )
        SELECT *
        FROM products_base
        {filter_clause}
        ORDER BY [company_item_code], [version], [id_prod_version]
        OFFSET :offset ROWS FETCH NEXT :page_size ROWS ONLY
        """
    )


def _fetch_extra_attribute_values(db: Session, prod_version_ids, fields):
    if not prod_version_ids or not fields:
        return {}

    field_ids = [field["id"] for field in fields]
    field_key_by_id = {field["id"]: field["field_key"] for field in fields}
    value_expression = _extra_attribute_value_expression()
    query = text(
        f"""
        SELECT
            ea.id_prod_version,
            ea.id_prod_extra_attrib_field,
            STRING_AGG(CONVERT(NVARCHAR(MAX), {value_expression}), N', ') AS display_value
        FROM dbo.prods_extra_attrib AS ea
        LEFT JOIN dbo.prods_extra_attrib_allowed_val AS av
            ON av.id = ea.id_prod_extra_attrib_allowed_val
        WHERE ea.id_prod_version IN :prod_version_ids
          AND ea.id_prod_extra_attrib_field IN :field_ids
        GROUP BY ea.id_prod_version, ea.id_prod_extra_attrib_field
        """
    ).bindparams(
        bindparam("prod_version_ids", expanding=True),
        bindparam("field_ids", expanding=True),
    )

    rows = db.execute(
        query,
        {
            "prod_version_ids": tuple(prod_version_ids),
            "field_ids": tuple(field_ids),
        },
    ).fetchall()

    values_by_version = {}
    for row in rows:
        value = dict(row._mapping)
        field_key = field_key_by_id.get(value["id_prod_extra_attrib_field"])
        if not field_key:
            continue
        values_by_version.setdefault(value["id_prod_version"], {})[field_key] = value[
            "display_value"
        ]

    return values_by_version


@router.get("/products/companies")
def get_product_companies(db: Session = Depends(get_db)):
    rows = db.execute(
        text(
            """
            SELECT
                c.id,
                c.company_name,
                NULL AS company_code
            FROM dbo.companies AS c
            ORDER BY c.company_name
            """
        )
    ).fetchall()

    return jsonable_encoder([dict(row._mapping) for row in rows])


@router.get("/products/lookups")
def get_product_lookups(limit: int = 25, db: Session = Depends(get_db)):
    lookups = {}
    safe_limit = min(max(limit, 1), 100)
    for key in PRODUCT_LOOKUP_SOURCES:
        lookups[key] = _fetch_product_lookup(db, key, "", safe_limit)

    return jsonable_encoder(lookups)


@router.get("/products/lookups/{lookup_key}")
def get_product_lookup(
    lookup_key: str,
    q: str = "",
    limit: int = 50,
    id_mc_lvl1: int | None = None,
    id_mc_lvl2: int | None = None,
    db: Session = Depends(get_db),
):
    if lookup_key not in PRODUCT_LOOKUP_SOURCES:
        raise HTTPException(status_code=404, detail="Lookup non trovato")

    safe_limit = min(max(limit, 1), 100)
    return jsonable_encoder(
        _fetch_product_lookup(
            db,
            lookup_key,
            q,
            safe_limit,
            id_mc_lvl1=id_mc_lvl1,
            id_mc_lvl2=id_mc_lvl2,
        )
    )


@router.get("/products/extra-attribute-fields")
def get_product_extra_attribute_fields(db: Session = Depends(get_db)):
    return jsonable_encoder(_get_extra_attribute_fields(db))


def _fetch_product_lookup(
    db: Session,
    lookup_key: str,
    q: str,
    limit: int,
    id_mc_lvl1: int | None = None,
    id_mc_lvl2: int | None = None,
):
    parent_conditions = []
    params = {
        "q": q.strip(),
        "q_like": f"%{q.strip()}%",
        "id_mc_lvl1": id_mc_lvl1,
        "id_mc_lvl2": id_mc_lvl2,
    }

    if lookup_key in {"mc_lvl2", "mc_lvl3"}:
        parent_conditions.append(
            "(:id_mc_lvl1 IS NULL OR id_mc_lvl1 = :id_mc_lvl1)"
        )
    if lookup_key == "mc_lvl3":
        parent_conditions.append(
            "(:id_mc_lvl2 IS NULL OR id_mc_lvl2 = :id_mc_lvl2)"
        )

    parent_clause = ""
    if parent_conditions:
        parent_clause = " AND " + " AND ".join(parent_conditions)

    query = text(
        f"""
        SELECT TOP ({limit})
            id,
            label,
            code
        FROM (
            {PRODUCT_LOOKUP_SOURCES[lookup_key]}
        ) AS lookup_source
        WHERE
            (
                :q = ''
                OR COALESCE(CONVERT(NVARCHAR(4000), label), '') LIKE :q_like
                OR COALESCE(CONVERT(NVARCHAR(4000), code), '') LIKE :q_like
            )
            {parent_clause}
        ORDER BY label
        """
    )
    rows = db.execute(query, params).fetchall()
    return [dict(row._mapping) for row in rows]


@router.post("/products/search")
def search_products(request: ProductSearchRequest, db: Session = Depends(get_db)):
    if request.id_company <= 0:
        raise HTTPException(status_code=400, detail="Company non valida")
    if request.page < 0:
        raise HTTPException(status_code=400, detail="page non puo essere negativa")
    if request.page_size not in PAGE_SIZE_OPTIONS:
        raise HTTPException(
            status_code=400,
            detail="page_size deve essere uno tra 25, 50, 100, 500",
        )

    extra_attribute_fields = (
        _get_extra_attribute_fields(db) if request.include_extra_attributes else []
    )
    filter_clause, params = _build_filter_clause(request, extra_attribute_fields)
    total = (
        db.execute(_count_query(request.company_role, filter_clause), params).scalar()
        or 0
    )

    query_params = dict(params)
    query_params["offset"] = request.page * request.page_size
    query_params["page_size"] = request.page_size

    rows = db.execute(
        _rows_query(request.company_role, filter_clause),
        query_params,
    ).fetchall()
    response_rows = [dict(row._mapping) for row in rows]

    if request.include_extra_attributes and response_rows:
        prod_version_ids = [
            row["id_prod_version"]
            for row in response_rows
            if row.get("id_prod_version") is not None
        ]
        extra_values = _fetch_extra_attribute_values(
            db,
            prod_version_ids,
            extra_attribute_fields,
        )
        for row in response_rows:
            row.update(extra_values.get(row.get("id_prod_version"), {}))

    return jsonable_encoder(
        {
            "rows": response_rows,
            "total": total,
            "page": request.page,
            "page_size": request.page_size,
            "extra_attribute_fields": extra_attribute_fields,
        }
    )


@router.get("/products")
def get_products(db: Session = Depends(get_db)):
    rows = db.execute(text("SELECT * FROM dbo.v_products_all")).fetchall()
    return jsonable_encoder([dict(row._mapping) for row in rows])
