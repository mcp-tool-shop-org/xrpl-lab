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

各モジュールでは、XRPLに関する1つのスキルを習得し、検証可能な成果物（トランザクションID、署名付きの領収書、または診断レポート）を作成します。アカウント登録や不要な機能は一切なく、必要な知識と成果のみを提供します。

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

10の分野にわたる32のモジュール：基礎、NFT、トークン、決済、ID管理、分散型取引所（DEX）、準備金、監査、自動マーケットメーカー（AMM）、および最終課題。前提条件は明確に定められており、コマンドラインインターフェースとリンターによって強制されます。

「#」列は、`xrpl-lab list`コマンドで表示される順序（標準的なトラックの順序）と一致します。

<!-- カリキュラム：自動生成されたREADMEテーブルの開始 -->
<!-- scripts/gen_docs.pyによって生成されました。手動で編集しないでください。代わりに、ジェネレーターを実行してください。 -->
| # | モジュール | 追跡する、記録する、線路 | モード | 前提条件 | 制作する、作り出す。 |
|---|--------|-------|------|---------------|----------|
| 1 | レシートの読み解き能力 | 基礎、基盤、財団 | テストネット | — | トランザクションID、レポート |
| 2 | 失敗から学ぶ力 | 基礎、基盤、財団 | テストネット | レシートの読み解き能力 | トランザクションID、レポート |
| 3 | 信頼関係の構築：発行通貨を人間関係として捉える | 基礎、基盤、財団 | テストネット | — | トランザクションID、レポート |
| 4 | 信頼関係の検証と問題解決 | 基礎、基盤、財団 | テストネット | 信頼関係の構築：発行通貨を人間関係として捉える | トランザクションID、レポート |
| 5 | マルチ署名による資金管理（署名者リスト設定）：スタジオウォレットに対するN人中M人の承認制御。 | 基礎、基盤、財団 | テストネット | レシートの読み解き能力 | トランザクションID、レポート |
| 6 | NFTミントの基礎：最初のゲームアセットを作成しよう | NFT（非代替性トークン） | テストネット | — | トランザクションID、レポート |
| 7 | NFTマーケットプレイス入門：ロイヤリティが確実に適用されるアセットの取引について | NFT（非代替性トークン） | テストネット | — | トランザクションID、レポート |
| 8 | ダイナミックNFT入門：レベルアップするゲームアイテム | NFT（非代替性トークン） | テストネット | — | トランザクションID、レポート |
| 9 | MPT発行の基本：ワンストップでゲーム内通貨を発行 | トークン | テストネット | — | トランザクションID、レポート |
| 10 | MPT（マルチプレイヤー・トークン）の配布方法：ゲーム内通貨をプレイヤーに届けるには | トークン | テストネット | MPT発行の基本：ワンストップでゲーム内通貨を発行 | トランザクションID、レポート |
| 11 | トークンの一時停止：発行者の「一時停止ボタン」 | トークン | テストネット | — | トランザクションID、レポート |
| 12 | リコール条項の基本：発行者のリコール権について | トークン | テストネット | — | トランザクションID、レポート |
| 13 | エスクローの基本：時間制限付きXRP | 支払い、支払額 | テストネット | — | トランザクションID、レポート |
| 14 | エスクロー完了の基礎：ロックされたXRPを解放する | 支払い、支払額 | テストネット | エスクローの基本：時間制限付きXRP | トランザクションID、レポート |
| 15 | トークンエスクロー（XLS-85）：IOUをロックするだけでなく、XRPもロックする。 | 支払い、支払額 | テストネット | トラストライン入門：発行通貨を関係性として捉える、エスクロー入門：時間制限付きのXRP | トランザクションID、レポート |
| 16 | 小切手に関する基礎知識101：後日払い方式の引き落とし（小切手の作成／換金／キャンセル） | 支払い、支払額 | テストネット | レシートの読み解き能力 | トランザクションID、レポート |
| 17 | 決済方法の基本：複数の支払い方法を用意し、一括して処理する。 | 支払い、支払額 | テストネット | — | トランザクションID、レポート |
| 18 | 支払われた金額：分割払いを利用した不正行為。 | 支払い、支払額 | テストネット | 信頼関係の構築：発行通貨を人間関係として捉える | トランザクションID、レポート |
| 19 | カストディアルプレイヤーへのクレジット：単一のプールされたウォレット、複数のプレイヤー（宛先タグ） | 支払い、支払額 | テストネット | 支払われた金額：分割払いを利用した不正行為。 | トランザクションID、レポート |
| 20 | DID 101：オン・レジャー型アイデンティティ | アイデンティティ、自己同一性 | テストネット | — | トランザクションID、レポート |
| 21 | 資格認証101（XLS-70）：オン・レジャー形式によるKYCおよび年齢確認 | アイデンティティ、自己同一性 | テストネット | DID 101：オン・レジャー型アイデンティティ | トランザクションID、レポート |
| 22 | 許可されたドメインとアクセス制限付きの分散型取引所（XLS-80/81）：コンプライアンスを遵守し、認証によるアクセス制御を行う取引。 | アイデンティティ、自己同一性 | テストネット | 資格認証101（XLS-70）：オン・レジャー形式によるKYCおよび年齢確認 | トランザクションID、レポート |
| 23 | デポジットゲート（デポジット認証＋事前デポジット認証）：認証による保護された資金の預け入れ。 | アイデンティティ、自己同一性 | テストネット | 資格認証101（XLS-70）：オン・レジャー形式によるKYCおよび年齢確認 | トランザクションID、レポート |
| 24 | DEXリテラシー：提示価格、注文板、および約定キャンセルについて。 | デクス | テストネット | 信頼関係の構築：発行通貨を人間関係として捉える | トランザクションID、レポート |
| 25 | 分散型取引所（DEX）におけるマーケットメイキング入門：注文板で利益を得る方法 | デクス | テストネット | DEXリテラシー：提示価格、注文板、および約定キャンセルについて。 | トランザクションID、レポート |
| 26 | DEXの在庫管理における注意点：偏った状態にならないようにしましょう。 | デクス | テストネット | 分散型取引所（DEX）におけるマーケットメイキング入門：注文板で利益を得る方法 | トランザクションID、レポート |
| 27 | リザーブとは何か：あなたのXRPが「どこへ」行ったのか？ | 予約席、予約状況、準備、備蓄品 | テストネット | 信頼関係の構築：発行通貨を人間関係として捉える | トランザクションID、レポート |
| 28 | アカウントの整理：未使用のアカウントを解放し、不要なオブジェクトを削除する。 | 予約席、予約状況、準備、備蓄品 | テストネット | リザーブとは何か：あなたのXRPが「どこへ」行ったのか？ | トランザクションID、レポート |
| 29 | 監査モード：大量の領収書を効率的に確認する。 | 監査 | テストネット | レシートの読み解き能力 | レポート、監査パッケージ |
| 30 | AMM（自動マーケットメーカー）の流動性とは：流動性の提供と手数料収入について | アンモニア | 予行演習、試運転 | 信頼関係の構築：発行通貨を人間関係として捉える | トランザクションID、レポート |
| 31 | 分散型取引所（DEX）と自動マーケットメーカー（AMM）におけるリスクに関する知識：取引戦略の比較 | アンモニア | 予行演習、試運転 | 分散型取引所（DEX）におけるマーケットメイキングの基礎：注文板でスプレッドを獲得する方法、自動マーケットメーカー（AMM）による流動性提供の基礎：流動性を提供し、手数料を得る方法。 | トランザクションID、レポート |
| 32 | 最終課題：XRPL上に、必要最低限のゲーム経済システムを構築する。 | 最終プロジェクト、集大成 | テストネット | MPT発行の基本：ワンストップでゲーム内通貨を発行、NFT生成の基本：最初のゲームアセットを作成、エスクローの基本：時間制限付きXRPを利用、監査モード：大量の取引明細を検証 | トランザクションID、レポート、監査パッケージ |
<!-- カリキュラムの自動生成機能とreadmeテーブルの終了タグ -->

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

