# Valutazione integrazione PAC-IA in MC CODE

> Analisi storica, precedente al chiarimento del perimetro. Per l'implementazione
> effettiva basata su PDB e Master Code unificato vedere [pac-ai.md](pac-ai.md).

Analisi del 17 settembre 2026. La conversione da Anthropic al servizio Codex di lucianavm04 è tecnicamente fattibile. È riutilizzabile il collegamento già impiegato da BS25AI; occorre adattare anche dati, tassonomia, gestione dei job e output. La qualità della classificazione con il nuovo modello richiede una verifica su casi validati.

Questa attività comprende lettura del codice, dei file di esempio e della documentazione, confronto con MC CODE e verifica in sola lettura del worker operativo. Non sono state eseguite classificazioni LLM, installazioni o modifiche ai servizi. Questo documento è l'unico file aggiunto alla webapp.

## Materiale esaminato

Il percorso disponibile è `\\atena\Personal_Folders\Wilson Sgroi\Marco_Claude`, diverso dal percorso inizialmente indicato.

| File | Funzione |
| --- | --- |
| `script_A_preprocess.py` | Importa quattro Excel storici e costruisce `reference_index.db`. |
| `script_B_classificatore_6_v01.py` | Classificatore T1/T2/T3, ricerca web, giudice in una o due fasi, esportazione risultati. |
| `DM_OLD.xlsx` | Tassonomia usata effettivamente dallo script B: descrizioni e note dei codici legacy. |
| `DM_Master_v02.xlsx` | Tassonomia Master e colonne di raccordo. Presente nella cartella, ma non caricata dallo script B. |
| `Dataset_Target_Classificato.xlsx` | Esempio di 300 articoli già elaborati; non è lo storico di addestramento né un insieme di risposte umane certificate. |
| `DVD_DM_OLD_Classifier_Documentazione_v06.docx` | Descrive metodologia, benchmark e migrazione futura a DM Master, ancora da realizzare nel codice consegnato. |

I percorsi Windows di Marco, il campionamento di 300 righe e la lingua spagnola sono fissati nello script: vanno sostituiti con input e configurazione del job.

## Cosa fa PAC-IA

1. **Preparazione delle reference.** Lo script A importa `Dataset_Target_Codificati.xlsx`, `DVD_Anagrafica.xlsx`, `PDB_Iberia.xlsx` e `PDB_Italia.xlsx`. Costruisce le tabelle `dvd_codificati`, `dvd_anagrafica`, `pdb_reference` e `libelle_dm_map`. Questa preparazione va ripetuta quando cambiano le fonti, non per ogni articolo.
2. **T1, storico delle categorie.** Dalla coppia `Libellé famille` / `Libelle Gamme` ricava il codice prevalente e la percentuale storica. Soglie originali: 90% forte, 70% moderato. È un dato specifico del distributore DVD/Cadence.
3. **T2, confronto testuale.** Usa RapidFuzz `token_sort_ratio` sulle descrizioni dello storico DVD e sui record PDB del medesimo brand. Non invia l'intero PDB al modello. Il codice originale importa solo Iberia e Italia; senza brand valido salta la ricerca PDB. Non è lo stesso algoritmo BM25 usato da BS25.
4. **T3, arbitrato IA.** Quando candidati e soglie richiedono un arbitrato, passa all'LLM l'articolo, candidati, esempi simili e un sottoinsieme della tassonomia. L'output iniziale comprende codice, punteggio composito, etichetta `ALTO` / `MEDIO` / `DA VERIFICARE` e motivazione. Il punteggio è una formula euristica, non una probabilità di correttezza misurata.
5. **Giudice IA con ricerca web.** Sui record `ALTO` e `DA VERIFICARE` cerca informazioni sul prodotto, eventualmente prova una query inglese e produce `CONFERMATO`, `CORRETTO` o `INCERTO`. I record `MEDIO` sono esclusi da questo passaggio nel codice originale. Se il contesto tassonomico è insufficiente, amplia i candidati e richiede una seconda valutazione.

La funzione chiamata `search_taxonomy` esegue un confronto lessicale RapidFuzz: non usa embeddings, anche se i commenti la definiscono ricerca semantica. Il sistema recupera piccoli insiemi di evidenze prima delle chiamate LLM.

