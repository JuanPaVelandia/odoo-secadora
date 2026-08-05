# Mantenimiento - Enlace con Facturas de Compra

Módulo para Odoo 19 que conecta las facturas de compra con la gestión de mantenimiento,
permitiendo trazabilidad completa de costos por equipo y orden de trabajo.

## Instalación

1. Copiar la carpeta `maintenance_purchase_link/` al directorio de addons de Odoo.
2. Reiniciar el servicio de Odoo.
3. Ir a **Aplicaciones**, buscar "Mantenimiento - Enlace con Facturas" e instalar.

### Dependencias

El módulo requiere que estén instalados:

- `maintenance` (Mantenimiento)
- `account` (Contabilidad)
- `purchase` (Compras)
- `analytic` (Cuentas analíticas)

## Datos iniciales

Al instalar el módulo se crean automáticamente:

- **Categorías de equipo** (áreas de planta): Campo/Cultivo, Recepción, Secado,
  Almacenamiento, Molienda, Empaque, Servicios generales

La cuenta analítica que dispara todo el flujo es **Maquinaria**, del plan
**Unidad de negocio**, que ya existe en la contabilidad de la empresa (hay una
por compañía y el módulo las acepta todas).

## Flujo de uso

### 1. Contabilidad

Al registrar una factura de proveedor, en cada línea seleccionar la distribución
analítica **Unidad de negocio → Maquinaria** para las líneas correspondientes a
gastos de mantenimiento.

Al **publicar** la factura, el módulo crea automáticamente un costo de
mantenimiento por cada una de esas líneas, todavía sin equipo ni orden de
trabajo.

> Las facturas anteriores a la **fecha pivote** (por defecto 2026-07-20) se
> omiten: ese gasto ya viene del histórico importado de Fracttal y contarlo otra
> vez lo duplicaría. Se ajusta en *Ajustes → Técnico → Parámetros del sistema*,
> parámetro `maintenance_purchase_link.fecha_pivote_costos`.

### 2. Coordinador de mantenimiento

1. Ir a **Mantenimiento → Costos → Facturas por asignar**. Se abre filtrado por
   las facturas que aún tienen costos sin equipo.
2. Cada fila muestra el proveedor, el **mensaje de WhatsApp** con el que llegó la
   factura y cuántas líneas quedan pendientes.
3. Escribir el **equipo** y la **orden de trabajo** directamente en la fila: se
   aplican a todas las líneas de la factura de una sola vez. Seleccionando varias
   facturas se pueden asignar en bloque.
4. Si el costo se reparte entre varios equipos, abrir la factura y usar la
   pestaña **Mantenimiento**, donde se indica equipo, OT y porcentaje por fila
   (deben sumar 100%).

El área de planta se resuelve automáticamente por la categoría del equipo.

### 3. Consultar costos desde equipos u órdenes de trabajo

- En el formulario de un **equipo**, el botón **"Costos"** muestra las líneas asociadas
  y el costo total acumulado.
- En el formulario de una **orden de trabajo**, el botón **"Costos"** muestra las líneas
  asociadas y el costo total.

### 4. Reportes

Desde **Mantenimiento → Costos → Costos de mantenimiento**, cambiar a vista
**Pivot** para analizar costos por equipo, mes, proveedor, etc. Esa lista reúne
tanto los costos que salen de facturas como el histórico importado y los
registros manuales; el campo **Origen** los distingue.

## Permisos

| Grupo | Puede ver campos M2M | Puede editar campos M2M |
|-------|---------------------|------------------------|
| Gestor de equipos (maintenance.group_equipment_manager) | Sí | Sí |
| Facturación (account.group_account_invoice) | Sí (vista factura) | No (solo lectura) |

## Restricciones

- Solo se puede asociar un equipo u orden de trabajo a una línea de factura que
  tenga la cuenta analítica **Maquinaria** (plan *Unidad de negocio*) en su
  distribución.
- Una línea de factura puede repartirse entre varios equipos, pero la suma de
  porcentajes no puede pasar de 100%.
- Al asignar desde la lista de facturas, una orden de trabajo ya puesta a mano en
  el detalle del costo no se sobrescribe.

## Estructura del módulo

```
maintenance_purchase_link/
├── __init__.py
├── __manifest__.py
├── data/
│   ├── analytic_data.xml
│   ├── config_parameter_data.xml     # fecha pivote de costos
│   ├── equipment_category_data.xml
│   └── sequence_data.xml             # numeración OT-<n>
├── models/
│   ├── __init__.py
│   ├── account_move.py               # automatización al publicar + asignación por factura
│   ├── account_move_line.py
│   ├── maintenance_equipment.py
│   ├── maintenance_equipment_cost_line.py   # modelo unificado de costos
│   ├── maintenance_equipment_location_history.py
│   ├── maintenance_horometro_reading.py
│   ├── maintenance_invoice_equipment.py     # equipo/OT a nivel de factura
│   └── maintenance_request.py
├── migrations/
├── security/
│   ├── ir.model.access.csv
│   └── maintenance_security.xml
├── views/
│   ├── account_move_views.xml        # pestaña Mantenimiento + Facturas por asignar
│   ├── maintenance_cost_views.xml
│   ├── maintenance_equipment_views.xml
│   ├── maintenance_horometro_views.xml
│   ├── maintenance_location_history_views.xml
│   ├── maintenance_menus.xml
│   └── maintenance_request_views.xml
├── report/
│   └── maintenance_cost_report.xml
└── tests/
    ├── __init__.py
    ├── test_horometro.py
    └── test_maintenance_cost.py
```
