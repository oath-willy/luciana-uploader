# Accesso alla webapp Luciana

Il sito è https://yellow-forest-0ad79d503.6.azurestaticapps.net/.
Il Navigator è nella radice. I vecchi collegamenti `/navigator/...` vengono
reindirizzati mantenendo pagina, parametri e frammento. Home, sezione Tests e i
due strumenti di esecuzione libera R sono stati rimossi, anche dal backend.

## Ufficio e accesso remoto

L'ufficio accede direttamente dall'IP pubblico `151.14.55.196/32`, senza VPN.
Da remoto occorrono il profilo Azure VPN già distribuito e la configurazione
proxy automatica riportata sotto. Il solo collegamento VPN, essendo split
tunnel, non cambia l'IP pubblico con cui si raggiungono i siti Internet.

Configurazione Windows, una volta per ciascun utente:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\set-webapp-vpn-proxy.ps1
```

Riavviare il browser. Da remoto connettere Azure VPN prima di aprire il sito.
Il PAC è pubblicato con HTTPS all'indirizzo
https://rstudio-ks.westeurope.cloudapp.azure.com/luciana-proxy.pac.
Quando il DNS VPN risolve RStudio in `10.0.0.5`, instrada solo i due host Luciana
nel proxy `10.0.0.5:3128`; dall'ufficio usa il collegamento diretto. Gli altri
siti rimangono diretti. Usare il DNS del sistema: un DNS personalizzato nel
browser può impedire il riconoscimento della VPN.

Il proxy accetta solo client `172.27.240.0/24` e solo connessioni HTTPS ai due
host Luciana. La porta 3128 nel NSG è aperta esclusivamente alla rete VPN.
La Static Web App accetta solo l'ufficio e l'IP di uscita del proxy
`20.160.158.80/32`. Le connessioni HTTPS attraversano il proxy senza decifrazione.

Per ripristinare la precedente configurazione proxy Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\set-webapp-vpn-proxy.ps1 -Disable
```

L'accesso remoto dipende da **lucianavm04 accesa**, che ospita DNS e proxy.
Se viene deallocata dal Control Panel, un utente dall'ufficio o un amministratore
dal portale Azure deve riaccenderla. lucianavm03 non serve per accedere al sito.

### Proposta: accesso VPN con entrambe le VM di lavoro spente

Spostare DNS e proxy in una VM Ubuntu dedicata sempre accesa nella VNet
esistente, separata da lucianavm03/04. Configurazione proposta: Standard_B1s
(1 vCPU, 1 GiB RAM), disco Standard HDD LRS da 32 GiB, IP pubblico Standard
statico. SSH e HTTPS di configurazione limitati a ufficio/VPN; porta proxy
limitata alla sola VPN. Aggiornare DNS del profilo VPN, PAC, pacchetto client e
IP consentito nella SWA. Il gateway Azure VPN esistente viene mantenuto.

Stima base per 730 ore/mese, listino West Europe in EUR verificato il 5/10/2026:

| Risorsa | Costo stimato al mese |
| --- | ---: |
| VM Linux B1s (0,01056 €/ora) | 7,71 € |
| IP pubblico Standard (0,0044 €/ora) | 3,21 € |
| Disco S4 LRS | 1,35 € |
| Totale base | **12,27 €** |

IVA, traffico e operazioni disco a consumo sono aggiuntivi. La stima usa il
[listino retail Azure](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices);
il prezzo effettivo dipende dal contratto della sottoscrizione. Questa risorsa
richiede una scelta esplicita prima della creazione e non è stata creata.

## Autenticazione e backend

Il login usa l'applicazione Entra `Luciana-WebApp`, nel tenant aziendale
`3630ff06-11ea-4763-960a-fc74e8780220`. La policy dedicata `MFA - Luciana WebApp`
richiede MFA per questa applicazione anche dall'ufficio. Le API autorizzano sul
server gli account `@key-stone.it` e gli indirizzi espliciti in `APP_ALLOWED_EMAILS`
(predefinito `matteo@finstat.it`, che deve essere ospite del tenant).
Le azioni di accensione/spegnimento VM richiedono `APP_ADMIN_EMAILS`, inizialmente
`wilson.sgroi@key-stone.it`.

Il frontend chiama `/api/...` sul proprio dominio. Azure App Service richiede
il provider Easy Auth `Azure Static Web Apps (Linked)`; i normali endpoint del
backend non sono utilizzabili direttamente, neppure falsificando le intestazioni
utente. Le API disabilitano la cache e la documentazione pubblica è disattivata.
Il backend rimane su un hostname pubblico con controllo di autenticazione.

Eccezioni: `/ping` è un controllo di salute senza dati; i quattro endpoint PUT
snapshot MC CODE/legacy Codex rimangono raggiungibili dai publisher esistenti,
con il loro token dedicato e confronto a tempo costante. Non permettono accesso
anonimo ai dati. Non cambiare `excludedPaths` in Easy Auth senza mantenere
questa verifica applicativa.

Le chiavi SSH presenti precedentemente nel repository sono state revocate su
entrambe le VM. La sostituzione è conservata in Key Vault
`ssh-private-key-lucianauser`, con controllo delle identità dei server tramite
`backend/keys/known_hosts`. Nessuna chiave privata viene inclusa nei pacchetti.
La vecchia password SQL nel codice è stata rimossa; quella attualmente configurata
in Azure era già diversa.

Il segreto dell'app Entra, conservato nelle impostazioni SWA e in Key Vault
`webapp-aad-client-secret`, scade il **5 ottobre 2027**. Rinnovarlo prima della
scadenza e aggiornare entrambe le destinazioni. Non copiare i valori nei log o
nel repository.

## Sviluppo e rilascio

`scripts/start-local-dev.ps1` carica le impostazioni Azure senza stamparne i
valori e avvia frontend/backend su loopback. Il bypass di login locale è
consentito al backend solo per connessioni effettive da localhost.
Le API locali usano la chiave Key Vault nuova e gli IP pubblici delle VM;
la versione Azure usa gli IP privati tramite l'integrazione VNet esistente.

Il backend si confeziona con `scripts/package-backend.py`, escludendo dati,
virtualenv, test, file `.env` e chiavi private. I dati persistenti Azure sono in
`/home/data`, fuori dalla cartella di distribuzione. Il workflow frontend mantiene
`REACT_APP_BACKEND_URL` vuoto e usa il gateway sullo stesso dominio.

La Static Web App usa la policy di pubblicazione **GitHub**, con token OIDC del
workflow: un token Azure passato al solo comando `swa deploy` viene rifiutato.
Usare il workflow del repository per pubblicare il frontend.

Le dipendenze compatibili sono state aggiornate, comprese Axios, React Router e
le due dipendenze che presentavano avvisi critici. L'audit finale non segnala
avvisi critici; rimangono 70 avvisi nella catena di strumenti di Create React
App (3 bassi, 4 moderati e 63 alti). Serve un aggiornamento separato della
toolchain per eliminarli: `npm audit fix --force` propone una sostituzione
incompatibile di `react-scripts` e non deve essere eseguito alla cieca.
