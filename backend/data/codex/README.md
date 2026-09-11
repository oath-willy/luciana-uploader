# Snapshot locale MC CODE

La pagina si trova in PDB > CODE TOOLS > MC CODE (`/navigator/mc-code`).
Il vecchio percorso `/navigator/codex` e le API `/api/codex/*` reindirizzano ai nuovi.
Le impostazioni `MC_CODE_*` hanno precedenza sulle precedenti `CODEX_*`, ancora accettate,
cosi come l'header `X-Codex-Snapshot-Token`. I percorsi fisici `data/codex`, la tabella
Databricks `codex_bs25_lookup` e il secret esistente mantengono i nomi precedenti per
riutilizzare i dati senza una migrazione. I moduli `bs25ai_worker/codex_app_server.py`
si riferiscono al prodotto OpenAI Codex, non al nome della pagina.

La webapp legge esclusivamente `snapshot-dev.sqlite3` / `snapshot-prod.sqlite3` e conserva
job BS25, job BS25AI e scelte operatore in `runtime.sqlite3`. Anche l'elenco delle company e
ricavato dalla tabella `companies` dello snapshot: nessun endpoint MC CODE interroga Databricks.
Gli snapshot vengono validati in un file temporaneo e sostituiti con rename atomico;
`runtime.sqlite3` non viene mai sovrascritto.

Databricks deve pubblicare un payload completo con `PUT /api/mc-code/snapshot` e header
`X-MC-Code-Snapshot-Token`. Il backend richiede `MC_CODE_SNAPSHOT_TOKEN`; i file risultanti sono
ignorati da Git. Il payload contiene `environment`, `snapshot_id`, `created_at`, `companies`,
`rows` e la reference canonica `master_codes`.

Il bootstrap o disaster recovery puo inviare un SQLite gia costruito a
`PUT /api/mc-code/snapshot-file?environment=dev`. Il backend applica token dedicato,
validazione di schema e contenuto, `quick_check` e sostituzione atomica.

Il Job `databricks/publish_mc_code_snapshot.py`, eseguito da un checkout Git del repository,
pubblica lo snapshot operativo da `product_to_classify` e `codex_bs25_lookup`. La reference
canonica dei Master Code viene letta dal Parquet corrente indicato dal manifest
`pdb_exports/ref_pdb_dump/latest.json`; non usa piu `dump_pdb_flats`.

Il processo produttore deve scrivere soltanto dopo aver congelato e validato le sorgenti
`product_to_classify`, `codex_bs25_lookup` e `ref_pdb_dump.parquet`. Non deve aggiornare il file
SQLite direttamente su share remota e non deve inviare payload parziali.

Il calcolo BS25 opzionale e delegato al servizio `pdb-bs25-worker` di lucianavm04. Il backend
invia `company`, `item_code`, `description` e l'oggetto estendibile `extra`, riceve esattamente
tre proposte e le salva nel runtime locale come in precedenza. Il servizio usa esclusivamente
`panel_data_utilities/scripts/jobs/pdb/ref_pdb_dump.parquet` e un indice SQLite derivato corrente,
senza conservare versioni storiche.

Il percorso sperimentale `POST /api/mc-code/bs23-v2` delega allo stesso worker tramite
`POST /v1/bs23-v2` e persiste le tre proposte nelle medesime colonne di
`local_bs25_results`. `retriever_version=pdb-coding-proposals-v2` distingue la revisione;
non vengono create colonne aggiuntive e gli item con proposte gia presenti restano bloccati.

La pagina `Database > PDB > Settings` esegue via SSH a chiave
`fetch_ref_pdb_dump.sh`, scarica in streaming lo stesso file come
`/home/data/codex/ref_pdb_dump.parquet` e ricostruisce atomicamente l'indice del worker. Lo stato
dell'operazione e persistito in `/home/data/codex/pdb-settings.sqlite3`.

Su Azure Web App configurare `MC_CODE_LOCAL_DATA_DIR=/home/data/codex` e
`MC_CODE_RUNTIME_DB=/home/data/codex/runtime.sqlite3`: `/home` e il relativo volume persistente
devono essere abilitati. In container diversi da App Service montare un volume persistente sullo
stesso percorso. Il default sotto `backend/data/codex` serve soltanto allo sviluppo locale.

Con `BS25AI_MOCK_MODE=true` il contratto verso lucianavm04 viene simulato e i risultati sono
marcati esplicitamente `SIMULAZIONE`. Disattivare la variabile quando il worker reale e pronto.
