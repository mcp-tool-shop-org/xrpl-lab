<p align="center">
  <a href="README.ja.md">日本語</a> | <a href="README.zh.md">中文</a> | <a href="README.es.md">Español</a> | <a href="README.fr.md">Français</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.md">English</a> | <a href="README.pt-BR.md">Português (BR)</a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/brand/main/logos/xrpl-lab/readme.png" width="500" alt="XRPL Lab">
</p>

<p align="center">
  <a href="https://github.com/mcp-tool-shop-org/xrpl-lab/actions/workflows/ci.yml"><img src="https://github.com/mcp-tool-shop-org/xrpl-lab/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/mcp-tool-shop-org/xrpl-lab/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="MIT License"></a>
  <a href="https://mcp-tool-shop-org.github.io/xrpl-lab/"><img src="https://img.shields.io/badge/Landing_Page-live-blue" alt="Landing Page"></a>
</p>

Manuale di formazione XRPL: impara facendo, dimostra con i risultati.

Ogni modulo insegna una competenza XRPL e produce un risultato verificabile: un ID di transazione,
una ricevuta firmata o un rapporto diagnostico. Nessun account, niente di superfluo, niente cloud: solo
competenza e prove concrete.

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/xrpl-lab/main/docs/images/dashboard-hero.png" width="800" alt="XRPL Lab dashboard showing completed modules with quick actions and status panels">
</p>

## Installa

```bash
pipx install xrpl-lab
```

Oppure con pip:

```bash
pip install xrpl-lab
```

Richiede Python 3.11 o superiore.

## Guida rapida

```bash
xrpl-lab start
```

Il programma guidato ti guida attraverso la configurazione del portafoglio, il finanziamento e il primo modulo.

### Modalità offline

```bash
xrpl-lab start --dry-run
```

Nessuna rete richiesta. Transazioni simulate per imparare il flusso di lavoro.

## Moduli

```
<!-- BEGIN curriculum:auto readme-intro -->
<!-- generato da scripts/gen_docs.py – non modificare manualmente; eseguire lo script di generazione -->
24 moduli suddivisi in dieci aree tematiche: Fondamenti, NFT, Token, Pagamenti, Identità, DEX, Riserve, Audit, AMM e Progetto finale.
I prerequisiti sono specificati esplicitamente: la CLI e il linter li applicano.

La colonna `#` corrisponde all'ordine mostrato da `xrpl-lab list` (ordine canonico delle aree tematiche).
<!-- END curriculum:auto readme-intro -->

