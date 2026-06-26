# Mixins para Libros Contables Colombia

## Descripcion

Esta carpeta contiene los mixins reutilizables para reportes contables colombianos.
Reduce aproximadamente 40% del codigo al centralizar funcionalidad comun.

## Mixins Disponibles

### 1. ReportLineMixin (`report.line.mixin`)

Genera lineas de reporte con estructura estandar.

**Metodos principales:**
- `_build_line()` - Construye linea base
- `_get_section_header()` - Encabezado de seccion
- `_get_data_line()` - Linea de datos
- `_get_subtotal_line()` - Subtotal
- `_get_total_line()` - Total general
- `_get_no_data_line()` - Mensaje sin datos
- `_get_error_line()` - Mensaje de error

**Ejemplo de uso:**
```python
class MiHandler(models.AbstractModel):
    _name = 'mi.handler'
    _inherit = ['account.report.custom.handler', 'report.line.mixin']

    def _dynamic_lines_generator(self, report, options, ...):
        lines = []
        lines.append(self._get_section_header(report, options, 'Activos', 'activos'))
        lines.append(self._get_data_line(report, options, 'Caja', 1000000, 'caja_1', code='110505'))
        lines.append(self._get_total_line(report, options, 'Total Activos', 1000000))
        return [(0, line) for line in lines]
```

### 2. PUCHierarchyMixin (`puc.hierarchy.mixin`)

Maneja la jerarquia del Plan Unico de Cuentas Colombia.

**Constantes:**
- `PUC_LEVELS` - Niveles del PUC (Clase, Grupo, Cuenta, Subcuenta, Auxiliar, Subauxiliar)
- `PUC_NAMES` - Nombres predefinidos para clases y grupos

**Metodos:**
- `get_puc_level(code)` - Determina nivel de un codigo
- `get_puc_level_name(prefix)` - Obtiene nombre del nivel
- `group_by_puc_level(data, level)` - Agrupa cuentas por nivel
- `build_puc_hierarchy(data)` - Construye jerarquia completa

**Ejemplo:**
```python
# Obtener nivel de una cuenta
nivel = self.get_puc_level('110505')  # Retorna 5 (Auxiliar)

# Agrupar cuentas por nivel
grouped = self.group_by_puc_level(account_data, target_level=3)
```

### 3. AccountQueryMixin (`account.query.mixin`)

Consultas SQL para datos contables.

**Metodos:**
- `get_account_balance_at_date()` - Saldo a una fecha
- `get_account_balance_range()` - Movimientos en rango
- `get_account_balance_change()` - Cambio entre fechas
- `get_options_initial_balance()` - Opciones para saldo inicial
- `build_account_query()` - Construye query completa

**Ejemplo:**
```python
# Obtener saldo de cuentas de caja a fecha
saldo = self.get_account_balance_at_date(
    report, options,
    account_prefixes=['11'],  # Disponible
    target_date='2024-12-31'
)
```

### 4. ReportExportMixin (`report.export.mixin`)

Exportacion unificada a PDF y Excel.

**Presets de estilo:**
- `professional` - Azul oscuro/verde/rojo
- `corporate` - Azul corporativo
- `minimal` - Blanco y negro
- `accounting` - Contable tradicional
- `colombia_dian` - Estilo DIAN

**Presets de columnas:**
- `balance_simple` - Codigo, Nombre, Saldo
- `balance_completo` - Con Inicial/Debito/Credito/Final
- `auxiliar` - Para libro auxiliar
- `comparativo` - Para comparacion de periodos
- `impuestos` - Para reportes de impuestos

**Metodos:**
- `build_export_config(options)` - Construye configuracion
- `export_to_xlsx_advanced()` - Exporta a Excel
- `get_pdf_context()` - Contexto para PDF QWeb

**Ejemplo:**
```python
# Exportar a Excel con estilo DIAN
config = self.build_export_config({
    'style_preset': 'colombia_dian',
    'column_preset': 'balance_completo',
    'header_template': 'dian',
    'use_colors': True,
})
excel_bytes = self.export_to_xlsx_advanced('Balance de Prueba', lines, options, config)
```

### 5. TranslatableFieldMixin (`translatable.field.mixin`)

Manejo de campos JSONB traducibles en Odoo 18.

**Metodos:**
- `get_field_sql_native()` - Usa _field_to_sql nativo (recomendado)
- `get_translatable_sql()` - SQL manual para traducibles
- `get_company_dependent_sql()` - SQL para campos company_dependent
- `get_account_code_sql()` - SQL para account.account.code
- `get_account_name_sql()` - SQL para account.account.name
- `get_partner_name_sql()` - SQL para res.partner.name
- `build_select_with_translations()` - Construye SELECT automatico

**Ejemplo (metodo nativo recomendado):**
```python
query = report._get_report_query(options, 'strict_range')
account_alias = query.join(
    lhs_alias='account_move_line',
    lhs_column='account_id',
    rhs_table='account_account',
    rhs_column='id',
    link='account_id'
)

# Metodo nativo Odoo 18
account_code = self.get_field_sql_native('account.account', 'code', account_alias, query)
account_name = self.get_field_sql_native('account.account', 'name', account_alias)
```

## Uso Combinado

Para crear un nuevo handler, heredar de todos los mixins necesarios:

```python
class MiReporteHandler(models.AbstractModel):
    _name = 'mi.reporte.handler'
    _inherit = [
        'account.report.custom.handler',
        'report.line.mixin',
        'puc.hierarchy.mixin',
        'account.query.mixin',
        'report.export.mixin',
        'translatable.field.mixin',
    ]
    _description = 'Mi Reporte Personalizado'

    _report_css_class = 'mi_reporte'

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        lines = []

        # Usar mixins
        account_data = self._get_account_data()  # AccountQueryMixin
        grouped = self.group_by_puc_level(account_data, 4)  # PUCHierarchyMixin

        for prefix, data in grouped.items():
            lines.append(self._get_data_line(...))  # ReportLineMixin

        return [(0, line) for line in lines]
```

## Campos JSONB en Odoo 18

En Odoo 18, los campos traducibles y company_dependent usan JSONB:

| Campo | Tipo | Almacenamiento |
|-------|------|----------------|
| `account.account.name` | translate | `{"es_CO": "Caja", "en_US": "Cash"}` |
| `account.account.code` | company_dependent | `{"1": "110505", "2": "110505"}` |
| `res.partner.name` | translate | `{"es_CO": "Cliente", ...}` |

**Siempre usar `_field_to_sql()` nativo cuando sea posible.**
