<p align="center">
  <a href="README.ja.md">日本語</a> | <a href="README.zh.md">中文</a> | <a href="README.md">English</a> | <a href="README.fr.md">Français</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.it.md">Italiano</a> | <a href="README.pt-BR.md">Português (BR)</a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/brand/main/logos/xrpl-lab/readme.png" width="500" alt="XRPL Lab">
</p>

<p align="center">
  <a href="https://github.com/mcp-tool-shop-org/xrpl-lab/actions/workflows/ci.yml"><img src="https://github.com/mcp-tool-shop-org/xrpl-lab/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/mcp-tool-shop-org/xrpl-lab/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="MIT License"></a>
  <a href="https://mcp-tool-shop-org.github.io/xrpl-lab/"><img src="https://img.shields.io/badge/Landing_Page-live-blue" alt="Landing Page"></a>
</p>

Manual de capacitación XRPL: aprende haciendo, demuestra con resultados.

Cada módulo enseña una habilidad de XRPL y produce un resultado verificable: un ID de transacción,
un recibo firmado o un informe de diagnóstico. Sin cuentas, sin información innecesaria, sin la nube; solo
competencia y comprobantes.

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/xrpl-lab/main/docs/images/dashboard-hero.png" width="800" alt="XRPL Lab dashboard showing completed modules with quick actions and status panels">
</p>

## Instalar

```bash
pipx install xrpl-lab
```

O con pip:

```bash
pip install xrpl-lab
```

Requiere Python 3.11 o superior.

## Guía rápida

```bash
xrpl-lab start
```

El lanzador guiado te guía a través de la configuración de la billetera, el financiamiento y tu primer módulo.

### Modo sin conexión

```bash
xrpl-lab start --dry-run
```

No se requiere red. Transacciones simuladas para aprender el flujo de trabajo.

## Módulos

```
<!-- BEGIN curriculum:auto readme-intro -->
<!-- generado por scripts/gen_docs.py — no editar manualmente; ejecutar el generador -->
21 módulos en diez áreas temáticas: Fundamentos, NFT, Tokens, Pagos, Identidad, DEX, Reservas, Auditoría, AMM y Proyecto Final.
Los requisitos previos se especifican explícitamente; la CLI y el analizador los hacen cumplir.

La columna `#` coincide con el orden que muestra `xrpl-lab list` (orden canónico de las áreas temáticas).
<!-- END curriculum:auto readme-intro -->

