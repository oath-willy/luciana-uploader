# Fast Track nella webapp Luciana

Il gruppo Navigator **Fast Track > Dashboard** contiene Gold monitoring, Forecast e Settings.
Il modulo riusa le dashboard HTML/JavaScript esistenti e gli script R di collegamento. Non avvia
RStudio, non esegue i rendering Quarto dei modelli e non modifica il repository sorgente o i dati sul blob.

## Settings e pubblicazione

Il riquadro **Aggiornamento dashboard** recupera pagine, asset, runtime e script R. Si possono
recuperare entrambe le dashboard oppure una sola dopo la prima inizializzazione. Il primo recupero
da un nuovo utente deve includerle entrambe. I documenti interni e i modelli R non sono pubblicati.

Il riquadro **Aggiornamento dati** offre quattro azioni:

- Monitoring `link_runs.R`: seleziona le ultime run complete con il contratto della dashboard.
- Monitoring `collection_status.R`: rigenera lo stato della raccolta da Bronze, Silver e Gold.
- Forecast `link_runs.R`: collega l'Excel dell'ultima run completa.
- Aggiorna tutti i dati: esegue i tre script in sequenza.

Ogni azione ha stato, errore, conferma di completamento e data dell'ultima esecuzione pubblicata
con successo. Le date dell'ultima operazione riuscita restano visibili anche dopo un errore.
Un solo aggiornamento Fast Track puo essere attivo: la prenotazione e condivisa dai worker tramite SQLite.
Gli aggiornamenti lunghi girano in background; la pagina consulta periodicamente lo stato.

I sorgenti sono acquisiti in una nuova versione locale. Gli script vengono eseguiti come l'utente
sorgente in una nuova directory della VM, usando copie del codice e symlink ai dati del blob.
Prima della pubblicazione si verificano file, contratto dei Parquet e workbook. Il puntatore alla
versione visibile cambia in una sola transazione SQLite dopo il completamento. Un errore lascia
disponibile la versione precedente. Le pagine aperte usano URL con versione immutabile, cosi non
mescolano file di due aggiornamenti. Dopo il completamento, riaprire la pagina della dashboard
dal menu carica la nuova versione.

Solo le pagine Gold monitoring e Forecast occupano tutta l'area disponibile, senza margini o
intestazione della webapp. Il menu parte collassato e riprende lo sfondo scuro e i colori delle
dashboard; resta espandibile. Settings e le altre pagine conservano il layout normale e la
precedente preferenza di apertura del menu. Queste regole sono isolate in `FastTrackLayout.module.css`.

Al primo utilizzo: recuperare entrambe le dashboard e poi premere **Aggiorna tutti i dati**.
L'avvio individuale di uno script inizializza solo i dati che quello script produce.

## Configurazione

| Variabile backend | Default / funzione |
| --- | --- |
| `FAST_TRACK_ENABLED` | `true`; impostare `false` per disabilitare tutti gli endpoint |
| `FAST_TRACK_SOURCE_USER` | `wilson_sgroi` |
| `FAST_TRACK_SOURCE_ROOT` | Se omessa, `/home/<utente>/dtl_fast-track` |
| `FAST_TRACK_LOCAL_DIR` | `backend/data/fast-track` in locale; `/home/data/fast-track` in App Service |
| `FAST_TRACK_RSCRIPT` | `/opt/R/4.5.2/bin/Rscript` |
| `FAST_TRACK_JOB_TIMEOUT_SECONDS` | `3600`, per l'esecuzione degli script |
| `FAST_TRACK_FILE_TIMEOUT_SECONDS` | `180`, per la lettura di un file |
| `FAST_TRACK_OPTIMIZATIONS_ENABLED` | `true`; `false` ripristina le letture dirette senza cache e riuso SSH |
| `FAST_TRACK_AUTH_MODE` | In locale `local`, consentito solo da loopback; in Azure disabilitato finche non si configura `linked` |

La connessione riusa le credenziali e le configurazioni SSH gia utilizzate per PDB e verifica
le chiavi host note di lucianavm04 prima dell'autenticazione. `FAST_TRACK_SSH_HOST_KEY_SHA256`
permette di configurare un diverso fingerprint verificato dall'IT. L'utente SSH
di servizio deve poter eseguire `sudo -n -H -u <utente sorgente> python3`; non si aprono nuove porte
sulla VM. R e le librerie richieste dagli script devono essere installati per l'utente sorgente.

Per passare a Lorenzo impostare **solo** `FAST_TRACK_SOURCE_USER=lorenzo_rosso`, lasciando
`FAST_TRACK_SOURCE_ROOT` omessa se il repository ha lo stesso nome. Recuperare entrambe le dashboard
e aggiornare tutti i dati. Le versioni precedenti restano associate all'utente che le ha generate.

## Accesso in Azure

Gli endpoint Fast Track non accettano accessi anonimi in Azure. Prima del deploy operativo:

`staticwebapp.config.json` contiene una regola `/api/*` autenticata prima del rewrite React,
per preservare gli endpoint del backend collegato.

1. Collegare `luciana-backend` a `luciana-frontend` mediante il backend App Service di Static Web Apps,
   mantenendo Easy Auth obbligatorio e l'accesso al backend attraverso il gateway collegato. Il frontend
   e gia sul piano Standard richiesto da questa integrazione.
2. Impostare `FAST_TRACK_AUTH_MODE=linked` e verificare `WEBSITE_AUTH_ENABLED=true` nell'ambiente
   App Service. Il flag descrive il requisito della piattaforma: non sostituisce l'abilitazione di Easy Auth.
