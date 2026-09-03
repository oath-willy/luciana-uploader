# Snapshot locale CODEX

La webapp legge esclusivamente `snapshot-dev.sqlite3` / `snapshot-prod.sqlite3` e conserva
job BS25, job BS25AI e scelte operatore in `runtime.sqlite3`. Anche l'elenco delle company e
ricavato dalla tabella `companies` dello snapshot: nessun endpoint CODEX interroga Databricks.
Gli snapshot vengono validati in un file temporaneo e sostituiti con rename atomico;
`runtime.sqlite3` non viene mai sovrascritto.

Databricks deve pubblicare un payload completo con `PUT /api/codex/snapshot` e header
`X-Codex-Snapshot-Token`. Il backend richiede `CODEX_SNAPSHOT_TOKEN`; i file risultanti sono
ignorati da Git. Il payload contiene `environment`, `snapshot_id`, `created_at`, `companies`,
`rows` e la reference canonica `master_codes`.

Il Job `databricks/publish_codex_snapshot.py`, eseguito da un checkout Git del repository,
pubblica nello stesso run anche `pdb-{environment}.sqlite3`. Riusa direttamente il builder
BS25 del backend, invia il file in streaming e confronta i conteggi prima di terminare. Il widget
`publish_pdb=false` consente di saltare il PDB soltanto nei run diagnostici.

Per il bootstrap manuale si usa `databricks/bootstrap_codex_snapshots.py`: legge in streaming
le sole tre tabelle Silver approvate tramite Statement Execution API, crea i due SQLite correnti
e non conserva dump CSV o versioni storiche. Questo script e il Job Databricks sono processi di
manutenzione esterni: non vengono importati o eseguiti dal backend web.

Il processo produttore deve scrivere soltanto dopo aver congelato e validato le sorgenti
`product_to_classify`, `codex_bs25_lookup` e `dump_pdb_flats`. Non deve aggiornare il file SQLite
direttamente su share remota e non deve inviare payload parziali.

Il calcolo BS25 opzionale della webapp usa un secondo file locale, `pdb-dev.sqlite3` /
`pdb-prod.sqlite3`, che contiene il dump PDB normalizzato e l'indice full-text. Il file puo
essere costruito sul backend da un dump CSV/CSV.GZ o JSONL/JSONL.GZ gia iniettato:

```powershell
python backend/scripts/build_codex_pdb_snapshot.py dump_pdb_flats.csv.gz --environment dev
```

In alternativa il produttore puo costruire lo stesso SQLite in staging e inviarlo in streaming
con `PUT /api/codex/pdb-snapshot?environment=dev`, `Content-Type: application/octet-stream` e
header `X-Codex-Snapshot-Token`. Il backend esegue controllo schema, conteggio e `quick_check`,
poi sostituisce atomicamente il file corrente. Le versioni precedenti non vengono conservate.

Su Azure Web App configurare `CODEX_LOCAL_DATA_DIR=/home/data/codex` e
`CODEX_RUNTIME_DB=/home/data/codex/runtime.sqlite3`: `/home` e il relativo volume persistente
devono essere abilitati. In container diversi da App Service montare un volume persistente sullo
stesso percorso. Il default sotto `backend/data/codex` serve soltanto allo sviluppo locale.

Con `BS25AI_MOCK_MODE=true` il contratto verso lucianavm04 viene simulato e i risultati sono
marcati esplicitamente `SIMULAZIONE`. Disattivare la variabile quando il worker reale e pronto.
