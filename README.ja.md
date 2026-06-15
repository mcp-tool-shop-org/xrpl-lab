<p align="center">
  <a href="README.md">English</a> | <a href="README.zh.md">中文</a> | <a href="README.es.md">Español</a> | <a href="README.fr.md">Français</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.it.md">Italiano</a> | <a href="README.pt-BR.md">Português (BR)</a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/brand/main/logos/xrpl-lab/readme.png" width="500" alt="XRPL Lab">
</p>

<p align="center">
  <a href="https://github.com/mcp-tool-shop-org/xrpl-lab/actions/workflows/ci.yml"><img src="https://github.com/mcp-tool-shop-org/xrpl-lab/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/mcp-tool-shop-org/xrpl-lab/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="MIT License"></a>
  <a href="https://mcp-tool-shop-org.github.io/xrpl-lab/"><img src="https://img.shields.io/badge/Landing_Page-live-blue" alt="Landing Page"></a>
</p>

XRPLトレーニングワークブック - 実践を通して学び、成果物で証明する。

各モジュールでは、1つのXRPLスキルを教え、検証可能な成果物を生成します：トランザクションID、署名されたレシート、または診断レポート。アカウントは不要、無駄な機能もありません。クラウドも使用しません。必要なのは、習熟とレシートだけです。

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/xrpl-lab/main/docs/images/dashboard-hero.png" width="800" alt="XRPL Lab dashboard showing 11/12 modules completed with quick actions and status panels">
</p>

## インストール

```bash
pipx install xrpl-lab
```

またはpipを使って：

```bash
pip install xrpl-lab
```

Python 3.11以上が必要です。

## クイックスタート

```bash
xrpl-lab start
```

ガイダンス付きのランチャーが、ウォレットの設定、資金調達、最初のモジュールまでをガイドします。

### オフラインモード

```bash
xrpl-lab start --dry-run
```

ネットワークは不要です。ワークフローを学習するためのシミュレーションされたトランザクションを使用します。

## モジュール

9つのトラックにまたがる16のモジュール：基礎、NFT、トークン、決済、ID、DEX、リザーブ、監査、AMM。
前提条件は明確に示されており、CLIとリンターによって強制されます。

