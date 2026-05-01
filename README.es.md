<p align="center">
  <a href="README.ja.md">日本語</a> | <a href="README.zh.md">中文</a> | <a href="README.md">English</a> | <a href="README.fr.md">Français</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.it.md">Italiano</a> | <a href="README.pt-BR.md">Português (BR)</a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/brand/main/logos/xrpl-lab/readme.png" width="400" alt="XRPL Lab">
</p>

<p align="center">
  <a href="https://github.com/mcp-tool-shop-org/xrpl-lab/actions/workflows/ci.yml"><img src="https://github.com/mcp-tool-shop-org/xrpl-lab/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/mcp-tool-shop-org/xrpl-lab/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="MIT License"></a>
  <a href="https://mcp-tool-shop-org.github.io/xrpl-lab/"><img src="https://img.shields.io/badge/Landing_Page-live-blue" alt="Landing Page"></a>
</p>

XRPL: Manual de capacitación: aprenda haciendo, demuestre con resultados.

Cada módulo enseña una habilidad de XRPL y produce un resultado verificable: un ID de transacción,
un recibo firmado o un informe de diagnóstico. Sin cuentas, sin rodeos, sin nube: solo
competencia y resultados.

## Instalación

```bash
pipx install xrpl-lab
```

O con pip:

```bash
pip install xrpl-lab
```

Requiere Python 3.11+.

## Inicio rápido

```bash
xrpl-lab start
```

El asistente te guía en la configuración de la billetera, la financiación y tu primer módulo.

### Modo sin conexión

```bash
xrpl-lab start --dry-run
```

No se requiere conexión de red. Transacciones simuladas para aprender el flujo de trabajo.

## Módulos

12 módulos en cinco áreas: Fundamentos, DEX, Reservas, Auditoría y AMM.
Los requisitos previos son explícitos; la CLI y el analizador de código los hacen cumplir.

| # | Módulo | Área | Modo | Lo que aprende | Lo que demuestra |
|---|--------|-------|------|----------------|----------------|
| 1 | Comprensión de los recibos | Fundamentos | Red de pruebas | La confirmación es un recibo, no un estado de "enviado". Envíe un pago, lea cada campo del recibo. | ID de transacción + informe de verificación |
| 2 | Comprensión de los errores | Fundamentos | Red de pruebas | Los errores de XRPL tienen significado (tec/tef/tem/ter). Rompa una transacción intencionalmente, diagnostique, corrija y vuelva a enviar. | Secuencia de transacciones fallidas y corregidas |
| 3 | Conceptos básicos de las líneas de confianza | Fundamentos | Red de pruebas | Los tokens se activan y son unidireccionales. Cree un emisor, establezca una línea de confianza, emita tokens. | Línea de confianza + saldo del token |
| 4 | Depuración de líneas de confianza | Fundamentos | Red de pruebas | Decodifique los códigos de error de la línea de confianza. Fallo intencionado, decodificación de errores, corrección. | Error → secuencia de transacciones de corrección |
| 5 | Comprensión de DEX | DEX | Red de pruebas | Los libros de órdenes emparejan a compradores y vendedores. Cree ofertas, lea libros de órdenes, cancele. | ID de transacción de creación y cancelación de ofertas |
| 6 | Conceptos básicos de las reservas | Reservas | Red de pruebas | Cada objeto propiedad bloquea XRP. Instantáneas, número de propietarios, cálculo de reservas. | Diferencia de instantáneas (antes/después) |
| 7 | Mantenimiento de la cuenta | Reservas | Red de pruebas | La limpieza es una habilidad fundamental. Cancele ofertas, elimine líneas de confianza, libere reservas. | Informe de verificación de limpieza |
| 8 | Auditoría | Auditoría | Red de pruebas | Las auditorías codifican la intención (ID de transacción + expectativa + veredicto). Verifique por lotes con expectativas. | Paquete de auditoría (MD + CSV + JSON) |
| 9 | Conceptos básicos de la liquidez de AMM | AMM | Prueba simulada | Los precios de producto constante (`x*y=k`) varían pasivamente. Cree un grupo, deposite, gane LP, retire. | ID de transacción del ciclo de vida de AMM |
| 10 | Conceptos básicos de la creación de mercado en DEX | DEX | Red de pruebas | Los diferenciales de oferta/demanda rastrean el inventario. Cotice ambos lados, haga instantáneas de las posiciones, limpie. | ID de transacción de la estrategia + informe de limpieza |
| 11 | Controles de inventario | DEX | Red de pruebas | Solo cotice el lado seguro cuando el inventario se desequilibra. Colocación basada en umbrales y protegida. | Comprobación de inventario + transacciones protegidas |
| 12 | Comprensión de los riesgos de DEX vs AMM | AMM | Prueba simulada | La pérdida imperceptible es una propiedad del modelo AMM. DEX y AMM lado a lado. | Informe de comparación + registro de auditoría |