<!-- BEGIN curriculum:auto readme-table -->
<!-- generado por scripts/gen_docs.py — no editar manualmente; ejecutar el generador -->
| # | Módulo | Área temática | Modo | Requisitos previos | Produce |
|---|--------|-------|------|---------------|----------|
| 1 | Conocimiento de recibos | fundamentos | testnet | — | txid, informe |
| 2 | Conocimiento de fallos | fundamentos | testnet | Conocimiento de recibos | txid, informe |
| 3 | Líneas de confianza 101: Monedas emitidas como relaciones | fundamentos | testnet | — | txid, informe |
| 4 | Depuración de líneas de confianza | fundamentos | testnet | Líneas de confianza 101: Monedas emitidas como relaciones | txid, informe |
| 5 | Creación de NFT 101: Tu primer activo de juego | nfts | testnet | — | txid, informe |
| 6 | Mercado de NFT 101: Intercambio de activos con regalías aplicadas | nfts | testnet | — | txid, informe |
| 7 | NFT dinámicos 101: Un objeto de juego que mejora su nivel | nfts | testnet | — | txid, informe |
| 8 | Emisión de MPT 101: Una moneda de juego en una sola transacción | tokens | testnet | — | txid, informe |
| 9 | Reversión 101: La herramienta de revocación del emisor | tokens | testnet | — | txid, informe |
| 10 | Depósito en garantía 101: XRP con bloqueo temporal | pagos | testnet | — | txid, informe |
| 11 | Finalización del depósito en garantía 101: Liberación del XRP bloqueado | pagos | testnet | Depósito en garantía 101: XRP con bloqueo temporal | txid, informe |
| 12 | DID 101: Identidad en la cadena de bloques | identidad | testnet | — | txid, informe |
| 13 | Conocimientos básicos sobre DEX: Ofertas, libros de órdenes y cancelaciones | dex | testnet | Líneas de confianza 101: Monedas emitidas como relaciones | txid, informe |
| 14 | Creación de mercado DEX 101: Obtención de un margen en el libro de órdenes | dex | testnet | Conocimientos básicos sobre DEX: Ofertas, libros de órdenes y cancelaciones | txid, informe |
| 15 | Protecciones de inventario DEX: No te excedas | dex | testnet | Creación de mercado DEX 101: Obtención de un margen en el libro de órdenes | txid, informe |
| 16 | Reservas 101: Dónde "fue" tu XRP | reservas | testnet | Líneas de confianza 101: Monedas emitidas como relaciones | txid, informe |
| 17 | Higiene de la cuenta: Liberación de reservas y limpieza de objetos | reservas | testnet | Reservas 101: Dónde "fue" tu XRP | txid, informe |
| 18 | Modo de auditoría: Verificación de recibos a escala | auditoria | testnet | Conocimiento de recibos | informe, paquete_de_auditoría |
| 19 | Liquidez AMM 101: Proporcionar liquidez y obtener comisiones | amm | prueba en seco | Líneas de confianza 101: Monedas emitidas como relaciones | txid, informe |
| 20 | Conocimientos básicos sobre riesgos de DEX frente a AMM: Comparación de estrategias comerciales | amm | prueba en seco | Creación de mercado DEX 101: Obtención de un margen en el libro de órdenes, Liquidez AMM 101: Proporcionar liquidez y obtener comisiones | txid, informe |
| 21 | Proyecto final: Implementa una economía de juego mínima en XRPL | proyecto_final | testnet | Emisión de MPT 101: Una moneda de juego en una sola transacción, Creación de NFT 101: Tu primer activo de juego, Depósito en garantía 101: XRP con bloqueo temporal, Modo de auditoría: Verificación de recibos a escala | txid, informe, paquete_de_auditoría |
<!-- END curriculum:auto readme-table -->

