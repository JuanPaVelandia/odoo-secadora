# Patron Nativo de Odoo 18 para Reportes

## Resumen

En Odoo 18, el modulo `account_reports` usa un patron especifico para handlers de reportes
con soporte para campos JSONB (company-dependent y translatable).

## Patrones Clave

### 1. Estructura del Handler

```python
from odoo import models, _
from odoo.tools import SQL, Query

class MiCustomHandler(models.AbstractModel):
    _name = 'mi.custom.report.handler'
    _inherit = 'account.report.custom.handler'
    _description = 'Mi Reporte Custom'

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        """Genera las lineas del reporte."""
        lines = []
        # ... logica del reporte
        return [(0, line) for line in lines]

    def _custom_options_initializer(self, report, options, previous_options):
        """Inicializa opciones custom del reporte."""
        super()._custom_options_initializer(report, options, previous_options=previous_options)
        # ... configurar opciones
```

### 2. Usando Query con _field_to_sql (Patron Nativo)

```python
def _get_aml_values(self, report, options, expanded_account_ids, offset=0, limit=None):
    """Consulta usando patron nativo de Odoo 18."""
    queries = []

    for column_group_key, group_options in report._split_options_per_column_group(options).items():
        # Crear Query object
        query = report._get_report_query(group_options, 'strict_range', domain=[...])

        # JOIN con tabla account_account
        account_alias = query.join(
            lhs_alias='account_move_line',
            lhs_column='account_id',
            rhs_table='account_account',
            rhs_column='id',
            link='account_id'
        )

        # Obtener campos usando _field_to_sql (maneja JSONB automaticamente)
        account_code = self.env['account.account']._field_to_sql(account_alias, 'code', query)
        account_name = self.env['account.account']._field_to_sql(account_alias, 'name')

        # JOIN con journal
        journal_alias = 'journal'
        journal_name = self.env['account.journal']._field_to_sql(journal_alias, 'name')

        # Construir query
        queries.append(SQL(
            '''
            SELECT
                account_move_line.id,
                account_move_line.date,
                %(account_code)s AS account_code,
                %(account_name)s AS account_name,
                %(debit_select)s AS debit,
                %(credit_select)s AS credit,
                %(balance_select)s AS balance,
                %(column_group_key)s AS column_group_key
            FROM %(table_references)s
            LEFT JOIN account_journal journal ON journal.id = account_move_line.journal_id
            %(currency_table_join)s
            WHERE %(search_condition)s
            ''',
            account_code=account_code,
            account_name=account_name,
            column_group_key=column_group_key,
            table_references=query.from_clause,
            debit_select=report._currency_table_apply_rate(SQL("account_move_line.debit")),
            credit_select=report._currency_table_apply_rate(SQL("account_move_line.credit")),
            balance_select=report._currency_table_apply_rate(SQL("account_move_line.balance")),
            currency_table_join=report._currency_table_aml_join(group_options),
            search_condition=query.where_clause,
        ))

    return SQL(" UNION ALL ").join(queries)
```

### 3. Alternativa Manual (Compatible)

Si no puedes usar Query object, usa expresiones JSONB manuales:

```python
def _get_sql_expressions(self):
    """Genera expresiones SQL para campos JSONB."""
    company_id = str(self.env.company.root_id.id or self.env.company.id)
    lang = self.env.user.lang or 'en_US'

    # Codigo de cuenta (company-dependent)
    account_code = f"""COALESCE(
        account.code_store->>'{company_id}',
        (SELECT value FROM jsonb_each_text(account.code_store) LIMIT 1),
        ''
    )"""

    # Nombre (translatable)
    account_name = f"""COALESCE(
        account.name->>'{lang}',
        account.name->>'en_US',
        (SELECT value FROM jsonb_each_text(account.name) LIMIT 1),
        ''
    )"""

    return account_code, account_name
```

### 4. Metodos Importantes del Report

```python
# Dividir opciones por grupo de columnas
options_by_column_group = report._split_options_per_column_group(options)

# Obtener query base del reporte
query = report._get_report_query(options, 'strict_range', domain=[...])

# Aplicar tasa de cambio
balance = report._currency_table_apply_rate(SQL("account_move_line.balance"))

# JOIN con tabla de moneda
currency_join = report._currency_table_aml_join(options)

# Construir diccionario de columna
col_dict = report._build_column_dict(value, column, options=options)

# Generar ID de linea
line_id = report._get_generic_line_id('account.account', account.id, markup='tag')
```

### 5. Extender un Reporte Existente

```python
class ExtendedGeneralLedger(models.AbstractModel):
    _name = 'account.general.ledger.report.handler.extended'
    _inherit = 'account.general.ledger.report.handler'
    _description = 'General Ledger Extendido'

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        # Llamar al metodo original
        lines = super()._dynamic_lines_generator(report, options, all_column_groups_expression_totals, warnings)

        # Agregar lineas adicionales
        lines.append((0, self._get_custom_summary_line(report, options)))

        return lines

    def _get_custom_summary_line(self, report, options):
        return {
            'id': report._get_generic_line_id(None, None, markup='custom_summary'),
            'name': _('Resumen Personalizado'),
            'level': 1,
            'columns': [...],
        }
```

## Mixins Disponibles

### sql.helper.mixin

```python
class MiHandler(models.AbstractModel):
    _inherit = ['account.report.custom.handler', 'sql.helper.mixin']

    def mi_metodo(self):
        # Metodo preferido con Query
        account_code = self._get_account_field_sql('account_alias', 'code', query)

        # Fallback sin Query
        account_code = self._sql_account_code('account')
```

### financial.indicators.mixin

```python
class MiHandler(models.AbstractModel):
    _inherit = ['account.report.custom.handler', 'financial.indicators.mixin']

    def calcular_indicadores(self, data):
        liquidity = self.calculate_liquidity_ratio(
            current_assets=data['activo_corriente'],
            current_liabilities=data['pasivo_corriente']
        )
        return self.calculate_all_ratios(balance_data, income_data)
```

### report.formulas.mixin

```python
class MiHandler(models.AbstractModel):
    _inherit = ['account.report.custom.handler', 'report.formulas.mixin']

    def calcular_secciones(self, report_data):
        total_assets = self.compute_total_assets(report_data)
        gross_profit = self.compute_gross_profit(report_data)
```

## Definicion XML del Reporte

```xml
<record id="mi_reporte_financiero" model="account.report">
    <field name="name">Mi Reporte Financiero</field>
    <field name="root_report_id" ref="account_reports.balance_sheet"/>
    <field name="custom_handler_model_id" ref="model_mi_custom_report_handler"/>
    <field name="column_ids">
        <record id="mi_reporte_col_name" model="account.report.column">
            <field name="name">Nombre</field>
            <field name="expression_label">name</field>
            <field name="figure_type">string</field>
        </record>
        <record id="mi_reporte_col_balance" model="account.report.column">
            <field name="name">Balance</field>
            <field name="expression_label">balance</field>
            <field name="figure_type">monetary</field>
        </record>
    </field>
</record>
```
