# Mantenimiento - Enlace con Facturas de Compra

Módulo para Odoo 18 que conecta las facturas de compra con la gestión de mantenimiento,
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

- **Plan analítico "Tipo de costo"** con tres cuentas: Mantenimiento, Operación, Administrativo
- **Categorías de equipo** (áreas de planta): Campo/Cultivo, Recepción, Secado,
  Almacenamiento, Molienda, Empaque, Servicios generales

## Flujo de uso

### 1. Contabilidad

Al registrar una factura de proveedor, en cada línea seleccionar la distribución analítica
**Tipo de costo → Mantenimiento** para las líneas correspondientes a gastos de mantenimiento.

### 2. Coordinador de mantenimiento

1. Ir a **Mantenimiento → Costos → Facturas de mantenimiento**.
2. La vista muestra todas las líneas de factura de proveedor.
   Se activa un filtro por defecto que muestra solo las publicadas.
3. En cada línea, asignar:
   - **Equipo(s)**: uno o varios equipos de mantenimiento
   - **Orden(es) de trabajo**: una o varias solicitudes de mantenimiento
4. El área de planta se resuelve automáticamente por la categoría del equipo.

### 3. Consultar costos desde equipos u órdenes de trabajo

- En el formulario de un **equipo**, el botón **"Costos"** muestra las líneas asociadas
  y el costo total acumulado.
- En el formulario de una **orden de trabajo**, el botón **"Costos"** muestra las líneas
  asociadas y el costo total.

### 4. Reportes

Desde **Mantenimiento → Costos → Facturas de mantenimiento**, cambiar a vista **Pivot**
para analizar costos por equipo, mes, proveedor, etc.

## Permisos

| Grupo | Puede ver campos M2M | Puede editar campos M2M |
|-------|---------------------|------------------------|
| Gestor de equipos (maintenance.group_equipment_manager) | Sí | Sí |
| Facturación (account.group_account_invoice) | Sí (vista factura) | No (solo lectura) |

## Restricciones

- Solo se puede asociar un equipo u orden de trabajo a una línea de factura que tenga
  la cuenta analítica "Mantenimiento" en su distribución.
- Una línea de factura puede asociarse a múltiples equipos y múltiples órdenes de trabajo.

## Estructura del módulo

```
maintenance_purchase_link/
├── __init__.py
├── __manifest__.py
├── data/
│   ├── analytic_data.xml
│   └── equipment_category_data.xml
├── models/
│   ├── __init__.py
│   ├── account_move_line.py
│   ├── maintenance_equipment.py
│   └── maintenance_request.py
├── security/
│   ├── ir.model.access.csv
│   └── maintenance_security.xml
├── views/
│   ├── account_move_views.xml
│   ├── maintenance_equipment_views.xml
│   ├── maintenance_request_views.xml
│   ├── maintenance_cost_views.xml
│   └── maintenance_menus.xml
├── report/
│   └── maintenance_cost_report.xml
└── tests/
    ├── __init__.py
    └── test_maintenance_cost.py
```
