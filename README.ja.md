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

XRPL トレーニング教材 — 実践を通して学び、成果物で証明します。

各モジュールは、XRPL の特定のスキルを教え、検証可能な成果物（トランザクションID、署名済みのレシート、または診断レポート）を生成します。アカウント情報や不要な情報は一切なく、実用的なスキルと成果物のみを提供します。

## インストール

```bash
pipx install xrpl-lab
```

または、pip を使用して：

```bash
pip install xrpl-lab
```

Python 3.11 以降が必要です。

## クイックスタート

```bash
xrpl-lab start
```

ガイド付きの起動ツールは、ウォレットの設定、資金の投入、最初のモジュールの学習を支援します。

### オフラインモード

```bash
xrpl-lab start --dry-run
```

ネットワーク接続は不要です。ワークフローを学習するためのシミュレーションされたトランザクションを使用します。

## モジュール

初心者、中級者、上級者の 3 つのレベルで構成された 12 のモジュール。

| # | モジュール | レベル | 学習内容 | 証明するもの |
|---|--------|-------|----------------|----------------|
| 1 | レシートの理解 | 初心者 | 支払い送信、すべてのレシートフィールドの確認 | トランザクションID + 検証レポート |
| 2 | エラーの理解 | 初心者 | 意図的にトランザクションを失敗させ、診断、修正、再送信 | 失敗したトランザクションと修正されたトランザクションの履歴 |
| 3 | 信頼関係の基礎 | 初心者 | 発行者の作成、信頼関係の設定、トークンの発行 | 信頼関係 + トークン残高 |
| 4 | 信頼関係のデバッグ | 初心者 | 意図的に信頼関係を失敗させ、エラーのデコード、修正 | エラー → 修正されたトランザクションの履歴 |
| 5 | 分散型取引所の基礎 | 中級者 | オファーの作成、板の確認、キャンセル | オファー作成 + キャンセル トランザクションID |
| 6 | 残高の基礎 | 中級者 | アカウントのスナップショット、所有者数、残高計算 | スナップショットの前後差分 |
| 7 | アカウントの管理 | 中級者 | オファーのキャンセル、信頼関係の削除、残高の解放 | クリーンアップの検証レポート |
| 8 | レシート監査 | 中級者 | 期待値に基づいてトランザクションをまとめて検証 | 監査パッケージ (MD + CSV + JSON) |
| 9 | 自動マーケットメーカー（AMM）の流動性の基礎 | 上級者 | プール作成、入金、流動性マイニング、引き出し | AMM のライフサイクル トランザクションID |
| 10 | 分散型取引所のマーケットメイキングの基礎 | 上級者 | 買い/売りオファー、ポジションのスナップショット、クリーンアップ | 戦略トランザクションID + 管理レポート |
| 11 | インベントリの制限 | 上級者 | 閾値ベースの価格設定、安全な注文のみの受け付け | インベントリチェック + 保護されたトランザクションID |
| 12 | 分散型取引所と自動マーケットメーカーのリスクの理解 | 上級者 | 分散型取引所と自動マーケットメーカーのライフサイクル比較 | 比較レポート + トランザクション履歴 |

## コマンド

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

すべてのコマンドは、オフラインモードで適用可能な場合、`--dry-run` オプションをサポートしています。

## 成果物

**証明パッケージ** (`xrpl_lab_proof_pack.json`): 完了したモジュールの記録、トランザクションID、およびエクスプローラーへのリンクをまとめた共有可能なファイル。SHA-256による整合性チェックが含まれます。機密情報は含まれません。

**証明書** (`xrpl_lab_certificate.json`): 完了記録の簡略版。

**レポート** (`reports/*.md`): 行ったことと証明したことの人間が読める要約。

**監査パッケージ** (`audit_pack_*.json`): SHA-256による整合性チェックが含まれた、まとめて検証した結果。

## セキュリティと信頼モデル

**XRPL Lab が扱うデータ:**
- ウォレットのシークレット（`~/.xrpl-lab/wallet.json` にローカルに保存され、アクセス制限のあるファイル権限を設定）
- モジュールの進捗状況とトランザクションID（`~/.xrpl-lab/state.json` に保存）
- XRPL テストネットの RPC（公開エンドポイント、トランザクションはローカルで署名後に送信）
- テストネットのファセット（公開HTTP、あなたのアドレスのみが送信される）

**Data XRPL Lab がアクセスしないデータ:**
- メインネットにはアクセスしません。テストネットのみです。
- いかなる種類のテレメトリー、分析、またはデータ送信機能もありません。
- クラウドアカウント、登録、サードパーティAPIは使用しません。
- 認証情報や秘密情報は、証明書やレポートなど、いかなる場合においても含まれません。

**アクセス許可:**
- ファイルシステム: 読み書きできるのは `~/.xrpl-lab/` と `./.xrpl-lab/` (ローカルワークスペース) のみです。
- ネットワーク: XRPL テストネットの RPC と、テスト用のウォレット機能のみを使用します (どちらも環境変数で上書き可能で、`--dry-run` オプションを使用すれば不要になります)。
- 特権的なアクセス権は必要ありません。

セキュリティポリシーの詳細については、[SECURITY.md](SECURITY.md) を参照してください。

## **必要条件:**

- Python 3.11 以降
- テストネットを使用する場合はインターネット接続が必要です (完全にオフラインで使用する場合は、`--dry-run` オプションを使用してください)。

## **ライセンス:**

MIT

[MCP Tool Shop](https://mcp-tool-shop.github.io/) が作成しました。
