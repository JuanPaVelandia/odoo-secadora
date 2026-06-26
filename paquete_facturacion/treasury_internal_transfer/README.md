# Transferencias Internas de Tesorería

Mueve dinero entre tus diarios (banco/caja) en **un solo paso**, con responsables
y confirmación de recepción. Reemplaza el flujo manual anterior (crear dos pagos
+ conciliar a mano) por un formulario único que contabiliza y concilia
automáticamente.

* **Versión:** 18.0.1.0.0
* **Licencia:** AGPL-3
* **Autor:** PARAMO LABS — https://paramodigital.com.co
* **Categoría:** Treasury

## Dependencias

* `account`
* `custom_account_treasury` — provee los grupos de seguridad
  (`group_treasury_user`, `group_treasury_manager`) y el menú padre de
  transferencias del que se cuelga este módulo.

## Qué hace

Desde un único formulario eliges **diario origen**, **diario destino**, **monto**
y **motivo**, y defines quién envía y quién recibe. Al confirmar, el sistema:

1. Crea y contabiliza el **pago de salida** (`outbound`) en el diario origen.
2. Crea y contabiliza el **cobro de entrada** (`inbound`) en el diario destino.
3. Empareja ambos pagos como transferencia interna nativa de Odoo
   (`paired_internal_transfer_payment_id`).
4. Fuerza la **cuenta de transferencia interna de la empresa**
   (`company.transfer_account_id`) como contrapartida y **concilia** la salida
   (débito) contra la entrada (crédito), dejando la cuenta puente en cero.
5. Programa una actividad al responsable destino para que **confirme la recepción**.

Todo queda trazado en el chatter, con un **comprobante PDF** imprimible.

## Flujo de estados

```
Borrador → Confirmada → Recibida
   │            │
   │            └── (Cancelar) ──┐
   └────────────────────────────┴──→ Cancelada → (Volver a Borrador)
```

| Estado | Acción | Quién | Efecto |
|--------|--------|-------|--------|
| **Borrador** | `Confirmar y Transferir` | Usuario de Tesorería | Crea, contabiliza y concilia los dos pagos |
| **Confirmada** | `Confirmar Recepción` | Responsable que recibe **o** Responsable de Tesorería | Marca el dinero como recibido y cierra la actividad |
| **Confirmada/Recibida** | `Cancelar` | Usuario de Tesorería | Revierte la conciliación, anula los pagos |
| **Cancelada** | `Volver a Borrador` | Usuario de Tesorería | Reabre para edición |

## Detalles de diseño

* **No dispara secuencias de negocio (RC/CE):** los pagos se crean con
  `partner_type` `customer`/`supplier` a propósito para evitar las secuencias de
  recibos de caja / comprobantes de egreso del módulo de tesorería. Una
  transferencia interna no es un cobro de cliente ni un pago a proveedor; la
  contrapartida real (cuenta puente) se fuerza justo antes de contabilizar.
* **Numeración:** secuencia `TR-%(range_year)s-#####` por rango de año
  (`treasury.internal.transfer`).
* **Validaciones:**
  * El monto debe ser mayor a cero.
  * Diario origen y destino deben ser distintos.
  * Ambos diarios deben operar en la misma moneda que la transferencia.

## Requisitos de configuración

La empresa debe tener definida una **Cuenta de transferencia interna**
(`Contabilidad → Configuración → Ajustes`, sección de cuentas predeterminadas).
Sin ella, `Confirmar y Transferir` arroja un error.

## Seguridad

| Grupo | Leer | Escribir | Crear | Borrar |
|-------|:----:|:--------:|:-----:|:------:|
| `custom_account_treasury.group_treasury_user` | ✓ | ✓ | ✓ | ✗ |
| `custom_account_treasury.group_treasury_manager` | ✓ | ✓ | ✓ | ✓ |

## Interfaz

* **Menú:** `Tesorería → Transferencias Internas → Transferencias` (se cuelga del
  menú existente del módulo de tesorería y oculta la "Nueva Transferencia" manual
  del flujo anterior).
* **Vistas:** kanban (agrupado por estado), lista (con total), formulario,
  búsqueda con filtros por estado y filtro **"Por confirmar (mías)"**.
* **Botón estadístico:** acceso directo a los pagos generados.

## Estructura del módulo

```
treasury_internal_transfer/
├── __manifest__.py
├── data/
│   └── sequence_data.xml          # Secuencia TR-AÑO-#####
├── models/
│   └── treasury_internal_transfer.py
├── report/
│   ├── treasury_internal_transfer_report.xml      # Acción de reporte PDF
│   └── treasury_internal_transfer_templates.xml   # Plantilla QWeb
├── security/
│   └── ir.model.access.csv
└── views/
    ├── treasury_internal_transfer_views.xml       # Form, list, kanban, search, action
    └── treasury_internal_transfer_menus.xml
```