Le chiamate Anthropic sono concentrate in `tier3_llm`, `translate_taxonomy`, `run_web_search` e nelle due fasi di `giudice_llm`. Si possono sostituire conservando le regole deterministiche, con output JSON strutturati, motivazioni verificabili ed evidenze.

## DM_OLD e Master Code richiedono un raccordo esplicito

I nomi si riferiscono allo stesso ambito di classificazione, ma i file consegnati rappresentano versioni diverse. Lo script B carica solo `DM_OLD.xlsx` e produce `28_SELLOUT_DM`. La colonna `XX_SELLOUT_DM_MASTER` dell'esempio è vuota in tutti i 300 record.

La documentazione, sezione 7.3, propone come lavoro successivo di mantenere T1/T2/T3 in DM_OLD, convertire i candidati e far giudicare il risultato in DM Master. Questa migrazione non risulta implementata nello script.

Controlli sui file disponibili:

- La colonna `DM CODE SELLOUT OLD` della tabella di raccordo contiene 1.201 valori distinti non vuoti; 9 hanno più destinazioni Master. Ad esempio `06_04_01` può diventare `06_04_11` oppure `06_04_12` (righe Excel 164–165).
- Questo dato non dimostra una copertura del 99,25% della vecchia tassonomia. Fra i 1.144 codici nel formato numerico valido di `DM_OLD.xlsx`, 102 non compaiono esattamente in quella colonna del raccordo.
- Già nell'output di esempio, 12 articoli usano complessivamente 6 codici finali senza corrispondenza esatta in `DM CODE SELLOUT OLD`. Anche `OLD CLASSIFICATION` va esaminata: contiene annotazioni e aggregazioni di più codici, quindi non è un dizionario utilizzabile senza normalizzazione.
- Nel file Master ci sono 1.225 codici distinti non vuoti. Lo snapshot **locale Dev** di MC CODE ne ammette 1.090: 258 codici Excel sono assenti dallo snapshot e 123 dello snapshot sono assenti dall'Excel. Queste differenze richiedono riconciliazione; non dimostrano da sole quale fonte sia errata.
- La reference canonica della webapp è oggi derivata dai codici presenti nel Parquet PDB e conserva i tre livelli numerici. Non sostituisce una tassonomia completa con descrizioni e note di classificazione.

Per la migrazione serve quindi una versione esplicita della tassonomia autorevole e una corrispondenza verificata. Le ambiguità possono passare al giudice; i codici senza raccordo devono restare segnalati. Il formato `00_00_00` da solo non basta a validare un risultato.

## Dati disponibili e mancanti

Su lucianavm04 è presente `panel_data_utilities/scripts/jobs/pdb/ref_pdb_dump.parquet`. L'health check del worker restituisce `ready`: 2.182.145 righe sorgente e 2.062.826 documenti indicizzati. Il servizio `pdb-worker.service` è attivo. I tre file principali del worker coincidono, per SHA-256, con il checkout locale `panel_data_utilities/functions/pdb` esaminato.

Il Parquet corrente contiene descrizione, company, brand, prefisso, father name, tre livelli MC, confezionamento e altri attributi. Permette di evitare gli Excel PDB Iberia/Italia come sorgente operativa, ma i codici devono essere trattati nella loro versione corretta: il PDB corrente espone livelli MC, mentre lo storico originale lavorava in DM_OLD.

Nella cartella PAC-IA mancano `reference_index.db`, `Dataset_Target_Codificati.xlsx` e `DVD_Anagrafica.xlsx`. Il database e i file DM/DVD non sono emersi neppure nella ricerca limitata ai percorsi pertinenti della VM; non è stata svolta una ricerca indiscriminata su tutta la macchina. Recuperare `reference_index.db` potrebbe essere sufficiente per conservare T1 e la memoria DVD; in alternativa servono le due sorgenti storiche.

La versione corrente del PDB non espone le categorie `Libellé` in colonne dedicate; il campo `extra` valorizzato è testo, non un oggetto strutturato equivalente. Anche il Parquet locale New Items esaminato ha dettagli `manufacturer`, `channel_raw`, `customer_raw` e `file_name`, senza le categorie DVD. La presenza del PDB completo non garantisce quindi che si possa ricostruire T1.