### Áreas

- **Fundamentos**: billetera, pagos, líneas de confianza, manejo de errores.
- **DEX**: ofertas, libros de órdenes, creación de mercado, gestión de inventario.
- **Reservas**: reservas de la cuenta, número de propietarios, limpieza.
- **Auditoría**: verificación por lotes, informes de auditoría.
- **AMM**: liquidez del mercado automatizado, comparación de DEX vs AMM.

### Modos

- **Red de pruebas**: transacciones reales en la red de pruebas de XRPL.
- **Prueba simulada**: sandbox sin conexión con transacciones simuladas (no se requiere conexión de red).

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

Todos los comandos admiten `--dry-run` para el modo sin conexión, cuando sea aplicable.

## Uso en talleres

XRPL Lab está diseñado para entornos de enseñanza reales. No requiere cuentas, ni telemetría, ni servicios en la nube.
Todo funciona localmente.

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

Un facilitador puede diagnosticar cualquier problema de un participante a partir de un paquete de soporte sin necesidad de reproducir toda la sesión. No se incluyen datos confidenciales.

### Flujos de trabajo del taller

**Entorno de pruebas completamente offline:** no se requiere conexión a la red.
```bash
xrpl-lab wallet create
xrpl-lab start --dry-run
```

**Combinación de offline y testnet:** transacciones reales para conceptos básicos, entorno de pruebas para temas avanzados.
```bash
xrpl-lab wallet create
xrpl-lab fund
xrpl-lab start
```

**Progresión de "campamento" a laboratorio:** permite continuar desde xrpl-camp.
```bash
xrpl-lab start    # auto-detects camp wallet and certificate
```

## Elementos

**Paquete de verificación** (`xrpl_lab_proof_pack.json`): Registro compartible de los módulos completados,
identificadores de transacción y enlaces al explorador. Incluye un hash de integridad SHA-256. No contiene datos confidenciales.

**Certificado** (`xrpl_lab_certificate.json`): Registro simplificado de la finalización.

**Informes** (`reports/*.md`): Resúmenes legibles por humanos de lo que se hizo y se demostró.

**Paquetes de auditoría** (`audit_pack_*.json`): Resultados de verificación por lotes con hash de integridad SHA-256.

## Modelo de seguridad y confianza

**Datos a los que XRPL Lab accede:**
- Clave de la billetera (almacenada localmente en `~/.xrpl-lab/wallet.json` como JSON de texto plano, protegida con permisos de archivo 0o600 y un directorio padre 0o700; no está encriptada).
- Progreso de los módulos y identificadores de transacción (almacenados en `~/.xrpl-lab/state.json`, escrituras atómicas a través de un archivo temporal y luego renombrado).
- RPC de la red de pruebas XRPL (punto de acceso público, las transacciones se firman localmente antes de enviarse).
- Grifo de la red de pruebas (HTTP público, solo se envía su dirección).

**Datos a los que XRPL Lab NO accede:**
- No se utiliza la red principal. Solo la red de pruebas.
- No hay telemetría, análisis ni envío de información a servidores externos.
- No hay cuentas en la nube, ni registro, ni APIs de terceros.
- No hay datos confidenciales en los paquetes de verificación, certificados, informes o paquetes de soporte, nunca.

**Permisos y niveles de almacenamiento:**
- Directorio principal `~/.xrpl-lab/`: nivel de secretos privados, directorio con permisos 0o700 y archivo de billetera con permisos 0o600. Almacena la clave de la billetera, el registro del facilitador y los paquetes de auditoría.
- Espacio de trabajo `./.xrpl-lab/`: nivel diseñado para compartir, directorio con permisos 0o755. Almacena informes de módulos, paquetes de verificación y certificados. Los facilitadores pueden revisarlos sin necesidad de permisos adicionales.
- Sistema de archivos: solo lee y escribe en las dos ubicaciones anteriores.
- Red: solo RPC y grifo de la red de pruebas XRPL (ambos pueden ser modificados a través de variables de entorno y son opcionales con `--dry-run`).
- No se requieren permisos elevados.

**Interfaz del panel de control (cuando se ejecuta `xrpl-lab serve`):**
- El punto de acceso del corredor WebSocket impone una lista de origen permitida (cierra las conexiones que no están en la lista con el código 4003).
- Todos los marcos de error emiten un envoltorio estructurado (`code`, `message`, `hint`, `severity`, `icon_hint`) — no se filtra información de la ruta, ni del estado interno.
- Cola de mensajes limitada por conexión con un comportamiento de retroalimentación documentado.

Consulte [SECURITY.md](SECURITY.md) para obtener la política de seguridad completa y las instrucciones de configuración del taller.

## Requisitos

- Python 3.11+
- Conexión a Internet para la red de pruebas (o use `--dry-run` para el modo completamente offline).

## Licencia

MIT

Desarrollado por [MCP Tool Shop](https://mcp-tool-shop.github.io/)
