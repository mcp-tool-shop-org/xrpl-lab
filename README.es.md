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

Manual de capacitación de XRPL: aprende poniendo en práctica lo aprendido y demuestra tus conocimientos con ejemplos concretos.

Cada módulo enseña una habilidad relacionada con XRPL y genera un resultado verificable: un identificador de transacción, un comprobante firmado o un informe de diagnóstico. Nada de cuentas innecesarias, ni información superflua, ni servicios en la nube; solo competencia y comprobantes.

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

Requiere Python versión 3.11 o superior.

## Guía de inicio rápido

```bash
xrpl-lab start
```

El asistente paso a paso te guiará en la configuración de tu billetera digital, el proceso de financiación y el uso de tu primer módulo.

### Modo sin conexión

```bash
xrpl-lab start --dry-run
```

No se requiere conexión a la red. Se simulan transacciones para aprender el flujo de trabajo.

## Módulos

<!-- INICIO del currículo: introducción automática del archivo Léame -->
<!-- generado por scripts/gen_docs.py; no editar manualmente; ejecutar el generador -->
32 módulos distribuidos en diez áreas temáticas: Fundamentos, NFT, tokens, pagos, identidad, DEX, reservas, auditoría, AMM y proyecto final.
Los requisitos previos están claramente definidos y se aplican mediante la interfaz de línea de comandos (CLI) y el analizador de código (linter).

La columna `#` corresponde al orden que se muestra con el comando `xrpl-lab list` (orden canónico de las pistas).

