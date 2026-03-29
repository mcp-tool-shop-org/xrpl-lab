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

XRPL: um guia de treinamento — aprenda fazendo, prove com evidências.

Cada módulo ensina uma habilidade do XRPL e gera uma evidência verificável: um ID de transação,
um recibo assinado ou um relatório de diagnóstico. Sem contas, sem informações desnecessárias — apenas competência e recibos.

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

12 módulos divididos em três níveis: Iniciante, Intermediário e Avançado.

| # | Módulo | Nível | O que você aprende | O que você demonstra |
|---|--------|-------|----------------|----------------|
| 1 | Interpretação de recibos | Iniciante | Envie um pagamento, leia todos os campos do recibo. | ID da transação + relatório de verificação. |
| 2 | Interpretação de falhas | Iniciante | Force uma falha na transação, diagnostique, corrija e reenvie. | Rastreamento de transações com falha e transações corrigidas. |
| 3 | Linhas de confiança 101 | Iniciante | Crie um emissor, defina uma linha de confiança, emita tokens. | Linha de confiança + saldo do token. |
| 4 | Depuração de linhas de confiança | Iniciante | Falha intencional na linha de confiança, decodificação de erros, correção. | Rastreamento de erros para correção. |
| 5 | Interpretação de DEX | Intermediário | Crie ofertas, leia livros de ordens, cancele. | IDs de transações de criação e cancelamento de ofertas. |
| 6 | Reservas 101 | Intermediário | Capturas de tela da conta, contagem de proprietários, cálculos de reservas. | Diferença entre a captura de tela antes e depois. |
| 7 | Manutenção da conta | Intermediário | Cancele ofertas, remova linhas de confiança, libere reservas. | Relatório de verificação de limpeza. |
| 8 | Auditoria de recibos | Intermediário | Verifique em lote as transações com as expectativas. | Pacote de auditoria (MD + CSV + JSON). |
| 9 | Liquidez AMM 101 | Avançado | Crie um pool, deposite, ganhe LP, retire. | IDs de transações do ciclo de vida do AMM. |
| 10 | Criação de mercado DEX 101 | Avançado | Ofertas de compra/venda, capturas de tela da posição, limpeza. | IDs de transações da estratégia + relatório de limpeza. |
| 11 | Controles de inventário | Avançado | Cotação baseada em limites, colocação apenas no lado seguro. | Verificação de inventário + IDs de transações protegidas. |
| 12 | Interpretação de riscos DEX vs AMM | Avançado | Comparação lado a lado do ciclo de vida do DEX e do AMM. | Relatório de comparação + rastreamento de auditoria. |

## Comandos

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

Todos os comandos suportam `--dry-run` para o modo offline, quando aplicável.

## Evidências

**Pacote de evidências** (`xrpl_lab_proof_pack.json`): Registro compartilhável dos módulos concluídos,
IDs de transações e links para o explorador. Inclui um hash de integridade SHA-256. Sem segredos.

**Certificado** (`xrpl_lab_certificate.json`): Registro simplificado de conclusão.

**Relatórios** (`reports/*.md`): Resumos legíveis por humanos do que você fez e comprovou.

**Pacotes de auditoria** (`audit_pack_*.json`): Resultados de verificação em lote com hash de integridade SHA-256.

## Segurança e modelo de confiança

**Dados acessados pelo XRPL Lab:**
- Semente da carteira (armazenada localmente em `~/.xrpl-lab/wallet.json` com permissões de arquivo restritivas)
- Progresso do módulo e IDs de transações (armazenados em `~/.xrpl-lab/state.json`)
- RPC do Testnet XRPL (ponto de extremidade público, transações assinadas localmente antes do envio)
- Torneira do Testnet (HTTP público, apenas seu endereço é enviado)

**Dados que o XRPL Lab NÃO acessa:**
- Não acessa a rede principal (mainnet). Apenas a rede de testes (testnet).
- Não coleta dados de telemetria, análises ou informações de qualquer tipo.
- Não utiliza contas na nuvem, nem requer registro, nem utiliza APIs de terceiros.
- Não armazena informações confidenciais em pacotes de prova, certificados ou relatórios, em nenhuma circunstância.

**Permissões:**
- Sistema de arquivos: apenas leitura/escrita nos diretórios `~/.xrpl-lab/` e `./.xrpl-lab/` (ambiente de trabalho local).
- Rede: Acesso à RPC da rede de testes XRPL e a um "faucet" (para obter fundos de teste), ambos configuráveis através de variáveis de ambiente e opcionais com a opção `--dry-run`.
- Não requer permissões elevadas.

Consulte o arquivo [SECURITY.md](SECURITY.md) para a política de segurança completa.

## Requisitos

- Python 3.11 ou superior
- Conexão com a internet para a rede de testes (ou utilize a opção `--dry-run` para um modo totalmente offline).

## Licença

MIT

Desenvolvido por [MCP Tool Shop](https://mcp-tool-shop.github.io/)
