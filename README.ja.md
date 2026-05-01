<p align="center">
  <a href="README.md">English</a> | <a href="README.zh.md">中文</a> | <a href="README.es.md">Español</a> | <a href="README.fr.md">Français</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.it.md">Italiano</a> | <a href="README.pt-BR.md">Português (BR)</a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/brand/main/logos/xrpl-lab/readme.png" width="400" alt="XRPL Lab">
</p>

<p align="center">
  <a href="https://github.com/mcp-tool-shop-org/xrpl-lab/actions/workflows/ci.yml"><img src="https://github.com/mcp-tool-shop-org/xrpl-lab/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/mcp-tool-shop-org/xrpl-lab/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="MIT License"></a>
  <a href="https://mcp-tool-shop-org.github.io/xrpl-lab/"><img src="https://img.shields.io/badge/Landing_Page-live-blue" alt="Landing Page"></a>
</p>

XRPLトレーニング教材 — 実践を通して学び、成果物で証明します。

各モジュールは、XRPLの特定のスキルを教え、検証可能な成果物（トランザクションID、署名済みのレシート、または診断レポート）を生成します。アカウントも、余計な情報も、クラウドも不要です。必要なのは、知識と成果物だけです。

## インストール

```bash
pipx install xrpl-lab
```

または、pipを使用:

```bash
pip install xrpl-lab
```

Python 3.11以上が必要です。

## クイックスタート

```bash
xrpl-lab start
```

ガイド付きのランチャーが、ウォレットの設定、資金の投入、最初のモジュールの学習をサポートします。

### オフラインモード

```bash
xrpl-lab start --dry-run
```

ネットワーク接続は不要です。ワークフローを学習するためのシミュレーションされたトランザクションを実行します。

## モジュール

5つのトラック（基礎、DEX、リザーブ、監査、AMM）に合計12のモジュールがあります。前提条件は明確に示されており、CLIとリンターによって強制されます。

| # | モジュール | トラック | モード | 学習内容 | 証明するもの |
|---|--------|-------|------|----------------|----------------|
| 1 | レシートの理解 | 基礎 | テストネット | トランザクションの完了は、レシートによって確認されます。「送信済み」ステータスではありません。支払いを行い、すべてのレシートの項目を確認してください。 | トランザクションID + 検証レポート |
| 2 | エラーの理解 | 基礎 | テストネット | XRPLのエラーには意味があります（tec/tef/tem/ter）。意図的にトランザクションを失敗させ、診断し、修正し、再送信します。 | 失敗したトランザクションの追跡 |
| 3 | トラストラインの基礎 | 基礎 | テストネット | トークンはオプトインであり、一方通行です。発行者を作成し、トラストラインを設定し、トークンを発行します。 | トラストライン + トークン残高 |
| 4 | トラストラインのデバッグ | 基礎 | テストネット | トラストラインのエラーコードをデコードします。意図的な失敗、エラーのデコード、修正を行います。 | エラー → 修正されたトランザクションIDの追跡 |
| 5 | DEXの理解 | DEX | テストネット | 板寄せは、買い手と売り手を結びつけます。オファーを作成し、板寄せを確認し、キャンセルします。 | オファー作成 + キャンセル トランザクションID |
| 6 | リザーブの基礎 | リザーブ | テストネット | 所有するすべてのオブジェクトは、XRPをロックします。スナップショット、所有者数、リザーブ計算。 | スナップショット前後の差分 |
| 7 | アカウントの管理 | リザーブ | テストネット | クリーンアップは重要なスキルです。オファーをキャンセルし、トラストラインを削除し、リザーブを解放します。 | クリーンアップの検証レポート |
| 8 | 監査 | 監査 | テストネット | 監査は、意図をコード化します（トランザクションID + 期待値 + 判定）。期待値とともに一括で検証します。 | 監査パッケージ（MD + CSV + JSON） |
| 9 | AMMの流動性の基礎 | AMM | シミュレーション | 定数積（x*y=k）は、受動的に価格を決定します。プールを作成し、預け入れを行い、流動性マイニング報酬を獲得し、引き出します。 | AMMのライフサイクル トランザクションID |
| 10 | DEXのマーケットメイキングの基礎 | DEX | テストネット | 買い/売りスプレッドは、在庫を追跡します。両方の価格を提示し、ポジションのスナップショットを作成し、クリーンアップします。 | 戦略 トランザクションID + 管理レポート |
| 11 | 在庫の制限 | DEX | テストネット | 在庫が偏っている場合は、安全な価格のみを提示します。閾値に基づいた、安全な価格設定を行います。 | 在庫チェック + 安全なトランザクションID |
| 12 | DEXとAMMのリスクの理解 | AMM | シミュレーション | インパーマネントロスは、AMMモデルの特性です。DEXとAMMのライフサイクルを並べて比較します。 | 比較レポート + トランザクションIDの追跡 |

### トラック

- **基礎**: ウォレット、支払い、トラストライン、エラー処理
- **DEX**: オファー、板寄せ、マーケットメイキング、在庫管理
- **リザーブ**: アカウントのリザーブ、所有者数、クリーンアップ
- **監査**: 一括検証、監査レポート
- **AMM**: 自動マーケットメイカーの流動性、DEXとAMMの比較

