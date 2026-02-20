# Reglas del Proyecto - Secadora La Gran Colombia

## Odoo 18 - Errores comunes a evitar
- Las vistas de lista se llaman `list`, NUNCA `tree`. Ejemplo: `<list>`, no `<tree>`
- NUNCA usar `@string` como selector xpath — usar `@name` o navegar via `//field[@name='...']`
- NUNCA usar `ancestor::` en xpath de herencia de vistas — no es soportado. Usar selectores directos como `//notebook`, `//div[@name='...']`, `//field[@name='...']`
- XMLIDs de ubicaciones de stock:
  - Virtual Locations parent: `stock.stock_location_locations_virtual` (NO `stock.stock_location_virtual`)
  - Physical Locations parent: `stock.stock_location_locations`
  - Production: `stock.stock_location_production`
  - Suppliers: `stock.stock_location_suppliers`
  - Customers: `stock.stock_location_customers`
  - WH/Stock: `stock.stock_location_stock`
  - Inventory loss: se crea dinamicamente por compania (no tiene xmlid estatico)

## Convenciones del proyecto
- Timezone: America/Bogota (Colombia)
- Modelos usan prefijo: `secadora.`
- Secuencias auto-generadas para pesajes y ordenes
- Estados siguen patron: borrador -> en_proceso -> completado
- Idioma de campos y strings: espanol

## Estructura del proyecto
- `bascula/` — Modulo principal (pesajes, ordenes, catalogos)
- `secadora_bascula/` — Integracion con stock.picking
- `bridge/` — Script Python para conectar bascula fisica

## Modulos Odoo de dependencia
- base, contacts, product, stock
- NO esta instalado el modulo `account` aun