| # | モジュール | トラック | モード | 学ぶこと | 証明すること |
|---|--------|-------|------|----------------|----------------|
| 1 | レシートの読み書き能力 | 基礎 | テストネット | 確定とは、「送信済み」ステータスではなく、レシートのことです。決済を送信し、すべてのレシートフィールドを読み取ってください。 | txid + 検証レポート |
| 2 | 失敗からの学び | 基礎 | テストネット | XRPLエラーには意味があります（tec/tef/tem/ter）。トランザクションを意図的に中断させ、診断し、修正し、再送信します。 | 失敗したトランザクションと修正後のトランザクションIDの履歴 |
| 3 | トラストライン101 | 基礎 | テストネット | トークンはオプトイン方式で方向性があります。発行者を作成し、トラストラインを設定し、トークンを発行します。 | トラストライン + トークンの残高 |
| 4 | トラストラインのデバッグ | 基礎 | テストネット | トラストラインのエラーコードを解読します。意図的な失敗、エラーのデコード、修正を行います。 | エラー → 修正後のトランザクションIDの履歴 |
| 5 | DEXの読み書き能力 | dex | テストネット | 注文板は、買い手と売り手をペアにします。オファーを作成し、注文板を読み取り、キャンセルします。 | オファー作成 + キャンセルトランザクションID |
| 6 | リザーブ101 | リザーブ | テストネット | 所有するすべてのオブジェクトはXRPをロックします。スナップショット、オーナー数、リザーブの計算を行います。 | 実行前/後のスナップショットデルタ |
| 7 | アカウントの衛生管理 | リザーブ | テストネット | クリーンアップは重要なスキルです。オファーをキャンセルし、トラストラインを削除し、リザーブを解放します。 | クリーンアップ検証レポート |
| 8 | レシート監査 | 監査 | テストネット | 監査は意図をエンコードします（トランザクションID + 期待値 + 結果）。期待値とともにバッチで検証します。 | 監査パック（MD + CSV + JSON） |
| 9 | AMM流動性101 | amm | ドライラン | 定数積（`x*y=k`）により、価格は受動的に決定されます。プールを作成し、入金し、LPを獲得し、引き出します。 | AMMライフサイクルトランザクションID |
| 10 | DEXマーケットメイキング101 | dex | テストネット | 買い/売りスプレッドは在庫を追跡します。両方の価格で提示し、ポジションのスナップショットを取得し、クリーンアップを行います。 | 戦略トランザクションID + 衛生管理レポート |
| 11 | 在庫の安全策 | dex | テストネット | 在庫が偏った場合は、安全な側のみを提示します。閾値ベースで保護された配置を行います。 | 在庫チェック + 保護トランザクションID |
| 12 | DEXとAMMのリスクに関する知識 | amm | ドライラン | インパーマネントロスは、AMMモデルの特性です。DEXとAMMのライフサイクルを並べて比較します。 | 比較レポート + 監査履歴 |
| 13 | NFTミント101 | nfts | テストネット | NFTはネイティブな台帳オブジェクトです。ゲームアセット（タクソン、URI、ロイヤリティ）をミントし、所有権を検証します。 | NFTokenID + オンチェーンでの検証 |
| 14 | MPT発行101 | トークン | テストネット | ゲーム内通貨を1つのトランザクションで作成します。多目的トークン（XLS-33）を発行します：供給上限、スケーリング、フラグを設定します。 | 発行ID + オンチェーンでの検証 |
| 15 | エスクロー101 | 決済 | テストネット | XRPを特定の時間までロックします。時間ベースのエスクローを作成し、オンチェーンで検証します。 | エスクローオブジェクト + FinishAfter |
| 16 | DID101 | ID | テストネット | オンチェーンのID。分散型識別子（XLS-40）をアンカーし、検証します。 | DIDオブジェクト + URI |

### トラック

- **基礎** - ウォレット、決済、トラストライン、エラー処理
- **NFT** - NFTゲームアセット：ミント、コレクション、ロイヤリティ（XLS-20）
- **トークン** - 多目的トークン（MPT）ゲーム内通貨の発行（XLS-33）
- **決済** - エスクローと時間制限付きの価値
- **ID** - 分散型識別子（DID、XLS-40）
- **DEX** - オファー、注文板、マーケットメイキング、在庫管理
- **リザーブ** - アカウントのリザーブ、オーナー数、クリーンアップ
- **監査** - バッチ検証、監査レポート
- **AMM** - 自動マーケットメーカーの流動性、DEXとAMMの比較

### モード

- **テストネット** - XRPLテストネット上の実際のトランザクション
- **ドライラン** - オフラインサンドボックスでシミュレーションされたトランザクションを使用（ネットワークは不要）

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

すべてのコマンドは、適用可能な場合は`--dry-run`をサポートし、オフラインモードで使用できます。

## ワークショップでの使用

XRPL Labは、実際の教育環境向けに設計されています。アカウント、テレメトリ、クラウドは不要です。すべてローカルで実行されます。

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/xrpl-lab/main/docs/images/facilitator-active-runs.png" width="800" alt="Facilitator dashboard listing active learner runs with module IDs, dry-run badges, status, queue depth, and run IDs">
</p>

### ファシリテーターのステータス

```bash
xrpl-lab status             # Where is this learner? What's blocked? What's next?
xrpl-lab status --json      # Machine-readable for scripting
xrpl-lab tracks             # Track-level completion: what was actually practiced
xrpl-lab recovery           # Stuck? See exactly what to run next
```

### サポートの引き継ぎ

```bash
xrpl-lab support-bundle              # Human-readable markdown bundle
xrpl-lab support-bundle --json       # Machine-parseable JSON
xrpl-lab support-bundle --verify bundle.json  # Verify a received bundle
```

