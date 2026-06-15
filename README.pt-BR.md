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

Manual de treinamento XRPL — aprenda praticando, comprove com resultados.

Cada módulo ensina uma habilidade do XRPL e produz um resultado verificável: um ID de transação,
um recibo assinado ou um relatório de diagnóstico. Sem contas, sem informações desnecessárias, sem nuvem — apenas
competência e comprovantes.

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/xrpl-lab/main/docs/images/dashboard-hero.png" width="800" alt="XRPL Lab dashboard showing 11/12 modules completed with quick actions and status panels">
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

O assistente de inicialização guiado orienta você na configuração da carteira, no financiamento e no seu primeiro módulo.

### Modo offline

```bash
xrpl-lab start --dry-run
```

Nenhuma rede é necessária. Transações simuladas para aprender o fluxo de trabalho.

## Módulos

16 módulos em nove trilhas: Fundamentos, NFTs, Tokens, Pagamentos, Identidade, DEX, Reservas, Auditoria e AMM.
Os pré-requisitos são explícitos — a CLI e o linter os aplicam.

| # | Módulo | Trilha | Modo | O que você aprende | O que você comprova |
|---|--------|-------|------|----------------|----------------|
| 1 | Alfabetização de recibos | fundamentos | testnet | A finalidade é um recibo, não um status de "enviado" — envie um pagamento, leia todos os campos do recibo. | txid + relatório de verificação |
| 2 | Alfabetização sobre falhas | fundamentos | testnet | Os erros do XRPL têm semântica (tec/tef/tem/ter) — force uma transação a falhar, diagnostique, corrija e reenvie. | txid de falha + trilha de correção |
| 3 | Linhas de confiança 101 | fundamentos | testnet | Os tokens são opcionais e direcionais — crie um emissor, defina uma linha de confiança e emita tokens. | linha de confiança + saldo do token |
| 4 | Depuração de linhas de confiança | fundamentos | testnet | Decodifique os códigos de erro da linha de confiança — falha intencional, decodificação de erros, correção. | trilha de erro → txid de correção |
| 5 | Alfabetização DEX | dex | testnet | Os livros de ordens combinam compradores e vendedores — crie ofertas, leia os livros de ordens e cancele. | txids de criação + cancelamento de oferta |
| 6 | Reservas 101 | reservas | testnet | Cada objeto que você possui bloqueia XRP — instantâneos, contagem de proprietários, cálculos de reserva. | delta do instantâneo antes/depois |
| 7 | Higiene da conta | reservas | testnet | A limpeza é uma habilidade essencial — cancele ofertas, remova linhas de confiança e libere reservas. | relatório de verificação de limpeza |
| 8 | Auditoria de recibos | auditoria | testnet | As auditorias codificam a intenção (txid + expectativa + resultado) — verifique em lote com as expectativas. | pacote de auditoria (MD + CSV + JSON) |
| 9 | Liquidez AMM 101 | amm | execução a seco | O produto constante (`x*y=k`) define os preços de forma passiva — crie um pool, deposite, ganhe LP e retire. | txids do ciclo de vida AMM |
| 10 | Criação de mercado DEX 101 | dex | testnet | As diferenças entre compra e venda rastreiam o inventário — cotar ambos os lados, registrar as posições e limpar. | txids da estratégia + relatório de higiene |
| 11 | Limites de inventário | dex | testnet | Cote apenas o lado seguro quando o inventário estiver desequilibrado — baseado em limite, posicionamento protegido. | verificação de inventário + txids protegidos |
| 12 | Alfabetização sobre riscos DEX vs AMM | amm | execução a seco | A perda impermanente é uma propriedade do modelo AMM — ciclo de vida DEX e AMM lado a lado. | relatório comparativo + trilha de auditoria |
| 13 | Criação de NFT 101 | nfts | testnet | Os NFTs são objetos nativos do livro-razão — crie um ativo de jogo (táxon, URI, royalties), verifique a propriedade. | NFTokenID + verificação no livro-razão |
| 14 | Emissão MPT 101 | tokens | testnet | Uma moeda de jogo em uma transação — emita um Token Multiuso (XLS-33): limite de fornecimento, escala, sinalizadores. | ID de emissão + verificação no livro-razão |
| 15 | Escrow 101 | pagamentos | testnet | Bloqueie XRP até um determinado momento — crie um escrow baseado em tempo e verifique-o no livro-razão. | objeto escrow + FinishAfter |
| 16 | DID 101 | identidade | testnet | Identidade no livro-razão — ancore um Identificador Descentralizado (XLS-40) e verifique-o. | objeto DID + URI |

### Trilhas

- **fundamentos** — carteira, pagamentos, linhas de confiança, tratamento de erros
- **nfts** — ativos de jogo NFT: criação, coleções, royalties (XLS-20)
- **tokens** — emissão de Token Multiuso (MPT), moeda do jogo (XLS-33)
- **pagamentos** — escrow e valor com tempo limitado
- **identidade** — Identificadores Descentralizados (DID, XLS-40)
- **dex** — ofertas, livros de ordens, criação de mercado, gerenciamento de inventário
- **reservas** — reservas da conta, contagem de proprietários, limpeza
- **auditoria** — verificação em lote, relatórios de auditoria
- **amm** — liquidez do criador de mercado automatizado, comparação DEX vs AMM

