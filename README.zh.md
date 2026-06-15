<p align="center">
  <a href="README.ja.md">日本語</a> | <a href="README.md">English</a> | <a href="README.es.md">Español</a> | <a href="README.fr.md">Français</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.it.md">Italiano</a> | <a href="README.pt-BR.md">Português (BR)</a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/brand/main/logos/xrpl-lab/readme.png" width="500" alt="XRPL Lab">
</p>

<p align="center">
  <a href="https://github.com/mcp-tool-shop-org/xrpl-lab/actions/workflows/ci.yml"><img src="https://github.com/mcp-tool-shop-org/xrpl-lab/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/mcp-tool-shop-org/xrpl-lab/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="MIT License"></a>
  <a href="https://mcp-tool-shop-org.github.io/xrpl-lab/"><img src="https://img.shields.io/badge/Landing_Page-live-blue" alt="Landing Page"></a>
</p>

XRPL 培训手册——通过实践学习，通过成果证明。

每个模块教授一项 XRPL 技能并生成一个可验证的成果：交易 ID、已签名的收据或诊断报告。无需账户、无需多余内容、无需云服务——只需掌握技能和获得凭证。

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/xrpl-lab/main/docs/images/dashboard-hero.png" width="800" alt="XRPL Lab dashboard showing 11/12 modules completed with quick actions and status panels">
</p>

## 安装

```bash
pipx install xrpl-lab
```

或者使用 pip：

```bash
pip install xrpl-lab
```

需要 Python 3.11 或更高版本。

## 快速入门

```bash
xrpl-lab start
```

引导式启动程序会指导您完成钱包设置、资金充值和第一个模块的学习过程。

### 离线模式

```bash
xrpl-lab start --dry-run
```

无需网络连接。模拟交易用于学习工作流程。

## 模块

包含 16 个模块，涵盖九个主题：基础知识、NFT、令牌、支付、身份验证、去中心化交易所 (DEX)、储备金、审计和自动做市商 (AMM)。
先决条件明确——命令行界面 (CLI) 和代码检查器会强制执行这些条件。

| # | 模块 | 主题 | 模式 | 您将学习的内容 | 您将证明的内容 |
|---|--------|-------|------|----------------|----------------|
| 1 | 收据解读 | 基础知识 | 测试网络 | 最终确认是一个收据，而不是“已发送”状态——发送付款，读取每个收据字段。 | txid + 验证报告 |
| 2 | 失败解读 | 基础知识 | 测试网络 | XRPL 错误具有语义（tec/tef/tem/ter）——故意使交易失败，进行诊断、修复并重新提交。 | 已失败 + 已修复的 txid 记录 |
| 3 | 信任线 101 | 基础知识 | 测试网络 | 令牌是可选且单向的——创建发行者，设置信任线，发行令牌。 | 信任线 + 令牌余额 |
| 4 | 调试信任线 | 基础知识 | 测试网络 | 解码信任线错误代码——有意的失败、错误解码、修复。 | 错误 → 修复的 txid 记录 |
| 5 | DEX 解读 | 去中心化交易所 | 测试网络 | 订单簿将做市商与买家配对——创建报价，读取订单簿，取消。 | 报价创建 + 取消的 txid |
| 6 | 储备金 101 | 储备金 | 测试网络 | 每个拥有的对象都会锁定 XRP——快照、所有者数量、储备金计算。 | 之前/之后快照差异 |
| 7 | 账户维护 | 储备金 | 测试网络 | 清理是一项重要的技能——取消报价，删除信任线，释放储备金。 | 清理验证报告 |
| 8 | 收据审计 | 审计 | 测试网络 | 审计编码了意图（txid + 预期 + 结果）——使用预期批量验证。 | 审计包（MD + CSV + JSON） |
| 9 | AMM 流动性 101 | 自动做市商 | 模拟运行 | 恒定乘积 (`x*y=k`) 以被动方式定价——创建池，存入资金，赚取流动性提供者费用，提取。 | AMM 生命周期 txid |
| 10 | DEX 市场做市商 101 | 去中心化交易所 | 测试网络 | 买/卖价差跟踪库存——同时报价双方，快照头寸，清理。 | 策略 txid + 维护报告 |
| 11 | 库存安全保障 | 去中心化交易所 | 测试网络 | 当库存倾斜时，仅报价安全的一方——基于阈值的受保护的交易。 | 库存检查 + 受保护的 txid |
| 12 | DEX 与 AMM 风险解读 | 自动做市商 | 模拟运行 | 无常损失是 AMM 模型的一个属性——并排比较 DEX 和 AMM 生命周期。 | 比较报告 + 审计跟踪 |
| 13 | NFT 铸造 101 | NFT | 测试网络 | NFT 是原生账本对象——铸造游戏资产（分类单元、URI、版税），验证所有权。 | NFTokenID + 链上验证 |
| 14 | MPT 发行 101 | 令牌 | 测试网络 | 一次交易中的游戏货币——发行多用途令牌（XLS-33）：供应上限、缩放、标志。 | 发行 ID + 链上验证 |
| 15 | 质押 101 | 支付 | 测试网络 | 锁定 XRP 直到某个时间——创建基于时间的质押，在账本上进行验证。 | 质押对象 + FinishAfter |
| 16 | DID 101 | 身份验证 | 测试网络 | 链上身份——锚定去中心化标识符（XLS-40），进行验证。 | DID 对象 + URI |

