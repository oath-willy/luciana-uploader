"""Databricks Job entry point for the CODEX local snapshot.

Run this script inside Databricks, not in the webapp backend. Configure the
widgets below and store the ingest token in a Databricks secret scope. The Job
reads the Delta tables once, freezes one payload, validates its cardinalities,
then publishes it atomically through the backend ingest endpoint.
"""

import json
from datetime import datetime, timezone

import requests
from pyspark.sql import Window, functions as F


dbutils.widgets.text("environment", "dev")
dbutils.widgets.text("catalog", "research_dev")
dbutils.widgets.text("backend_url", "")
dbutils.widgets.text("secret_scope", "luciana")
dbutils.widgets.text("secret_key", "codex-snapshot-token")

environment = dbutils.widgets.get("environment").strip()
catalog = dbutils.widgets.get("catalog").strip()
backend_url = dbutils.widgets.get("backend_url").strip().rstrip("/")
secret_scope = dbutils.widgets.get("secret_scope").strip()
secret_key = dbutils.widgets.get("secret_key").strip()

if environment not in {"dev", "prod"}:
    raise ValueError("environment deve essere dev o prod")
if not backend_url.startswith("https://"):
    raise ValueError("backend_url deve usare HTTPS")

products = spark.table(f"{catalog}.silver.product_to_classify")
lookups = spark.table(f"{catalog}.silver.codex_bs25_lookup")
pdb = spark.table(f"{catalog}.silver.dump_pdb_flats")

company_mapping = {
    "EURONDA": ("landing_euronda", ["item_description", "product_family_level_1", "brand_company", "item_code", "channel_raw", "customer_raw", "file_name"]),
    "INTVENT": ("landing_intvent", ["item_description", "product_family_level_1", "manufacturer_item_code", "brand_company", "channel_raw", "customer_raw", "file_name"]),
    "IVOCLAR": ("landing_ivoclar", ["item_description", "brand_company", "channel_raw", "customer_raw", "file_name"]),
    "HERAEUS": ("landing_kulzer", ["item_description", "brand_company", "channel_raw", "customer_raw", "file_name"]),
}
all_landing_fields = sorted({field for _, fields in company_mapping.values() for field in fields})

latest_lookup_window = Window.partitionBy(
    F.upper(F.trim("company")), F.trim("item_code")
).orderBy(F.col("requested_at").desc_nulls_last())
latest_lookups = (
    lookups.withColumn("_rank", F.row_number().over(latest_lookup_window))
    .where(F.col("_rank") == 1)
    .select(
        F.upper(F.trim("company")).alias("_company"),
        F.trim("item_code").alias("_item_code"),
        F.col("lookup_status").alias("bs25_status"),
        F.col("proposal_1").alias("bs25_proposal_1"),
        F.col("proposal_2").alias("bs25_proposal_2"),
        F.col("proposal_3").alias("bs25_proposal_3"),
    )
)

base_items = (
    products.alias("p")
    .join(
        latest_lookups.alias("b"),
        (F.upper(F.trim(F.col("p.company"))) == F.col("b._company"))
        & (F.trim(F.col("p.item_code")) == F.col("b._item_code")),
        "left",
    )
    .select(
        F.upper(F.trim(F.col("p.company"))).alias("company"),
        F.trim(F.col("p.item_code")).alias("item_code"),
        F.concat_ws("|", F.trim(F.col("p.company")), F.trim(F.col("p.item_code"))).alias(
            "company_item_code"
        ),
        F.col("p.description").alias("description"),
        F.col("b.bs25_status"),
        F.col("b.bs25_proposal_1"),
        F.col("b.bs25_proposal_2"),
        F.col("b.bs25_proposal_3"),
        F.col("p.first_received_date"),
        F.col("p.source_file"),
        F.col("p.search_type"),
        F.col("p.status"),
        F.col("p.created_date"),
    )
)

landing_frames = []
for company, (table_name, fields) in company_mapping.items():
    landing = spark.table(f"{catalog}.bronze.{table_name}")
    landing_frames.append(
        landing.select(
            F.lit(company).alias("_landing_company"),
            F.upper(F.trim("company_item_code")).alias("_landing_key"),
            F.col("date").alias("_landing_date"),
            F.col("file_name").alias("_landing_file"),
            *[
                (F.col(field) if field in fields else F.lit(None)).alias(f"landing_{field}")
                for field in all_landing_fields
            ],
        )
    )