<!-- INICIO del currículo: tabla automática de contenido -->
<!-- generado por el script scripts/gen_docs.py; no editar manualmente; ejecutar el generador -->
| # | Módulo | Pista; seguir; rastrear. | Modo | Requisitos previos | Produce |
|---|--------|-------|------|---------------|----------|
| 1 | Comprensión de los recibos | cimientos | red de pruebas | — | ID de transacción, informe. |
| 2 | Alfabetización sobre el fracaso. | cimientos | red de pruebas | Comprensión de los recibos | ID de transacción, informe. |
| 3 | Principios básicos de las relaciones de confianza: las divisas emitidas como vínculo relacional. | cimientos | red de pruebas | — | ID de transacción, informe. |
| 4 | Resolución de problemas en las líneas de confianza. | cimientos | red de pruebas | Principios básicos de las relaciones de confianza: las divisas emitidas como vínculo relacional. | ID de transacción, informe. |
| 5 | Tesorería con múltiples firmas (conjunto de lista de firmantes): control N de M sobre la billetera del estudio. | cimientos | red de pruebas | Comprensión de los recibos | ID de transacción, informe. |
| 6 | Guía básica sobre la creación de NFT: tu primer activo para un juego. | NFT (tokens no fungibles) | red de pruebas | — | ID de transacción, informe. |
| 7 | Mercado de NFT para principiantes: cómo comprar y vender activos con derechos de autor garantizados. | NFT (tokens no fungibles) | red de pruebas | — | ID de transacción, informe. |
| 8 | NFT dinámicos: lo básico sobre un objeto de juego que mejora con el tiempo. | NFT (tokens no fungibles) | red de pruebas | — | ID de transacción, informe. |
| 9 | MPT: los conceptos básicos de la emisión: una moneda para juegos en una sola transacción. | fichas; símbolos; regalos | red de pruebas | — | ID de transacción, informe. |
| 10 | Guía básica sobre la distribución de MPT: cómo hacer llegar la moneda virtual a los jugadores. | fichas; símbolos; regalos | red de pruebas | MPT: los conceptos básicos de la emisión: una moneda para juegos en una sola transacción. | ID de transacción, informe. |
| 11 | Congelación de tokens: la función de pausa del emisor. | fichas; símbolos; regalos | red de pruebas | — | ID de transacción, informe. |
| 12 | Lo básico sobre la recuperación de fondos: el mecanismo que permite al emisor solicitar la devolución. | fichas; símbolos; regalos | red de pruebas | — | ID de transacción, informe. |
| 13 | Conceptos básicos sobre las cuentas de depósito en garantía: XRP con un plazo de tiempo definido. | pagos | red de pruebas | — | ID de transacción, informe. |
| 14 | Guía básica sobre el proceso de liberación de XRP en cuentas de depósito en garantía. | pagos | red de pruebas | Conceptos básicos sobre las cuentas de depósito en garantía: XRP con un plazo de tiempo definido. | ID de transacción, informe. |
| 15 | Servicio de depósito en garantía de tokens (XLS-85): permite bloquear las obligaciones de pago, no solo los XRP. | pagos | red de pruebas | Líneas de confianza 101: las divisas emitidas como relaciones; Depósitos en garantía 101: XRP con un período de bloqueo temporal. | ID de transacción, informe. |
| 16 | Cheques 101: Pagos diferidos (Creación de cheque/Cobro de cheque/Anulación de cheque) | pagos | red de pruebas | Comprensión de los recibos | ID de transacción, informe. |
| 17 | Canales de pago: conceptos básicos: utilice múltiples opciones y realice un único pago. | pagos | red de pruebas | — | ID de transacción, informe. |
| 18 | Cantidad entregada: la vulnerabilidad del pago parcial. | pagos | red de pruebas | Principios básicos de las relaciones de confianza: las divisas emitidas como vínculo relacional. | ID de transacción, informe. |
| 19 | Asignación de fondos a jugadores bajo custodia: una única billetera común y múltiples jugadores (etiquetas de destino). | pagos | red de pruebas | Cantidad entregada: la vulnerabilidad del pago parcial. | ID de transacción, informe. |
| 20 | DID 101: Identidad gestionada directamente en el libro mayor. | identidad | red de pruebas | — | ID de transacción, informe. |
| 21 | Credenciales 101 (XLS-70): Verificación de identidad y declaración de edad directamente en el libro mayor. | identidad | red de pruebas | DID 101: Identidad gestionada directamente en el libro mayor. | ID de transacción, informe. |
| 22 | Dominios con permisos y plataforma descentralizada restringida (XLS-80/81): operaciones comerciales que cumplen con las normas y requieren autenticación. | identidad | red de pruebas | Credenciales 101 (XLS-70): Verificación de identidad y declaración de edad directamente en el libro mayor. | ID de transacción, informe. |
| 23 | Puerta de depósito (DepositAuth + DepositPreauth): Depósitos en la tesorería protegidos por credenciales. | identidad | red de pruebas | Credenciales 101 (XLS-70): Verificación de identidad y declaración de edad directamente en el libro mayor. | ID de transacción, informe. |
| 24 | DEX Literacy: Ofertas, libros de órdenes y cancelaciones. | dex | red de pruebas | Principios básicos de las relaciones de confianza: las divisas emitidas como vínculo relacional. | ID de transacción, informe. |
| 25 | Fundamentos de la creación de mercados DEX: cómo obtener beneficios a partir del diferencial en el libro de órdenes. | dex | red de pruebas | DEX Literacy: Ofertas, libros de órdenes y cancelaciones. | ID de transacción, informe. |
| 26 | Medidas de seguridad para el inventario DEX: evite desequilibrios. | dex | red de pruebas | Fundamentos de la creación de mercados DEX: cómo obtener beneficios a partir del diferencial en el libro de órdenes. | ID de transacción, informe. |
| 27 | Conceptos básicos sobre las reservas: ¿a dónde fueron tus XRP? | reservas | red de pruebas | Principios básicos de las relaciones de confianza: las divisas emitidas como vínculo relacional. | ID de transacción, informe. |
| 28 | Mantenimiento de la cuenta: liberación de reservas y eliminación de objetos innecesarios. | reservas | red de pruebas | Conceptos básicos sobre las reservas: ¿a dónde fueron tus XRP? | ID de transacción, informe. |
| 29 | Modo de auditoría: verificación masiva de recibos. | auditoría | red de pruebas | Comprensión de los recibos | informe, paquete de auditoría |
| 30 | Liquidez en AMM: cómo proporcionar liquidez y obtener comisiones. | amm | ensayo general; simulación práctica | Principios básicos de las relaciones de confianza: las divisas emitidas como vínculo relacional. | ID de transacción, informe. |
| 31 | Nivel de comprensión del riesgo en DEX y AMM: comparación de estrategias de negociación. | amm | ensayo general; simulación práctica | Fundamentos de la creación de mercados en DEX: obtención de beneficios a partir del diferencial en el libro de órdenes; fundamentos de la liquidez en los protocolos AMM: provisión de liquidez y obtención de comisiones. | ID de transacción, informe. |
| 32 | Proyecto final: crea una economía de juego básica en XRPL. | piedra angular; proyecto final; culminación | red de pruebas | MPT: Introducción a las transacciones con tokens de juegos, NFT: Creación de tu primer activo para un juego, Depósito en garantía: XRP con bloqueo temporal, Modo de auditoría: verificación masiva de recibos. | ID de transacción, informe, paquete de auditoría. |
<!-- FIN del currículo: tabla automática de la documentación -->

