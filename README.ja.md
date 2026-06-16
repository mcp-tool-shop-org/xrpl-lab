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

XRPLトレーニングワークブック：実践を通して学び、成果物で実証する。

各モジュールでは、XRPLの特定のスキルを習得し、検証可能な成果物（トランザクションID、署名付きの領収書、または診断レポート）を作成します。アカウント登録や不要な機能は一切なく、必要な知識と成果のみを提供します。

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/xrpl-lab/main/docs/images/dashboard-hero.png" width="800" alt="XRPL Lab dashboard showing completed modules with quick actions and status panels">
</p>

## インストールする

```bash
pipx install xrpl-lab
```

または、pipを使ってインストールします。

```bash
pip install xrpl-lab
```

Python 3.11 以降が必要です。

## クイックスタートガイド

```bash
xrpl-lab start
```

このガイド付きのランチャーは、ウォレットの設定、資金の投入、そして最初のモジュールの使用方法をステップごとに説明します。

### オフラインモード

```bash
xrpl-lab start --dry-run
```

ネットワーク接続は不要です。ワークフローを学ぶための模擬取引を行います。

## モジュール

10の分野にわたる21のモジュール：基礎、NFT、トークン、決済、ID、分散型取引所（DEX）、準備金、監査、自動マーケットメーカー（AMM）、および最終課題。前提条件は明確に定められており、コマンドラインインターフェースとリンターによって強制されます。

「#」の列は、`xrpl-lab list` コマンドで表示される順序（標準的なトラック順）と一致します。

<!-- カリキュラム：自動生成されたREADMEテーブルの開始 -->
<!-- scripts/gen_docs.pyによって生成されました。手動で編集しないでください。代わりに、ジェネレーターを実行してください。 -->
| # | モジュール | 追跡する、記録する、線路 | モード | 前提条件 | 制作する、作り出す。 |
|---|--------|-------|------|---------------|----------|
| 1 | レシートの読み解き能力 | 基礎、基盤、財団 | テストネット | — | トランザクションID、レポート |
| 2 | 失敗から学ぶ力 | 基礎、基盤、財団 | テストネット | レシートの読み解き能力 | トランザクションID、レポート |
| 3 | 信頼関係の構築：発行通貨を人間関係として捉える | 基礎、基盤、財団 | テストネット | — | トランザクションID、レポート |
| 4 | 信頼関係の検証と問題解決 | 基礎、基盤、財団 | テストネット | 信頼関係の構築：発行通貨を人間関係として捉える | トランザクションID、レポート |
| 5 | NFTミントの基礎：最初のゲームアセットを作成しよう | NFT（非代替性トークン） | テストネット | — | トランザクションID、レポート |
| 6 | NFTマーケットプレイス入門：ロイヤリティが確実に適用されるアセットの取引について | NFT（非代替性トークン） | テストネット | — | トランザクションID、レポート |
| 7 | ダイナミックNFT入門：レベルアップするゲームアイテム | NFT（非代替性トークン） | テストネット | — | トランザクションID、レポート |
| 8 | MPT発行の基本：ワンストップでゲーム内通貨を発行 | トークン | テストネット | — | トランザクションID、レポート |
| 9 | リコール条項の基本：発行者の回収権限について | トークン | テストネット | — | トランザクションID、レポート |
| 10 | エスクローの基本：時間制限付きXRP | 支払い、支払額 | テストネット | — | トランザクションID、レポート |
| 11 | エスクロー完了の基礎：ロックされたXRPを解放する | 支払い、支払額 | テストネット | エスクローの基本：時間制限付きXRP | トランザクションID、レポート |
| 12 | DID 101：オン・レジャー型アイデンティティ | アイデンティティ、自己同一性 | テストネット | — | トランザクションID、レポート |
| 13 | DEXリテラシー：提示価格、注文板、および約定キャンセルについて。 | デクス | テストネット | 信頼関係の構築：発行通貨を人間関係として捉える | トランザクションID、レポート |
| 14 | 分散型取引所（DEX）におけるマーケットメイキング入門：注文板で利益を得る方法 | デクス | テストネット | DEXリテラシー：提示価格、注文板、および約定キャンセルについて。 | トランザクションID、レポート |
| 15 | DEXの在庫管理における注意点：偏った状態にならないようにしましょう。 | デクス | テストネット | 分散型取引所（DEX）におけるマーケットメイキング入門：注文板で利益を得る方法 | トランザクションID、レポート |
| 16 | リザーブとは何か：あなたのXRPが「どこへ」行ったのか？ | 予約、準備、留保 | テストネット | 信頼関係の構築：発行通貨を人間関係として捉える | トランザクションID、レポート |
| 17 | アカウントの整理：未使用のアカウントを解放し、不要なオブジェクトを削除する。 | 予約、準備、留保 | テストネット | リザーブとは何か：あなたのXRPが「どこへ」行ったのか？ | トランザクションID、レポート |
| 18 | 監査モード：大量の領収書を効率的に確認する。 | 監査 | テストネット | レシートの読み解き能力 | レポート、監査パッケージ |
| 19 | AMM（自動マーケットメーカー）の流動性とは：流動性の提供と手数料収入について | （意味が不明なため、翻訳できません。文脈や意図を教えていただければ、適切な翻訳を提供できます。） | 予行演習、試運転 | 信頼関係の構築：発行通貨を人間関係として捉える | トランザクションID、レポート |
| 20 | 分散型取引所（DEX）と自動マーケットメーカー（AMM）におけるリスクに関する知識：取引戦略の比較 | （意味が不明なため、翻訳できません。文脈や意図を教えていただければ、適切な翻訳を提供できます。） | 予行演習、試運転 | 分散型取引所（DEX）におけるマーケットメイキングの基本：注文板でスプレッドを獲得する方法、自動マーケットメーカー（AMM）による流動性提供の基本：流動性を提供し、手数料を得る方法。 | トランザクションID、レポート |
| 21 | 最終課題：XRPL上に、必要最低限のゲーム経済システムを構築する。 | 頂点、集大成、最終プロジェクト | テストネット | MPT発行の基本：ワンストップでゲーム内通貨を発行、NFT生成の基本：最初のゲームアセットを作成、エスクローの基本：時間制限付きXRPを利用、監査モード：大量の取引記録を検証 | トランザクションID、レポート、監査パッケージ |
<!-- カリキュラムの自動生成処理終了：readmeテーブル -->