ファシリテーターは、学習者の問題をサポートバンドルから診断できます。セッション全体を再現する必要はありません。秘密情報は含まれません。

### ワークショップの流れ

**完全にオフラインのサンドボックス** - ネットワークは不要です：
```bash
xrpl-lab wallet create
xrpl-lab start --dry-run
```

**オフラインとテストネットの組み合わせ** - 基本的な操作には実際のトランザクションを使用し、高度な操作にはサンドボックスを使用します：
```bash
xrpl-lab wallet create
xrpl-lab fund
xrpl-lab start
```

**CampからLabへの移行** - xrpl-campからの継続：
```bash
xrpl-lab start    # auto-detects camp wallet and certificate
```

## 成果物

**証明パック** (`xrpl_lab_proof_pack.json`): 完了したモジュール、トランザクションID、およびエクスプローラーへのリンクを含む、共有可能な記録。SHA-256の整合性ハッシュが含まれます。秘密情報は含まれません。

**証明書** (`xrpl_lab_certificate.json`): 簡潔な完了記録。

**レポート** (`reports/*.md`): あなたが行ったことと、それを証明した内容を人間が読める形式でまとめたもの。

**監査パック** (`audit_pack_*.json`): SHA-256の整合性ハッシュを含む、一括検証結果。

## セキュリティと信頼モデル

**XRPL Labがアクセスするデータ:**
- ウォレットシード（`~/.xrpl-lab/wallet.json`にプレーンテキストのJSONとしてローカルに保存され、0o600のファイルパーミッションと0o700の親ディレクトリによって保護される。暗号化はされない）
- モジュールの進捗状況とトランザクションID（`~/.xrpl-lab/state.json`に保存され、tmp + renameによるアトミックな書き込みが行われる）
- XRPLテストネットRPC（パブリックエンドポイント、送信前にローカルで署名されたトランザクション）
- テストネットファセット（パブリックHTTP、あなたのウォレットアドレスのみが送信される）

**XRPL Labがアクセスしないデータ:**
- メインネットは使用しない。テストネットのみ。
- どのような種類のテレメトリ、分析、または自動的な情報収集も行わない。
- クラウドアカウント、登録、サードパーティAPIは使用しない。
- 証明パック、証明書、レポート、またはサポートバンドルに秘密情報は一切含まれない。

**権限とストレージ階層:**
- ホームディレクトリ`~/.xrpl-lab/`: 秘密情報を保存するプライベートな階層。0o700のディレクトリと0o600のウォレットファイル。ウォレットシード、ドクターログ、監査パックを保存。
- 作業スペース`./.xrpl-lab/`: 共有可能なように設計された階層。0o755のディレクトリ。モジュールレポート、証明パック、証明書を保存。ファシリテーターは権限昇格なしで確認できる。
- ファイルシステム: 上記の2つの場所のみ読み書きを行う。
- ネットワーク: XRPLテストネットRPCとファセットのみ（両方とも環境変数でオーバーライド可能、`--dry-run`オプションを使用するとどちらも省略可能）。
- 特権昇格は不要。

**ダッシュボードの表示内容（`xrpl-lab serve`が実行されている場合）:**
- WebSocketランナーエンドポイントは、許可リストに登録されたオリジンのみを許可する（許可リストにない接続はコード4003で閉じられる）。
- すべてのエラーフレームは、構造化されたエンベロープ（`code`、`message`、`hint`、`severity`、`icon_hint`）を出力する。パスや内部状態が漏洩することはない。
- ドキュメント化されたバックプレッシャー動作を持つ、接続ごとに制限されたメッセージキュー。

完全なセキュリティポリシーとワークショップのセットアップに関するガイダンスについては、[SECURITY.md](SECURITY.md)を参照してください。

## 要件

- Python 3.11+
- テストネットへのインターネット接続（または、完全にオフラインモードで実行する場合は`--dry-run`を使用）。

## ライセンス

MIT

[MCP Tool Shop](https://mcp-tool-shop.github.io/)によって作成されました。