<!-- BEGIN curriculum:auto readme-table -->
<!-- generato da scripts/gen_docs.py – non modificare manualmente; eseguire lo script di generazione -->
| # | Modulo | Area tematica | Modalità | Prerequisiti | Risultati |
|---|--------|-------|------|---------------|----------|
| 1 | Alfabetizzazione delle ricevute | fondamenti | testnet | — | txid, report |
| 2 | Alfabetizzazione dei fallimenti | fondamenti | testnet | Alfabetizzazione delle ricevute | txid, report |
| 3 | Trust Lines 101: Valute emesse come relazioni | fondamenti | testnet | — | txid, report |
| 4 | Debug delle linee di credito | fondamenti | testnet | Trust Lines 101: Valute emesse come relazioni | txid, report |
| 5 | NFT Minting 101: Il tuo primo asset di gioco | nfts | testnet | — | txid, report |
| 6 | NFT Marketplace 101: Scambio di asset con royalty applicate | nfts | testnet | — | txid, report |
| 7 | Dynamic NFTs 101: Un oggetto di gioco che aumenta di livello | nfts | testnet | — | txid, report |
| 8 | MPT Issuance 101: Una valuta di gioco in una singola transazione | tokens | testnet | — | txid, report |
| 9 | MPT Distribution 101: Distribuzione della valuta ai giocatori | tokens | testnet | MPT Issuance 101: Una valuta di gioco in una singola transazione | txid, report |
| 10 | Token Freeze 101: Il pulsante di pausa dell'emittente | tokens | testnet | — | txid, report |
| 11 | Clawback 101: La leva per il richiamo dell'emittente | tokens | testnet | — | txid, report |
| 12 | Escrow 101: XRP con blocco temporale | payments | testnet | — | txid, report |
| 13 | Escrow Finish 101: Rilascio di XRP bloccati | payments | testnet | Escrow 101: XRP con blocco temporale | txid, report |
| 14 | Payment Channels 101: Firma molte transazioni, esegui il saldo una sola volta | payments | testnet | — | txid, report |
| 15 | DID 101: Identità on-ledger | identity | testnet | — | txid, report |
| 16 | DEX Literacy: Offerte, libri degli ordini e cancellazioni | dex | testnet | Trust Lines 101: Valute emesse come relazioni | txid, report |
| 17 | DEX Market Making 101: Guadagno dello spread sul libro degli ordini | dex | testnet | DEX Literacy: Offerte, libri degli ordini e cancellazioni | txid, report |
| 18 | DEX Inventory Guardrails: Non sbilanciarti troppo | dex | testnet | DEX Market Making 101: Guadagno dello spread sul libro degli ordini | txid, report |
| 19 | Reserves 101: Dove sono "andati" i tuoi XRP | riserve | testnet | Trust Lines 101: Valute emesse come relazioni | txid, report |
| 20 | Account Hygiene: Liberare le riserve e ripulire gli oggetti | riserve | testnet | Reserves 101: Dove sono "andati" i tuoi XRP | txid, report |
| 21 | Audit Mode: Verifica delle ricevute su larga scala | audit | testnet | Alfabetizzazione delle ricevute | report, audit_pack |
| 22 | AMM Liquidity 101: Fornire liquidità e guadagnare commissioni | amm | dry-run | Trust Lines 101: Valute emesse come relazioni | txid, report |
| 23 | DEX vs AMM Risk Literacy: Confronto tra strategie di trading | amm | dry-run | DEX Market Making 101: Guadagno dello spread sul libro degli ordini, AMM Liquidity 101: Fornire liquidità e guadagnare commissioni | txid, report |
| 24 | Capstone: Crea un'economia di gioco minima su XRPL | capstone | testnet | MPT Issuance 101: Una valuta di gioco in una singola transazione, NFT Minting 101: Il tuo primo asset di gioco, Escrow 101: XRP con blocco temporale, Audit Mode: Verifica delle ricevute su larga scala | txid, report, audit_pack |
<!-- END curriculum:auto readme-table -->