「**生成物**」欄には、各モジュールが生成する成果物の種類（`txid`、`report`、`audit_pack`）が記載されています。各モジュールの詳細と、オンチェーンで検証される内容については、[ハンドブック](https://mcp-tool-shop-org.github.io/xrpl-lab/handbook/modules/)の各モジュールのページをご覧ください。

### トラック、軌道

<!-- BEGIN curriculum:auto readme-tracks -->
<!-- scripts/gen_docs.py によって生成。手動で編集せず、ジェネレーターを実行してください -->
- **基礎** — ウォレット、決済、信頼関係、エラー処理
- **NFT** — NFTゲームアセット：発行、マーケットプレイスでの取引、動的なNFT（XLS-20）
- **トークン** — 多目的トークン（MPT）、ゲーム内通貨の発行と回収（XLS-33）
- **決済** — エスクローおよび時間制限付きの価値
- **アイデンティティ** — 分散型識別子（DID、XLS-40）
- **DEX** — オファー、注文帳、マーケットメイク、在庫管理
- **リザーブ** — アカウントのリザーブ、オーナー数、クリーンアップ
- **監査** — バッチ検証、監査レポート
- **AMM** — 自動マーケットメーカーの流動性、DEXとAMMの比較
- **集大成** — 各トラックで学んだスキルを統合し、1つのゲーム経済システムを構築する
<!-- END curriculum:auto readme-tracks -->

### モード

- **テストネット**：XRPLテストネット上での実際のトランザクションを実行します。
- **ドライラン**：オフラインのサンドボックス環境で、シミュレーションされたトランザクションを実行します（ネットワークは不要）。

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

可能な限り、すべてのコマンドはオフラインモードで使用できる `--dry-run` オプションをサポートします。

## ワークショップでの使用

XRPLラボは、実際の教育現場での利用を想定して設計されています。アカウント登録やテレメトリー機能、クラウドサービスは一切使用しません。すべての処理はローカルで行われます。

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

### 引き継ぎをサポートします

```bash
xrpl-lab support-bundle              # Human-readable markdown bundle
xrpl-lab support-bundle --json       # Machine-parseable JSON
xrpl-lab support-bundle --verify bundle.json  # Verify a received bundle
```

ファシリテーターは、セッション全体を再現することなく、サポート資料を使って学習者の問題を特定できます。機密情報は含まれません。

### ワークショップの進め方

**完全にオフラインで動作するサンドボックス環境**：ネットワーク接続は不要です。
```bash
xrpl-lab wallet create
xrpl-lab start --dry-run
```

**オフライン環境とテストネットの組み合わせ**：基本的な機能については実際の取引を行い、高度な機能についてはサンドボックス環境で試す。
```bash
xrpl-lab wallet create
xrpl-lab fund
xrpl-lab start
```

**キャンプからラボへの移行**—xrpl-campの続きとして進める。
```bash
xrpl-lab start    # auto-detects camp wallet and certificate
```

## 遺物、工芸品

**検証用パッケージ**（`xrpl_lab_proof_pack.json`）：完了したモジュール、トランザクションID、およびエクスプローラーへのリンクを含む、共有可能な記録。SHA-256による整合性ハッシュが含まれます。機密情報は含まれません。

**証明書**（`xrpl_lab_certificate.json`）：簡潔な修了記録。

**レポート** (`reports/*.md`): あなたが行ったことと、その結果を人間が読める形式でまとめたもの。

**監査用パッケージ** (`audit_pack_*.json`): SHA-256ハッシュによる整合性チェックを含む、一括検証結果。

## セキュリティと信頼モデル

**Data XRPL Labがアクセスするデータ:**
- ウォレットシード（プレーンテキストのJSON形式で`~/.xrpl-lab/wallet.json`にローカルに保存。ファイルパーミッション0o600と、親ディレクトリのパーミッション0o700によって保護されており、暗号化はされていない）
- モジュールの進捗状況とトランザクションID（`~/.xrpl-lab/state.json`に保存。tmpファイルへの書き込みとリネームによるアトミックな書き込み）
- XRPLテストネットRPC（パブリックエンドポイント、送信前にローカルで署名されたトランザクション）
- テストネットのFaucet（パブリックHTTP、あなたのウォレットアドレスのみを送信）

**Data XRPL Labがアクセスしないデータ:**
- メインネットにはアクセスしない。テストネットのみ。
- どのような種類のテレメトリ、分析、または外部への通信も行わない。
- クラウドアカウント、登録、サードパーティAPIは使用しない。
- 証明パッケージ、証明書、レポート、サポートバンドルに秘密情報を一切含めない。

**アクセス権とストレージ階層:**
- ホームディレクトリ`~/.xrpl-lab/`: 秘密情報専用の階層。ディレクトリパーミッション0o700 + ウォレットファイルのパーミッション0o600。ウォレットシード、ログファイル、監査用パッケージを保存。
- 作業ディレクトリ`./.xrpl-lab/`: 共有可能なように設計された階層。ディレクトリパーミッション0o755。モジュールレポート、証明パッケージ、証明書を保存。管理者権限なしでレビュー可能。
- ファイルシステム: 上記の2つの場所のみ読み書きする。
- ネットワーク: XRPLテストネットRPC + Faucetのみ（両方とも環境変数でオーバーライド可能、`--dry-run`オプションを使用するとどちらも省略可能）。
- 特権昇格は不要。

**ダッシュボードの表示内容（`xrpl-lab serve`が実行されている場合）:**
- WebSocketランナーエンドポイントは、許可リストに登録されたオリジンのみを許可する（許可リストにない接続はエラーコード4003で閉じる）。
- すべてのエラーフレームは、構造化されたエンベロープ（`code`、`message`、`hint`、`severity`、`icon_hint`）を出力する。パスや内部状態が漏洩することはない。
- ドキュメント化されたバックプレッシャー動作を持つ、接続ごとに制限されたメッセージキュー。

完全なセキュリティポリシーとワークショップのセットアップ手順については、[SECURITY.md](SECURITY.md)を参照してください。

## 要件

- Python 3.11+
- テストネットへのインターネット接続（完全にオフラインモードで使用する場合は`--dry-run`オプションを使用）。

## ライセンス

MIT

[MCP Tool Shop](https://mcp-tool-shop.github.io/)によって作成されました。
