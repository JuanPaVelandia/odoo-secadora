# Reglas del Proyecto - Secadora La Gran Colombia

## Odoo 18 - Errores comunes a evitar
- Las vistas de lista se llaman `list`, NUNCA `tree`. Ejemplo: `<list>`, no `<tree>`
- (Se iran agregando mas reglas conforme el usuario las identifique)

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
