<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/brand/main/logos/xrpl-lab/readme.png" width="400" alt="XRPL Lab">
</p>

<p align="center">
  <a href="https://github.com/mcp-tool-shop-org/xrpl-lab/actions/workflows/ci.yml"><img src="https://github.com/mcp-tool-shop-org/xrpl-lab/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/mcp-tool-shop-org/xrpl-lab/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="MIT License"></a>
  <a href="https://mcp-tool-shop-org.github.io/xrpl-lab/"><img src="https://img.shields.io/badge/Landing_Page-live-blue" alt="Landing Page"></a>
</p>

XRPL: un cuaderno de ejercicios para aprender haciendo y demostrar con resultados.

Cada módulo enseña una habilidad de XRPL y genera un resultado verificable: un ID de transacción,
un recibo firmado o un informe de diagnóstico. Sin cuentas, sin rodeos: solo competencia y resultados.

## Instalación

```bash
pipx install xrpl-lab
```

O con pip:

```bash
pip install xrpl-lab
```

Requiere Python 3.11+.

## Guía de inicio rápido

```bash
xrpl-lab start
```

El asistente te guiará en la configuración de la billetera, la carga de fondos y tu primer módulo.

### Modo sin conexión

```bash
xrpl-lab start --dry-run
```

No se requiere conexión a la red. Transacciones simuladas para aprender el flujo de trabajo.

## Módulos

12 módulos en tres niveles: principiante, intermedio y avanzado.

| # | Módulo | Nivel | Lo que aprendes | Lo que demuestras |
|---|--------|-------|----------------|----------------|
| 1 | Lectura de recibos | Principiante | Realiza un pago, lee cada campo del recibo. | ID de transacción + informe de verificación. |
| 2 | Análisis de errores | Principiante | Provoca un error en una transacción intencionalmente, diagnostica, corrige y vuelve a enviar. | Rastro de transacciones fallidas y corregidas. |
| 3 | Conceptos básicos de las líneas de confianza | Principiante | Crea un emisor, establece una línea de confianza, emite tokens. | Línea de confianza + saldo de tokens. |
| 4 | Depuración de líneas de confianza | Principiante | Falla intencional de la línea de confianza, decodificación de errores, corrección. | Rastro de errores a correcciones (ID de transacción). |
| 5 | Conceptos básicos de los intercambios descentralizados (DEX) | Intermedio | Crea ofertas, lee libros de órdenes, cancela. | ID de transacción para la creación y cancelación de ofertas. |
| 6 | Conceptos básicos de las reservas | Intermedio | Instantáneas de la cuenta, número de propietarios, cálculos de reservas. | Diferencia entre la instantánea anterior y la actual. |
| 7 | Mantenimiento de la cuenta | Intermedio | Cancela ofertas, elimina líneas de confianza, libera reservas. | Informe de verificación de limpieza. |
| 8 | Auditoría de recibos | Intermedio | Verifica por lotes las transacciones con expectativas. | Paquete de auditoría (MD + CSV + JSON). |
| 9 | Conceptos básicos de la liquidez de los mercados automatizados (AMM) | Avanzado | Crea un pool, deposita, gana recompensas de LP, retira. | ID de transacción del ciclo de vida de un AMM. |
| 10 | Conceptos básicos de la creación de mercado en DEX | Avanzado | Ofertas de compra/venta, instantáneas de la posición, limpieza. | ID de transacción de la estrategia + informe de limpieza. |
| 11 | Controles de inventario | Avanzado | Cotización basada en umbrales, colocación solo en el lado seguro. | Verificación de inventario + ID de transacción con protección. |
| 12 | Comprensión de riesgos: DEX vs. AMM | Avanzado | Comparación lado a lado del ciclo de vida de DEX y AMM. | Informe de comparación + rastro de auditoría. |

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
xrpl-lab send               Send a payment
xrpl-lab verify --tx <id>   Verify a transaction on-ledger
```

Todos los comandos admiten `--dry-run` para el modo sin conexión, cuando sea aplicable.

## Resultados

**Paquete de prueba** (`xrpl_lab_proof_pack.json`): Registro compartible de los módulos completados,
ID de transacciones y enlaces al explorador. Incluye un hash de integridad SHA-256. No contiene secretos.

**Certificado** (`xrpl_lab_certificate.json`): Registro de finalización simplificado.

**Informes** (`reports/*.md`): Resúmenes legibles por humanos de lo que hiciste y demostraste.

**Paquetes de auditoría** (`audit_pack_*.json`): Resultados de verificación por lotes con hash de integridad SHA-256.

## Seguridad y modelo de confianza

**Datos a los que accede XRPL Lab:**
- Semilla de la billetera (almacenada localmente en `~/.xrpl-lab/wallet.json` con permisos de archivo restrictivos)
- Progreso del módulo y ID de transacciones (almacenados en `~/.xrpl-lab/state.json`)
- RPC de la red de pruebas de XRPL (punto de acceso público, las transacciones se firman localmente antes de enviarse)
- Grifo de la red de pruebas (HTTP público, solo se envía tu dirección)

**Datos que XRPL Lab NO manipula:**
- No se utiliza la red principal (mainnet). Solo se utiliza la red de pruebas (testnet).
- No se recopilan datos de telemetría, análisis ni información de ningún tipo.
- No se requieren cuentas en la nube, ni registros, ni APIs de terceros.
- No se incluyen secretos en los paquetes de prueba, certificados o informes, nunca.

**Permisos:**
- Sistema de archivos: solo lectura/escritura de los directorios `~/.xrpl-lab/` y `./.xrpl-lab/` (espacio de trabajo local).
- Red: Solo se utiliza el servicio RPC de la red de pruebas XRPL y un "faucet" (para obtener fondos de prueba). Ambos son opcionales y pueden ser modificados a través de variables de entorno, y ambos pueden desactivarse con la opción `--dry-run`.
- No se requieren permisos elevados.

Consulte el archivo [SECURITY.md](SECURITY.md) para obtener la política de seguridad completa.

## Requisitos

- Python 3.11 o superior.
- Conexión a Internet para la red de pruebas (o utilice la opción `--dry-run` para un modo completamente offline).

## Licencia

MIT

Desarrollado por [MCP Tool Shop](https://mcp-tool-shop.github.io/)
