<p align="center">
  <a href="README.ja.md">日本語</a> | <a href="README.zh.md">中文</a> | <a href="README.es.md">Español</a> | <a href="README.fr.md">Français</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.it.md">Italiano</a> | <a href="README.md">English</a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/brand/main/logos/xrpl-lab/readme.png" width="500" alt="XRPL Lab">
</p>

<p align="center">
  <a href="https://github.com/mcp-tool-shop-org/xrpl-lab/actions/workflows/ci.yml"><img src="https://github.com/mcp-tool-shop-org/xrpl-lab/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/mcp-tool-shop-org/xrpl-lab/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="MIT License"></a>
  <a href="https://mcp-tool-shop-org.github.io/xrpl-lab/"><img src="https://img.shields.io/badge/Landing_Page-live-blue" alt="Landing Page"></a>
</p>

Manual de treinamento XRPL — aprenda praticando, demonstre com resultados concretos.

Cada módulo ensina uma habilidade do XRPL e produz um resultado verificável: um ID de transação,
um recibo assinado ou um relatório de diagnóstico. Sem contas, sem informações desnecessárias, sem nuvem — apenas
competência e comprovantes.

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/xrpl-lab/main/docs/images/dashboard-hero.png" width="800" alt="XRPL Lab dashboard showing completed modules with quick actions and status panels">
</p>

## Instalar

```bash
pipx install xrpl-lab
```

Ou com pip:

```bash
pip install xrpl-lab
```

Requer Python 3.11+.

## Guia rápido

```bash
xrpl-lab start
```

O assistente de inicialização guia você na configuração da carteira, no financiamento e no seu primeiro módulo.

### Modo offline

```bash
xrpl-lab start --dry-run
```

Nenhuma rede é necessária. Transações simuladas para aprender o fluxo de trabalho.

## Módulos

<!-- BEGIN curriculum:auto readme-intro -->
<!-- gerado por scripts/gen_docs.py — não edite manualmente; execute o gerador -->
32 módulos em dez trilhas: Fundamentos, NFTs, Tokens, Pagamentos, Identidade, DEX, Reservas, Auditoria, AMM e Projeto Final.
Os pré-requisitos são explícitos — a CLI e o linter os aplicam.

A coluna `#` corresponde à ordem mostrada por `xrpl-lab list` (ordem canônica da trilha).
<!-- END curriculum:auto readme-intro -->