La colonna **Risultati** elenca i tipi di artefatti che ogni modulo produce (`txid`, `report`, `audit_pack`); consulta la pagina di ciascun modulo nel [manuale](https://mcp-tool-shop-org.github.io/xrpl-lab/handbook/modules/) per la guida completa alle competenze e ciò che dimostrerai sull'ledger.

### Aree tematiche

<!-- BEGIN curriculum:auto readme-tracks -->
<!-- generato da scripts/gen_docs.py – non modificare manualmente; eseguire lo script di generazione -->
- **foundations** – portafoglio, pagamenti, trust lines, gestione degli errori
- **nfts** – asset di gioco NFT: creazione, regolamento del marketplace, NFT dinamici (XLS-20)
- **tokens** – emissione e richiamo di token multiuso (MPT) per valuta di gioco (XLS-33)
- **payments** – escrow e valore con blocco temporale
- **identity** – identificatori decentralizzati (DID, XLS-40)
- **dex** – offerte, libri degli ordini, market making, gestione dell'inventario
- **reserves** – riserve di account, conteggio dei proprietari, pulizia
- **audit** – verifica in batch, report di audit
- **amm** – liquidità per market maker automatizzato, confronto DEX vs AMM
- **capstone** – combina le competenze tra le aree tematiche nella creazione di un'economia di gioco
<!-- END curriculum:auto readme-tracks -->
```

### Modalità

- **testnet**: transazioni reali sulla XRPL Testnet
- **dry-run**: sandbox offline con transazioni simulate (nessuna rete richiesta)

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
xrpl-lab proof generate     Export shareable proof pack (alias of proof-pack)
xrpl-lab proof verify <file>  Verify a proof pack's integrity (SHA-256)
xrpl-lab certificate        Export completion certificate
xrpl-lab cert-verify <file>   Verify a completion certificate's integrity
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

Tutti i comandi supportano `--dry-run` per la modalità offline, quando applicabile.

## Utilizzo in workshop

XRPL Lab è progettato per ambienti di insegnamento reali. Nessun account, nessuna telemetria, niente cloud.
Tutto viene eseguito localmente.

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/xrpl-lab/main/docs/images/facilitator-active-runs.png" width="800" alt="Facilitator dashboard listing active learner runs with module IDs, dry-run badges, status, queue depth, and run IDs">
</p>

### Stato del facilitatore

```bash
xrpl-lab status             # Where is this learner? What's blocked? What's next?
xrpl-lab status --json      # Machine-readable for scripting
xrpl-lab tracks             # Track-level completion: what was actually practiced
xrpl-lab recovery           # Stuck? See exactly what to run next
```

### Supporto handover

```bash
xrpl-lab support-bundle              # Human-readable markdown bundle
xrpl-lab support-bundle --json       # Machine-parseable JSON
xrpl-lab support-bundle --verify bundle.json  # Verify a received bundle
```

Un facilitatore può diagnosticare qualsiasi problema di un partecipante da un pacchetto di supporto senza
riprodurre l'intera sessione. Nessun segreto è incluso.

### Flussi di lavoro per workshop

**Sandbox completamente offline**: nessuna rete richiesta:
```bash
xrpl-lab wallet create
xrpl-lab start --dry-run
```

**Offline + testnet misti**: transazioni reali per le basi, sandbox per gli argomenti avanzati:
```bash
xrpl-lab wallet create
xrpl-lab fund
xrpl-lab start
```

**Progressione da Camp a Lab**: continua da xrpl-camp:
```bash
xrpl-lab start    # auto-detects camp wallet and certificate
```

## Risultati

**Pacchetto di verifica** (`xrpl_lab_proof_pack.json`): archivio condivisibile dei moduli completati, degli ID delle transazioni e dei link all’esploratore. Include un hash di integrità SHA-256. Non contiene informazioni sensibili.

**Certificato** (`xrpl_lab_certificate.json`): archivio semplificato del completamento.

**Report** (`reports/*.md`): riepiloghi leggibili da persone di ciò che è stato fatto e verificato.

**Pacchetti di audit** (`audit_pack_*.json`): risultati della verifica in batch con hash di integrità SHA-256.

## Modello di sicurezza e affidabilità

**Dati a cui accede XRPL Lab:**
- Seed del wallet (memorizzato localmente in `~/.xrpl-lab/wallet.json` come JSON in chiaro, protetto da permessi di file 0o600 e una directory principale con permessi 0o700 — non crittografato)
- Avanzamento dei moduli e ID delle transazioni (memorizzati in `~/.xrpl-lab/state.json`, scritture atomiche tramite tmp + ridenominazione)
- XRPL Testnet RPC (endpoint pubblico, le transazioni vengono firmate localmente prima dell’invio)
- Faucet della testnet (HTTP pubblico, viene inviato solo il tuo indirizzo)

**Dati a cui XRPL Lab NON accede:**
- Nessuna mainnet. Solo testnet
- Nessun telemetria, analisi o comunicazione di dati di alcun tipo
- Nessun account cloud, nessuna registrazione, nessuna API di terze parti
- Nessuna informazione sensibile nei pacchetti di verifica, nei certificati, nei report o nei pacchetti di supporto — mai

**Permessi e livelli di archiviazione:**
- Directory principale `~/.xrpl-lab/` — livello privato per informazioni sensibili, directory con permessi 0o700 + file wallet con permessi 0o600. Memorizza il seed del wallet, il log del dottore, i pacchetti di audit.
- Area di lavoro `./.xrpl-lab/` — livello progettato per la condivisione, directory con permessi 0o755. Memorizza i report dei moduli, i pacchetti di verifica, i certificati. I facilitatori possono esaminarli senza richiedere autorizzazioni aggiuntive.
- File system: legge e scrive solo nelle due posizioni sopra indicate
- Rete: solo XRPL Testnet RPC + faucet (entrambi modificabili tramite variabili d’ambiente, entrambi opzionali con `--dry-run`)
- Non sono richieste autorizzazioni elevate

**Interfaccia del dashboard (quando `xrpl-lab serve` è in esecuzione):**
- L’endpoint WebSocket applica una lista di origine consentita (chiude le connessioni non presenti nella lista con il codice 4003)
- Tutti i frame di errore emettono un envelope strutturato (`code`, `message`, `hint`, `severity`, `icon_hint`) — nessuna divulgazione del percorso, nessuna divulgazione dello stato interno
- Coda di messaggi per connessione limitata con comportamento documentato in caso di sovraccarico

Consulta [SECURITY.md](SECURITY.md) per la politica di sicurezza completa e le istruzioni per la configurazione del workshop.

## Requisiti

- Python 3.11+
- Connessione Internet per la testnet (o utilizzare `--dry-run` per una modalità completamente offline)

## Licenza

MIT

Creato da [MCP Tool Shop](https://mcp-tool-shop.github.io/)