すべてのコマンドは、オフラインモードで利用可能な場合に、`--dry-run`オプションをサポートします。

## ワークショップでの使用

XRPL Labは、実際の教育現場での使用を想定して設計されています。アカウントやテレメトリー、クラウドは一切使用しません。すべての処理はローカルで行われます。

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

ファシリテーターは、セッション全体を再現することなく、サポートバンドルから学習者の問題を診断できます。機密情報は含まれません。

### ワークショップの流れ

**完全オフラインのサンドボックス** — ネットワークは不要です。
```bash
xrpl-lab wallet create
xrpl-lab start --dry-run
```

**オフラインとテストネットの組み合わせ** — 基本的な操作には実際のトランザクションを、高度な操作にはサンドボックスを使用します。
```bash
xrpl-lab wallet create
xrpl-lab fund
xrpl-lab start
```

**CampからLabへの移行** — xrpl-campからの続きとして使用できます。
```bash
xrpl-lab start    # auto-detects camp wallet and certificate
```

## 成果物

**証明パック** (`xrpl_lab_proof_pack.json`): 完了したモジュール、トランザクションID、およびエクスプローラーへのリンクを共有できる記録です。SHA-256の整合性ハッシュが含まれます。機密情報は含まれません。

**証明書** (`xrpl_lab_certificate.json`): 簡潔な完了記録です。

