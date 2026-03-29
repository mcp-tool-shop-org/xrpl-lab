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
已签名收据或诊断报告。 没有冗余内容，只有实用技能和收据。

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

引导式启动程序将引导您完成钱包设置、充值以及第一个模块的学习。

### 离线模式

```bash
xrpl-lab start --dry-run
```

无需网络连接。 模拟交易，用于学习工作流程。

## 模块

分为初级、中级和高级三个阶段，共有 12 个模块。

| # | 模块 | 阶段 | 您将学到的内容 | 您将证明的内容 |
|---|--------|-------|----------------|----------------|
| 1 | 收据知识 | 初级 | 发送支付，阅读每个收据字段 | 交易 ID + 验证报告 |
| 2 | 故障知识 | 初级 | 故意制造交易失败，进行诊断，修复，然后重新提交 | 失败交易 + 修复后的交易 ID 记录 |
| 3 | 信任线基础知识 | 初级 | 创建发行方，设置信任线，发行 令牌 | 信任线 + 令牌余额 |
| 4 | 调试信任线 | 初级 | 故意制造信任线故障，解码错误，修复 | 错误 → 修复后的交易 ID 记录 |
| 5 | 去中心化交易所 (DEX) 知识 | 中级 | 创建订单，阅读订单簿，取消订单 | 创建订单 + 取消订单的交易 ID |
| 6 | 储备金基础知识 | 中级 | 账户快照，持币数量，储备金计算 | 快照前后差异 |
| 7 | 账户维护 | 中级 | 取消订单，移除信任线，释放储备金 | 清理验证报告 |
| 8 | 收据审计 | 中级 | 批量验证带有预期结果的交易 | 审计包 (包含 MD、CSV 和 JSON 文件) |
| 9 | 自动做市商 (AMM) 基础知识 | 高级 | 创建流动性池，存入资产，赚取 LP 收益，提取 | AMM 生命周期交易 ID |
| 10 | 去中心化交易所 (DEX) 做市基础知识 | 高级 | 买入/卖出订单，持仓快照，清理 | 策略交易 ID + 维护报告 |
| 11 | 库存管理 | 高级 | 基于阈值的报价，仅限单向下单 | 库存检查 + 保护交易 ID |
| 12 | 去中心化交易所 (DEX) 与自动做市商 (AMM) 风险知识 | 高级 | 去中心化交易所 (DEX) 和自动做市商 (AMM) 生命周期对比 | 对比报告 + 审计记录 |

## 命令

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
xrpl-lab send --to <address> --amount <xrp> [--memo <text>]  Send a payment
xrpl-lab verify --tx <id>   Verify a transaction on-ledger
```

所有命令都支持 `--dry-run` 参数，用于离线模式（如果适用）。

## 成果

**证明包** (`xrpl_lab_proof_pack.json`): 包含已完成模块的记录，
交易 ID 和链接到浏览器的链接。 包含 SHA-256 完整性哈希值。 不包含任何敏感信息。

**证书** (`xrpl_lab_certificate.json`): 简洁的完成记录。

**报告** (`reports/*.md`): 简明扼要地总结您所做的事情以及您所证明的内容。

**审计包** (`audit_pack_*.json`): 批量验证结果，包含 SHA-256 完整性哈希值。

## 安全与信任模型

**XRPL Lab 访问的数据：**
- 钱包助记词 (存储在本地的 `~/.xrpl-lab/wallet.json` 文件中，具有严格的文件权限)
- 模块进度和交易 ID (存储在 `~/.xrpl-lab/state.json` 文件中)
- XRPL 测试网 RPC (公共端点，交易在本地签名后提交)
- 测试网水龙头 (公共 HTTP，仅发送您的地址)

**XRPL Lab 不会访问的数据：**
- 不支持主网，仅支持测试网。
- 不会收集任何形式的遥测数据、分析数据或远程访问。
- 不使用云账户，无需注册，也不使用任何第三方 API。
- 永远不会在验证包、证书或报告中包含任何敏感信息。

**权限：**
- 文件系统：仅读写 `~/.xrpl-lab/` 和 `./.xrpl-lab/` 目录（本地工作区）。
- 网络：仅支持 XRPL 测试网的 RPC 接口和水龙头（可以通过环境变量进行修改，两者都是可选的，可以使用 `--dry-run` 选项）。
- 不需要任何高级权限。

请参阅 [SECURITY.md](SECURITY.md) 文件以获取完整的安全策略。

## 系统要求

- Python 3.11 及以上版本
- 需要互联网连接才能使用测试网（或者使用 `--dry-run` 选项以实现完全离线模式）。

## 许可证

MIT

由 [MCP Tool Shop](https://mcp-tool-shop.github.io/) 构建。