<!-- BEGIN curriculum:auto readme-table -->
<!-- gerado por scripts/gen_docs.py — não edite manualmente; execute o gerador -->
| # | Módulo | Trilha | Modo | Pré-requisitos | Produz |
|---|--------|-------|------|---------------|----------|
| 1 | Compreensão de Recibos | fundamentos | testnet | — | txid, relatório |
| 2 | Compreensão de Falhas | fundamentos | testnet | Compreensão de Recibos | txid, relatório |
| 3 | Trust Lines 101: Moedas Emitidas como Relacionamentos | fundamentos | testnet | — | txid, relatório |
| 4 | Depuração de Trust Lines | fundamentos | testnet | Trust Lines 101: Moedas Emitidas como Relacionamentos | txid, relatório |
| 5 | Tesouraria Multissig (SignerListSet): Controle N-de-M da Carteira do Studio | fundamentos | testnet | Compreensão de Recibos | txid, relatório |
| 6 | NFT Minting 101: Seu Primeiro Ativo de Jogo | nfts | testnet | — | txid, relatório |
| 7 | Mercado NFT 101: Negociação de Ativos com Royalties Aplicados | nfts | testnet | — | txid, relatório |
| 8 | NFTs Dinâmicos 101: Um Item de Jogo que Evolui | nfts | testnet | — | txid, relatório |
| 9 | MPT Issuance 101: Uma Moeda de Jogo em uma Única Transação | tokens | testnet | — | txid, relatório |
| 10 | MPT Distribution 101: Distribuindo a Moeda aos Jogadores | tokens | testnet | MPT Issuance 101: Uma Moeda de Jogo em uma Única Transação | txid, relatório |
| 11 | Token Freeze 101: O Botão de Pausa do Emissor | tokens | testnet | — | txid, relatório |
| 12 | Clawback 101: A Ferramenta de Retirada do Emissor | tokens | testnet | — | txid, relatório |
| 13 | Escrow 101: XRP com Tempo Bloqueado | pagamentos | testnet | — | txid, relatório |
| 14 | Escrow Finish 101: Liberando o XRP Bloqueado | pagamentos | testnet | Escrow 101: XRP com Tempo Bloqueado | txid, relatório |
| 15 | Token Escrow (XLS-85): Bloqueando IOUs, Não Apenas XRP | pagamentos | testnet | Trust Lines 101: Moedas Emitidas como Relacionamentos, Escrow 101: XRP com Tempo Bloqueado | txid, relatório |
| 16 | Checks 101: Pagamentos Diferidos (CheckCreate / CheckCash / CheckCancel) | pagamentos | testnet | Compreensão de Recibos | txid, relatório |
| 17 | Payment Channels 101: Assine Muitos, Liquide Uma Vez | pagamentos | testnet | — | txid, relatório |
| 18 | Valor Entregue: A Exploração de Pagamento Parcial | pagamentos | testnet | Trust Lines 101: Moedas Emitidas como Relacionamentos | txid, relatório |
| 19 | Crédito de Jogador Custodial: Uma Carteira Agrupada, Vários Jogadores (Tags de Destino) | pagamentos | testnet | Valor Entregue: A Exploração de Pagamento Parcial | txid, relatório |
| 20 | DID 101: Identidade On-Ledger | identidade | testnet | — | txid, relatório |
| 21 | Credentials 101 (XLS-70): KYC e Atestações de Idade On-Ledger | identidade | testnet | DID 101: Identidade On-Ledger | txid, relatório |
| 22 | Domínios com Permissão e DEX Protegido (XLS-80/81): Negociação Compatível e Protegida por Credenciais | identidade | testnet | Credentials 101 (XLS-70): KYC e Atestações de Idade On-Ledger | txid, relatório |
| 23 | Deposit Gate (DepositAuth + DepositPreauth): Depósitos de Tesouraria Protegidos por Credenciais | identidade | testnet | Credentials 101 (XLS-70): KYC e Atestações de Idade On-Ledger | txid, relatório |
| 24 | DEX Literacy: Ofertas, Livros de Ordens e Cancelamentos | dex | testnet | Trust Lines 101: Moedas Emitidas como Relacionamentos | txid, relatório |
| 25 | DEX Market Making 101: Obtendo Lucro com o Spread no Livro de Ordens | dex | testnet | DEX Literacy: Ofertas, Livros de Ordens e Cancelamentos | txid, relatório |
| 26 | DEX Inventory Guardrails: Não Seja Pego de Surpresa | dex | testnet | DEX Market Making 101: Obtendo Lucro com o Spread no Livro de Ordens | txid, relatório |
| 27 | Reservas 101: Onde Seu XRP 'Foi' | reservas | testnet | Trust Lines 101: Moedas Emitidas como Relacionamentos | txid, relatório |
| 28 | Higiene da Conta: Liberando Reservas e Limpando Objetos | reservas | testnet | Reservas 101: Onde Seu XRP 'Foi' | txid, relatório |
| 29 | Modo de Auditoria: Verificando Recibos em Escala | auditoria | testnet | Compreensão de Recibos | relatório, audit_pack |
| 30 | AMM Liquidity 101: Fornecendo Liquidez e Obtendo Taxas | amm | dry-run | Trust Lines 101: Moedas Emitidas como Relacionamentos | txid, relatório |
| 31 | DEX vs AMM Risk Literacy: Comparando Estratégias de Negociação | amm | dry-run | DEX Market Making 101: Obtendo Lucro com o Spread no Livro de Ordens, AMM Liquidity 101: Fornecendo Liquidez e Obtendo Taxas | txid, relatório |
| 32 | Projeto Final: Crie uma Economia de Jogo Mínima no XRPL | capstone | testnet | MPT Issuance 101: Uma Moeda de Jogo em uma Única Transação, NFT Minting 101: Seu Primeiro Ativo de Jogo, Escrow 101: XRP com Tempo Bloqueado, Modo de Auditoria: Verificando Recibos em Escala | txid, relatório, audit_pack |
<!-- END curriculum:auto readme-table -->