Il file degli articoli da classificare viene invece sostituito dagli item selezionati in MC CODE. Per generalizzare PAC-IA ad altre company occorre una mappa dei campi per company, una lingua configurabile e uno storico appropriato. Se le categorie non esistono, T1 va dichiarato non disponibile: il percorso PDB + IA rimane fattibile, ma non replica integralmente il classificatore DVD.

## Ripartizione proposta

| Componente | Responsabilità |
| --- | --- |
| Frontend MC CODE | Pulsante PAC-IA, selezione degli articoli, avanzamento, nuove colonne, dettaglio evidenze, gestione del retry. |
| Backend webapp | Recupera gli input dallo snapshot, normalizza i campi, verifica ammissibilità, registra i job, invia le richieste al worker, acquisisce gli aggiornamenti, valida i codici restituiti e salva i risultati nel runtime. |
| Worker Python su lucianavm04 | Prepara gli indici, consulta PDB e storico, calcola T1/T2 e punteggi, seleziona il contesto tassonomico, orchestra T3, ricerca web e giudice, mantiene checkpoint e risultati dei job. |
| Codex avviato dal worker | Esegue i passaggi linguistici e decisionali su un contesto limitato: arbitrato, eventuale traduzione, ricerca web e giudizio. Restituisce JSON conforme allo schema. |

Tenere anche la parte deterministica vicino al PDB evita trasferimenti estesi e scansioni nel processo web. Il backend riceve evidenze e risultati, non una copia del PDB per ogni richiesta. Il modello riceve candidati e sezioni di tassonomia, non milioni di record.

Il codice attuale conferma il percorso riutilizzabile: `mc_code_bs25ai.py` chiama `POST /v1/reviews`; `functions/pdb/app.py` avvia il client `CodexAppServer`; quest'ultimo esegue `codex app-server --stdio` come `lucianauser`, con la sessione già configurata e il modello impostato nel worker. Per PAC-IA servono prompt e schemi propri: l'endpoint BS25AI attuale è specializzato nella revisione di tre proposte.

La sostituzione elimina le chiamate dirette Anthropic. La ricerca web deve usare il percorso abilitato nel worker Codex, con verifica reale della disponibilità dello strumento, salvataggio delle fonti e uno stato esplicito se la ricerca fallisce. L'health check non prova da solo l'esecuzione di una ricerca web o di un turno LLM; in questa analisi non sono stati avviati.

Le traduzioni, se conservate, vanno riutilizzate per versione della tassonomia e lingua. Il vecchio script le rigenera a ogni esecuzione e le conserva solo nella memoria di quella sessione.

## Flusso di integrazione

Contratto proposto, da implementare:

1. `POST /api/mc-code/pac-ia` riceve ambiente, company e item selezionati. Registra il job e risponde `202` con gli identificativi accettati.
2. Il backend invia a un endpoint PAC-IA del worker un `request_id` stabile, input normalizzati e versioni attese delle reference. Un reinvio dello stesso identificativo non deve duplicare le elaborazioni.
3. Il worker salva il lavoro e aggiorna fasi quali preparazione, T1/T2, T3, web e giudice. Prevede concorrenza limitata e ripresa dai checkpoint.
4. Il backend recupera progressi e risultati con richieste brevi, valida schema, identità dell'articolo e appartenenza dei codici alla reference concordata, quindi persiste i campi `pac_ia_*`.
5. MC CODE aggiorna le righe durante l'elaborazione, come già fa per BS25/BS25AI. Il risultato PAC-IA compare in colonne dedicate.

La modalità utente rimane quella già nota, ma per PAC-IA è opportuno persistere anche la coda sulla VM. Il flusso attuale usa `BackgroundTasks` nella webapp e una chiamata HTTP al worker che resta aperta durante il turno LLM, con timeout predefinito di 900 secondi. Il documento PAC-IA riporta circa 2h45 per 300 articoli con il vecchio sistema: è un dato storico, non una stima delle prestazioni di Codex. Un lotto completo non dovrebbe dipendere da un'unica connessione aperta o sopravvivere solo nella memoria del backend.

