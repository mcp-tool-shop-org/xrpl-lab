<p align="center">
  <a href="README.ja.md">日本語</a> | <a href="README.zh.md">中文</a> | <a href="README.es.md">Español</a> | <a href="README.md">English</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.it.md">Italiano</a> | <a href="README.pt-BR.md">Português (BR)</a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/brand/main/logos/xrpl-lab/readme.png" width="500" alt="XRPL Lab">
</p>

<p align="center">
  <a href="https://github.com/mcp-tool-shop-org/xrpl-lab/actions/workflows/ci.yml"><img src="https://github.com/mcp-tool-shop-org/xrpl-lab/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/mcp-tool-shop-org/xrpl-lab/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="MIT License"></a>
  <a href="https://mcp-tool-shop-org.github.io/xrpl-lab/"><img src="https://img.shields.io/badge/Landing_Page-live-blue" alt="Landing Page"></a>
</p>

Manuel de formation XRPL : apprenez en pratiquant, prouvez par des exemples concrets.

Chaque module enseigne une compétence XRPL et produit un exemple vérifiable : un ID de transaction,
un reçu signé ou un rapport de diagnostic. Pas de comptes, pas de superflu, pas de cloud – juste
des compétences et des reçus.

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/xrpl-lab/main/docs/images/dashboard-hero.png" width="800" alt="XRPL Lab dashboard showing 11/12 modules completed with quick actions and status panels">
</p>

## Installer

```bash
pipx install xrpl-lab
```

Ou avec pip :

```bash
pip install xrpl-lab
```

Nécessite Python 3.11 ou supérieur.

## Démarrage rapide

```bash
xrpl-lab start
```

Le lanceur guidé vous guide à travers la configuration du portefeuille, le financement et votre premier module.

### Mode hors ligne

```bash
xrpl-lab start --dry-run
```

Aucun réseau requis. Transactions simulées pour apprendre le flux de travail.

## Modules

16 modules répartis en neuf thèmes : Fondamentaux, NFT, jetons, paiements, identité, DEX, réserves, audit et AMM.
Les prérequis sont clairement définis – l’interface de ligne de commande (CLI) et le vérificateur les font respecter.

| # | Module | Thème | Mode | Ce que vous apprenez | Ce que vous prouvez |
|---|--------|-------|------|----------------|----------------|
| 1 | Maîtrise des reçus | fondamentaux | testnet | La finalité est un reçu, et non un statut « envoyé » – envoyez un paiement, lisez chaque champ du reçu. | txid + rapport de vérification |
| 2 | Maîtrise des échecs | fondamentaux | testnet | Les erreurs XRPL ont une sémantique (tec/tef/tem/ter) – provoquez intentionnellement une erreur de transaction, diagnostiquez-la, corrigez-la et renvoyez-la. | txid d’échec + historique des corrections |
| 3 | Lignes de confiance 101 | fondamentaux | testnet | Les jetons nécessitent une autorisation préalable et sont directionnels – créez un émetteur, définissez une ligne de confiance, émettez des jetons. | ligne de confiance + solde du jeton |
| 4 | Débogage des lignes de confiance | fondamentaux | testnet | Décryptez les codes d’erreur des lignes de confiance – défaillance intentionnelle, décodage de l’erreur, correction. | erreur → historique des txid de correction |
| 5 | Maîtrise du DEX | dex | testnet | Les carnets d’ordres mettent en relation les vendeurs et les acheteurs – créez des offres, consultez les carnets d’ordres, annulez. | txid de création + d’annulation d’offre |
| 6 | Réserves 101 | réserves | testnet | Chaque objet détenu bloque des XRP – instantanés, nombre de propriétaires, calcul des réserves. | delta d’instantané avant/après |
| 7 | Hygiène du compte | réserves | testnet | Le nettoyage est une compétence essentielle – annulez les offres, supprimez les lignes de confiance, libérez les réserves. | rapport de vérification du nettoyage |
| 8 | Audit des reçus | audit | testnet | Les audits encodent l’intention (txid + attente + verdict) – vérifiez par lots avec les attentes. | paquet d’audit (MD + CSV + JSON) |
| 9 | Liquidité AMM 101 | amm | exécution à blanc | Le produit constant (`x*y=k`) fixe passivement les prix – créez un pool, déposez des fonds, gagnez des frais de liquidité, retirez. | txid du cycle de vie AMM |
| 10 | Création de marché DEX 101 | dex | testnet | Les écarts acheteur/vendeur suivent les stocks – coter les deux côtés, prendre des instantanés des positions, nettoyer. | txid de stratégie + rapport d’hygiène |
| 11 | Garde-fous sur les stocks | dex | testnet | Ne cotez que le côté sûr lorsque les stocks sont déséquilibrés – basé sur un seuil, placement protégé. | vérification des stocks + txid protégés |
| 12 | Maîtrise des risques DEX par rapport à AMM | amm | exécution à blanc | La perte temporaire est une propriété du modèle AMM – cycle de vie DEX et AMM côte à côte. | rapport comparatif + historique d’audit |
| 13 | Création de NFT 101 | nfts | testnet | Les NFT sont des objets natifs du registre – créez un actif de jeu (taxon, URI, redevance), vérifiez la propriété. | NFTokenID + vérification sur le registre |
| 14 | Émission MPT 101 | jetons | testnet | Une monnaie de jeu dans une seule transaction – émettez un jeton polyvalent (XLS-33) : limite d’approvisionnement, échelle, indicateurs. | ID d’émission + vérification sur le registre |
| 15 | Escrow 101 | paiements | testnet | Bloquez des XRP jusqu’à un certain moment – créez un escrow basé sur le temps, vérifiez-le sur le registre. | objet escrow + FinishAfter |
| 16 | DID 101 | identité | testnet | Identité sur le registre – ancrez un identifiant décentralisé (XLS-40), vérifiez-le. | objet DID + URI |