A coluna **Produz** lista os tipos de resultados que cada módulo gera (`txid`,
`relatório`, `audit_pack`); consulte a página de cada módulo no
[manual](https://mcp-tool-shop-org.github.io/xrpl-lab/handbook/modules/) para obter o
guia completo das habilidades e o que você demonstra no livro-razão.

### Trilhas

<!-- BEGIN curriculum:auto readme-tracks -->
<!-- gerado por scripts/gen_docs.py — não edite manualmente; execute o gerador -->
- **fundamentos** — carteira, pagamentos, trust lines, tratamento de erros
- **nfts** — ativos de jogo NFT: criação, liquidação no mercado, NFTs dinâmicos (XLS-20)
- **tokens** — emissão e retirada de tokens multiuso (MPT) para jogos (XLS-33)
- **pagamentos** — escrow e valor com tempo bloqueado
- **identidade** — Identificadores Descentralizados (DID, XLS-40)
- **dex** — ofertas, livros de ordens, criação de mercado, gerenciamento de inventário
- **reservas** — reservas da conta, contagem de proprietários, limpeza
- **auditoria** — verificação em lote, relatórios de auditoria
- **amm** — liquidez do criador de mercado automatizado, comparação DEX vs AMM
- **projeto final** — combine habilidades entre as trilhas para criar uma economia de jogo
<!-- END curriculum:auto readme-tracks -->

### Modos

- **testnet** — transações reais na XRPL Testnet
- **dry-run** — sandbox offline com transações simuladas (sem rede necessária)

## Comandos

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

Todos os comandos suportam `--dry-run` para o modo offline, quando aplicável.

## Uso no Workshop

O XRPL Lab foi projetado para ambientes de ensino reais. Sem contas, sem telemetria, sem nuvem. Tudo é executado localmente.

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/xrpl-lab/main/docs/images/facilitator-active-runs.png" width="800" alt="Facilitator dashboard listing active learner runs with module IDs, dry-run badges, status, queue depth, and run IDs">
</p>

### Status de facilitador

```bash
xrpl-lab status             # Where is this learner? What's blocked? What's next?
xrpl-lab status --json      # Machine-readable for scripting
xrpl-lab tracks             # Track-level completion: what was actually practiced
xrpl-lab recovery           # Stuck? See exactly what to run next
```

### Transferência de suporte

```bash
xrpl-lab support-bundle              # Human-readable markdown bundle
xrpl-lab support-bundle --json       # Machine-parseable JSON
xrpl-lab support-bundle --verify bundle.json  # Verify a received bundle
```

Um facilitador pode diagnosticar qualquer problema do aluno a partir de um pacote de suporte, sem precisar reproduzir toda a sessão. Nenhum dado confidencial é incluído.

### Fluxos de workshop

**Ambiente totalmente offline** — nenhuma rede necessária:
```bash
xrpl-lab wallet create
xrpl-lab start --dry-run
```

**Offline misto + testnet** — transações reais para o básico, ambiente de teste para recursos avançados:
```bash
xrpl-lab wallet create
xrpl-lab fund
xrpl-lab start
```

**Progressão Camp → Lab** — continue a partir do xrpl-camp:
```bash
xrpl-lab start    # auto-detects camp wallet and certificate
```

## Artefatos

**Pacote de prova** (`xrpl_lab_proof_pack.json`): Registro compartilhável dos módulos concluídos, IDs de transação e links para o explorador. Inclui um hash de integridade SHA-256. Nenhum dado confidencial.

**Certificado** (`xrpl_lab_certificate.json`): Registro simplificado da conclusão.

**Relatórios** (`reports/*.md`): Resumos legíveis por humanos do que você fez e comprovou.

**Pacotes de auditoria** (`audit_pack_*.json`): Resultados de verificação em lote com hash de integridade SHA-256.

## Modelo de segurança e confiança

**Dados que o XRPL Lab acessa:**
- Seed da carteira (armazenado localmente em `~/.xrpl-lab/wallet.json` como JSON simples, protegido por permissões de arquivo 0o600 e um diretório pai 0o700 — não criptografado)
- Progresso do módulo e IDs de transação (armazenados em `~/.xrpl-lab/state.json`, gravações atômicas via tmp + renomear)
- XRPL Testnet RPC (endpoint público, transações assinadas localmente antes do envio)
- Faucet da testnet (HTTP público, apenas o seu endereço é enviado)

**Dados que o XRPL Lab NÃO acessa:**
- Nenhuma mainnet. Apenas testnet
- Sem telemetria, análise ou qualquer tipo de comunicação com servidores externos
- Sem contas na nuvem, sem registro, sem APIs de terceiros
- Nenhum dado confidencial nos pacotes de prova, certificados, relatórios ou pacotes de suporte — nunca

**Permissões e níveis de armazenamento:**
- Diretório `~/.xrpl-lab/` — nível privado para dados confidenciais, diretório 0o700 + arquivo da carteira 0o600. Armazena a seed da carteira, o log do "doctor" e os pacotes de auditoria.
- Diretório `./.xrpl-lab/` — nível projetado para compartilhamento, diretório 0o755. Armazena relatórios de módulos, pacotes de prova e certificados. Os facilitadores podem revisar sem elevação de permissões.
- Sistema de arquivos: lê/grava apenas nos dois locais acima
- Rede: XRPL Testnet RPC + faucet (ambos substituíveis via variáveis de ambiente, ambos opcionais com `--dry-run`)
- Nenhuma permissão elevada é necessária

**Interface do painel (quando `xrpl-lab serve` está em execução):**
- O endpoint do executor WebSocket impõe uma lista de permissões de origem (fecha conexões não listadas com o código 4003)
- Todos os quadros de erro emitem um envelope estruturado (`code`, `message`, `hint`, `severity`, `icon_hint`) — sem vazamento de caminho, sem vazamento de estado interno
- Fila de mensagens por conexão limitada com comportamento documentado de "back-pressure"

Consulte [SECURITY.md](SECURITY.md) para obter a política de segurança completa e as orientações de configuração do workshop.

## Requisitos

- Python 3.11+
- Conexão com a Internet para testnet (ou use `--dry-run` para o modo totalmente offline)

## Licença

MIT

Criado por [MCP Tool Shop](https://mcp-tool-shop.github.io/)
