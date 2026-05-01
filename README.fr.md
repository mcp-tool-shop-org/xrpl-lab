<p align="center">
  <a href="README.ja.md">日本語</a> | <a href="README.zh.md">中文</a> | <a href="README.es.md">Español</a> | <a href="README.md">English</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.it.md">Italiano</a> | <a href="README.pt-BR.md">Português (BR)</a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/brand/main/logos/xrpl-lab/readme.png" width="400" alt="XRPL Lab">
</p>

<p align="center">
  <a href="https://github.com/mcp-tool-shop-org/xrpl-lab/actions/workflows/ci.yml"><img src="https://github.com/mcp-tool-shop-org/xrpl-lab/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/mcp-tool-shop-org/xrpl-lab/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="MIT License"></a>
  <a href="https://mcp-tool-shop-org.github.io/xrpl-lab/"><img src="https://img.shields.io/badge/Landing_Page-live-blue" alt="Landing Page"></a>
</p>

XRPL : manuel de formation – apprenez en pratiquant, prouvez vos compétences grâce aux résultats.

Chaque module enseigne une compétence XRPL et produit un résultat vérifiable : un identifiant de transaction,
un reçu signé ou un rapport de diagnostic. Pas de comptes, pas de fioritures, pas de cloud : seulement
des compétences et des résultats.

## Installation

```bash
pipx install xrpl-lab
```

Ou avec pip :

```bash
pip install xrpl-lab
```

Nécessite Python 3.11 ou supérieur.

## Démarrage rapide

```bash
xrpl-lab start
```

Le lanceur guidé vous accompagne dans la configuration de votre portefeuille, le financement et votre premier module.

### Mode hors ligne

```bash
xrpl-lab start --dry-run
```

Aucun réseau requis. Transactions simulées pour apprendre le processus.

## Modules

12 modules répartis en cinq domaines : Bases, DEX, Réserves, Audit et AMM.
Les prérequis sont clairement définis, et l'interface en ligne de commande (CLI) et le linter les font respecter.

| # | Module | Domaine | Mode | Ce que vous apprenez | Ce que vous prouvez |
|---|--------|-------|------|----------------|----------------|
| 1 | Compréhension des reçus | Bases | Testnet | La finalisation est un reçu, et non un statut "envoyé" – effectuez un paiement, examinez chaque champ du reçu. | Identifiant de transaction + rapport de vérification |
| 2 | Compréhension des erreurs | Bases | Testnet | Les erreurs XRPL ont une signification (tec/tef/tem/ter) – provoquez intentionnellement une erreur, diagnostiquez, corrigez, renvoyez. | Chaîne d'identifiants de transactions échouées et corrigées |
| 3 | Principes des lignes de confiance | Bases | Testnet | Les jetons sont facultatifs et unidirectionnels – créez un émetteur, définissez une ligne de confiance, émettez des jetons. | Ligne de confiance + solde du jeton |
| 4 | Débogage des lignes de confiance | Bases | Testnet | Décodez les codes d'erreur des lignes de confiance – échec intentionnel, décodage de l'erreur, correction. | Erreur → chaîne d'identifiants de transactions corrigées |
| 5 | Compréhension du DEX | DEX | Testnet | Les carnets d'ordres mettent en relation les acheteurs et les vendeurs – créez des offres, consultez les carnets d'ordres, annulez. | Identifiants de transactions de création et d'annulation d'offres |
| 6 | Principes des réserves | Réserves | Testnet | Chaque objet détenu verrouille des XRP – instantanés, nombre de propriétaires, calcul des réserves. | Différence entre l'état avant et après l'instantané |
| 7 | Hygiène du compte | Réserves | Testnet | Le nettoyage est une compétence essentielle – annulez les offres, supprimez les lignes de confiance, libérez les réserves. | Rapport de vérification du nettoyage |
| 8 | Audit | Audit | Testnet | Les audits encodent l'intention (identifiant de transaction + attente + verdict) – vérifiez par lots avec des attentes. | Paquet d'audit (MD + CSV + JSON) |
| 9 | Principes de la liquidité AMM | AMM | Test en mode simulation | Les prix constants (`x*y=k`) sont déterminés passivement – créez un pool, déposez des fonds, gagnez des LP, retirez. | Identifiants de transactions du cycle de vie de l'AMM |
| 10 | Principes de la création de marché DEX | DEX | Testnet | Les écarts entre les prix d'achat et de vente suivent l'inventaire – citez les deux côtés, prenez des instantanés des positions, nettoyez. | Identifiants de transactions de stratégie + rapport d'hygiène |
| 11 | Contrôles de l'inventaire | DEX | Testnet | Citez uniquement le côté sûr lorsque l'inventaire est déséquilibré – basé sur des seuils, placement sécurisé. | Vérification de l'inventaire + identifiants de transactions sécurisés |
| 12 | Compréhension des risques DEX vs AMM | AMM | Test en mode simulation | La perte de liquidité est une caractéristique du modèle AMM – cycle de vie du DEX et de l'AMM côte à côte. | Rapport de comparaison + chaîne d'audit |

### Domaines

- **Bases** – portefeuille, paiements, lignes de confiance, gestion des erreurs.
- **DEX** – offres, carnets d'ordres, création de marché, gestion de l'inventaire.
- **Réserves** – réserves du compte, nombre de propriétaires, nettoyage.
- **Audit** – vérification par lots, rapports d'audit.
- **AMM** – liquidité de l'automatiseur de marché, comparaison DEX vs AMM.