### Modos

- **testnet** — transações reais na XRPL Testnet
- **execução a seco** — sandbox offline com transações simuladas (sem rede necessária)

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

## Uso em workshops

O XRPL Lab foi projetado para ambientes de ensino reais. Sem contas, sem telemetria, sem nuvem.
Tudo é executado localmente.

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/xrpl-lab/main/docs/images/facilitator-active-runs.png" width="800" alt="Facilitator dashboard listing active learner runs with module IDs, dry-run badges, status, queue depth, and run IDs">
</p>

### Status do facilitador

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

Um facilitador pode diagnosticar o problema de qualquer aluno a partir de um pacote de suporte, sem
reproduzir toda a sessão. Nenhum segredo é incluído.

### Fluxos de workshop

**Sandbox totalmente offline** — nenhuma rede necessária:
```bash
xrpl-lab wallet create
xrpl-lab start --dry-run
```

**Offline + testnet misturados** — transações reais para o básico, sandbox para o avançado:
```bash
xrpl-lab wallet create
xrpl-lab fund
xrpl-lab start
```

**Progressão Camp → Lab** — continue a partir do xrpl-camp:
```bash
xrpl-lab start    # auto-detects camp wallet and certificate
```

## Resultados

**Pacote de comprovação** (`xrpl_lab_proof_pack.json`): Registo partilhável dos módulos concluídos, identificadores de transação e hiperligações para o explorador. Inclui um código de verificação de integridade SHA-256. Não contém informações confidenciais.

**Certificado** (`xrpl_lab_certificate.json`): Registo conciso do processo de conclusão.

**Relatórios** (`reports/*.md`): Resumos legíveis para humanos do que foi feito e comprovado.

**Pacotes de auditoria** (`audit_pack_*.json`): resultados da verificação em lote, com hash de integridade SHA-256.

## Modelo de Segurança e Confiança

**Elementos relevantes do Data XRPL Lab:**

*   Chave da carteira (armazenada localmente em `~/.xrpl-lab/wallet.json` como JSON simples, protegida por permissões de ficheiro 0o600 e um diretório principal com permissões 0o700 — não criptografada)
*   Progresso do módulo e IDs das transações (armazenados em `~/.xrpl-lab/state.json`, gravações atómicas através de ficheiros temporários + renomeação)
*   RPC da rede de testes XRPL (ponto final público, as transações são assinadas localmente antes de serem enviadas)
*   Distribuidor da rede de testes (HTTP público, apenas o seu endereço é enviado)

**O Data XRPL Lab NÃO utiliza:**

*   Apenas a testnet; não a mainnet.
*   Nenhum tipo de telemetria, análise ou comunicação com servidores externos.
*   Nenhuma conta na nuvem, nenhum registo e nenhuma API de terceiros.
*   Nenhum dado sensível em pacotes de prova, certificados, relatórios ou conjuntos de suporte — nunca.

**Permissões e níveis de armazenamento:**

*   Diretório pessoal `~/.xrpl-lab/` — nível privado para informações confidenciais, diretório com permissão 0o700 + ficheiro da carteira com permissão 0o600. Armazena a chave privada da carteira, registos de diagnóstico e pacotes de auditoria.
*   Diretório de trabalho `./.xrpl-lab/` — nível concebido para partilha, diretório com permissão 0o755. Armazena relatórios de módulos, pacotes de prova e certificados. Os facilitadores podem consultar sem necessidade de elevação de permissões.
*   Sistema de ficheiros: apenas leitura/escrita nos dois locais acima mencionados.
*   Rede: apenas acesso ao RPC da rede de testes XRPL e à torneira (ambos configuráveis através de variáveis de ambiente, ambos opcionais com `--dry-run`).
*   Não são necessárias permissões elevadas.

**Interface do painel (quando o comando `xrpl-lab serve` está em execução):**
- O ponto de extremidade do executor WebSocket aplica uma lista de origens permitidas (encerra as conexões que não estão na lista com o código 4003).
- Todos os quadros de erro emitem um envelope estruturado (`código`, `mensagem`, `dica`, `gravidade`, `dica_do_ícone`) — sem vazamento de informações do caminho, sem vazamento de estado interno.
- Fila de mensagens por conexão com limite definido e comportamento documentado para evitar sobrecarga.

Consulte o ficheiro [SECURITY.md](SECURITY.md) para obter informações detalhadas sobre a política de segurança e as instruções para configurar o ambiente do workshop.

## Requisitos

- Python 3.11 ou versão superior
- Conexão à internet para a rede de testes (ou utilize a opção `--dry-run` para o modo totalmente offline)

## Licença

MIT (Instituto de Tecnologia de Massachusetts)

Criado por [MCP Tool Shop](https://mcp-tool-shop.github.io/)