landing_union = landing_frames[0]
for frame in landing_frames[1:]:
    landing_union = landing_union.unionByName(frame, allowMissingColumns=True)
landing_window = Window.partitionBy("_landing_company", "_landing_key").orderBy(
    F.col("_landing_date").desc_nulls_last(), F.col("_landing_file").desc_nulls_last()
)
landing_latest = (
    landing_union.withColumn("_landing_rank", F.row_number().over(landing_window))
    .where(F.col("_landing_rank") == 1)
    .drop("_landing_rank", "_landing_date", "_landing_file")
)

joined_with_landing = base_items.alias("i").join(
    landing_latest.alias("l"),
    (F.col("i.company") == F.col("l._landing_company"))
    & (F.upper(F.trim(F.col("i.company_item_code"))) == F.col("l._landing_key")),
    "left",
)
joined = joined_with_landing.select(
    *[F.col(f"i.{field}") for field in ("company", "item_code", "company_item_code", "description", "bs25_status", "bs25_proposal_1", "bs25_proposal_2", "bs25_proposal_3")],
    F.to_json(
        F.struct(
            F.col("i.first_received_date"),
            F.col("i.source_file"),
            F.col("i.search_type"),
            F.col("i.status"),
            F.col("i.created_date"),
            *[F.col(f"l.landing_{field}") for field in all_landing_fields],
        )
    ).alias("details_json"),
)

row_count = joined.count()
if row_count <= 0:
    raise RuntimeError("Snapshot CODEX vuoto: pubblicazione interrotta")

rows = []
for row in joined.toLocalIterator():
    item = row.asDict(recursive=True)
    item["details"] = json.loads(item.pop("details_json") or "{}")
    for rank in (1, 2, 3):
        field = f"bs25_proposal_{rank}"
        item[field] = json.loads(item[field]) if item.get(field) else None
    rows.append(item)

company_values = sorted({item["company"] for item in rows})
base_detail_columns = [
    {"field": "first_received_date", "header_name": "First Received Date", "value_type": "date"},
    {"field": "source_file", "header_name": "Product Source File", "value_type": "string"},
    {"field": "search_type", "header_name": "Search Type", "value_type": "string"},
    {"field": "status", "header_name": "Status", "value_type": "string"},
    {"field": "created_date", "header_name": "Created Date", "value_type": "date"},
]
companies = []
for company in company_values:
    mapping = company_mapping.get(company)
    extra_columns = list(base_detail_columns)
    if mapping:
        extra_columns.extend(
            {
                "field": f"landing_{field}",
                "header_name": field.replace("_", " ").title(),
                "value_type": "string",
            }
            for field in mapping[1]
        )
    companies.append(
        {
            "company": company,
            "full_view_available": True,
            "full_view_message": None,
            "extra_columns": extra_columns[:12],
        }
    )

master_code_rows = (
    pdb.where(
        F.col("mc_lvl1_code").isNotNull()
        & F.col("mc_lvl2_code").isNotNull()
        & F.col("mc_lvl3_code").isNotNull()
    )
    .select("mc_lvl1_code", "mc_lvl2_code", "mc_lvl3_code")
    .dropDuplicates()
    .collect()
)
master_codes = []
for row in master_code_rows:
    level_1 = str(row["mc_lvl1_code"]).zfill(2)
    level_2 = str(row["mc_lvl2_code"]).zfill(2)
    level_3 = str(row["mc_lvl3_code"]).zfill(2)
    master_codes.append(
        {
            "master_code": f"{level_1}_{level_2}_{level_3}",
            "components": {
                "mc_lvl1_code": level_1,
                "mc_lvl2_code": level_2,
                "mc_lvl3_code": level_3,
            },
        }
    )
if not master_codes:
    raise RuntimeError("Reference Master Code vuota: pubblicazione interrotta")

created_at = datetime.now(timezone.utc).isoformat()
payload = {
    "environment": environment,
    "snapshot_id": f"{catalog}-{created_at}",
    "created_at": created_at,
    "companies": companies,
    "rows": rows,
    "master_codes": master_codes,
}
token = dbutils.secrets.get(scope=secret_scope, key=secret_key)
response = requests.put(
    f"{backend_url}/api/codex/snapshot",
    headers={"X-Codex-Snapshot-Token": token},
    json=payload,
    timeout=900,
)
response.raise_for_status()
receipt = response.json()
if receipt.get("rows") != row_count:
    raise RuntimeError(f"Conteggio snapshot non coerente: {receipt}")
print(json.dumps(receipt, ensure_ascii=False))
