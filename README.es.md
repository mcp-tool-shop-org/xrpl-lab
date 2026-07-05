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

Manual de capacitación XRPL: aprende haciendo, demuestra con resultados concretos.

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

## Guía de inicio rápido

```bash
xrpl-lab start
```

El asistente guiado te guía a través de la configuración de la billetera, la financiación y tu primer módulo.

### Modo sin conexión

```bash
xrpl-lab start --dry-run
```

No se requiere red. Transacciones simuladas para aprender el flujo de trabajo.

## Módulos

<!-- BEGIN curriculum:auto readme-intro -->
<!-- generado por scripts/gen_docs.py — no editar manualmente; ejecutar el generador -->
28 módulos en diez áreas temáticas: Fundamentos, NFT, Tokens, Pagos, Identidad, DEX, Reservas, Auditoría, AMM y Proyecto Final.
Los requisitos previos se especifican claramente; la CLI y el analizador los hacen cumplir.

La columna `#` coincide con el orden que muestra `xrpl-lab list` (orden canónico de las áreas temáticas).
<!-- END curriculum:auto readme-intro -->

<!-- BEGIN curriculum:auto readme-table -->
<!-- generado por scripts/gen_docs.py — no editar manualmente; ejecutar el generador -->
| # | Módulo | Área temática | Modo | Requisitos previos | Produce |
|---|--------|-------|------|---------------|----------|
| 1 | Comprensión de recibos | fundamentos | testnet | — | txid, informe |
| 2 | Comprensión de fallas | fundamentos | testnet | Comprensión de recibos | txid, informe |
| 3 | Líneas de confianza 101: Monedas emitidas como relaciones | fundamentos | testnet | — | txid, informe |
| 4 | Depuración de líneas de confianza | fundamentos | testnet | Líneas de confianza 101: Monedas emitidas como relaciones | txid, informe |
| 5 | Creación de NFT 101: Tu primer activo de juego | nfts | testnet | — | txid, informe |
| 6 | Mercado de NFT 101: Intercambio de activos con regalías aplicadas | nfts | testnet | — | txid, informe |
| 7 | NFT dinámicos 101: Un artículo de juego que sube de nivel | nfts | testnet | — | txid, informe |
| 8 | Emisión de MPT 101: Una moneda de juego en una sola transacción | tokens | testnet | — | txid, informe |
| 9 | Distribución de MPT 101: Hacer llegar la moneda a los jugadores | tokens | testnet | Emisión de MPT 101: Una moneda de juego en una sola transacción | txid, informe |
| 10 | Congelación de tokens 101: El botón de pausa del emisor | tokens | testnet | — | txid, informe |
| 11 | Reembolso 101: La herramienta de revocación del emisor | tokens | testnet | — | txid, informe |
| 12 | Escrow 101: XRP con tiempo limitado | pagos | testnet | — | txid, informe |
| 13 | Finalización de Escrow 101: Liberar el XRP bloqueado | pagos | testnet | Escrow 101: XRP con tiempo limitado | txid, informe |
| 14 | Escrow de tokens (XLS-85): Bloquear IOUs, no solo XRP | pagos | testnet | Líneas de confianza 101: Monedas emitidas como relaciones, Escrow 101: XRP con tiempo limitado | txid, informe |
| 15 | Canales de pago 101: Firmar muchos, liquidar una vez | pagos | testnet | — | txid, informe |
| 16 | Cantidad entregada: La vulnerabilidad del pago parcial | pagos | testnet | Líneas de confianza 101: Monedas emitidas como relaciones | txid, informe |
| 17 | DID 101: Identidad en la cadena de bloques | identidad | testnet | — | txid, informe |
| 18 | Credenciales 101 (XLS-70): KYC y atestaciones de edad en la cadena de bloques | identidad | testnet | DID 101: Identidad en la cadena de bloques | txid, informe |
| 19 | Dominios con permisos y DEX restringida (XLS-80/81): Intercambio compatible y restringido por credenciales | identidad | testnet | Credenciales 101 (XLS-70): KYC y atestaciones de edad en la cadena de bloques | txid, informe |
| 20 | Comprensión de DEX: Ofertas, libros de órdenes y cancelaciones | dex | testnet | Líneas de confianza 101: Monedas emitidas como relaciones | txid, informe |
| 21 | Creación de mercado en DEX 101: Obtener ganancias del diferencial en el libro de órdenes | dex | testnet | Comprensión de DEX: Ofertas, libros de órdenes y cancelaciones | txid, informe |
| 22 | Protecciones de inventario de DEX: No te desequilibres | dex | testnet | Creación de mercado en DEX 101: Obtener ganancias del diferencial en el libro de órdenes | txid, informe |
| 23 | Reservas 101: Dónde "fue" tu XRP | reservas | testnet | Líneas de confianza 101: Monedas emitidas como relaciones | txid, informe |
| 24 | Higiene de la cuenta: Liberar reservas y limpiar objetos | reservas | testnet | Reservas 101: Dónde "fue" tu XRP | txid, informe |
| 25 | Modo de auditoría: Verificar recibos a escala | auditoría | testnet | Comprensión de recibos | informe, paquete de auditoría |
| 26 | Liquidez AMM 101: Proporcionar liquidez y obtener comisiones | amm | prueba en seco | Líneas de confianza 101: Monedas emitidas como relaciones | txid, informe |
| 27 | Comprensión del riesgo de DEX vs. AMM: Comparación de estrategias comerciales | amm | prueba en seco | Creación de mercado en DEX 101: Obtener ganancias del diferencial en el libro de órdenes, Liquidez AMM 101: Proporcionar liquidez y obtener comisiones | txid, informe |
| 28 | Proyecto final: Implementar una economía de juego mínima en XRPL | proyecto final | testnet | Emisión de MPT 101: Una moneda de juego en una sola transacción, Creación de NFT 101: Tu primer activo de juego, Escrow 101: XRP con tiempo limitado, Modo de auditoría: Verificar recibos a escala | txid, informe, paquete de auditoría |
<!-- END curriculum:auto readme-table -->