**レポート** (`reports/*.md`): 実行した内容と検証結果を人間が読める形式でまとめたものです。

**監査パック** (`audit_pack_*.json`): SHA-256の整合性ハッシュを含む、一括検証の結果です。

## セキュリティと信頼モデル

**XRPL Labがアクセスするデータ:**
- ウォレットシード（プレーンテキストJSONとして`~/.xrpl-lab/wallet.json`にローカルに保存され、0o600のファイルパーミッションと0o700の親ディレクトリによって保護されます。暗号化はされていません）
- モジュールの進捗状況とトランザクションID（`~/.xrpl-lab/state.json`に保存され、tmp + renameによるアトミックな書き込みが行われます）
- XRPLテストネットRPC（パブリックエンドポイント、送信前にローカルで署名されたトランザクション）
- テストネットFaucet（パブリックHTTP、あなたのウォレットアドレスのみが送信されます）

**XRPL Labがアクセスしないデータ:**
- メインネットは使用しません。テストネットのみです。
- テレメトリー、分析、またはその他の種類の外部への通信は行いません。
- クラウドアカウント、登録、またはサードパーティAPIは使用しません。
- 証明パック、証明書、レポート、またはサポートバンドルに機密情報は一切含まれません。

**権限とストレージ階層:**
- ホームディレクトリ`~/.xrpl-lab/`: 機密情報を保存するプライベートな階層で、0o700のディレクトリと0o600のウォレットファイルがあります。ウォレットシード、診断ログ、監査パックが保存されます。
- ワークスペース`./.xrpl-lab/`: 設計上共有可能な階層で、0o755のディレクトリです。モジュールレポート、証明パック、証明書が保存されます。ファシリテーターは、権限を昇格することなく内容を確認できます。
- ファイルシステム: 上記の2つの場所のみ読み書きします。
- ネットワーク: XRPLテストネットRPCとFaucetのみを使用します（どちらも環境変数でオーバーライド可能で、`--dry-run`オプションを使用すると完全にオフラインモードで使用できます）。
- 特権昇格は必要ありません。

**ダッシュボードの表示 (xrpl-lab serveを実行している場合):**
- WebSocketランナーエンドポイントは、許可リストに登録されたOriginのみを許可します（許可されていない接続はコード4003で閉じられます）。
- すべてのエラーフレームは、構造化されたエンベロープ（`code`、`message`、`hint`、`severity`、`icon_hint`）を出力します。パスや内部状態が漏洩することはありません。
- 接続ごとにメッセージキューがあり、ドキュメントに記載されているバックプレッシャーの動作があります。

完全なセキュリティポリシーとワークショップの設定については、[SECURITY.md](SECURITY.md)を参照してください。

## 要件

- Python 3.11+
- テストネット用のインターネット接続（または、完全にオフラインモードで使用する場合は`--dry-run`を使用します）。

## ライセンス

MIT

[MCP Tool Shop](https://mcp-tool-shop.github.io/)によって作成されました。
