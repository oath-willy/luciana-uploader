"""Databricks Job entry point for the MC CODE local snapshot.

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
dbutils.widgets.text(
    "pdb_manifest_uri",
    "dbfs:/Volumes/research_dev/silver/pdb_exports/ref_pdb_dump/latest.json",
)

environment = dbutils.widgets.get("environment").strip()
catalog = dbutils.widgets.get("catalog").strip()
backend_url = dbutils.widgets.get("backend_url").strip().rstrip("/")
secret_scope = dbutils.widgets.get("secret_scope").strip()
secret_key = dbutils.widgets.get("secret_key").strip()
pdb_manifest_uri = dbutils.widgets.get("pdb_manifest_uri").strip()

if environment not in {"dev", "prod"}:
    raise ValueError("environment deve essere dev o prod")
if not backend_url.startswith("https://"):
    raise ValueError("backend_url deve usare HTTPS")

products = spark.table(f"{catalog}.silver.product_to_classify")
lookups = spark.table(f"{catalog}.silver.codex_bs25_lookup")
pdb_manifest = json.loads(dbutils.fs.head(pdb_manifest_uri, 1_000_000))
pdb_path = str(pdb_manifest.get("parquet_path") or "").strip()
if not pdb_path:
    raise RuntimeError("Manifest ref_pdb_dump privo di parquet_path")
pdb = spark.read.parquet(pdb_path)

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
        F.col("selected_proposal_rank").alias("bs25_selected_proposal_rank"),
        F.col("selected_master_code").alias("bs25_selected_master_code"),
        F.col("selection_status").alias("bs25_selection_status"),
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
        F.col("b.bs25_selected_proposal_rank"),
        F.col("b.bs25_selected_master_code"),
        F.col("b.bs25_selection_status"),
        F.col("p.first_received_date"),
        F.col("p.source_file"),
        F.col("p.search_type"),
        F.col("p.status"),
        F.col("p.created_date"),
    )
)

joined = base_items.alias("i").select(
    *[
        F.col(f"i.{field}")
        for field in (
            "company",
            "item_code",
            "company_item_code",
            "description",
            "bs25_status",
            "bs25_proposal_1",
            "bs25_proposal_2",
            "bs25_proposal_3",
            "bs25_selected_proposal_rank",
            "bs25_selected_master_code",
            "bs25_selection_status",
        )
    ],
    F.to_json(
        F.struct(
            F.col("i.first_received_date"),
            F.col("i.source_file"),
            F.col("i.search_type"),
            F.col("i.status"),
            F.col("i.created_date"),
        )
    ).alias("details_json"),
)

row_count = joined.count()
if row_count <= 0:
    raise RuntimeError("Snapshot MC CODE vuoto: pubblicazione interrotta")

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
    extra_columns = list(base_detail_columns)
    companies.append(
        {
            "company": company,
            "full_view_available": True,
            "full_view_message": None,
            "extra_columns": extra_columns,
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
    f"{backend_url}/api/mc-code/snapshot",
    headers={"X-MC-Code-Snapshot-Token": token},
    json=payload,
    timeout=900,
)
response.raise_for_status()
receipt = response.json()
if receipt.get("rows") != row_count:
    raise RuntimeError(f"Conteggio snapshot non coerente: {receipt}")

print(
    json.dumps(
        {
            "mc_code": receipt,
            "reference_pdb": {
                "manifest_uri": pdb_manifest_uri,
                "parquet_path": pdb_path,
                "row_count": pdb_manifest.get("row_count"),
            },
        },
        ensure_ascii=False,
    )
)