I metadati del risultato dovrebbero includere versione input, PDB, tassonomia, regole/prompt e identificativi dei turni. La persistenza web può estendere `RuntimeStore` con tabelle PAC-IA, lasciando lo snapshot dei dati sorgente separato dai risultati.

## Colonne proposte

| Gruppo | Campi |
| --- | --- |
| Vista principale | Stato PAC-IA, Master Code proposto, affidabilità iniziale, esito del giudice, motivazione. |
| Candidati | Codice T1 e percentuale storica; codice T2, score e fonte; codice T3. Ogni codice deve indicare la versione tassonomica a cui appartiene. |
| Tracciabilità | DM_OLD originario se applicabile, Master prima del giudice, Master finale, score composito, motivazione del classificatore. |
| Giudice | Esito, motivazione verificabile, evidenze e URL, numero di fasi, eventuale necessità di revisione umana. |
| Esecuzione | Fase, errore tecnico, versioni delle reference, data elaborazione. |

Le etichette iniziali e il giudizio finale vanno distinti: il vecchio script non ricalcola `LABEL` e `SCORE_COMPOSITO` dopo una correzione del giudice. Un errore tecnico deve essere distinto da un'autentica incertezza di classificazione.

Nel frontend l'ammissibilità attuale della selezione è legata agli stati BS25/BS25AI: servirà una regola autonoma per PAC-IA. Anche gli oggetti inviati ai worker esistenti vanno controllati: oggi escludono soltanto i prefissi `bs25_` e `aibs25_`; i nuovi output `pac_ia_*` non devono rientrare involontariamente negli input di altri classificatori.

L'integrazione richiesta riguarda proposte in nuove colonne. Un eventuale comando successivo per adottare una proposta PAC-IA richiede un contratto di selezione dedicato: l'attuale `/bs25/select` accetta solo un rank fra le tre proposte BS25.

## Correzioni necessarie e verifica

- Validare i codici contro tassonomia e candidati consentiti. Lo script originale verifica soprattutto la forma del codice; il vincolo scritto nel prompt non è una validazione applicativa.
- Separare eccezioni, timeout e JSON invalidi dagli esiti `INCERTO`. Il codice originale può conservare un candidato dopo un errore LLM e nascondere il problema nel risultato aggregato.
- Conservare l'algoritmo RapidFuzz per un confronto fedele. Sostituirlo con BS25 può essere un'evoluzione, ma modifica ranking e punteggi e va valutato separatamente.
- Rendere configurabile il perimetro del giudice. L'esclusione dei record `MEDIO` è una scelta del progetto originale, non una proprietà generale dell'affidabilità.
- Normalizzare e riconciliare le versioni DM prima di unire candidati legacy e PDB corrente.

Il workbook di esempio contiene 161 `ALTO`, 88 `MEDIO` e 51 `DA VERIFICARE`; il giudice produce 138 conferme, 67 correzioni e 7 esiti incerti, con 31 seconde fasi. Questi conteggi coincidono con il documento, ma sono decisioni del modello, non misure di accuratezza rispetto a una verità umana.

La verifica della conversione dovrebbe partire da un campione validato da una Product Specialist, includendo codici invariati, mapping multipli, codici senza raccordo, brand/categorie mancanti e disaccordi T1/T2. Vanno controllati anche retry idempotenti, recupero dopo riavvio e isolamento dai risultati BS25. Non si può garantire identità dei risultati cambiando modello, PDB e tassonomia.

## Punti di intervento nel codice

- Webapp: `backend/api/mc_code.py`, nuovo servizio PAC-IA accanto a `backend/services/mc_code_bs25ai.py`, `backend/services/mc_code_local_store.py`, `frontend/src/components/McCode.tsx`.
- Worker: repository adiacente `panel_data_utilities`, cartella `functions/pdb`; nuova pipeline PAC-IA, adapter delle reference e schemi, riuso di `codex_app_server.py` con parametri e prompt appropriati.
- Reference: import controllato di tassonomia/raccordo, recupero storico DVD o percorso esplicito senza T1, collegamento al refresh del PDB già presente.

La sostituzione di Anthropic è circoscritta. Le parti sostanziali dell'integrazione sono la riconciliazione DM_OLD/Master, la disponibilità dello storico per T1 e la trasformazione dello script batch in elaborazioni persistenti consultabili da MC CODE.
