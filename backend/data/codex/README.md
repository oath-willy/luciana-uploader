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

## Browsing Reference PDB in items-code

La vista iniziale comprende tutte le company, ma l'API restituisce solo la pagina richiesta
(default 100 righe). I filtri generali e per colonna sono applicati all'intero dataset, con
ricerca case-insensitive di sottostringhe letterali: `%` e `_` non sono wildcard.

Al primo accesso viene preparato in background un Parquet derivato in `.items-code-cache`,
con blocchi da 16.384 righe, identificativi stabili, Company normalizzata, Master Code
precalcolato e testo di ricerca generale. Il file originale `ref_pdb_dump.parquet` rimane
inalterato. Durante la preparazione, o se fallisce, si continua a leggere l'originale.
La pubblicazione e atomica e protetta da lock anche fra processi backend; dimensione e data
di modifica della sorgente invalidano automaticamente snapshot e risultati dei filtri.
Modifiche alle espressioni precalcolate richiedono di incrementare `CACHE_VERSION` in
`items_code_browse_cache.py`, per non riutilizzare copie preparate dal codice precedente.
Si conservano almeno gli ultimi due snapshot; quelli ulteriori vengono eliminati dopo un
giorno, alla preparazione successiva. Un aggiornamento deve sostituire atomicamente il
Parquet, come fa il recupero da PDB Settings, non modificarlo mentre viene letto.

La prima ricerca con un nuovo filtro richiede ancora una scansione. Conteggio esatto e
identificativi dei risultati vengono poi riutilizzati per le pagine successive, in una LRU
di massimo 64 MB e 32 filtri per processo. Gli identificativi usano 32 bit quando possibile
(64 bit per file oltre quattro miliardi di righe), permettendo di conservare insieme anche
quattro filtri che coprono tutto il dataset attuale. Non si conservano le righe complete in RAM.
Richieste identiche nello stesso processo condividono la scansione in corso; filtri diversi
non interferiscono. La paginazione senza filtri usa un intervallo di identificativi, senza
un ordinamento di milioni di righe con OFFSET. La memoria cache e un limite, non una
prenotazione: cresce solo quando serve. Filtri con troppi risultati mantengono il conteggio
senza memorizzare tutti gli identificativi e usano la paginazione SQL come fallback.

Ogni processo ammette al massimo due query DuckDB contemporanee, ciascuna con budget 128 MB
e due thread. La preparazione usa uno degli stessi slot, un thread e budget 256 MB.
Con i due worker di `backend/startup.txt` si hanno quattro slot query e al massimo 128 MB
di cache risultati, oltre alla memoria dell'applicazione, dei risultati temporanei e del
sistema operativo. Non e un limite alla RAM totale del processo. Quattro utenti possono
quindi navigare insieme senza generare query e cache illimitate. Il browser cancella le
richieste obsolete, ignora risposte tardive e conserva solo pagina corrente e righe
selezionate, non tutte le pagine visitate. La cancellazione HTTP non garantisce
l'interruzione di una scansione gia avviata nel backend.

`ITEMS_CODE_BROWSE_CACHE_DIR` puo spostare la cache su un disco locale veloce; il default e
accanto al Parquet, sul volume persistente. `ITEMS_CODE_BROWSE_CACHE_ENABLED=false`
disabilita lo snapshot derivato per diagnosi (paginazione e cache dei filtri restano attive).
La copia tecnica del dataset corrente occupa circa 192 MB e si prepara in circa 6 secondi
sul computer di sviluppo; le prestazioni Azure vanno misurate separatamente.

Benchmark locale ripetibile, dalla cartella backend, senza chiamate a SQL o worker:

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_items_code.py
```

Eventualmente aggiungere `--path C:\percorso\ref_pdb_dump.parquet`, `--search testo` o
`--company NOME`. Il test lancia anche quattro filtri diversi contemporaneamente.

### Modifiche Items Code

Reference PDB e nascosto all'apertura. Il toggle monta la seconda tabella, ma le righe
vengono richieste solo dopo una scelta esplicita: Company oppure `- FULL PDB -`.
I metadati non avviano la preparazione dello snapshot completo.

Per New Items, i dati sorgente e le colonne JSON espanse sono preparati per Company
e riutilizzati come tabelle Arrow immutabili: cache LRU di massimo 64 MiB e 8 Company
per processo. Le richieste concorrenti per la stessa Company condividono la preparazione.
Percorso, data di modifica, dimensione del Parquet e proiezione delle colonne identificano
la versione della cache. Le modifiche SQLite vengono sempre lette nuovamente e unite
prima dei filtri: non vengono conservate nella cache dei dati sorgente.
I due worker possono trattenere fino a 128 MiB aggiuntivi per questa cache, non l'intero
Reference PDB; il limite non comprende allocazioni temporanee o il resto dell'applicazione.

La tabella superiore conserva i valori modificati in `runtime.sqlite3`, tabella
`items_code_edits`, con chiave `(company, item_code)`. Non usa il numero di riga del
Parquet come chiave persistente: riordinare o recuperare la sorgente non perde le modifiche.
Il Parquet originale e le tabelle BS25/selezioni esistenti non vengono modificati.
La lettura combina i valori salvati con la sorgente prima di ricerca, filtri e paginazione.
Un valore NULL esplicito cancella il campo; un campo assente nella modifica conserva il
valore precedente. Ogni salvataggio batch e atomico; la fusione delle sole colonne inviate
avviene sotto una transazione SQLite, senza perdere aggiornamenti concorrenti su altri campi.

`PATCH /api/items-code/new-items/values` riceve `company`, `item_codes` (massimo 10000)
e `values`. Il server verifica esistenza e Company dei record, campi di supporto ammessi,
precisione dei numeri e formato `00_00_00` del Master Code, prima di scrivere.
Solo i campi da Prefix Code in poi della tabella superiore sono editabili.
Invio salva la cella; Ctrl+Invio applica anche alle righe selezionate oppure, senza
selezione, alle sole righe della pagina corrente. Escape/uscita dalla cella scartano
il testo non confermato. Copia/incolla superiore usa una copia delle caratteristiche
da Father Name in poi, escludendo i campi deselezionati nel menu; anche la copia dal
Reference PDB passa per lo stesso salvataggio. La copia resta in memoria del browser
fino al reload della pagina, mentre i valori incollati restano nel database runtime.