### モード

- **テストネット**: XRPLテストネット上の実際のトランザクション
- **シミュレーション**: オフラインのサンドボックスで、シミュレーションされたトランザクションを実行します（ネットワーク接続は不要）。

## コマンド

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

すべてのコマンドは、オフラインモードで実行できる`--dry-run`オプションをサポートしています。

## ワークショップでの利用

XRPL Labは、実際の教育環境での利用を想定して設計されています。アカウント、テレメトリー、クラウドは一切不要です。
すべてがローカルで動作します。

### ファシリテーターの役割

```bash
xrpl-lab status             # Where is this learner? What's blocked? What's next?
xrpl-lab status --json      # Machine-readable for scripting
xrpl-lab tracks             # Track-level completion: what was actually practiced
xrpl-lab recovery           # Stuck? See exactly what to run next
```

### サポート体制

```bash
xrpl-lab support-bundle              # Human-readable markdown bundle
xrpl-lab support-bundle --json       # Machine-parseable JSON
xrpl-lab support-bundle --verify bundle.json  # Verify a received bundle
```

ファシリテーターは、サポートバンドルから、学習者の問題を診断できます。セッション全体を再現する必要はありません。機密情報は一切含まれていません。

### ワークショップの流れ

**オフラインサンドボックス**：ネットワーク接続は不要です。
```bash
xrpl-lab wallet create
xrpl-lab start --dry-run
```

**オフラインとテストネットの組み合わせ**：基本的な操作には実際のトランザクションを使用し、高度な操作にはサンドボックスを使用します。
```bash
xrpl-lab wallet create
xrpl-lab fund
xrpl-lab start
```

**xrpl-campからの継続**：xrpl-campで学習した内容を、このラボでさらに深めます。
```bash
xrpl-lab start    # auto-detects camp wallet and certificate
```

## 成果物

**証明パック** (`xrpl_lab_proof_pack.json`)：完了したモジュール、トランザクションID、およびエクスプローラーへのリンクをまとめた共有可能な記録です。SHA-256による整合性チェックサムが含まれています。機密情報は一切含まれていません。

**証明書** (`xrpl_lab_certificate.json`)：完了状況を簡潔にまとめた記録です。

**レポート** (`reports/*.md`)：行ったことや検証結果を人間が読めるようにまとめたものです。

**監査パック** (`audit_pack_*.json`)：SHA-256による整合性チェックサム付きの検証結果のバッチデータです。

## セキュリティと信頼性

**XRPL Labが扱うデータ:**
- ウォレットのシードフレーズ（`~/.xrpl-lab/wallet.json`にプレーンテキストのJSON形式で保存。ファイル権限は0o600、親ディレクトリの権限は0o700で保護。暗号化はされていません。）
- モジュールの進捗状況とトランザクションID（`~/.xrpl-lab/state.json`に保存。一時ファイルを使用してアトミックに書き込みます。）
- XRPLテストネットのRPC（パブリックエンドポイント。トランザクションはローカルで署名してから送信されます。）
- テストネットのファセット（パブリックHTTP。送信されるのはあなたのアドレスのみです。）

**XRPL Labが扱わないデータ:**
- メインネットは使用しません。テストネットのみです。
- テレメトリー、アナリティクス、およびあらゆる種類のデータ送信は行いません。
- クラウドアカウント、登録、およびサードパーティのAPIは使用しません。
- 証明パック、証明書、レポート、およびサポートバンドルには、いかなる機密情報も含まれません。

**権限とストレージの階層:**
- ホームディレクトリ `~/.xrpl-lab/`：機密情報を保存するディレクトリ。権限は0o700、ウォレットファイルは0o600です。ウォレットのシードフレーズ、ログ、監査パックなどを保存します。
- ワークスペースディレクトリ `./.xrpl-lab/`：共有することを想定したディレクトリ。権限は0o755です。モジュールのレポート、証明パック、証明書などを保存します。ファシリテーターは、特別な権限なしで内容を確認できます。
- ファイルシステム：上記の2つのディレクトリへのみ読み書きを行います。
- ネットワーク：XRPLテストネットのRPCとファセットのみを使用します（どちらも環境変数で上書き可能で、`--dry-run`オプションで無効にできます）。
- 特権的な権限は必要ありません。

**ダッシュボードのインターフェース（`xrpl-lab serve`が実行中）：**
- WebSocketランナーのエンドポイントは、許可リストに基づいて接続を制限します（許可されていない接続はコード4003で拒否されます）。
- すべてのエラーメッセージは、構造化された形式（`code`、`message`、`hint`、`severity`、`icon_hint`）で出力されます。パス情報や内部状態の情報は一切含まれません。
- 接続ごとのメッセージキューには上限があり、オーバーフロー時の動作がドキュメントに記載されています。

セキュリティポリシーの詳細とワークショップのセットアップについては、[SECURITY.md](SECURITY.md) を参照してください。

## システム要件

- Python 3.11 以降
- テストネットを使用するにはインターネット接続が必要です（完全にオフラインで使用する場合は、`--dry-run` オプションを使用します）。

## ライセンス

MIT

開発元：[MCP Tool Shop](https://mcp-tool-shop.github.io/)
