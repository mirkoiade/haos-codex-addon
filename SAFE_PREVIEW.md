# Mirko Home Assistant Green – anteprima Codex in sola lettura

Questa è una **variante sperimentale non ufficiale** del progetto di Christin Löhner.
Serve esclusivamente per la prima analisi di Home Assistant Green senza modificare la configurazione.

## Limiti impostati nel fork

- `/workspace` monta la configurazione di Home Assistant con `read_only: true`.
- Le cartelle `/share`, `/ssl` e `addon_config` non sono montate.
- Avvio automatico dell'app disattivato (`boot: manual`).
- Rimossa dal menu la voce che avviava Codex con `--dangerously-bypass-approvals-and-sandbox`.
- Ingress attivo; nessuna porta esposta al router e nessun accesso Nabu Casa necessario.

**Attenzione:** sola lettura NON significa che i dati siano riservati. L'add-on può ancora leggere
`/workspace/secrets.yaml`, `/workspace/.storage/`, token, configurazioni di integrazione e altri
file sensibili. Codex usa una connessione ai server OpenAI. Non autorizzare l'analisi indiscriminata
di tutti i file e non chiedere di stampare o copiare segreti.

Questo fork non è stato sottoposto ad audit indipendente e non è stato ancora collaudato su Home Assistant Green.
Non installare sul sistema principale finché non sono stati verificati e approvati i cambiamenti.

## Primo impiego controllato

1. Mantieni un backup completo scaricato dal Green e il kit di emergenza al sicuro.
2. Installa **solo** la versione del fork dopo la revisione/merge, non l'add-on originale.
3. Accedi a Codex con il tuo account ChatGPT, senza incollare token o chiavi nelle chat.
4. Chiedi inizialmente analisi mirate di `automations.yaml` o delle plance YAML, senza aprire `secrets.yaml` e `.storage/`.
5. Per qualunque modifica reale, crea una variante separata con permessi di scrittura temporanei e revisione manuale dei diff; mai disabilitare approvazioni o sandbox.

## Funzionalità NON incluse

- Nessuna scrittura sulle automazioni o plance del Green in questa modalità.
- Nessuna lettura garantita degli stati live degli Shelly: per quelli servirà un collegamento MCP/API
  separato con autorizzazioni limitate.
- Nessuna garanzia di funzionamento del login o della build su Green prima di prove pratiche.
