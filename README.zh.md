<p align="center">
  <a href="README.ja.md">日本語</a> | <a href="README.md">English</a> | <a href="README.es.md">Español</a> | <a href="README.fr.md">Français</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.it.md">Italiano</a> | <a href="README.pt-BR.md">Português (BR)</a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/brand/main/logos/xrpl-lab/readme.png" width="400" alt="XRPL Lab">
</p>

<p align="center">
  <a href="https://github.com/mcp-tool-shop-org/xrpl-lab/actions/workflows/ci.yml"><img src="https://github.com/mcp-tool-shop-org/xrpl-lab/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/mcp-tool-shop-org/xrpl-lab/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="MIT License"></a>
  <a href="https://mcp-tool-shop-org.github.io/xrpl-lab/"><img src="https://img.shields.io/badge/Landing_Page-live-blue" alt="Landing Page"></a>
</p>

XRPL 训练手册 — 通过实践学习，通过成果证明。

每个模块教授一项 XRPL 技能，并生成可验证的成果：交易 ID、
已签名收据或诊断报告。没有账户，没有冗余信息，没有云服务——只有
技能和收据。

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

引导程序将指导您完成钱包设置、充值以及第一个模块的学习。

### 离线模式

```bash
xrpl-lab start --dry-run
```

无需网络连接。模拟交易，用于学习工作流程。

## 模块

包含 12 个模块，分布在五个方向：基础知识、DEX、储备金、审计和自动做市商 (AMM)。
先决条件明确，CLI 和代码检查工具会强制执行。

| # | 模块 | 方向 | 模式 | 您将学到的内容 | 您将证明的内容 |
|---|--------|-------|------|----------------|----------------|
| 1 | 收据知识 | 基础知识 | 测试网络 | 最终确认是一个收据，而不是“已发送”状态——发送一笔付款，阅读每个收据字段。 | 交易 ID + 验证报告 |
| 2 | 故障知识 | 基础知识 | 测试网络 | XRPL 错误具有语义含义（tec/tef/tem/ter）——故意使交易失败，进行诊断，修复，然后重新提交。 | 失败交易的 ID 追踪 |
| 3 | 信任线基础知识 | 基础知识 | 测试网络 | 令牌是可选的，并且是单向的——创建发行者，设置信任线，发行令牌。 | 信任线 + 令牌余额 |
| 4 | 调试信任线 | 基础知识 | 测试网络 | 解码信任线错误代码——故意失败，错误解码，修复。 | 错误 → 修复交易 ID 追踪 |
| 5 | DEX 知识 | DEX | 测试网络 | 订单簿将买家和卖家联系起来——创建报价，阅读订单簿，取消订单。 | 创建报价 + 取消订单的交易 ID |
| 6 | 储备金基础知识 | 储备金 | 测试网络 | 每个拥有的对象都会锁定 XRP——快照、所有者数量、储备金计算。 | 快照前后的差异 |
| 7 | 账户维护 | 储备金 | 测试网络 | 清理是一项重要的技能——取消报价，移除信任线，释放储备金。 | 清理验证报告 |
| 8 | 收据审计 | 审计 | 测试网络 | 审计记录了意图（交易 ID + 期望 + 结论）——使用期望进行批量验证。 | 审计包（MD + CSV + JSON） |
| 9 | AMM 流动性基础知识 | AMM | 模拟运行 | 恒定乘积 (`x*y=k`) 以被动方式确定价格——创建池子，存入资金，赚取流动性代币，提取资金。 | AMM 生命周期交易 ID |
| 10 | DEX 市场做市基础知识 | DEX | 测试网络 | 买入/卖出价差跟踪库存——同时报价，快照仓位，清理。 | 策略交易 ID + 清理报告 |
| 11 | 库存保护 | DEX | 测试网络 | 当库存倾斜时，只报价安全的方面——基于阈值，进行保护性操作。 | 库存检查 + 保护性交易 ID |
| 12 | DEX 与 AMM 风险知识 | AMM | 模拟运行 | 无常损失是 AMM 模型的特性——DEX 和 AMM 生命周期并排比较。 | 比较报告 + 审计追踪 |

### 方向

- **基础知识** — 钱包、支付、信任线、错误处理
- **DEX** — 报价、订单簿、市场做市、库存管理
- **储备金** — 账户储备金、所有者数量、清理
- **审计** — 批量验证、审计报告
- **AMM** — 自动做市商流动性、DEX 与 AMM 比较

