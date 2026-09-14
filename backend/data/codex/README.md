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

La sorgente degli item e ora `stkeystoneresearchdev/pdb/pdb_new_items.parquet`.
In PDB Settings, **Recupera New Items** scarica il file mantenendo lo stesso nome in
`backend/data/codex` (su Azure, nella directory persistente configurata).
Il download e validato prima di aggiornare lo snapshot SQLite usato da MC CODE:
il Parquet originale e conservato, mentre SQLite permette filtri e paginazione senza
scaricare tutti gli item nel browser. `item_extra_descriptions` e un oggetto JSON;
i suoi campi sono esposti nella vista FULL e inviati ai worker insieme agli altri dettagli.
Job e scelte gia presenti nel runtime vengono conservati; vengono mantenute anche le
proposte precedentemente importate per gli item ancora presenti nella nuova sorgente.
Il recupero riguarda Dev; non copia i dati Dev nello snapshot Prod.

Autenticazione: preferire la Managed Identity della Web App con **Storage Blob Data Reader**
sul container `pdb`. In locale `DefaultAzureCredential` usa anche il login Azure CLI.
In alternativa configurare `PDB_NEW_ITEMS_STORAGE_CONNECTION_STRING`, oppure il nome di un
secret Key Vault in `PDB_NEW_ITEMS_STORAGE_SECRET` (vault `KEY_VAULT_NAME`). Non inserire
credenziali nel frontend o nel repository. Stato e errori sono persistiti in
`pdb-new-items-sync.sqlite3`. Gli endpoint sono `GET /api/pdb/settings/new-items` e
`POST /api/pdb/settings/new-items/refresh`.
La prima importazione richiede uno snapshot MC CODE con la reference canonica gia pubblicata.
Lo script `scripts/start-local-dev.ps1` usa sempre la directory dati locale, anche quando
importa le app settings Azure. In assenza di un secret o una connection string dedicata,
prova a recuperare la chiave dello storage tramite il login Azure CLI sulla subscription
`sub-keystone-research-dev` (parametro `NewItemsSubscription`): resta soltanto nell'ambiente
del processo backend, non viene scritta in file o log. Se il login non permette questa
lettura, occorre autorizzare Storage Blob Data Reader per l'autenticazione Azure diretta.

Il Job `databricks/publish_mc_code_snapshot.py`, eseguito da un checkout Git del repository,
pubblica lo snapshot operativo da `pdb_new_items.parquet` e `codex_bs25_lookup`. Il widget
`new_items_uri` permette di specificare la sorgente per ambiente. La reference
canonica dei Master Code viene letta dal Parquet corrente indicato dal manifest
`pdb_exports/ref_pdb_dump/latest.json`; non usa piu `dump_pdb_flats`.

Il processo produttore deve scrivere soltanto dopo aver congelato e validato le sorgenti
`pdb_new_items.parquet`, `codex_bs25_lookup` e `ref_pdb_dump.parquet`. Non deve aggiornare il file
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
