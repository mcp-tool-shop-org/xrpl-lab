<p align="center">
  <a href="README.ja.md">日本語</a> | <a href="README.zh.md">中文</a> | <a href="README.es.md">Español</a> | <a href="README.fr.md">Français</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.md">English</a> | <a href="README.pt-BR.md">Português (BR)</a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/brand/main/logos/xrpl-lab/readme.png" width="400" alt="XRPL Lab">
</p>

<p align="center">
  <a href="https://github.com/mcp-tool-shop-org/xrpl-lab/actions/workflows/ci.yml"><img src="https://github.com/mcp-tool-shop-org/xrpl-lab/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/mcp-tool-shop-org/xrpl-lab/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="MIT License"></a>
  <a href="https://mcp-tool-shop-org.github.io/xrpl-lab/"><img src="https://img.shields.io/badge/Landing_Page-live-blue" alt="Landing Page"></a>
</p>

XRPL: manuale di formazione – impara facendo, dimostra con risultati concreti.

Ogni modulo insegna una competenza specifica di XRPL e produce un risultato verificabile: un ID di transazione,
una ricevuta firmata o un rapporto diagnostico. Nessun account, nessuna divagazione, nessuna piattaforma cloud: solo
competenze e risultati tangibili.

## Installazione

```bash
pipx install xrpl-lab
```

Oppure con pip:

```bash
pip install xrpl-lab
```

Richiede Python 3.11 o superiore.

## Guida all'uso

```bash
xrpl-lab start
```

La procedura guidata di avvio ti accompagnerà nella configurazione del wallet, nel finanziamento e nel primo modulo.

### Modalità offline

```bash
xrpl-lab start --dry-run
```

Non è necessaria una connessione di rete. Transazioni simulate per l'apprendimento del flusso di lavoro.

## Moduli

12 moduli suddivisi in cinque aree: Fondamenti, DEX, Riserve, Audit e AMM.
I prerequisiti sono espliciti e vengono applicati dal CLI e dal linter.

| # | Modulo | Area | Modalità | Cosa impari | Cosa dimostri |
|---|--------|-------|------|----------------|----------------|
| 1 | Comprensione delle ricevute | Fondamenti | Testnet | La conferma di una transazione è una ricevuta, non uno stato "inviato" – effettua un pagamento, leggi ogni campo della ricevuta. | ID transazione + rapporto di verifica |
| 2 | Comprensione degli errori | Fondamenti | Testnet | Gli errori di XRPL hanno un significato specifico (tec/tef/tem/ter) – interrompi intenzionalmente una transazione, diagnostica, risolvi, riproponi. | Sequenza di transazioni fallite e corrette |
| 3 | Linee di fiducia: le basi | Fondamenti | Testnet | I token sono attivabili e direzionali – crea l'emittente, imposta la linea di fiducia, emetti i token. | Linea di fiducia + saldo del token |
| 4 | Debug delle linee di fiducia | Fondamenti | Testnet | Decodifica i codici di errore delle linee di fiducia – interruzione intenzionale, decodifica dell'errore, risoluzione. | Errore → sequenza di transazioni di risoluzione |
| 5 | Comprensione del DEX | DEX | Testnet | I libri degli ordini mettono in contatto acquirenti e venditori – crea offerte, leggi i libri degli ordini, annulla. | ID delle transazioni di creazione e annullamento delle offerte |
| 6 | Riserve: le basi | Riserve | Testnet | Ogni oggetto posseduto blocca XRP – snapshot, numero di proprietari, calcolo delle riserve. | Differenza tra snapshot precedenti e successivi |
| 7 | Gestione dell'account | Riserve | Testnet | La pulizia è un'abilità fondamentale – annulla le offerte, rimuovi le linee di fiducia, libera le riserve. | Rapporto di verifica della pulizia |
| 8 | Audit | Audit | Testnet | Gli audit codificano l'intento (ID transazione + aspettativa + verdetto) – verifica in batch con aspettative. | Pacchetto di audit (MD + CSV + JSON) |
| 9 | AMM: liquidità – le basi | AMM | Simulazione | I prezzi del prodotto costante (`x*y=k`) variano passivamente – crea un pool, deposita, guadagna LP, preleva. | ID delle transazioni del ciclo di vita dell'AMM |
| 10 | Creazione di mercato DEX: le basi | DEX | Testnet | Spread bid/ask tracciano l'inventario – quota entrambi i lati, snapshot delle posizioni, pulizia. | ID delle transazioni delle strategie + rapporto di pulizia |
| 11 | Protezione dell'inventario | DEX | Testnet | Quota solo il lato sicuro quando l'inventario è sbilanciato – basato su soglie, posizionamento protetto. | Controllo dell'inventario + transazioni protette |
| 12 | Comprensione dei rischi DEX vs AMM | AMM | Simulazione | La perdita impermanente è una proprietà del modello AMM – ciclo di vita DEX e AMM affiancati. | Rapporto di confronto + sequenza di audit |