### Thèmes

- **fondamentaux** – portefeuille, paiements, lignes de confiance, gestion des erreurs
- **nfts** – actifs de jeu NFT : création, collections, redevances (XLS-20)
- **jetons** – émission de jeton polyvalent (MPT), monnaie du jeu (XLS-33)
- **paiements** – escrow et valeur bloquée dans le temps
- **identité** – identifiants décentralisés (DID, XLS-40)
- **dex** – offres, carnets d’ordres, création de marché, gestion des stocks
- **réserves** – réserves du compte, nombre de propriétaires, nettoyage
- **audit** – vérification par lots, rapports d’audit
- **amm** – liquidité du teneur de marché automatisé, comparaison DEX et AMM

### Modes

- **testnet** – transactions réelles sur le testnet XRPL
- **exécution à blanc** – bac à sable hors ligne avec des transactions simulées (aucun réseau requis)

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

Toutes les commandes prennent en charge l’option `--dry-run` pour le mode hors ligne, lorsque cela est applicable.

## Utilisation dans un atelier

XRPL Lab est conçu pour des environnements d’enseignement réels. Pas de comptes, pas de télémétrie, pas de cloud. Tout s’exécute localement.

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/xrpl-lab/main/docs/images/facilitator-active-runs.png" width="800" alt="Facilitator dashboard listing active learner runs with module IDs, dry-run badges, status, queue depth, and run IDs">
</p>

### Statut du facilitateur

```bash
xrpl-lab status             # Where is this learner? What's blocked? What's next?
xrpl-lab status --json      # Machine-readable for scripting
xrpl-lab tracks             # Track-level completion: what was actually practiced
xrpl-lab recovery           # Stuck? See exactly what to run next
```

### Transfert d’assistance

```bash
xrpl-lab support-bundle              # Human-readable markdown bundle
xrpl-lab support-bundle --json       # Machine-parseable JSON
xrpl-lab support-bundle --verify bundle.json  # Verify a received bundle
```

Un facilitateur peut diagnostiquer le problème de n’importe quel apprenant à partir d’un ensemble d’assistance sans avoir à reproduire toute la session. Aucun secret n’est inclus.

### Déroulement des ateliers

