# PAC-AI in MC CODE

PAC-AI classifica i `pdb_new_items` usando lo storico PDB e la classificazione
Master Code corrente, comprese le indicazioni di `mc_desc`. Può partire anche
per articoli già analizzati o con una scelta BS25 salvata. Produce una proposta
indipendente e non modifica automaticamente la codifica salvata.

## Ripartizione del lavoro

| Componente | Responsabilità |
| --- | --- |
| Backend | Recupera gli articoli dallo snapshot, seleziona gli attributi di origine, registra richieste e risultati nel runtime persistente, invia job e legge lo stato, valida i codici contro la tassonomia corrente. |
| Worker lucianavm04 | Cerca sull'intero indice PDB, prepara esempi e tassonomia, esegue classificazione e revisione con Codex come `lucianauser`, conserva coda e checkpoint. |
| Pagina MC CODE | Avvia fino a 100 articoli per richiesta; mostra avanzamento, codice, affidabilità qualitativa, classificazione, motivazione e precedenti citati; permette di riprovare i job falliti. |

I due switch senza etichetta, nei gruppi BS25 e PAC-AI, controllano separatamente la
visibilità. Quello BS25 include stato, tre proposte e BS25AI. Nascondere un gruppo
non cancella risultati, selezioni o elaborazioni. Sono stati rimossi pulsanti
e colonne segnaposto Fuzzy Lookup / AI Lookup.

Gruppo e intestazioni BS25 sono blu; PAC-AI usa il verde acqua. Le celle condividono
tipografia e indicatori di avanzamento. A riga compatta resta una sola linea con
ellissi e lo spinner durante l'elaborazione; espandendo si vedono barra e dettagli.

## Elaborazione

1. Il backend invia un ID idempotente, gli attributi dell'articolo e lo SHA-256 del
   proprio `pdb_mc_classification.parquet`. Il worker accetta la stessa versione.
2. La ricerca usa l'indice FTS/BM25 dell'intero PDB, senza vincolo di company o brand
   e senza dipendere dalle tre proposte BS25. Esclude il record stesso e i codici
   fuori tassonomia. Il prompt riceve un campione deduplicato di precedenti.
3. Un primo passaggio Codex propone un codice e può chiedere fino a due ricerche
   aggiuntive nello storico. Sono disponibili le note dei candidati e un file con
   l'intera tassonomia, consultabile dal modello.
4. Un secondo passaggio, in un thread distinto, verifica sempre la proposta.
   Usa effort `xhigh` se il primo passaggio è incerto o a bassa affidabilità,
   altrimenti `low`. Il client condiviso con BS25AI usa `gpt-5.6-sol` tramite
   `codex app-server --stdio` e la sessione di `lucianauser`.
5. Worker e backend validano il risultato. `completed` può contenere una proposta
   `ambiguous`/`unresolved`, mostrata come **Da verificare**. Gli errori tecnici
   producono invece `failed`, con azione **Riprova PAC-AI**.

Non vengono usati mapping SellOut/FastTrack/Flash, categorie DVD, ricerche web,
API Anthropic o risultati di altri classificatori come evidenze. Le frequenze
descrivono solo il campione recuperato; l'affidabilità è qualitativa.

## Persistenza e recupero

Il backend usa `pac_ai_jobs` nel runtime SQLite MC CODE, separato dallo snapshot e
dalle selezioni BS25. Il worker usa `data/pac_ai_jobs.sqlite3`: una elaborazione
PAC-AI concorrente, lease da 120 secondi e heartbeat ogni 20. Conserva contesto e
prima proposta; dopo un riavvio riprende dal checkpoint completato. Un passaggio
LLM interrotto prima del checkpoint può essere rieseguito.

La pagina interroga il backend ogni 3 secondi durante il lavoro e ogni 15 secondi
a riposo. L'LLM lavora nella coda persistente anche a pagina chiusa. Al ritorno,
il backend recupera gli esiti e reinvia con lo stesso ID eventuali richieste non
ancora ricevute dal worker. Una variazione incompatibile delle reference richiede
un nuovo tentativo.

## Configurazione e API

Backend: `PAC_AI_WORKER_URL` e `PAC_AI_WORKER_TOKEN` sono opzionali e usano
`BS25AI_WORKER_URL` / `BS25AI_WORKER_TOKEN` quando assenti.
`PDB_MC_CLASSIFICATION_LOCAL_PATH` indica la reference già sincronizzata;
il default è nella directory dati MC CODE.

Worker:

- `PDB_MC_CLASSIFICATION_PATH`: default `scripts/jobs/pdb/pdb_mc_classification.parquet`.
- `PAC_AI_JOBS_DB`: default `functions/pdb/data/pac_ai_jobs.sqlite3`.
- `PAC_AI_WORKER_TOKEN`: opzionale, fallback su `BS25AI_WORKER_TOKEN`.
- `PAC_AI_CODEX_TIMEOUT_SECONDS`: timeout per passaggio, default 900 secondi.
- Restano valide `PDB_REF_DUMP_PATH`, `PDB_REF_INDEX_PATH`, `CODEX_EXECUTABLE`.

Backend: `POST /api/mc-code/pac-ai` con `environment`, `company`, `item_codes`;
`GET /api/mc-code/pac-ai/status?environment=dev&company=...`.
Worker con bearer: `POST /v1/pac-ai/jobs`, `POST /v1/pac-ai/status`.
`GET /health` include versione e disponibilità PAC-AI.

Da un PC esterno alla rete Azure serve accesso alla rete privata o un tunnel SSH;
non è necessario esporre pubblicamente la porta 8094.

## Verifiche del 17 settembre 2026

64 test backend e 15 test worker superati. Test UI su avvio indipendente da BS25
e visibilità dei gruppi; build frontend e controllo TypeScript. La verifica
TypeScript usa TS 5.9.3 perché alcune dichiarazioni delle dipendenze installate
richiedono TS 5.

Prova reale con Codex di `lucianauser`: IVOCLAR `000640459`, “SR Nexco Paste Effect
T 2.5g clear”, completato con `37_03_01`, confermato dal revisore e due precedenti
PDB di altre company. Questo verifica il percorso, non l'accuratezza generale.
Worker installato e servizio riavviato sulla VM. Backend e frontend pubblicati
su Azure il 17 settembre 2026 dal commit `4d5fc6f`; entrambe le pipeline GitHub
sono concluse con successo (run `35243589314` e `35243589393`). Verificato il
bundle online `main.c4be5fb9.js`, inclusi PAC-AI e i due toggle. La stessa prova
è stata completata anche dal backend Azure, sull'ambiente dati `dev`, con
risultato `37_03_01` confermato e due evidenze PDB.