### Modes

- **Testnet** – transactions réelles sur le réseau de test XRPL.
- **Test en mode simulation** – bac à sable hors ligne avec des transactions simulées (aucun réseau requis).

## Commandes

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

Toutes les commandes prennent en charge l'option `--dry-run` pour le mode hors ligne, le cas échéant.

## Utilisation en atelier

XRPL Lab est conçu pour des environnements d'apprentissage réels. Pas de comptes, pas de télémétrie, pas de cloud.
Tout fonctionne localement.

### Statut de l'animateur

```bash
xrpl-lab status             # Where is this learner? What's blocked? What's next?
xrpl-lab status --json      # Machine-readable for scripting
xrpl-lab tracks             # Track-level completion: what was actually practiced
xrpl-lab recovery           # Stuck? See exactly what to run next
```

### Transmission du support

```bash
xrpl-lab support-bundle              # Human-readable markdown bundle
xrpl-lab support-bundle --json       # Machine-parseable JSON
xrpl-lab support-bundle --verify bundle.json  # Verify a received bundle
```

Un animateur peut diagnostiquer les problèmes d'un apprenant à partir d'un ensemble de données de support sans avoir à reproduire toute la session. Aucun secret n'est inclus.

### Flux de travail des ateliers

**Bac à sable entièrement hors ligne** : aucune connexion réseau requise.
```bash
xrpl-lab wallet create
xrpl-lab start --dry-run
```

**Mode mixte hors ligne + testnet** : transactions réelles pour les bases, bac à sable pour les fonctionnalités avancées.
```bash
xrpl-lab wallet create
xrpl-lab fund
xrpl-lab start
```

**Progression Camp → Lab** : continuation depuis xrpl-camp.
```bash
xrpl-lab start    # auto-detects camp wallet and certificate
```

## Artefacts

**Paquet de preuve** (`xrpl_lab_proof_pack.json`) : enregistrement partageable des modules terminés, des identifiants de transaction et des liens vers l'explorateur. Inclut une somme de contrôle SHA-256. Aucun secret.

**Certificat** (`xrpl_lab_certificate.json`) : enregistrement simplifié de l'achèvement.

**Rapports** (`reports/*.md`) : résumés lisibles par l'homme de ce que vous avez fait et prouvé.

**Paquets d'audit** (`audit_pack_*.json`) : résultats de vérification par lots avec une somme de contrôle SHA-256.

## Modèle de sécurité et de confiance

**Données auxquelles XRPL Lab accède :**
- Clé de portefeuille (stockée localement dans `~/.xrpl-lab/wallet.json` au format JSON en texte clair, protégée par les permissions de fichier 0o600 et un répertoire parent 0o700 – non chiffrée)
- Progression des modules et identifiants de transaction (stockés dans `~/.xrpl-lab/state.json`, écritures atomiques via un fichier temporaire + renommage)
- RPC du testnet XRPL (point de terminaison public, les transactions sont signées localement avant d'être soumises)
- Robinet de testnet (HTTP public, seule votre adresse est envoyée)

**Données auxquelles XRPL Lab N'ACCÈDE PAS :**
- Pas de réseau principal. Uniquement le testnet.
- Pas de télémétrie, d'analyse ou de signalement de quelque nature que ce soit.
- Pas de comptes cloud, pas d'inscription, pas d'API tierces.
- Aucun secret dans les paquets de preuve, les certificats, les rapports ou les ensembles de données de support – jamais.

**Permissions et niveaux de stockage :**
- Répertoire personnel `~/.xrpl-lab/` : niveau de secrets privés, répertoire 0o700 + fichier de portefeuille 0o600. Stocke la clé de portefeuille, le journal de l'animateur, les paquets d'audit.
- Espace de travail `./.xrpl-lab/` : niveau partageable, répertoire 0o755. Stocke les rapports de module, les paquets de preuve, les certificats. Les animateurs peuvent consulter sans élévation de privilèges.
- Système de fichiers : lecture/écriture uniquement dans les deux emplacements ci-dessus.
- Réseau : uniquement le RPC et le robinet du testnet XRPL (les deux peuvent être remplacés via les variables d'environnement, les deux sont facultatifs avec `--dry-run`).
- Aucune permission élevée requise.

**Interface du tableau de bord (lorsque `xrpl-lab serve` est en cours d'exécution) :**
- Le point de terminaison du runner WebSocket applique une liste d'autorisation d'origine (ferme les connexions non autorisées avec le code 4003).
- Toutes les trames d'erreur émettent une enveloppe structurée (`code`, `message`, `hint`, `severity`, `icon_hint`) – aucune fuite de chemin, aucune fuite d'état interne.
- File d'attente de messages par connexion limitée avec un comportement de rétroaction documenté.

Consultez [SECURITY.md](SECURITY.md) pour la politique de sécurité complète et les instructions de configuration de l'atelier.

## Prérequis

- Python 3.11+
- Connexion Internet pour le testnet (ou utilisez `--dry-run` pour un mode entièrement hors ligne)

## Licence

MIT

Développé par [MCP Tool Shop](https://mcp-tool-shop.github.io/)