La columna **Produces** (Genera) enumera los tipos de artefactos que genera cada módulo (`txid`, `report`, `audit_pack`); consulte la página de cada módulo en el [manual](https://mcp-tool-shop-org.github.io/xrpl-lab/handbook/modules/) para obtener información detallada sobre las funciones y lo que se demuestra en el libro mayor.

### Pistas

<!-- INICIO del currículo: auto readme-tracks -->
<!-- generado por scripts/gen_docs.py; no editar manualmente; ejecutar el generador -->
- **fundamentos**: billetera, pagos, líneas de crédito, gestión de errores
- **NFT**: activos de juego NFT: creación, liquidación en el mercado, NFT dinámicos (XLS-20)
- **tokens**: emisión y recuperación de tokens multifuncionales (MPT) para juegos (XLS-33)
- **pagos**: depósito en garantía y valor con bloqueo temporal
- **identidad**: identificadores descentralizados (DID, XLS-40)
- **DEX**: ofertas, libros de órdenes, creación de mercado, gestión de inventario
- **reservas**: reservas de cuenta, recuento de propietarios, limpieza
- **auditoría**: verificación por lotes, informes de auditoría
- **AMM**: liquidez del creador automático de mercado, comparación entre DEX y AMM
- **proyecto final**: combinar habilidades de diferentes módulos para crear una economía de juego completa
<!-- FIN del currículo: auto readme-tracks -->

### Modos

- **red de pruebas** — transacciones reales en la red de pruebas XRPL.
- **simulación** — entorno de prueba sin conexión con transacciones simuladas (no se requiere conexión a la red).

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

Todos los comandos admiten la opción `--dry-run` para el modo sin conexión, cuando sea aplicable.

## Uso en talleres

XRPL Lab está diseñado para entornos de enseñanza reales. No hay cuentas, ni telemetría, ni acceso a la nube. Todo se ejecuta localmente.

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/xrpl-lab/main/docs/images/facilitator-active-runs.png" width="800" alt="Facilitator dashboard listing active learner runs with module IDs, dry-run badges, status, queue depth, and run IDs">
</p>

### Estado de facilitador

```bash
xrpl-lab status             # Where is this learner? What's blocked? What's next?
xrpl-lab status --json      # Machine-readable for scripting
xrpl-lab tracks             # Track-level completion: what was actually practiced
xrpl-lab recovery           # Stuck? See exactly what to run next
```

### Transferencia de soporte

```bash
xrpl-lab support-bundle              # Human-readable markdown bundle
xrpl-lab support-bundle --json       # Machine-parseable JSON
xrpl-lab support-bundle --verify bundle.json  # Verify a received bundle
```

Un facilitador puede diagnosticar cualquier problema de un estudiante a partir de un paquete de soporte sin tener que reproducir toda la sesión. No se incluyen datos confidenciales.

### Flujos de trabajo

**Entorno de pruebas completamente desconectado:** no requiere conexión de red:
```bash
xrpl-lab wallet create
xrpl-lab start --dry-run
```

**Entorno mixto (desconectado + testnet):** transacciones reales para los conceptos básicos, entorno de pruebas para funciones avanzadas:
```bash
xrpl-lab wallet create
xrpl-lab fund
xrpl-lab start
```

**Progresión de "Camp" a "Lab":** continúa desde xrpl-camp:
```bash
xrpl-lab start    # auto-detects camp wallet and certificate
```

## Artefactos

**Paquete de prueba** (`xrpl_lab_proof_pack.json`): registro compartible de los módulos completados, ID de transacción y enlaces al explorador. Incluye un hash de integridad SHA-256. No se incluyen datos confidenciales.

**Certificado** (`xrpl_lab_certificate.json`): registro conciso de la finalización.

**Informes** (`reports/*.md`): resúmenes legibles por humanos de lo que se hizo y demostró.

**Paquetes de auditoría** (`audit_pack_*.json`): resultados de verificación por lotes con hash de integridad SHA-256.

## Modelo de seguridad y confianza

**Datos a los que accede XRPL Lab:**
- Semilla de la billetera (almacenada localmente en `~/.xrpl-lab/wallet.json` como JSON sin formato, protegida por permisos de archivo 0o600 y un directorio principal 0o700; no está cifrada)
- Progreso del módulo e ID de transacción (almacenados en `~/.xrpl-lab/state.json`, escrituras atómicas mediante tmp + cambio de nombre)
- RPC de XRPL Testnet (punto final público, las transacciones se firman localmente antes del envío)
- Grifo de testnet (HTTP público, solo se envía su dirección)

**Datos a los que NO accede XRPL Lab:**
- No hay acceso a la red principal. Solo a la testnet.
- No hay telemetría, análisis ni envío de datos de ningún tipo.
- No hay cuentas en la nube, ni registro, ni API de terceros.
- No hay datos confidenciales en los paquetes de prueba, certificados, informes o paquetes de soporte, nunca.

**Permisos y niveles de almacenamiento:**
- Directorio principal `~/.xrpl-lab/`: nivel de secretos privados, directorio 0o700 + archivo de billetera 0o600. Almacena la semilla de la billetera, el registro del "doctor" y los paquetes de auditoría.
- Espacio de trabajo `./.xrpl-lab/`: nivel diseñado para ser compartido, directorio 0o755. Almacena informes de módulos, paquetes de prueba y certificados. Los facilitadores pueden revisarlos sin necesidad de permisos elevados.
- Sistema de archivos: solo lee y escribe en las dos ubicaciones anteriores.
- Red: solo RPC de XRPL Testnet + grifo (ambos se pueden anular mediante variables de entorno, ambos son opcionales con `--dry-run`).
- No se requieren permisos elevados.

**Interfaz del panel de control (cuando `xrpl-lab serve` está en ejecución):**
- El punto final del ejecutor WebSocket aplica una lista de permitidos de origen (cierra las conexiones que no están en la lista con el código 4003).
- Todos los marcos de error emiten un sobre estructurado (`code`, `message`, `hint`, `severity`, `icon_hint`); no hay fugas de rutas ni de estado interno.
- Cola de mensajes por conexión limitada con comportamiento documentado de contrapresión.

Consulte [SECURITY.md](SECURITY.md) para obtener la política de seguridad completa y las instrucciones de configuración del taller.

## Requisitos

- Python 3.11+
- Conexión a Internet para testnet (o use `--dry-run` para un modo completamente desconectado)

## Licencia

MIT

Creado por [MCP Tool Shop](https://mcp-tool-shop.github.io/)