La columna **Produce** enumera los tipos de artefactos que genera cada módulo (`txid`, `informe`, `paquete_de_auditoría`); consulta la página de cada módulo en el [manual](https://mcp-tool-shop-org.github.io/xrpl-lab/handbook/modules/) para obtener la guía completa de habilidades y lo que demuestras en la cadena de bloques.

### Áreas temáticas

<!-- BEGIN curriculum:auto readme-tracks -->
<!-- generado por scripts/gen_docs.py — no editar manualmente; ejecutar el generador -->
- **fundamentos** — billetera, pagos, líneas de confianza, manejo de errores
- **nfts** — activos de juego NFT: creación, liquidación del mercado, NFT dinámicos (XLS-20)
- **tokens** — emisión y reversión de tokens multipropósito (MPT) para juegos (XLS-33)
- **pagos** — depósito en garantía y valor con bloqueo temporal
- **identidad** — identificadores descentralizados (DID, XLS-40)
- **dex** — ofertas, libros de órdenes, creación de mercado, gestión de inventario
- **reservas** — reservas de cuenta, recuento de propietarios, limpieza
- **auditoría** — verificación por lotes, informes de auditoría
- **amm** — liquidez del creador automático de mercado, comparación DEX frente a AMM
- **proyecto_final** — combina las habilidades entre las áreas temáticas en una única implementación de economía de juego
<!-- END curriculum:auto readme-tracks -->
```

### Modos

- **testnet**: transacciones reales en la red de prueba XRPL
- **prueba en seco**: sandbox sin conexión con transacciones simuladas (no se requiere red)

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

Todos los comandos admiten `--dry-run` para el modo sin conexión cuando corresponda.

## Uso en talleres

XRPL Lab está diseñado para entornos de enseñanza reales. Sin cuentas, sin telemetría, sin la nube.
Todo se ejecuta localmente.

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/xrpl-lab/main/docs/images/facilitator-active-runs.png" width="800" alt="Facilitator dashboard listing active learner runs with module IDs, dry-run badges, status, queue depth, and run IDs">
</p>

### Estado del facilitador

```bash
xrpl-lab status             # Where is this learner? What's blocked? What's next?
xrpl-lab status --json      # Machine-readable for scripting
xrpl-lab tracks             # Track-level completion: what was actually practiced
xrpl-lab recovery           # Stuck? See exactly what to run next
```

### Asistencia

```bash
xrpl-lab support-bundle              # Human-readable markdown bundle
xrpl-lab support-bundle --json       # Machine-parseable JSON
xrpl-lab support-bundle --verify bundle.json  # Verify a received bundle
```

Un facilitador puede diagnosticar el problema de cualquier alumno a partir de un paquete de asistencia sin
reproducir toda la sesión. No se incluyen secretos.

### Flujos de trabajo

**Sandbox completamente desconectado**: no se requiere red:
```bash
xrpl-lab wallet create
xrpl-lab start --dry-run
```

**Modo mixto, sin conexión + testnet**: transacciones reales para los conceptos básicos, sandbox para funciones avanzadas:
```bash
xrpl-lab wallet create
xrpl-lab fund
xrpl-lab start
```

**Progresión de Camp → Lab**: continúa desde xrpl-camp:
```bash
xrpl-lab start    # auto-detects camp wallet and certificate
```

## Resultados

**Paquete de prueba** (`xrpl_lab_proof_pack.json`): Registro compartible de los módulos completados, identificadores de transacción y enlaces al explorador. Incluye un hash de integridad SHA-256. No contiene información confidencial.

**Certificado** (`xrpl_lab_certificate.json`): Registro conciso de la finalización.

**Informes** (`reports/*.md`): Resúmenes legibles para humanos sobre lo que se hizo y demostró.

**Paquetes de auditoría** (`audit_pack_*.json`): Resultados de verificación por lotes con hash de integridad SHA-256.

## Modelo de seguridad y confianza

**Datos a los que accede XRPL Lab:**
- Semilla de la billetera (almacenada localmente en `~/.xrpl-lab/wallet.json` como JSON sin formato, protegida por permisos de archivo 0o600 y un directorio principal 0o700; no está cifrada)
- Progreso del módulo e identificadores de transacción (almacenados en `~/.xrpl-lab/state.json`, escrituras atómicas mediante tmp + cambio de nombre)
- RPC de XRPL Testnet (punto final público, las transacciones se firman localmente antes del envío)
- Grifo de Testnet (HTTP público, solo se envía su dirección)

**Datos a los que XRPL Lab NO accede:**
- No a la red principal. Solo a la red de prueba (Testnet).
- No recopila telemetría, análisis ni datos de ningún tipo.
- No utiliza cuentas en la nube, no requiere registro y no emplea API de terceros.
- No contiene información confidencial en los paquetes de prueba, certificados, informes o paquetes de soporte, nunca.

**Permisos y niveles de almacenamiento:**
- Directorio principal `~/.xrpl-lab/`: nivel privado para secretos, directorio 0o700 + archivo de billetera 0o600. Almacena la semilla de la billetera, el registro del programa y los paquetes de auditoría.
- Espacio de trabajo `./.xrpl-lab/`: nivel diseñado para ser compartido, directorio 0o755. Almacena informes de módulos, paquetes de prueba y certificados. Los facilitadores pueden revisarlos sin necesidad de permisos elevados.
- Sistema de archivos: solo lee y escribe en las dos ubicaciones anteriores.
- Red: solo utiliza XRPL Testnet RPC + grifo (ambos se pueden anular mediante variables de entorno, ambos son opcionales con `--dry-run`).
- No requiere permisos elevados.

**Interfaz del panel de control (cuando `xrpl-lab serve` está en ejecución):**
- El punto final del ejecutor WebSocket aplica una lista de origen permitida (cierra las conexiones que no están en la lista con el código 4003).
- Todos los marcos de error emiten un sobre estructurado (`code`, `message`, `hint`, `severity`, `icon_hint`); no se filtran rutas ni información del estado interno.
- Cola de mensajes por conexión limitada con comportamiento documentado de contrapresión.

Consulte [SECURITY.md](SECURITY.md) para obtener la política de seguridad completa y las instrucciones de configuración del taller.

## Requisitos

- Python 3.11+
- Conexión a Internet para la red de prueba (o utilice `--dry-run` para el modo completamente desconectado).

## Licencia

MIT

Creado por [MCP Tool Shop](https://mcp-tool-shop.github.io/)
