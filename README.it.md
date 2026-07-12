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

Manuale di formazione XRPL: imparare facendo e dimostrare attraverso esempi concreti.

Ogni modulo insegna una specifica competenza relativa a XRPL e produce un risultato verificabile: un codice identificativo di transazione, una ricevuta firmata o un rapporto diagnostico. Niente conti utente, niente elementi superflui, niente cloud – solo competenze concrete e ricevute.

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

Richiede Python versione 3.11 o successiva.

## Guida rapida all’avvio

```bash
xrpl-lab start
```

La guida interattiva vi accompagnerà passo dopo passo nella configurazione del portafoglio digitale, nel finanziamento e nell’utilizzo del primo modulo.

### Modalità offline

```bash
xrpl-lab start --dry-run
```

Non è necessaria una connessione di rete. Sono disponibili transazioni simulate per apprendere il flusso di lavoro.

## Moduli

<!-- INIZIO curriculum:auto readme-intro -->
<!-- generato tramite scripts/gen_docs.py – non modificare manualmente; eseguire lo script di generazione -->
32 moduli suddivisi in dieci aree tematiche: Fondamenti, NFT, Token, Pagamenti, Identità, DEX, Riserve, Audit, AMM e Progetto finale.
I requisiti preliminari sono chiaramente definiti e vengono applicati tramite la CLI e il linter.

La colonna `#` corrisponde all’ordine visualizzato dal comando `xrpl-lab list` (l’ordine canonico delle tracce).