La columna **Produce** enumera los tipos de resultados que genera cada módulo (`txid`,
`report`, `audit_pack`); consulta la página de cada módulo en el
[manual](https://mcp-tool-shop-org.github.io/xrpl-lab/handbook/modules/) para obtener
la guía completa de habilidades y lo que demuestras en la cadena de bloques.

### Áreas temáticas

<!-- BEGIN curriculum:auto readme-tracks -->
<!-- generado por scripts/gen_docs.py — no editar manualmente; ejecutar el generador -->
- **fundamentos** — billetera, pagos, líneas de confianza, manejo de errores
- **nfts** — activos de juego NFT: creación, liquidación en el mercado, NFT dinámicos (XLS-20)
- **tokens** — emisión y revocación de tokens multifuncionales (MPT) para juegos (XLS-33)
- **pagos** — escrow y valor con tiempo limitado
- **identidad** — identificadores descentralizados (DID, XLS-40)
- **dex** — ofertas, libros de órdenes, creación de mercado, gestión de inventario
- **reservas** — reservas de cuenta, recuento de propietarios, limpieza
- **auditoría** — verificación por lotes, informes de auditoría
- **amm** — liquidez del creador automático de mercado, comparación de DEX y AMM
- **proyecto final** — combinar habilidades de diferentes áreas temáticas en una implementación de economía de juego
<!-- END curriculum:auto readme-tracks -->

### Modos

- **testnet** — transacciones reales en la red de prueba XRPL
- **prueba en seco** — entorno de pruebas sin conexión con transacciones simuladas (no se requiere red)

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

Todos los comandos admiten `--dry-run` para el modo sin conexión cuando sea aplicable.

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

### Asistencia en la resolución de problemas

```bash
xrpl-lab support-bundle              # Human-readable markdown bundle
xrpl-lab support-bundle --json       # Machine-parseable JSON
xrpl-lab support-bundle --verify bundle.json  # Verify a received bundle
```

Un facilitador puede diagnosticar cualquier problema de un alumno a partir de un paquete de soporte sin
reproducir toda la sesión. No se incluyen secretos.

### Flujo del taller

**Entorno completamente desconectado (sandbox)**: no se requiere conexión de red.
```bash
xrpl-lab wallet create
xrpl-lab start --dry-run
```

**Entorno mixto, desconectado + testnet**: transacciones reales para los conceptos básicos y entorno sandbox para funciones avanzadas.
```bash
xrpl-lab wallet create
xrpl-lab fund
xrpl-lab start
```

**Progresión de "Camp" a "Lab"**: continúa desde xrpl-camp.
```bash
xrpl-lab start    # auto-detects camp wallet and certificate
```

## Artefactos

**Paquete de prueba** (`xrpl_lab_proof_pack.json`): registro compartible de los módulos completados, identificadores de transacción y enlaces al explorador. Incluye un hash de integridad SHA-256. No contiene información confidencial.

**Certificado** (`xrpl_lab_certificate.json`): registro conciso de la finalización.

**Informes** (`reports/*.md`): resúmenes legibles para humanos sobre lo que se hizo y demostró.

**Paquetes de auditoría** (`audit_pack_*.json`): resultados de verificación por lotes con hash de integridad SHA-256.

## Modelo de seguridad y confianza

**Datos a los que accede XRPL Lab:**
- Semilla de la billetera (almacenada localmente en `~/.xrpl-lab/wallet.json` como JSON sin formato, protegida por permisos de archivo 0o600 y un directorio principal con permisos 0o700; no está cifrada).
- Progreso del módulo e identificadores de transacción (almacenados en `~/.xrpl-lab/state.json`, escrituras atómicas mediante tmp + cambio de nombre).
- RPC de XRPL Testnet (punto final público, las transacciones se firman localmente antes del envío).
- Grifo de testnet (HTTP público, solo se envía su dirección).

**Datos a los que XRPL Lab NO accede:**
- No a la red principal. Solo a la testnet.
- No recopila datos de telemetría, análisis ni información de ningún tipo.
- No utiliza cuentas en la nube, no requiere registro y no usa API de terceros.
- No contiene información confidencial en los paquetes de prueba, certificados, informes o paquetes de soporte, nunca.

**Permisos y niveles de almacenamiento:**
- Directorio principal `~/.xrpl-lab/`: nivel privado para secretos, directorio con permisos 0o700 + archivo de billetera con permisos 0o600. Almacena la semilla de la billetera, el registro del programa y los paquetes de auditoría.
- Espacio de trabajo `./.xrpl-lab/`: nivel diseñado para ser compartido, directorio con permisos 0o755. Almacena informes de módulos, paquetes de prueba y certificados. Los facilitadores pueden revisarlos sin necesidad de elevar los permisos.
- Sistema de archivos: solo lee y escribe en las dos ubicaciones anteriores.
- Red: solo utiliza XRPL Testnet RPC + grifo (ambos se pueden anular mediante variables de entorno, ambos son opcionales con `--dry-run`).
- No requiere permisos elevados.

**Interfaz del panel de control (cuando `xrpl-lab serve` está en ejecución):**
- El punto final del ejecutor WebSocket aplica una lista de origen permitida (cierra las conexiones que no están en la lista con el código 4003).
- Todos los marcos de error emiten un sobre estructurado (`code`, `message`, `hint`, `severity`, `icon_hint`); no se filtran rutas ni información del estado interno.
- Cola de mensajes por conexión limitada con comportamiento documentado para la gestión de la presión.

Consulte [SECURITY.md](SECURITY.md) para obtener la política de seguridad completa y las instrucciones de configuración del taller.

## Requisitos

- Python 3.11+
- Conexión a Internet para testnet (o utilice `--dry-run` para el modo completamente desconectado).

## Licencia

MIT

Creado por [MCP Tool Shop](https://mcp-tool-shop.github.io/)