**Bac à sable entièrement hors ligne** – aucun réseau requis :
```bash
xrpl-lab wallet create
xrpl-lab start --dry-run
```

**Hors ligne + testnet mixtes** – transactions réelles pour les bases, bac à sable pour les éléments avancés :
```bash
xrpl-lab wallet create
xrpl-lab fund
xrpl-lab start
```

**Progression de Camp vers Lab** – continuez à partir de xrpl-camp :
```bash
xrpl-lab start    # auto-detects camp wallet and certificate
```

## Artefacts

**Ensemble de preuves** (`xrpl_lab_proof_pack.json`) : ensemble de données partageable contenant les modules terminés, les identifiants des transactions et les liens vers l’explorateur. Il comprend un hachage d’intégrité SHA-256. Aucune information sensible n’y est stockée.

**Certificat** (`xrpl_lab_certificate.json`) : enregistrement succinct de la progression.

**Rapports** (`reports/*.md`) : résumés lisibles par l’homme de ce que vous avez fait et prouvé.

**Ensembles d’audit** (`audit_pack_*.json`) : résultats de vérification groupés avec un hachage d’intégrité SHA-256.

## Modèle de sécurité et de confiance

**Données auxquelles XRPL Lab a accès :**
- Clé privée du portefeuille (stockée localement dans `~/.xrpl-lab/wallet.json` au format JSON en texte clair, protégée par des permissions de fichier 0o600 et un répertoire parent avec les permissions 0o700 — non chiffrée)
- Progression des modules et identifiants des transactions (stockés dans `~/.xrpl-lab/state.json`, écrit atomique via un fichier temporaire + renommage)
- RPC du réseau de test XRPL (point de terminaison public, les transactions sont signées localement avant l’envoi)
- Distributeur du réseau de test (HTTP public, seule votre adresse est envoyée)

**Données auxquelles XRPL Lab n’a PAS accès :**
- Pas d’accès au réseau principal. Uniquement le réseau de test.
- Aucune télémétrie, analyse ou transmission de données vers un serveur externe.
- Aucun compte cloud, aucun enregistrement, aucune API tierce.
- Aucune information sensible dans les ensembles de preuves, les certificats, les rapports ou les fichiers d’assistance — jamais.

**Permissions et niveaux de stockage :**
- Répertoire personnel `~/.xrpl-lab/` : niveau de confidentialité privée, répertoire avec les permissions 0o700 + fichier de portefeuille avec les permissions 0o600. Stocke la clé privée du portefeuille, le journal d’activité et les ensembles d’audit.
- Espace de travail `./.xrpl-lab/` : niveau conçu pour être partagé, répertoire avec les permissions 0o755. Stocke les rapports des modules, les ensembles de preuves et les certificats. Les facilitateurs peuvent consulter ces éléments sans élévation de privilèges.
- Système de fichiers : lecture/écriture uniquement dans les deux emplacements ci-dessus.
- Réseau : uniquement le RPC du réseau de test XRPL + distributeur (les deux peuvent être remplacés via des variables d’environnement, les deux sont facultatifs avec l’option `--dry-run`).
- Aucune permission élevée n’est requise.

**Interface du tableau de bord (lorsque `xrpl-lab serve` est en cours d’exécution) :**
- Le point de terminaison WebSocket applique une liste blanche d’origines autorisées (ferme les connexions non autorisées avec le code 4003).
- Tous les messages d’erreur émettent une enveloppe structurée (`code`, `message`, `hint`, `severity`, `icon_hint`) — aucune fuite de chemin, aucune fuite d’état interne.
- File d’attente de messages par connexion limitée avec un comportement documenté en cas de surcharge.

Consultez le fichier [SECURITY.md](SECURITY.md) pour connaître l’intégralité de la politique de sécurité et les instructions de configuration de l’atelier.

## Prérequis

- Python 3.11+
- Connexion Internet pour le réseau de test (ou utilisez l’option `--dry-run` pour un mode entièrement hors ligne).

## Licence

MIT

Créé par [MCP Tool Shop](https://mcp-tool-shop.github.io/)