### Aree

- **Fondamenti**: wallet, pagamenti, linee di fiducia, gestione degli errori.
- **DEX**: offerte, libri degli ordini, creazione di mercato, gestione dell'inventario.
- **Riserve**: riserve dell'account, numero di proprietari, pulizia.
- **Audit**: verifica in batch, rapporti di audit.
- **AMM**: liquidità del market maker automatizzato, confronto DEX vs AMM.

### Modalità

- **Testnet**: transazioni reali sulla XRPL Testnet.
- **Simulazione**: sandbox offline con transazioni simulate (nessuna connessione di rete richiesta).

## Comandi

```text
xrpl-lab start              Guided launcher
xrpl-lab list               Show all modules with status and progression
xrpl-lab run <module_id>    Run a specific module
xrpl-lab status [--json]    Progress, curriculum position, blockers, track progress
xrpl-lab cohort-status [--dir DIR] [--format FORMAT]  Aggregate per-learner status across a cohort directory (facilitator)
xrpl-lab session-export [--dir DIR] [--format FORMAT] [--outfile FILE]  Archive all learner artifacts with a SHA-256 manifest
xrpl-lab tracks             Track-level completion summaries
xrpl-lab recovery           Diagnose stuck states, show recovery commands
xrpl-lab lint [glob] [--json] [--no-curriculum]  Validate module files and curriculum
xrpl-lab proof-pack         Export shareable proof pack
xrpl-lab certificate        Export completion certificate
xrpl-lab doctor             Run diagnostic checks
xrpl-lab self-check         Alias for doctor
xrpl-lab feedback           Generate support bundle (markdown)
xrpl-lab support-bundle [--json] [--verify FILE]  Generate or verify support bundles
xrpl-lab audit              Batch verify transactions
xrpl-lab last-run           Show last module run + audit command
xrpl-lab serve [--port N] [--host H] [--dry-run]  Start web dashboard and API server
xrpl-lab reset [--module MODULE_ID]  Wipe local state OR reset a single module (requires confirmation)
xrpl-lab module init --id ID --track TRACK --title TITLE --time TIME  Scaffold a lint-passing module skeleton

xrpl-lab wallet create      Create a new wallet
xrpl-lab wallet show        Show wallet info (no secrets)
xrpl-lab fund               Fund wallet from testnet faucet
xrpl-lab send --to <address> --amount <xrp> [--memo <text>]  Send a payment
xrpl-lab verify --tx <id>   Verify a transaction on-ledger
```

Tutti i comandi supportano l'opzione `--dry-run` per la modalità offline, quando applicabile.

## Utilizzo in laboratorio

XRPL Lab è progettato per ambienti di apprendimento reali. Non richiede account, telemetria o servizi cloud.
Tutto funziona localmente.

### Ruolo di facilitatore

```bash
xrpl-lab status             # Where is this learner? What's blocked? What's next?
xrpl-lab status --json      # Machine-readable for scripting
xrpl-lab tracks             # Track-level completion: what was actually practiced
xrpl-lab recovery           # Stuck? See exactly what to run next
```

### Supporto e assistenza

```bash
xrpl-lab support-bundle              # Human-readable markdown bundle
xrpl-lab support-bundle --json       # Machine-parseable JSON
xrpl-lab support-bundle --verify bundle.json  # Verify a received bundle
```

Un facilitatore può diagnosticare qualsiasi problema di un partecipante analizzando un pacchetto di supporto senza dover riprodurre l'intera sessione. Non sono inclusi dati sensibili.

