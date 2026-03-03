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

XRPL: manuale di formazione – impara facendo, dimostra con prove concrete.

Ogni modulo insegna una competenza specifica di XRPL e produce una prova verificabile: un ID di transazione,
una ricevuta firmata o un rapporto diagnostico. Nessun contenuto superfluo, solo competenze e prove.

## Installazione

```bash
pipx install xrpl-lab
```

Oppure con pip:

```bash
pip install xrpl-lab
```

Richiede Python 3.11 o superiore.

## Guida introduttiva

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

12 moduli suddivisi in tre livelli: principiante, intermedio e avanzato.

| # | Modulo | Livello | Cosa impari | Cosa dimostri |
|---|--------|-------|----------------|----------------|
| 1 | Lettura delle ricevute | Principiante | Effettua un pagamento, leggi ogni campo della ricevuta. | ID transazione + rapporto di verifica |
| 2 | Comprensione degli errori | Principiante | Provoca intenzionalmente un errore in una transazione, diagnostica, risolvi e ripresenta. | Traccia di transazioni fallite e corrette |
| 3 | Linee di fiducia 101 | Principiante | Crea un emittente, imposta una linea di fiducia, emetti token. | Linea di fiducia + saldo del token |
| 4 | Debug delle linee di fiducia | Principiante | Errore intenzionale nella linea di fiducia, decodifica dell'errore, risoluzione. | Traccia di transazioni che mostrano l'errore e la sua correzione |
| 5 | Lettura degli scambi decentralizzati (DEX) | Intermedio | Crea offerte, leggi i libri degli ordini, annulla. | ID delle transazioni di creazione e annullamento delle offerte |
| 6 | Riserve 101 | Intermedio | Snapshot dell'account, numero di proprietari, calcoli delle riserve. | Differenza tra lo snapshot precedente e quello successivo |
| 7 | Gestione dell'account | Intermedio | Annulla offerte, rimuovi linee di fiducia, libera le riserve. | Rapporto di verifica della pulizia |
| 8 | Controllo delle ricevute | Intermedio | Verifica in batch delle transazioni con le aspettative. | Pacchetto di verifica (MD + CSV + JSON) |
| 9 | Liquidità degli scambi decentralizzati (AMM) 101 | Avanzato | Crea un pool, deposita, guadagna LP (Liquid Pool), preleva. | ID delle transazioni del ciclo di vita dell'AMM |
| 10 | Creazione di mercato negli scambi decentralizzati (DEX) 101 | Avanzato | Offerte di acquisto/vendita, snapshot della posizione, pulizia. | ID delle transazioni della strategia + rapporto di pulizia |
| 11 | Protezione dell'inventario | Avanzato | Quotazione basata su soglie, posizionamento solo sul lato sicuro. | Controllo dell'inventario + ID delle transazioni protette |
| 12 | Lettura dei rischi degli scambi decentralizzati rispetto agli AMM | Avanzato | Confronto lato a lato del ciclo di vita degli scambi decentralizzati e degli AMM. | Rapporto di confronto + traccia di verifica |

## Comandi

```
xrpl-lab start              Guided launcher
xrpl-lab list               Show all modules with status
xrpl-lab run <module_id>    Run a specific module
xrpl-lab status             Progress, wallet, recent txs
xrpl-lab proof-pack         Export shareable proof pack
xrpl-lab certificate        Export completion certificate
xrpl-lab doctor             Run diagnostic checks
xrpl-lab self-check         Alias for doctor
xrpl-lab feedback           Generate issue-ready markdown
xrpl-lab audit              Batch verify transactions
xrpl-lab last-run           Show last module run + audit command
xrpl-lab reset              Wipe local state (requires RESET confirmation)

xrpl-lab wallet create      Create a new wallet
xrpl-lab wallet show        Show wallet info (no secrets)
xrpl-lab fund               Fund wallet from testnet faucet
xrpl-lab send               Send a payment
xrpl-lab verify --tx <id>   Verify a transaction on-ledger
```

Tutti i comandi supportano l'opzione `--dry-run` per la modalità offline, quando applicabile.

## Prove

**Pacchetto di prove** (`xrpl_lab_proof_pack.json`): Record condivisibile dei moduli completati,
ID delle transazioni e link all'explorer. Include un hash di integrità SHA-256. Nessun segreto.

**Certificato** (`xrpl_lab_certificate.json`): Record di completamento semplificato.

**Report** (`reports/*.md`): Riepiloghi leggibili da umani di ciò che hai fatto e dimostrato.

**Pacchetti di verifica** (`audit_pack_*.json`): Risultati di verifica in batch con hash di integrità SHA-256.

## Sicurezza e modello di fiducia

**Dati a cui XRPL Lab accede:**
- Seed del wallet (memorizzato localmente in `~/.xrpl-lab/wallet.json` con permessi di file restrittivi)
- Progresso dei moduli e ID delle transazioni (memorizzati in `~/.xrpl-lab/state.json`)
- RPC del testnet XRPL (endpoint pubblico, le transazioni vengono firmate localmente prima dell'invio)
- Faucet del testnet (HTTP pubblico, viene inviato solo il tuo indirizzo)

**Dati a cui XRPL Lab NON accede:**
- Nessuna connessione alla rete principale. Solo alla rete di test.
- Nessuna telemetria, analisi o trasmissione di dati di alcun tipo.
- Nessun account cloud, nessuna registrazione, nessuna API di terze parti.
- Nessun segreto contenuto in pacchetti di verifica, certificati o report, mai.

**Autorizzazioni:**
- File system: lettura/scrittura solo nelle directory `~/.xrpl-lab/` e `./.xrpl-lab/` (area di lavoro locale).
- Rete: solo connessione RPC alla rete di test XRPL e al "faucet" (entrambe modificabili tramite variabili d'ambiente, entrambe opzionali con `--dry-run`).
- Non sono richieste autorizzazioni elevate.

Consultare il file [SECURITY.md](SECURITY.md) per la politica di sicurezza completa.

## Requisiti

- Python 3.11 o superiore
- Connessione a Internet per la rete di test (oppure utilizzare `--dry-run` per la modalità completamente offline).

## Licenza

MIT

Creato da [MCP Tool Shop](https://mcp-tool-shop.github.io/)
