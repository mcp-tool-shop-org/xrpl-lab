<p align="center">
  <a href="README.ja.md">日本語</a> | <a href="README.zh.md">中文</a> | <a href="README.es.md">Español</a> | <a href="README.fr.md">Français</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.it.md">Italiano</a> | <a href="README.md">English</a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/brand/main/logos/xrpl-lab/readme.png" width="400" alt="XRPL Lab">
</p>

<p align="center">
  <a href="https://github.com/mcp-tool-shop-org/xrpl-lab/actions/workflows/ci.yml"><img src="https://github.com/mcp-tool-shop-org/xrpl-lab/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/mcp-tool-shop-org/xrpl-lab/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="MIT License"></a>
  <a href="https://mcp-tool-shop-org.github.io/xrpl-lab/"><img src="https://img.shields.io/badge/Landing_Page-live-blue" alt="Landing Page"></a>
</p>

XRPL: material de treinamento — aprenda fazendo, prove com evidências.

Cada módulo ensina uma habilidade do XRPL e gera uma evidência verificável: um ID de transação,
um recibo assinado ou um relatório de diagnóstico. Sem contas, sem informações desnecessárias, sem nuvem — apenas
competência e evidências.

## Instalação

```bash
pipx install xrpl-lab
```

Ou com pip:

```bash
pip install xrpl-lab
```

Requer Python 3.11+.

## Início rápido

```bash
xrpl-lab start
```

O assistente guia você na configuração da carteira, no financiamento e no seu primeiro módulo.

### Modo offline

```bash
xrpl-lab start --dry-run
```

Não requer conexão com a rede. Transações simuladas para aprender o fluxo de trabalho.

## Módulos

12 módulos em cinco trilhas: Fundamentos, DEX, Reservas, Auditoria e AMM.
Os pré-requisitos são explícitos — o CLI e o linter os impõem.

| # | Módulo | Trilha | Modo | O que você aprende | O que você prova |
|---|--------|-------|------|----------------|----------------|
| 1 | Interpretação de recibos | Fundamentos | Testnet | A confirmação é um recibo, não um status de "enviado" — faça um pagamento, leia todos os campos do recibo. | ID da transação + relatório de verificação |
| 2 | Interpretação de falhas | Fundamentos | Testnet | Os erros do XRPL têm significado (tec/tef/tem/ter) — force um erro intencionalmente, diagnostique, corrija e reenvie. | Rastreamento de transações com falha e transações corrigidas |
| 3 | Linhas de confiança 101 | Fundamentos | Testnet | Tokens são opcionais e direcionais — crie um emissor, defina uma linha de confiança, emita tokens. | Linha de confiança + saldo do token |
| 4 | Depuração de linhas de confiança | Fundamentos | Testnet | Decodifique os códigos de erro das linhas de confiança — falha intencional, decodificação de erro, correção. | Erro → rastreamento de transação corrigida |
| 5 | Interpretação de DEX | DEX | Testnet | Livros de ofertas conectam compradores e vendedores — crie ofertas, leia livros de ofertas, cancele. | IDs de transações de criação e cancelamento de ofertas |
| 6 | Reservas 101 | Reservas | Testnet | Cada objeto possui bloqueia XRP — snapshots, contagem de proprietários, cálculos de reservas. | Diferença do snapshot (antes/depois) |
| 7 | Manutenção da conta | Reservas | Testnet | A limpeza é uma habilidade essencial — cancele ofertas, remova linhas de confiança, libere reservas. | Relatório de verificação de limpeza |
| 8 | Auditoria de recibos | Auditoria | Testnet | As auditorias codificam a intenção (ID da transação + expectativa + veredicto) — verifique em lote com expectativas. | Pacote de auditoria (MD + CSV + JSON) |
| 9 | Liquidez AMM 101 | AMM | Teste | Os preços do produto constante (`x*y=k`) são determinados passivamente — crie uma pool, deposite, ganhe LP, retire. | IDs de transações do ciclo de vida do AMM |
| 10 | Criação de mercado DEX 101 | DEX | Testnet | As diferenças entre ofertas de compra e venda rastreiam o inventário — faça ofertas em ambos os lados, registre posições, limpe. | IDs de transações da estratégia + relatório de limpeza |
| 11 | Controles de inventário | DEX | Testnet | Faça ofertas apenas no lado seguro quando o inventário estiver desequilibrado — baseado em limites, alocação protegida. | Verificação de inventário + transações protegidas |
| 12 | Interpretação de riscos DEX vs AMM | AMM | Teste | A perda impermanente é uma propriedade do modelo AMM — DEX e AMM lado a lado. | Relatório de comparação + rastreamento de auditoria |

### Trilhas