<!-- INIZIO del curriculum: tabella automatica readme -->
<!-- generato tramite lo script scripts/gen_docs.py – non modificare manualmente; eseguire lo script di generazione -->
| # | Modulo | Traccia | Modalità | Requisiti preliminari | Produce |
|---|--------|-------|------|---------------|----------|
| 1 | Capacità di comprendere le ricevute | fondamenta; basi | rete di test | — | ID transazione, rapporto |
| 2 | Alfabetizzazione sul fallimento | fondamenta; basi | rete di test | Capacità di comprendere le ricevute | ID transazione, rapporto |
| 3 | Le basi delle relazioni di fiducia: le valute emesse come indicatori del livello di fiducia. | fondamenta; basi | rete di test | — | ID transazione, rapporto |
| 4 | Risoluzione dei problemi relativi alle relazioni di fiducia. | fondamenta; basi | rete di test | Le basi delle relazioni di fiducia: le valute emesse come indicatori del livello di fiducia. | ID transazione, rapporto |
| 5 | Portafoglio multi-firma per la gestione delle risorse (elenco dei firmatari): controllo N su M del portafoglio dello studio. | fondamenta; basi | rete di test | Capacità di comprendere le ricevute | ID transazione, rapporto |
| 6 | Introduzione alla creazione di NFT: il tuo primo elemento di gioco. | NFT (token non fungibili) | rete di test | — | ID transazione, rapporto |
| 7 | Guida introduttiva ai marketplace NFT: come scambiare asset digitali garantendo il pagamento delle royalty. | NFT (token non fungibili) | rete di test | — | ID transazione, rapporto |
| 8 | NFT dinamici: le basi e un esempio di oggetto di gioco che migliora con il tempo. | NFT (token non fungibili) | rete di test | — | ID transazione, rapporto |
| 9 | MPT: le basi per l’emissione di valuta virtuale con una sola transazione. | gettoni; simboli | rete di test | — | ID transazione, rapporto |
| 10 | Guida introduttiva alla distribuzione di valuta nei giochi MPT: come fornire la valuta ai giocatori. | gettoni; simboli | rete di test | MPT: le basi per l’emissione di valuta virtuale con una sola transazione. | ID transazione, rapporto |
| 11 | Congelamento dei token: la funzione di sospensione dell’emittente. | gettoni; simboli | rete di test | — | ID transazione, rapporto |
| 12 | Il meccanismo di «clawback»: uno strumento a disposizione dell’emittente per richiedere la restituzione dei compensi. | gettoni; simboli | rete di test | — | ID transazione, rapporto |
| 13 | Guida introduttiva ai servizi di deposito a garanzia: XRP con vincolo temporale. | pagamenti | rete di test | — | ID transazione, rapporto |
| 14 | Guida introduttiva all’utilizzo dell’escrow: come sbloccare gli XRP vincolati. | pagamenti | rete di test | Guida introduttiva ai servizi di deposito a garanzia: XRP con vincolo temporale. | ID transazione, rapporto |
| 15 | Servizio di deposito temporaneo di token (XLS-85): blocco degli IOU, non solo di XRP. | pagamenti | rete di test | Principi fondamentali delle linee di fiducia: le valute emesse come relazioni; principi fondamentali dei depositi a garanzia: XRP con scadenza temporale. | ID transazione, rapporto |
| 16 | Controlli di base: pagamenti differiti tramite assegno (creazione/incasso/annullamento dell’assegno). | pagamenti | rete di test | Capacità di comprendere le ricevute | ID transazione, rapporto |
| 17 | Canali di pagamento: la guida base: stipulare molti accordi, effettuare un unico addebito. | pagamenti | rete di test | — | ID transazione, rapporto |
| 18 | Importo erogato: la vulnerabilità legata ai pagamenti parziali. | pagamenti | rete di test | Le basi delle relazioni di fiducia: le valute emesse come indicatori del livello di fiducia. | ID transazione, rapporto |
| 19 | Attribuzione dei crediti ai giocatori tramite un custode: un unico portafoglio centralizzato, molti giocatori (etichette di destinazione). | pagamenti | rete di test | Importo erogato: la vulnerabilità legata ai pagamenti parziali. | ID transazione, rapporto |
| 20 | DID 101: Identità gestita direttamente sulla blockchain. | identità | rete di test | — | ID transazione, rapporto |
| 21 | Credenziali 101 (XLS-70): Verifica dell’identità e attestazione dell’età direttamente nel registro contabile. | identità | rete di test | DID 101: Identità gestita direttamente sulla blockchain. | ID transazione, rapporto |
| 22 | Domini autorizzati e DEX con accesso controllato (XLS-80/81): trading conforme e basato su credenziali. | identità | rete di test | Credenziali 101 (XLS-70): Verifica dell’identità e attestazione dell’età direttamente nel registro contabile. | ID transazione, rapporto |
| 23 | Deposit Gate (DepositAuth + DepositPreauth): Depositi nel portafoglio digitale protetti da autenticazione. | identità | rete di test | Credenziali 101 (XLS-70): Verifica dell’identità e attestazione dell’età direttamente nel registro contabile. | ID transazione, rapporto |
| 24 | DEX Literacy: Offerte, registri degli ordini e annullamenti. | dex | rete di test | Le basi delle relazioni di fiducia: le valute emesse come indicatori del livello di fiducia. | ID transazione, rapporto |
| 25 | Nozioni di base sul market making decentralizzato (DEX): come ottenere un profitto dalle differenze di prezzo nel registro ordini. | dex | rete di test | DEX Literacy: Offerte, registri degli ordini e annullamenti. | ID transazione, rapporto |
| 26 | Linee guida per la gestione dell’inventario DEX: evitate squilibri. | dex | rete di test | Nozioni di base sul market making decentralizzato (DEX): come ottenere un profitto dalle differenze di prezzo nel registro ordini. | ID transazione, rapporto |
| 27 | Riserve 101: Cosa è successo alle tue riserve di XRP? | riserve | rete di test | Le basi delle relazioni di fiducia: le valute emesse come indicatori del livello di fiducia. | ID transazione, rapporto |
| 28 | Gestione ottimale dell’account: liberare risorse e riordinare gli oggetti. | riserve | rete di test | Riserve 101: Cosa è successo alle tue riserve di XRP? | ID transazione, rapporto |
| 29 | Modalità di controllo: verifica su larga scala delle ricevute. | revisione contabile; controllo | rete di test | Capacità di comprendere le ricevute | relazione, pacchetto di documenti per la verifica |
| 30 | AMM e liquidità: come fornire liquidità e ottenere compensi. | amm | prova generale; simulazione pratica | Le basi delle relazioni di fiducia: le valute emesse come indicatori del livello di fiducia. | ID transazione, rapporto |
| 31 | DEX e AMM: confronto tra le strategie di trading e valutazione dei rischi. | amm | prova generale; simulazione pratica | Nozioni di base sul market making decentralizzato (DEX): come ottenere un profitto dallo spread nel book degli ordini; nozioni di base sulla liquidità negli Automated Market Maker (AMM): come fornire liquidità e guadagnare commissioni. | ID transazione, rapporto |
| 32 | Progetto conclusivo: creare un sistema economico di gioco semplificato su XRPL. | pietra angolare; progetto conclusivo; elemento fondamentale | rete di test | Guida introduttiva all’emissione di MPT: una valuta di gioco con una sola transazione; Guida introduttiva alla creazione di NFT: il tuo primo asset di gioco; Guida introduttiva ai servizi di deposito a garanzia: XRP con vincolo temporale; Modalità di controllo: verifica delle ricevute su larga scala. | ID transazione, rapporto, pacchetto di controllo. |
<!-- FINE del curriculum: tabella automatica nel file README -->