### Flussi di lavoro del laboratorio

**Ambiente di test completamente offline:** non è necessaria alcuna connessione di rete.
```bash
xrpl-lab wallet create
xrpl-lab start --dry-run
```

**Combinazione di offline e testnet:** transazioni reali per le basi, ambiente di test per funzionalità avanzate.
```bash
xrpl-lab wallet create
xrpl-lab fund
xrpl-lab start
```

**Progressione da corso a laboratorio:** possibilità di continuare da un corso precedente (xrpl-camp).
```bash
xrpl-lab start    # auto-detects camp wallet and certificate
```

## Risultati

**Pacchetto di verifica** (`xrpl_lab_proof_pack.json`): registro condivisibile dei moduli completati, ID delle transazioni e link all'esploratore. Include un hash di integrità SHA-256. Non contiene dati sensibili.

**Certificato** (`xrpl_lab_certificate.json`): registro di completamento semplificato.

**Report** (`reports/*.md`): riassunti leggibili da persone di ciò che è stato fatto e dimostrato.

**Pacchetti di verifica** (`audit_pack_*.json`): risultati di verifica in batch con hash di integrità SHA-256.

## Modello di sicurezza e affidabilità

**Dati a cui XRPL Lab accede:**
- Chiave segreta del wallet (memorizzata localmente in `~/.xrpl-lab/wallet.json` in formato JSON non crittografato, protetta dalle autorizzazioni del file 0o600 e dalla directory principale 0o700)
- Progresso dei moduli e ID delle transazioni (memorizzati in `~/.xrpl-lab/state.json`, scrittura atomica tramite file temporaneo e ridenominazione)
- RPC della rete di test XRPL (endpoint pubblico, le transazioni vengono firmate localmente prima dell'invio)
- Rubinetto (faucet) della rete di test (HTTP pubblico, viene inviato solo il tuo indirizzo)

**Dati a cui XRPL Lab NON accede:**
- Nessuna connessione alla rete principale (solo alla rete di test)
- Nessuna telemetria, analisi o funzionalità di "phone-home" di alcun tipo
- Nessun account cloud, nessuna registrazione, nessuna API di terze parti
- Nessun dato sensibile nei pacchetti di verifica, nei certificati, nei report o nei pacchetti di supporto, mai.

**Autorizzazioni e livelli di archiviazione:**
- Directory principale `~/.xrpl-lab/` — livello per dati sensibili, directory con autorizzazioni 0o700 e file del wallet con autorizzazioni 0o600. Contiene la chiave segreta del wallet, il registro del facilitatore e i pacchetti di verifica.
- Directory di lavoro `./.xrpl-lab/` — livello progettato per la condivisione, directory con autorizzazioni 0o755. Contiene i report dei moduli, i pacchetti di verifica e i certificati. I facilitatori possono visualizzare i contenuti senza richiedere autorizzazioni aggiuntive.
- Sistema di file: legge e scrive solo nelle due directory sopra indicate.
- Rete: solo RPC e rubinetto (faucet) della rete di test XRPL (entrambi sovrascrivibili tramite variabili d'ambiente, entrambi opzionali con `--dry-run`).
- Non sono richieste autorizzazioni elevate.

**Interfaccia del pannello di controllo (quando `xrpl-lab serve` è in esecuzione):**
- Il componente WebSocket runner applica una lista di controllo degli origini consentiti (blocca le connessioni non presenti nella lista con il codice 4003)
- Tutti i messaggi di errore generano un involucro strutturato (`code`, `message`, `hint`, `severity`, `icon_hint`) — nessuna perdita di percorsi, nessuna perdita dello stato interno.
- Coda dei messaggi limitata per connessione con comportamento di back-pressure documentato.

Consultare il file [SECURITY.md](SECURITY.md) per la politica di sicurezza completa e le istruzioni per la configurazione del laboratorio.

## Requisiti

- Python 3.11+
- Connessione a Internet per la rete di test (oppure utilizzare `--dry-run` per la modalità completamente offline)

## Licenza

MIT

Creato da [MCP Tool Shop](https://mcp-tool-shop.github.io/)