3. Compilare il frontend con `REACT_APP_BACKEND_URL` vuota, cosi anche le altre API esistenti usano
   `/api` sul gateway. **Il workflow attuale imposta ancora l'URL diretto**: adeguare quel valore
   insieme al collegamento prima del rilascio, per evitare di interrompere le altre pagine.
4. Verificare un utente interno, un utente non autorizzato e la richiesta diretta anonima a un Parquet.

Il modulo controlla il principal autenticato inoltrato dal gateway, il provider Entra e gli utenti
gia ammessi nel Navigator. Imporre l'autenticazione sul gateway e indispensabile: un header scritto
da un client su un backend pubblico non e una prova di identita. Se la configurazione manca, il modulo
risponde 503. Le nuove richieste frontend Fast Track usano sempre il gateway relativo in produzione.

Le risposte dei file sono private, richiedono autenticazione e consentono l'incorporamento solo dalla
webapp configurata. I trasferimenti dei dati via SSH sono in streaming, con al massimo quattro letture
contemporanee per worker. Non vengono salvati Parquet o Excel su disco nel backend. I modelli `.rds`, gli script
`.R`, i documenti e i percorsi fuori dalle directory consentite non sono esposti.

## Prestazioni e compatibilita con gli aggiornamenti

Le ottimizzazioni sono implementate solo in `backend/services/fast_track_performance.py` e
nel servizio di integrazione. Non modificano HTML, JavaScript o R in `dtl_fast-track/dashboard`,
quindi il recupero di nuovi sorgenti non le sovrascrive. L'autore puo continuare a sviluppare
le dashboard mantenendo i punti di ingresso e il contratto dati supportato dall'integrazione.

Ogni worker mantiene al massimo quattro connessioni SSH per le letture, usate in modo esclusivo.
Solo un comando terminato e consumato completamente restituisce la connessione al pool;
interruzioni, errori di trasporto e letture incomplete la chiudono. Alla richiesta successiva
si scartano connessioni inattive da 60 secondi, piu vecchie di 5 minuti o non piu valide.
Gli aggiornamenti dei sorgenti e gli script R mantengono connessioni dedicate.
La chiave SSH viene conservata solo in memoria per 5 minuti; una nuova configurazione o un
file chiave modificato forza una nuova lettura. Un'autenticazione rifiutata rilegge la chiave
e riprova una sola volta, per gestire anche la rotazione del segreto Key Vault.
La verifica della chiave host resta obbligatoria per ogni nuova connessione.

La cache dati e privata al processo: massimo **32 MiB per worker**, **512 file**, massimo
**8 MiB per file**, scadenza **5 minuti**. I file piu grandi continuano a essere trasferiti
in streaming. Le richieste simultanee dello stesso file piccolo condividono un unico download;
solo trasferimenti completi riusciti entrano in cache. Errori e file mancanti non sono memorizzati.
Con i due worker attuali il limite dei contenuti in cache e 64 MiB complessivi, oltre ai buffer
temporanei di trasferimento. Non viene creata una cache persistente sul filesystem.

La chiave della cache comprende directory runtime, destinazione SSH, utente sorgente, revisione
pubblicata e percorso. Una nuova pubblicazione utilizza automaticamente nuove voci: non riceve
i dati della versione precedente, che resta disponibile alle pagine gia aperte. Autenticazione
e validazione di versione/percorso avvengono prima di ogni accesso alla cache; le risposte HTTP
restano private e rispettano le regole del gateway. La cache non e condivisa fra worker o istanze.

Per annullare tutte le ottimizzazioni impostare `FAST_TRACK_OPTIMIZATIONS_ENABLED=false` e
riavviare il backend. La pubblicazione, gli aggiornamenti e i dati originali non cambiano.
Il numero di richieste e il lavoro nel browser restano determinati dal codice delle dashboard:
le ottimizzazioni del backend riducono i collegamenti ripetuti, senza sostituire caricamenti
progressivi o altre migliorie che l'autore potra implementare nel JavaScript.

## Disabilitazione e rimozione

Per disabilitare: `FAST_TRACK_ENABLED=false` nel backend e `REACT_APP_FAST_TRACK_ENABLED=false`
nella build frontend. I dati originali e la pipeline R continuano a funzionare indipendentemente.

Per rimuovere il codice, eliminare i due collegamenti Fast Track in `backend/main.py`, gli import,
il gruppo di navigazione e le tre route in `frontend/src/pages/Navigator.tsx`. Rimuovere quindi:

- `backend/api/fast_track.py`, `backend/services/fast_track.py`, `backend/services/fast_track_remote.py`,
  `backend/services/fast_track_performance.py` e i test dedicati;
- `frontend/src/components/fastTrack/` e i test dedicati;
- le variabili `FAST_TRACK_*`, `REACT_APP_FAST_TRACK_ENABLED` e le due righe Fast Track nello script di avvio locale.

La regola `/api/*` di Static Web Apps puo restare se il gateway viene usato dalle altre API.

Le sole directory generate sono `FAST_TRACK_LOCAL_DIR` e, per ogni utente usato sulla VM,
`~/.local/share/luciana-fast-track-webapp/`. Dopo aver fermato i job si possono eliminare queste
directory verificate, senza seguire i symlink ai dataset. **Non rimuovere `/mnt`, il repository
`dtl_fast-track` o le directory PDB.** Non ci sono servizi systemd, cron o configurazioni nginx da annullare.
