# BS25AI worker (lucianavm04)

Servizio locale da eseguire come utente `sole_abate`. Espone un endpoint autenticato e usa
`codex app-server` con un thread e un Goal persistente per ogni item. `low` usa
`gpt-5.6-sol`/`low` senza rete; `xhigh` riprende lo stesso thread, abilita la rete e usa la
reference canonica inviata dal backend.

## Provisioning (non eseguito)

1. Copiare questa directory in `/home/sole_abate/luciana-bs25ai-worker`.
2. Estrarre i quattro file di `handover_llm_bundle.zip` nella directory indicata da
   `BS25AI_HANDOVER_DIR`.
3. Creare `.venv`, installare `requirements.txt` e copiare `.env.example` in `.env` con un
   token casuale. Il token va configurato anche nel backend della webapp.
4. Verificare con `codex login status` eseguito come `sole_abate`.
5. Installare `bs25ai-worker.service`, limitando la porta 8094 al solo indirizzo privato/IP
   del backend tramite NSG/firewall.

Il servizio non contiene credenziali ChatGPT: usa la sessione Codex già presente nella home
di `sole_abate`. Non esporre mai la porta pubblicamente senza firewall e bearer token.
