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
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/xrpl-lab/main/docs/images/dashboard-hero.png" width="800" alt="XRPL Lab dashboard showing 11/12 modules completed with quick actions and status panels">
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

16 módulos en nueve áreas temáticas: Fundamentos, NFT, Tokens, Pagos, Identidad, DEX, Reservas, Auditoría y AMM.
Los requisitos previos se especifican explícitamente; la CLI y el analizador los hacen cumplir.

| # | Módulo | Área temática | Modo | Lo que aprenderás | Lo que demostrarás |
|---|--------|-------|------|----------------|----------------|
| 1 | Conocimiento de recibos | fundamentos | testnet | La finalización es un recibo, no un estado de "enviado". Envía un pago, lee cada campo del recibo. | txid + informe de verificación |
| 2 | Conocimiento de fallos | fundamentos | testnet | Los errores de XRPL tienen semántica (tec/tef/tem/ter). Provoca un fallo en una transacción, diagnostica, corrige y vuelve a enviarla. | registro de transacciones fallidas + corregidas |
| 3 | Líneas de confianza 101 | fundamentos | testnet | Los tokens requieren aceptación previa y son direccionales: crea un emisor, establece una línea de confianza, emite tokens. | línea de confianza + saldo del token |
| 4 | Depuración de líneas de confianza | fundamentos | testnet | Decodifica los códigos de error de las líneas de confianza: fallo intencional, decodificación de errores, corrección. | registro de errores → transacciones corregidas |
| 5 | Conocimiento de DEX | dex | testnet | Los libros de órdenes emparejan a los creadores con los compradores: crea ofertas, lee los libros de órdenes, cancela. | txid de creación + cancelación de la oferta |
| 6 | Reservas 101 | reservas | testnet | Cada objeto que posees bloquea XRP: instantáneas, recuento de propietarios, cálculos de reserva. | delta de la instantánea antes/después |
| 7 | Higiene de la cuenta | reservas | testnet | La limpieza es una habilidad fundamental: cancela ofertas, elimina líneas de confianza, libera reservas. | informe de verificación de la limpieza |
| 8 | Auditoría de recibos | auditoria | testnet | Las auditorías codifican la intención (txid + expectativa + veredicto): verifica por lotes con expectativas. | paquete de auditoría (MD + CSV + JSON) |
| 9 | Liquidez AMM 101 | amm | prueba en seco | El producto constante (`x*y=k`) establece precios de forma pasiva: crea un grupo, deposita, gana LP, retira. | txid del ciclo de vida AMM |
| 10 | Creación de mercado DEX 101 | dex | testnet | Bid/ask spreads rastrean el inventario: cotiza ambos lados, toma instantáneas de las posiciones, limpia. | txid de la estrategia + informe de higiene |
| 11 | Límites de seguridad del inventario | dex | testnet | Cotiza solo el lado seguro cuando el inventario se inclina: basado en umbrales, colocación protegida. | verificación del inventario + txid protegido |
| 12 | Conocimiento de los riesgos de DEX vs AMM | amm | prueba en seco | La pérdida impermanente es una propiedad del modelo AMM: ciclo de vida DEX y AMM lado a lado. | informe comparativo + registro de auditoría |
| 13 | Creación de NFT 101 | nfts | testnet | Los NFT son objetos nativos del libro mayor: crea un activo de juego (taxón, URI, regalías), verifica la propiedad. | NFTokenID + verificación en el libro mayor |
| 14 | Emisión de MPT 101 | tokens | testnet | Una moneda del juego en una transacción: emite un token multipropósito (XLS-33): límite de suministro, escala, indicadores. | ID de emisión + verificación en el libro mayor |
| 15 | Escrow 101 | pagos | testnet | Bloquea XRP hasta un momento determinado: crea un escrow basado en el tiempo, verifícalo en el libro mayor. | objeto de escrow + FinishAfter |
| 16 | DID 101 | identidad | testnet | Identidad en el libro mayor: ancla un identificador descentralizado (XLS-40), verifícalo. | objeto DID + URI |

### Áreas temáticas

- **fundamentos**: billetera, pagos, líneas de confianza, manejo de errores
- **nfts**: activos de juego NFT: creación, colecciones, regalías (XLS-20)
- **tokens**: emisión de tokens multipropósito (MPT), moneda del juego (XLS-33)
- **pagos**: escrow y valor con bloqueo temporal
- **identidad**: identificadores descentralizados (DID, XLS-40)
- **dex**: ofertas, libros de órdenes, creación de mercado, gestión de inventario
- **reservas**: reservas de la cuenta, recuento de propietarios, limpieza
- **auditoria**: verificación por lotes, informes de auditoría
- **amm**: liquidez del creador automático de mercado, comparación DEX vs AMM

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