### 主题

- **基础知识**——钱包、支付、信任线、错误处理
- **NFT**——NFT 游戏资产：铸造、系列、版税（XLS-20）
- **令牌**——多用途令牌 (MPT) 游戏货币发行（XLS-33）
- **支付**——质押和时间锁定的价值
- **身份验证**——去中心化标识符（DID，XLS-40）
- **DEX**——报价、订单簿、市场做市商、库存管理
- **储备金**——账户储备金、所有者数量、清理
- **审计**——批量验证、审计报告
- **AMM**——自动做市商流动性，DEX 与 AMM 比较

### 模式

- **测试网络**——在 XRPL 测试网上进行真实交易。
- **模拟运行**——离线沙盒，使用模拟交易（无需网络连接）。

## 命令

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

所有命令都支持 `--dry-run` 选项，以便在适用时进行离线模式操作。

## 研讨会使用

XRPL Lab 专为实际教学环境设计。无需账户、无需遥测数据、无需云服务。所有内容都在本地运行。

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/xrpl-lab/main/docs/images/facilitator-active-runs.png" width="800" alt="Facilitator dashboard listing active learner runs with module IDs, dry-run badges, status, queue depth, and run IDs">
</p>

### 协调员状态

```bash
xrpl-lab status             # Where is this learner? What's blocked? What's next?
xrpl-lab status --json      # Machine-readable for scripting
xrpl-lab tracks             # Track-level completion: what was actually practiced
xrpl-lab recovery           # Stuck? See exactly what to run next
```

### 支持移交

```bash
xrpl-lab support-bundle              # Human-readable markdown bundle
xrpl-lab support-bundle --json       # Machine-parseable JSON
xrpl-lab support-bundle --verify bundle.json  # Verify a received bundle
```

协调员可以从支持包中诊断任何学习者的遇到的问题，而无需重现整个会话。不包含任何秘密信息。

### 研讨会流程

**完全离线沙盒**——无需网络连接：
```bash
xrpl-lab wallet create
xrpl-lab start --dry-run
```

**混合离线 + 测试网络**——对于基础知识使用真实交易，对于高级内容使用沙盒：
```bash
xrpl-lab wallet create
xrpl-lab fund
xrpl-lab start
```

**从 xrpl-camp 逐步过渡到 Lab**——继续使用 xrpl-camp 的内容：
```bash
xrpl-lab start    # auto-detects camp wallet and certificate
```

## 成果

**证明包**（`xrpl_lab_proof_pack.json`）：可共享的已完成模块记录、交易 ID 和资源链接。包含 SHA-256 完整性哈希值。不包含任何敏感信息。

**证书**（`xrpl_lab_certificate.json`）：精简的完成记录。

**报告**（`reports/*.md`）：对您所做的工作和已验证内容的人类可读摘要。

**审计包**（`audit_pack_*.json`）：包含 SHA-256 完整性哈希值的批量验证结果。

## 安全与信任模型

**XRPL Lab 访问的数据：**
- 钱包种子（以纯文本 JSON 格式存储在 `~/.xrpl-lab/wallet.json` 中，受 0o600 文件权限和 0o700 父目录保护——未加密）
- 模块进度和交易 ID（存储在 `~/.xrpl-lab/state.json` 中，通过临时文件 + 重命名进行原子写入）
- XRPL 测试网 RPC（公共端点，事务在提交前本地签名）
- 测试网水龙头（公共 HTTP，仅发送您的地址）

**XRPL Lab 不访问的数据：**
- 不使用主网。仅使用测试网。
- 不收集任何形式的遥测数据、分析数据或“回传”信息。
- 不使用云帐户、不进行注册，也不使用第三方 API。
- 证明包、证书、报告或支持包中绝不会包含任何敏感信息。

**权限和存储层级：**
- 主目录 `~/.xrpl-lab/`——私有敏感数据层级，0o700 目录 + 0o600 钱包文件。存储钱包种子、日志文件和审计包。
- 工作区 `./.xrpl-lab/`——设计为可共享的层级，0o755 目录。存储模块报告、证明包和证书。协调员无需提升权限即可查看。
- 文件系统：仅读取/写入上述两个位置。
- 网络：仅使用 XRPL 测试网 RPC + 水龙头（两者都可以通过环境变量覆盖，并且都是可选的，可以使用 `--dry-run`）。
- 不需要任何提升的权限。

**仪表板界面（当 `xrpl-lab serve` 运行时）：**
- WebSocket 运行程序端点强制执行 Origin 允许列表（关闭未在允许列表中连接，返回代码 4003）。
- 所有错误帧都发出一个结构化的信封（`code`、`message`、`hint`、`severity`、`icon_hint`），不泄露路径信息，也不泄露内部状态。
- 每个连接都有一个有界的消息队列，并记录了反压行为。

有关完整的安全策略和研讨会设置指南，请参阅 [SECURITY.md](SECURITY.md)。

## 要求

- Python 3.11+
- 测试网的互联网连接（或者使用 `--dry-run` 以完全离线模式运行）

## 许可证

MIT

由 [MCP Tool Shop](https://mcp-tool-shop.github.io/) 构建。
