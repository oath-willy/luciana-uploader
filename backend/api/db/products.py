from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.db import get_db


router = APIRouter()

CompanyRole = Literal["dealer", "manufacturer", "any"]


class ProductSearchRequest(BaseModel):
    id_company: int
    company_role: CompanyRole = "any"
    max_rows: int = 5000


PRODUCTS_QUERY_TEMPLATE = """
    SELECT TOP (:max_rows)
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

    ORDER BY
        p.company_item_code,
        pv.[version]
"""

PRODUCTS_QUERY_BY_ROLE = {
    "dealer": text(PRODUCTS_QUERY_TEMPLATE.format(company_filter="pv.id_dealer = :id_company")),
    "manufacturer": text(
        PRODUCTS_QUERY_TEMPLATE.format(company_filter="pv.id_manufacturer = :id_company")
    ),
    "any": text(
        PRODUCTS_QUERY_TEMPLATE.format(
            company_filter=(
                "(pv.id_dealer = :id_company OR pv.id_manufacturer = :id_company)"
            )
        )
    ),
}

LEGACY_PRODUCTS_QUERY = text(
    """
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

    WHERE
        (
            :company_role = 'dealer'
            AND pv.id_dealer = :id_company
        )
        OR (
            :company_role = 'manufacturer'
            AND pv.id_manufacturer = :id_company
        )
        OR (
            :company_role = 'any'
            AND (
                pv.id_dealer = :id_company
                OR pv.id_manufacturer = :id_company
            )
        )

    ORDER BY
        p.company_item_code,
        pv.[version]
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


@router.post("/products/search")
def search_products(request: ProductSearchRequest, db: Session = Depends(get_db)):
    if request.id_company <= 0:
        raise HTTPException(status_code=400, detail="Company non valida")
    if request.max_rows < 1 or request.max_rows > 10000:
        raise HTTPException(status_code=400, detail="max_rows deve essere tra 1 e 10000")

    rows = db.execute(
        PRODUCTS_QUERY_BY_ROLE[request.company_role],
        {
            "id_company": request.id_company,
            "company_role": request.company_role,
            "max_rows": request.max_rows,
        },
    ).fetchall()

    return jsonable_encoder([dict(row._mapping) for row in rows])


@router.get("/products")
def get_products(db: Session = Depends(get_db)):
    rows = db.execute(text("SELECT * FROM dbo.v_products_all")).fetchall()
    return jsonable_encoder([dict(row._mapping) for row in rows])