### 模式

- **测试网络** — 在 XRPL 测试网络上进行真实交易。
- **模拟运行** — 离线沙箱，使用模拟交易（无需网络连接）。

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

所有命令都支持 `--dry-run`，用于离线模式（如果适用）。

## 工作坊使用

XRPL Lab 旨在用于真实的教学环境。无需账户，无需遥测数据，无需云服务。
所有操作都在本地运行。

### 引导者状态

```bash
xrpl-lab status             # Where is this learner? What's blocked? What's next?
xrpl-lab status --json      # Machine-readable for scripting
xrpl-lab tracks             # Track-level completion: what was actually practiced
xrpl-lab recovery           # Stuck? See exactly what to run next
```

### 支持问题处理

```bash
xrpl-lab support-bundle              # Human-readable markdown bundle
xrpl-lab support-bundle --json       # Machine-parseable JSON
xrpl-lab support-bundle --verify bundle.json  # Verify a received bundle
```

引导者可以通过支持包诊断任何学习者的遇到的问题，而无需重现整个会话。不包含任何敏感信息。

### 工作坊流程

**完全离线沙箱**：无需网络连接。
```bash
xrpl-lab wallet create
xrpl-lab start --dry-run
```

**混合离线 + 测试网络**：基础知识使用真实交易，高级内容使用沙箱环境。
```bash
xrpl-lab wallet create
xrpl-lab fund
xrpl-lab start
```

**从 xrpl-camp 延续**：可以从 xrpl-camp 继续学习。
```bash
xrpl-lab start    # auto-detects camp wallet and certificate
```

## 成果

**证明包** (`xrpl_lab_proof_pack.json`)：包含已完成模块的记录，交易 ID 和浏览器链接。包含 SHA-256 完整性哈希值。不包含任何敏感信息。

**证书** (`xrpl_lab_certificate.json`)：简化的完成记录。

**报告** (`reports/*.md`)：人类可读的摘要，说明您所做的事情以及证明内容。

**审计包** (`audit_pack_*.json`)：包含批量验证结果，以及 SHA-256 完整性哈希值。

## 安全与信任模型

**XRPL Lab 访问的数据：**
- 钱包助记词（以明文 JSON 格式存储在 `~/.xrpl-lab/wallet.json` 中，通过 0o600 文件权限和 0o700 父目录进行保护，未加密）
- 模块进度和交易 ID（存储在 `~/.xrpl-lab/state.json` 中，使用临时文件 + 重命名的方式进行原子写入）
- XRPL 测试网络 RPC（公共端点，交易在本地签名后提交）
- 测试网络水龙头（公共 HTTP，仅发送您的地址）

**XRPL Lab 不访问的数据：**
- 不支持主网络，仅支持测试网络。
- 不收集任何遥测数据、分析数据或任何形式的“远程报告”。
- 不使用任何云账户，不进行任何注册，不使用任何第三方 API。
- 证明包、证书、报告或支持包中绝不包含任何敏感信息。

**权限和存储级别：**
- 根目录 `~/.xrpl-lab/`：私有敏感信息级别，目录权限为 0o700，文件权限为 0o600。存储钱包助记词、调试日志、审计包。
- 工作区 `./.xrpl-lab/`：设计为可共享级别，目录权限为 0o755。存储模块报告、证明包、证书。引导者可以在不提升权限的情况下查看。
- 文件系统：仅读取和写入上述两个位置。
- 网络：仅使用 XRPL 测试网络 RPC 和水龙头（两者都可以通过环境变量覆盖，并且都可以通过 `--dry-run` 选项禁用）。
- 不需要任何提升的权限。

**仪表盘界面（当 `xrpl-lab serve` 运行时）：**
- WebSocket 运行端强制执行 Origin 允许列表（拒绝未在允许列表中连接的连接，返回错误代码 4003）。
- 所有错误帧都包含结构化的数据包（`code`、`message`、`hint`、`severity`、`icon_hint`），不泄露任何路径信息，也不泄露任何内部状态信息。
- 每个连接的消息队列大小有限，并有明确的背压行为说明。

请参阅 [SECURITY.md](SECURITY.md)，了解完整的安全策略和工作坊设置指南。

## 系统要求

- Python 3.11+
- 需要互联网连接才能使用测试网络（或者使用 `--dry-run` 选项以完全离线模式运行）。

## 许可证

MIT

由 [MCP Tool Shop](https://mcp-tool-shop.github.io/) 构建。
