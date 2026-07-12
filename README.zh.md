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

XRPL 培训手册——通过实践学习，以成果证明。

每个模块教授一项 XRPL 相关技能，并生成可验证的成果：交易 ID、已签名的收据或诊断报告。无需账户注册，没有冗余信息，也不需要云服务——我们只关注实际能力和结果。

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/xrpl-lab/main/docs/images/dashboard-hero.png" width="800" alt="XRPL Lab dashboard showing completed modules with quick actions and status panels">
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

引导程序会逐步指导您完成钱包设置、资金充值以及使用第一个模块的操作。

### 离线模式

```bash
xrpl-lab start --dry-run
```

无需网络连接。提供模拟交易，以便学习操作流程。

## 模块

包含十个主题的 32 个模块：基础知识、NFT、令牌、支付、身份验证、去中心化交易所 (DEX)、储备金、审计、自动做市商 (AMM) 和综合项目。

明确规定了先修条件，命令行界面和代码检查工具会强制执行这些条件。

“#”列显示与`xrpl-lab list`命令输出的顺序一致（即标准排序）。

<!-- 开始：课程自动生成的 README 表格 -->
<!-- 由脚本 scripts/gen_docs.py 生成，请勿手动编辑；运行生成器即可 -->
| # | 模块 | 跟踪；轨迹；音轨 | 模式。 | 先决条件。 | 生产；产生。 |
|---|--------|-------|------|---------------|----------|
| 1 | 收据解读能力 | 基础；地基；建立 | 测试网络 | — | 事务 ID，报告。 |
| 2 | 应对失败的能力/从失败中学习的能力 | 基础；地基；建立 | 测试网络 | 收据解读能力 | 事务 ID，报告。 |
| 3 | 信任关系入门：已发行货币即为一种关系。 | 基础；地基；建立 | 测试网络 | — | 事务 ID，报告。 |
| 4 | 调试信任关系。 | 基础；地基；建立 | 测试网络 | 信任关系入门：已发行货币即为一种关系。 | 事务 ID，报告。 |
| 5 | 多重签名资金管理（签名人列表）：对工作室钱包进行“N选M”控制。 | 基础；地基；建立 | 测试网络 | 收据解读能力 | 事务 ID，报告。 |
| 6 | NFT铸造入门：您的第一个游戏资产。 | 非同质化代币 | 测试网络 | — | 事务 ID，报告。 |
| 7 | NFT 交易平台入门：通过强制执行版税来交易数字资产。 | 非同质化代币 | 测试网络 | — | 事务 ID，报告。 |
| 8 | 动态 NFT 入门：一种可以升级的游戏道具。 | 非同质化代币 | 测试网络 | — | 事务 ID，报告。 |
| 9 | MPT 发行指南：一次交易即可完成游戏货币的发行。 | 令牌 | 测试网络 | — | 事务 ID，报告。 |
| 10 | 《多人游戏货币分配基础知识：如何将虚拟货币分发给玩家》 | 令牌 | 测试网络 | MPT 发行指南：一次交易即可完成游戏货币的发行。 | 事务 ID，报告。 |
| 11 | 令牌冻结入门：发行方的暂停按钮。 | 令牌 | 测试网络 | — | 事务 ID，报告。 |
| 12 | 回购机制入门：发行人可行的回购手段。 | 令牌 | 测试网络 | — | 事务 ID，报告。 |
| 13 | 托管服务入门：限时锁定的瑞波币（XRP） | 付款；支付 | 测试网络 | — | 事务 ID，报告。 |
| 14 | 托管服务终结指南：解锁被锁定的 XRP。 | 付款；支付 | 测试网络 | 托管服务入门：限时锁定的瑞波币（XRP） | 事务 ID，报告。 |
| 15 | 令牌托管（XLS-85）：锁定欠款，而不仅仅是XRP。 | 付款；支付 | 测试网络 | 信任线路入门：已发行货币作为关系纽带；托管服务入门：带有时间锁的瑞波币。 | 事务 ID，报告。 |
| 16 | 支票操作指南 101：延迟付款（支票创建/支票兑付/支票作废） | 付款；支付 | 测试网络 | 收据解读能力 | 事务 ID，报告。 |
| 17 | 支付渠道入门：支持多种支付方式，一次性结算。 | 付款；支付 | 测试网络 | — | 事务 ID，报告。 |
| 18 | 已交付金额：分期付款漏洞。 | 付款；支付 | 测试网络 | 信任关系入门：已发行货币即为一种关系。 | 事务 ID，报告。 |
| 19 | 托管方玩家积分：一个共享钱包，多个玩家（目标标签） | 付款；支付 | 测试网络 | 已交付金额：分期付款漏洞。 | 事务 ID，报告。 |
| 20 | DID 101：基于账本的身份认证 | 身份；个性；识别 | 测试网络 | — | 事务 ID，报告。 |
| 21 | 资质认证 101（XLS-70）：基于账本的“了解您的客户”（KYC）和年龄验证。 | 身份；个性；识别 | 测试网络 | DID 101：基于账本的身份认证 | 事务 ID，报告。 |
| 22 | 受权限控制的域名和封闭式去中心化交易所（XLS-80/81）：符合规范、基于身份验证的交易。 | 身份；个性；识别 | 测试网络 | 资质认证 101（XLS-70）：基于账本的“了解您的客户”（KYC）和年龄验证。 | 事务 ID，报告。 |
| 23 | 存款网关（包括凭据验证和预授权）：通过身份验证控制的资金存入。 | 身份；个性；识别 | 测试网络 | 资质认证 101（XLS-70）：基于账本的“了解您的客户”（KYC）和年龄验证。 | 事务 ID，报告。 |
| 24 | DEX 流动性：报价、订单簿和取消操作。 | （通常指）甲氧安非他命，一种兴奋剂。 | 测试网络 | 信任关系入门：已发行货币即为一种关系。 | 事务 ID，报告。 |
| 25 | 去中心化交易所（DEX）做市商入门：从订单簿中获取价差收益。 | （通常指）甲氧安非他命，一种兴奋剂。 | 测试网络 | DEX 流动性：报价、订单簿和取消操作。 | 事务 ID，报告。 |
| 26 | DEX 库存管理规范：避免出现偏差。 | （通常指）甲氧安非他命，一种兴奋剂。 | 测试网络 | 去中心化交易所（DEX）做市商入门：从订单簿中获取价差收益。 | 事务 ID，报告。 |
| 27 | 储备金 101：您的 XRP “去了哪里”？ | 储备；保留；预订 | 测试网络 | 信任关系入门：已发行货币即为一种关系。 | 事务 ID，报告。 |
| 28 | 账户维护：释放储备资源并清理对象。 | 储备；保留；预订 | 测试网络 | 储备金 101：您的 XRP “去了哪里”？ | 事务 ID，报告。 |
| 29 | 审计模式：大规模验证收据。 | 审计；审核。 | 测试网络 | 收据解读能力 | 报告，审计包。 |
| 30 | AMM 流动性基础知识：提供流动性并赚取手续费。 | 氨 | 预演；模拟运行 | 信任关系入门：已发行货币即为一种关系。 | 事务 ID，报告。 |
| 31 | 去中心化交易所（DEX）与自动做市商（AMM）的风险认知：比较交易策略。 | 氨 | 预演；模拟运行 | 去中心化交易所（DEX）做市商入门：通过订单簿赚取价差；自动做市商（AMM）流动性提供入门：提供流动性并赚取手续费。 | 事务 ID，报告。 |
| 32 | 最终项目：在 XRP Ledger 上构建一个简化的游戏经济系统。 | 顶点；最重要的部分；毕业设计。 | 测试网络 | MPT 发行入门：一次交易即可获得游戏货币；NFT 创建入门：您的第一个游戏资产；托管服务入门：时间锁定的 XRP；审计模式：大规模验证收据。 | 事务 ID、报告、审计包。 |
<!-- 课程大纲：自动生成 README 表格 -->