- **Fundamentos** — carteira, pagamentos, linhas de confiança, tratamento de erros.
- **DEX** — ofertas, livros de ofertas, criação de mercado, gerenciamento de inventário.
- **Reservas** — reservas da conta, contagem de proprietários, limpeza.
- **Auditoria** — verificação em lote, relatórios de auditoria.
- **AMM** — liquidez de mercado automatizado, comparação DEX vs AMM.

### Modos

- **Testnet** — transações reais na rede de teste XRPL.
- **Teste** — sandbox offline com transações simuladas (não requer conexão com a rede).

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

Todos os comandos suportam `--dry-run` para o modo offline, quando aplicável.

## Uso em Workshops

O XRPL Lab foi projetado para ambientes de aprendizado práticos. Não requer contas, telemetria ou serviços em nuvem.
Tudo funciona localmente.

### Status de Facilitador

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

Um facilitador pode diagnosticar qualquer problema de um aluno a partir de um pacote de suporte, sem precisar reproduzir toda a sessão. Nenhum dado confidencial está incluído.

### Fluxos de trabalho

**Ambiente de testes offline:** Não requer conexão com a internet.
```bash
xrpl-lab wallet create
xrpl-lab start --dry-run
```

**Ambiente misto (offline + testnet):** Transações reais para conceitos básicos, ambiente de testes para tópicos avançados.
```bash
xrpl-lab wallet create
xrpl-lab fund
xrpl-lab start
```

**Progressão do curso (Camp → Lab):** Permite continuar a partir do curso "xrpl-camp".
```bash
xrpl-lab start    # auto-detects camp wallet and certificate
```

## Artefatos

**Pacote de comprovação** (`xrpl_lab_proof_pack.json`): Registro compartilhável de módulos concluídos, IDs de transações e links para o explorador. Inclui um hash de integridade SHA-256. Não contém dados confidenciais.

**Certificado** (`xrpl_lab_certificate.json`): Registro simplificado de conclusão.

**Relatórios** (`reports/*.md`): Resumos legíveis por humanos do que você fez e comprovou.

**Pacotes de auditoria** (`audit_pack_*.json`): Resultados de verificação em lote com hash de integridade SHA-256.

## Modelo de Segurança e Confiança

**Dados acessados pelo XRPL Lab:**
- Chave de acesso da carteira (armazenada localmente em `~/.xrpl-lab/wallet.json` como JSON em texto simples, protegida por permissões de arquivo 0o600 e um diretório pai com permissões 0o700 – não criptografada)
- Progresso dos módulos e IDs de transações (armazenados em `~/.xrpl-lab/state.json`, escritas atômicas via arquivo temporário + renomeação)
- RPC da rede de testes XRPL (endpoint público, as transações são assinadas localmente antes de serem enviadas)
- Torneira da rede de testes (HTTP público, apenas seu endereço é enviado)

**Dados que o XRPL Lab NÃO acessa:**
- Não acessa a rede principal (apenas a rede de testes)
- Não coleta telemetria, análises ou informações de qualquer tipo
- Não usa contas em nuvem, não requer registro, não usa APIs de terceiros
- Nenhum dado confidencial está incluído em pacotes de comprovação, certificados, relatórios ou pacotes de suporte – nunca.

**Permissões e níveis de armazenamento:**
- Diretório inicial `~/.xrpl-lab/` – nível de dados confidenciais, diretório com permissões 0o700 + arquivo de carteira com permissões 0o600. Armazena a chave de acesso da carteira, o registro do facilitador e os pacotes de auditoria.
- Área de trabalho `./.xrpl-lab/` – nível projetado para compartilhamento, diretório com permissões 0o755. Armazena relatórios de módulos, pacotes de comprovação e certificados. Facilitadores podem revisar sem elevação de permissões.
- Sistema de arquivos: lê e grava apenas nos dois locais acima.
- Rede: Apenas RPC e torneira da rede de testes XRPL (ambos podem ser substituídos via variáveis de ambiente, ambos opcionais com `--dry-run`).
- Não requer permissões elevadas.

**Interface do painel (quando `xrpl-lab serve` está em execução):**
- O endpoint do runner WebSocket impõe uma lista de permissão de origem (bloqueia conexões não listadas com o código 4003)
- Todos os quadros de erro emitem um envelope estruturado (`code`, `message`, `hint`, `severity`, `icon_hint`) – sem vazamento de caminho, sem vazamento de estado interno.
- Fila de mensagens limitada por conexão com comportamento de controle de fluxo documentado.

Consulte [SECURITY.md](SECURITY.md) para a política de segurança completa e orientações para a configuração do workshop.

## Requisitos

- Python 3.11+
- Conexão com a internet para a rede de testes (ou use `--dry-run` para o modo totalmente offline)

## Licença

MIT

Desenvolvido por [MCP Tool Shop](https://mcp-tool-shop.github.io/)
