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

XRPL : manuel de formation – apprenez en pratiquant, prouvez par des résultats concrets.

Chaque module enseigne une compétence XRPL et produit un résultat vérifiable : un identifiant de transaction,
un reçu signé ou un rapport de diagnostic. Pas de comptes inutiles, juste des compétences et des résultats.

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

L'assistant guidé vous accompagne dans la configuration de votre portefeuille, le financement et votre premier module.

### Mode hors ligne

```bash
xrpl-lab start --dry-run
```

Aucune connexion réseau requise. Transactions simulées pour apprendre le processus.

## Modules

12 modules répartis en trois niveaux : débutant, intermédiaire et avancé.

| # | Module | Niveau | Ce que vous apprenez | Ce que vous prouvez |
|---|--------|-------|----------------|----------------|
| 1 | Lecture des reçus | Débutant | Effectuer un paiement, lire chaque champ du reçu. | Identifiant de transaction + rapport de vérification |
| 2 | Analyse des erreurs | Débutant | Faire échouer une transaction intentionnellement, diagnostiquer, corriger, renvoyer. | Chaîne d'identifiants de transactions échouées et corrigées |
| 3 | Principes de base des lignes de confiance | Débutant | Créer un émetteur, définir une ligne de confiance, émettre des jetons. | Ligne de confiance + solde des jetons |
| 4 | Débogage des lignes de confiance | Débutant | Échec intentionnel d'une ligne de confiance, décodage des erreurs, correction. | Chaîne d'identifiants de transactions d'erreur → correction |
| 5 | Principes de base de la bourse décentralisée (DEX) | Intermédiaire | Créer des offres, lire les carnets d'ordres, annuler. | Identifiants de création et d'annulation des offres |
| 6 | Principes de base des réserves | Intermédiaire | Instantanés des comptes, nombre de propriétaires, calcul des réserves. | Différence entre l'état avant et après l'instantané |
| 7 | Maintenance des comptes | Intermédiaire | Annuler les offres, supprimer les lignes de confiance, libérer les réserves. | Rapport de vérification de la maintenance |
| 8 | Audit des reçus | Intermédiaire | Vérifier par lots les transactions avec les attentes. | Paquet d'audit (MD + CSV + JSON) |
| 9 | Principes de base de la liquidité des marchés automatisés (AMM) | Avancé | Créer un pool, déposer, gagner des LP (Liquid Pool Tokens), retirer. | Identifiants du cycle de vie de l'AMM |
| 10 | Principes de base de la création de marché sur une bourse décentralisée (DEX) | Avancé | Offres d'achat/vente, instantanés de position, maintenance. | Identifiants de la stratégie + rapport de maintenance |
| 11 | Contrôles de l'inventaire | Avancé | Cotation basée sur des seuils, placement uniquement côté sécurisé. | Vérification de l'inventaire + identifiants protégés |
| 12 | Différences entre DEX et AMM : analyse des risques | Avancé | Comparaison côte à côte du cycle de vie d'une DEX et d'une AMM. | Rapport de comparaison + historique des transactions |

## Commandes

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

Toutes les commandes prennent en charge l'option `--dry-run` pour le mode hors ligne, le cas échéant.

## Résultats concrets

**Paquet de preuve** (`xrpl_lab_proof_pack.json`) : Enregistrement partageable des modules terminés,
des identifiants de transaction et des liens vers l'explorateur. Inclut un hachage d'intégrité SHA-256. Ne contient aucun secret.

**Certificat** (`xrpl_lab_certificate.json`) : Enregistrement simplifié de l'achèvement.

**Rapports** (`reports/*.md`) : Résumés lisibles par l'homme de ce que vous avez fait et prouvé.

**Paquets d'audit** (`audit_pack_*.json`) : Résultats de vérification par lots avec un hachage d'intégrité SHA-256.

## Sécurité et modèle de confiance

**Données auxquelles XRPL Lab accède :**
- Clé de portefeuille (stockée localement dans `~/.xrpl-lab/wallet.json` avec des permissions de fichier restrictives)
- Progression des modules et identifiants de transaction (stockés dans `~/.xrpl-lab/state.json`)
- RPC du réseau de test XRPL (point de terminaison public, les transactions sont signées localement avant d'être soumises)
- Robinette du réseau de test (HTTP public, uniquement votre adresse est envoyée)

**Données que XRPL Lab ne traite PAS :**
- Pas de réseau principal. Uniquement le réseau de test.
- Aucune télémétrie, analyse ou transmission de données à des serveurs externes.
- Pas de comptes cloud, pas d'inscription, pas d'API tierces.
- Aucun secret dans les paquets de preuve, les certificats ou les rapports, jamais.

**Autorisations :**
- Système de fichiers : lecture/écriture uniquement dans les répertoires `~/.xrpl-lab/` et `./.xrpl-lab/` (espace de travail local).
- Réseau : Accès RPC au réseau de test XRPL et au "faucet" (les deux peuvent être modifiés via les variables d'environnement, et les deux sont facultatifs avec l'option `--dry-run`).
- Aucune autorisation spéciale requise.

Consultez le fichier [SECURITY.md](SECURITY.md) pour la politique de sécurité complète.

## Prérequis

- Python 3.11 ou version supérieure
- Connexion Internet pour le réseau de test (ou utilisez l'option `--dry-run` pour un mode entièrement hors ligne).

## Licence

MIT

Créé par [MCP Tool Shop](https://mcp-tool-shop.github.io/)