“**生成内容**”一栏列出了每个模块所生成的工件类型（`txid`、`report`、`audit_pack`）；请参阅[手册](https://mcp-tool-shop-org.github.io/xrpl-lab/handbook/modules/)中各个模块的页面，以了解完整的技能介绍以及您需要在链上证明的内容。

### 轨道；音轨；足迹

- **基础知识**——钱包、支付、信任关系、错误处理
- **NFT**——NFT游戏资产：铸造、市场结算、动态NFT（XLS-20）
- **令牌**——多用途令牌（MPT）游戏货币发行与回收（XLS-33）
- **支付**——托管和时间锁定的价值
- **身份**——去中心化标识符（DID，XLS-40）
- **DEX**——报价、订单簿、做市、库存管理
- **储备金**——账户储备、所有者数量、清理
- **审计**——批量验证、审计报告
- **AMM**——自动化做市商流动性、DEX与AMM的比较
- **总结**——将各个模块中的技能组合起来，构建一个完整的游戏经济系统

### 模式

- **测试网络**——在 XRPL 测试网上进行真实的交易。
- **模拟运行**——离线沙盒环境，用于模拟交易（无需网络连接）。

## 命令；指令

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

所有命令都支持使用 `--dry-run` 参数进行离线模式下的模拟运行（如果适用）。

## 用于车间

XRPL Lab 专为真实的教学环境设计。无需账户、无需遥测数据，也不需要云服务。所有操作都在本地进行。

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/xrpl-lab/main/docs/images/facilitator-active-runs.png" width="800" alt="Facilitator dashboard listing active learner runs with module IDs, dry-run badges, status, queue depth, and run IDs">
</p>

### 指导者状态

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

指导者可以从支持包中诊断任何学习者的遇到的问题，而无需重现整个会话。其中不包含任何敏感信息。

### 研讨会流程

**完全离线沙盒**——无需网络连接：
```bash
xrpl-lab wallet create
xrpl-lab start --dry-run
```

**混合离线 + 测试网**——基本操作使用真实交易，高级操作使用沙盒：
```bash
xrpl-lab wallet create
xrpl-lab fund
xrpl-lab start
```

**从“训练营”过渡到“实验室”**——继续使用 xrpl-camp 的内容：
```bash
xrpl-lab start    # auto-detects camp wallet and certificate
```

## 成果

**证明包** (`xrpl_lab_proof_pack.json`)：可共享的已完成模块记录、交易 ID 和资源链接。包含 SHA-256 完整性哈希值。不包含任何敏感信息。

**证书** (`xrpl_lab_certificate.json`)：精简的完成记录。

**报告** (`reports/*.md`)：以人类可读的方式总结您所做的事情和已证明的内容。

**审计包** (`audit_pack_*.json`)：包含 SHA-256 完整性哈希值的批量验证结果。

## 安全与信任模型

**XRPL Lab 访问的数据：**
- 钱包种子（以明文 JSON 格式存储在 `~/.xrpl-lab/wallet.json` 中，受 0o600 文件权限和 0o700 父目录保护——未加密）
- 模块进度和交易 ID（存储在 `~/.xrpl-lab/state.json` 中，通过 tmp + 重命名进行原子写入）
- XRPL 测试网 RPC（公共端点，事务在提交前在本地签名）
- 测试网水龙头（公共 HTTP，仅发送您的地址）

**XRPL Lab 不会访问的数据：**
- 无主网。仅限测试网
- 无遥测数据、分析或任何形式的“回传”功能
- 无云账户、无注册、无第三方 API
- 证明包、证书、报告或支持包中绝不包含任何敏感信息

**权限和存储层级：**
- 主目录 `~/.xrpl-lab/`——私有密钥层级，0o700 目录 + 0o600 钱包文件。存储钱包种子、调试日志、审计包。
- 工作区 `./.xrpl-lab/`——设计为可共享的层级，0o755 目录。存储模块报告、证明包、证书。指导者无需提升权限即可查看。
- 文件系统：仅读取和写入上述两个位置
- 网络：仅 XRPL 测试网 RPC + 水龙头（两者都可以通过环境变量覆盖，并且都是可选的，可以使用 `--dry-run`）
- 无需高级权限

**仪表板界面（当 `xrpl-lab serve` 运行时）：**
- WebSocket 运行程序端点强制执行 Origin 允许列表（关闭未在允许列表中连接，返回代码 4003）
- 所有错误帧都发出结构化的信封 (`code`, `message`, `hint`, `severity`, `icon_hint`)——不泄露路径信息，不泄露内部状态
- 每个连接都有一个有界的消息队列，并记录了反压行为

有关完整的安全策略和研讨会设置指南，请参阅 [SECURITY.md](SECURITY.md)。

## 要求

- Python 3.11+
- 测试网需要互联网连接（或者使用 `--dry-run` 以完全离线模式运行）

## 许可证

MIT

由 [MCP Tool Shop](https://mcp-tool-shop.github.io/) 构建