La colonna **Produces** elenca i tipi di artefatti generati da ciascun modulo (`txid`, `report`, `audit_pack`); per una descrizione completa delle funzionalità e dei risultati ottenuti, consultare la pagina dedicata a ciascun modulo nel [manuale](https://mcp-tool-shop-org.github.io/xrpl-lab/handbook/modules/).

### Brani musicali / Tracce

<!-- INIZIO curriculum:auto readme-tracks -->
<!-- generato da scripts/gen_docs.py – non modificare manualmente; eseguire lo script di generazione -->
- **fondamenti** — portafoglio, pagamenti, linee di credito, gestione degli errori
- **NFT** — risorse di gioco NFT: creazione, regolamento del mercato, NFT dinamici (XLS-20)
- **token** — emissione e recupero della valuta di gioco Multi-Purpose Token (MPT) (XLS-33)
- **pagamenti** — deposito a garanzia e valore con scadenza temporale
- **identità** — identificatori decentralizzati (DID, XLS-40)
- **DEX** — offerte, registri degli ordini, creazione del mercato, gestione dell’inventario
- **riserve** — riserve di conto, numero di proprietari, pulizia
- **audit** — verifica in batch, report di audit
- **AMM** — liquidità automatizzata per il market maker, confronto tra DEX e AMM
- **progetto finale** — combinazione delle competenze acquisite nei diversi moduli per creare un’economia di gioco completa
<!-- FINE curriculum:auto readme-tracks -->

### Modalità

- **testnet**: esecuzione di transazioni reali sulla rete di test XRPL.
- **dry-run**: ambiente di prova offline con transazioni simulate (non è necessaria una connessione alla rete).

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

Tutti i comandi supportano l’opzione `--dry-run` per la modalità offline, quando applicabile.

## Utilizzo in officina

XRPL Lab è progettato per contesti di insegnamento reali. Nessun account, nessuna telemetria, nessun cloud. Tutto viene eseguito in locale.

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/xrpl-lab/main/docs/images/facilitator-active-runs.png" width="800" alt="Facilitator dashboard listing active learner runs with module IDs, dry-run badges, status, queue depth, and run IDs">
</p>

### Ruolo di facilitatore

```bash
xrpl-lab status             # Where is this learner? What's blocked? What's next?
xrpl-lab status --json      # Machine-readable for scripting
xrpl-lab tracks             # Track-level completion: what was actually practiced
xrpl-lab recovery           # Stuck? See exactly what to run next
```

### Passaggio di consegne al supporto

```bash
xrpl-lab support-bundle              # Human-readable markdown bundle
xrpl-lab support-bundle --json       # Machine-parseable JSON
xrpl-lab support-bundle --verify bundle.json  # Verify a received bundle
```

Un facilitatore può diagnosticare qualsiasi problema di un partecipante a partire da una serie di dati di supporto, senza dover riprodurre l'intera sessione. Non sono inclusi dati sensibili.

### Flussi di lavoro del workshop

**Sandbox completamente offline:** non è richiesta alcuna connessione di rete:
```bash
xrpl-lab wallet create
xrpl-lab start --dry-run
```

**Offline misto + testnet:** transazioni reali per le basi, sandbox per funzionalità avanzate:
```bash
xrpl-lab wallet create
xrpl-lab fund
xrpl-lab start
```

**Progressione da Camp a Lab:** continua da xrpl-camp:
```bash
xrpl-lab start    # auto-detects camp wallet and certificate
```

## Risultati

**Pacchetto di prova** (`xrpl_lab_proof_pack.json`): registro condivisibile dei moduli completati, degli ID delle transazioni e dei link all'esploratore. Include un hash di integrità SHA-256. Non sono inclusi dati sensibili.

**Certificato** (`xrpl_lab_certificate.json`): registro semplificato del completamento.

**Report** (`reports/*.md`): riepiloghi leggibili da persone di ciò che è stato fatto e dimostrato.

**Pacchetti di audit** (`audit_pack_*.json`): risultati della verifica in batch con hash di integrità SHA-256.

## Modello di sicurezza e affidabilità

**Dati a cui XRPL Lab ha accesso:**
- Seed del portafoglio (memorizzato localmente in `~/.xrpl-lab/wallet.json` come JSON in chiaro, protetto da permessi di file 0o600 e una directory principale con permessi 0o700 – non crittografato)
- Avanzamento dei moduli e ID delle transazioni (memorizzati in `~/.xrpl-lab/state.json`, scritture atomiche tramite tmp + ridenominazione)
- XRPL Testnet RPC (endpoint pubblico, le transazioni vengono firmate localmente prima dell'invio)
- Faucet della testnet (HTTP pubblico, viene inviato solo il tuo indirizzo)

**Dati a cui XRPL Lab NON ha accesso:**
- Nessuna mainnet. Solo testnet
- Nessuna telemetria, analisi o trasmissione di dati di alcun tipo
- Nessun account cloud, nessuna registrazione, nessuna API di terze parti
- Nessun dato sensibile nei pacchetti di prova, nei certificati, nei report o nelle serie di dati di supporto – mai

**Permessi e livelli di archiviazione:**
- Directory principale `~/.xrpl-lab/`: livello privato per i dati sensibili, directory con permessi 0o700 + file del portafoglio con permessi 0o600. Memorizza il seed del portafoglio, il registro degli errori e i pacchetti di audit.
- Area di lavoro `./.xrpl-lab/`: livello progettato per la condivisione, directory con permessi 0o755. Memorizza i report dei moduli, i pacchetti di prova e i certificati. I facilitatori possono esaminarli senza richiedere autorizzazioni aggiuntive.
- File system: legge e scrive solo nelle due posizioni sopra indicate
- Rete: solo XRPL Testnet RPC + faucet (entrambi modificabili tramite variabili d'ambiente, entrambi facoltativi con `--dry-run`)
- Non sono richieste autorizzazioni elevate

**Interfaccia del dashboard (quando `xrpl-lab serve` è in esecuzione):**
- L'endpoint del runner WebSocket applica una lista di origine consentita (chiude le connessioni non presenti nella lista con il codice 4003)
- Tutti i frame di errore emettono un envelope strutturato (`code`, `message`, `hint`, `severity`, `icon_hint`) – nessuna divulgazione del percorso, nessuna divulgazione dello stato interno
- Coda di messaggi per connessione limitata con comportamento documentato della gestione della pressione

Consulta [SECURITY.md](SECURITY.md) per la politica di sicurezza completa e le linee guida sulla configurazione del workshop.

## Requisiti

- Python 3.11+
- Connessione Internet per la testnet (o utilizzare `--dry-run` per la modalità completamente offline)

## Licenza

MIT

Creato da [MCP Tool Shop](https://mcp-tool-shop.github.io/)
