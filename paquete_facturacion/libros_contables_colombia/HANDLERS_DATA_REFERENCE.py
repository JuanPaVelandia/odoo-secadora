# -*- coding: utf-8 -*-
"""
=====================================================
REFERENCIA DE HANDLERS Y DATOS DE REPORTES COLOMBIA
=====================================================

Este archivo documenta la estructura de datos y handlers
para extender los reportes financieros colombianos.
"""

# =====================================================
# ESTRUCTURA DE DATOS DE REPORTES (XML)
# =====================================================

"""
MODELO: co.report.config.base (Configuracion de Reporte)
=========================================================
Campos principales:
- name: Nombre del reporte
- code: Codigo unico (ej: CO_BAL_RESUMEN)
- report_type: Tipo (balance_sheet, profit_loss, cash_flow, trial_balance, etc.)
- sequence: Orden en menus
- filter_date_range: Habilitar filtro de fechas
- filter_period_comparison: Habilitar comparacion de periodos
- custom_handler: Handler personalizado (standard, custom_name)
- create_menu_on_save: Crear entrada de menu automaticamente

Ejemplo XML:
<record id="report_balance_detallado" model="co.report.config.base">
    <field name="name">Balance General - Detallado</field>
    <field name="code">CO_BAL_DETALLADO</field>
    <field name="report_type">balance_sheet</field>
    <field name="sequence">110</field>
    <field name="filter_date_range" eval="True"/>
    <field name="custom_handler">standard</field>
</record>


MODELO: co.report.column (Columnas del Reporte)
===============================================
Campos principales:
- report_id: Referencia al reporte
- sequence: Orden de la columna
- name: Nombre visible
- expression_label: Etiqueta para mapeo de datos
  * account_code: Codigo de cuenta
  * account_name: Nombre de cuenta
  * partner_name: Nombre de tercero
  * balance: Saldo
  * debit: Debito
  * credit: Credito
  * initial_balance: Saldo inicial
  * final_balance: Saldo final
- figure_type: Tipo de dato (string, monetary, percentage, integer, date)
- use_sql_engine: Usar motor SQL optimizado
- comparison_period_type: Tipo de comparacion (previous_year, previous_month)
- show_comparison_variance: Mostrar variacion absoluta
- show_comparison_percent: Mostrar variacion porcentual

Ejemplo XML:
<record id="col_bal_det_saldo" model="co.report.column">
    <field name="report_id" ref="report_balance_detallado"/>
    <field name="sequence">30</field>
    <field name="name">Saldo</field>
    <field name="expression_label">balance</field>
    <field name="figure_type">monetary</field>
    <field name="use_sql_engine" eval="True"/>
</record>


MODELO: co.report.line (Lineas del Reporte)
===========================================
Campos principales:
- report_id: Referencia al reporte
- parent_id: Linea padre (para jerarquia)
- sequence: Orden
- name: Nombre visible
- code: Codigo interno
- account_codes_formula: Prefijos PUC separados por coma
  * "1" = Todas las cuentas de activo
  * "11,12,13,14" = Activo corriente
  * "2" = Todas las cuentas de pasivo
  * "3" = Patrimonio
  * "4" = Ingresos
  * "5" = Gastos
  * "6" = Costos
- calculation_type: Tipo de calculo
  * accounts: Suma de cuentas
  * formula: Formula personalizada
  * subtotal: Subtotal de lineas hijas
- style_class: Estilo CSS (total, subtotal, normal, highlight)
- foldable: Permite expandir/colapsar
- groupby: Agrupacion (account_id, partner_id, journal_id)
- enable_drill_down: Permite desglose

Ejemplo XML:
<record id="line_bal_det_activo_cte" model="co.report.line">
    <field name="report_id" ref="report_balance_detallado"/>
    <field name="parent_id" ref="line_bal_det_activo"/>
    <field name="sequence">110</field>
    <field name="name">Activo Corriente</field>
    <field name="code">ACT_CTE</field>
    <field name="account_codes_formula">11,12,13,14,19</field>
    <field name="calculation_type">accounts</field>
    <field name="style_class">subtotal</field>
    <field name="foldable" eval="True"/>
    <field name="groupby">account_id</field>
</record>
"""

# =====================================================
# ESTRUCTURA DE HANDLERS
# =====================================================

"""
PATRON BASICO DE HANDLER
========================
"""

from odoo import models, fields, api, _
from odoo.tools import SQL, Query


class BaseReportHandler(models.AbstractModel):
    """
    Handler base para reportes financieros Colombia.
    Hereda de account.report.custom.handler y mixins utiles.
    """
    _name = 'base.report.handler.template'
    _inherit = ['account.report.custom.handler', 'sql.helper.mixin', 'financial.indicators.mixin']
    _description = 'Template de Handler para Reportes'

    # -------------------------------------------------
    # CONFIGURACION DE DISPLAY
    # -------------------------------------------------
    def _get_custom_display_config(self):
        """
        Configura componentes visuales del reporte.
        Retorna dict con configuracion de templates.
        """
        return {
            'css_custom_class': 'mi_reporte_custom',  # Clase CSS
            'templates': {
                'AccountReportLineName': 'account_reports.GeneralLedgerLineName',
            },
        }

    # -------------------------------------------------
    # INICIALIZACION DE OPCIONES
    # -------------------------------------------------
    def _custom_options_initializer(self, report, options, previous_options=None):
        """
        Inicializa opciones personalizadas del reporte.
        Llamado al cargar el reporte.
        """
        super()._custom_options_initializer(report, options, previous_options=previous_options)

        # Opciones de filtro
        options['show_details'] = True
        options['group_by_partner'] = False

        # Restaurar opciones anteriores
        if previous_options:
            for key in ['show_details', 'group_by_partner']:
                if key in previous_options:
                    options[key] = previous_options[key]

        # Agregar botones personalizados
        options['buttons'].append({
            'name': _('Exportar Excel'),
            'sequence': 30,
            'action': 'export_to_xlsx',
            'file_export_type': 'xlsx',
        })

    # -------------------------------------------------
    # GENERADOR DE LINEAS DINAMICAS
    # -------------------------------------------------
    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        """
        Genera las lineas del reporte.
        Este es el metodo principal que construye el reporte.

        Args:
            report: Objeto account.report
            options: Opciones del reporte (fechas, filtros, etc.)
            all_column_groups_expression_totals: Totales por grupo de columnas
            warnings: Lista para agregar advertencias

        Returns:
            List of tuples: [(sequence, line_dict), ...]
        """
        lines = []

        try:
            # 1. Obtener datos con consulta SQL
            report_data = self._get_report_data(report, options)

            if not report_data:
                return [(0, self._get_no_data_line(report, options))]

            # 2. Construir lineas del reporte
            # Linea de encabezado
            lines.append(self._get_header_line(report, options))

            # Lineas de datos
            total_balance = 0
            for row in report_data:
                lines.append(self._get_data_line(report, options, row))
                total_balance += row.get('balance', 0)

            # Linea de total
            lines.append(self._get_total_line(report, options, total_balance))

        except Exception as e:
            lines = [(0, self._get_error_line(report, options, str(e)))]

        return [(0, line) for line in lines]

    # -------------------------------------------------
    # CONSULTAS SQL
    # -------------------------------------------------
    def _get_report_data(self, report, options):
        """
        Obtiene datos del reporte usando SQL.
        Usa el patron nativo de Odoo 18.
        """
        queries = []

        # Obtener expresiones SQL para campos JSONB
        company_id = self._get_company_id_for_sql()
        lang = self.env.user.lang or 'es_CO'

        # Expresion para codigo de cuenta
        account_code = f"""COALESCE(
            account.code_store->>'{company_id}',
            (SELECT value FROM jsonb_each_text(account.code_store) LIMIT 1),
            ''
        )"""

        # Expresion para nombre de cuenta
        account_name = f"""COALESCE(
            account.name->>'{lang}',
            account.name->>'en_US',
            (SELECT value FROM jsonb_each_text(account.name) LIMIT 1),
            ''
        )"""

        for column_group_key, group_options in report._split_options_per_column_group(options).items():
            # Obtener query base del reporte
            query = report._get_report_query(group_options, 'strict_range')

            queries.append(SQL(
                """
                SELECT
                    account_move_line.account_id,
                    %(account_code)s AS account_code,
                    %(account_name)s AS account_name,
                    SUM(%(balance_select)s) AS balance,
                    SUM(%(debit_select)s) AS debit,
                    SUM(%(credit_select)s) AS credit,
                    %(column_group_key)s AS column_group_key
                FROM %(table_references)s
                JOIN account_account account ON account.id = account_move_line.account_id
                %(currency_table_join)s
                WHERE %(search_condition)s
                GROUP BY account_move_line.account_id, account.code_store, account.name
                ORDER BY %(account_code)s
                """,
                account_code=SQL(account_code),
                account_name=SQL(account_name),
                column_group_key=column_group_key,
                table_references=query.from_clause,
                balance_select=report._currency_table_apply_rate(SQL("account_move_line.balance")),
                debit_select=report._currency_table_apply_rate(SQL("account_move_line.debit")),
                credit_select=report._currency_table_apply_rate(SQL("account_move_line.credit")),
                currency_table_join=report._currency_table_aml_join(group_options),
                search_condition=query.where_clause,
            ))

        full_query = SQL(" UNION ALL ").join(queries)
        self._cr.execute(full_query)
        return self._cr.dictfetchall()

    # -------------------------------------------------
    # CONSTRUCCION DE LINEAS
    # -------------------------------------------------
    def _get_header_line(self, report, options):
        """Construye linea de encabezado."""
        return {
            'id': report._get_generic_line_id(None, None, markup='header'),
            'name': _('REPORTE FINANCIERO'),
            'level': 0,
            'unfoldable': False,
            'columns': [{'name': ''} for _ in options['columns']],
            'class': 'o_account_reports_totals_below_sections',
        }

    def _get_data_line(self, report, options, row):
        """Construye linea de datos."""
        cols = []
        for col in options['columns']:
            lbl = col['expression_label']
            val = None

            if lbl == 'account_code':
                val = row.get('account_code', '')
            elif lbl == 'account_name':
                val = row.get('account_name', '')
            elif lbl == 'balance':
                val = row.get('balance', 0)
            elif lbl == 'debit':
                val = row.get('debit', 0)
            elif lbl == 'credit':
                val = row.get('credit', 0)

            cols.append(report._build_column_dict(val, col, options=options))

        return {
            'id': report._get_generic_line_id('account.account', row.get('account_id')),
            'name': f"{row.get('account_code', '')} - {row.get('account_name', '')}",
            'level': 2,
            'unfoldable': False,
            'columns': cols,
        }

    def _get_total_line(self, report, options, total):
        """Construye linea de total."""
        cols = []
        for col in options['columns']:
            lbl = col['expression_label']
            val = total if lbl == 'balance' else None
            cols.append(report._build_column_dict(val, col, options=options))

        return {
            'id': report._get_generic_line_id(None, None, markup='total'),
            'name': _('TOTAL'),
            'level': 0,
            'unfoldable': False,
            'columns': cols,
            'class': 'o_account_reports_totals_below_sections font-weight-bold',
        }

    def _get_no_data_line(self, report, options):
        """Linea cuando no hay datos."""
        return {
            'id': report._get_generic_line_id(None, None, markup='no_data'),
            'name': _('No hay datos para mostrar'),
            'level': 1,
            'unfoldable': False,
            'columns': [{'name': ''} for _ in options['columns']],
        }

    def _get_error_line(self, report, options, error_msg):
        """Linea de error."""
        return {
            'id': report._get_generic_line_id(None, None, markup='error'),
            'name': _('Error: %s') % error_msg,
            'level': 1,
            'unfoldable': False,
            'columns': [{'name': ''} for _ in options['columns']],
            'class': 'text-danger',
        }


# =====================================================
# EJEMPLOS DE EXTENSION
# =====================================================

class BalanceSheetExtendedHandler(models.AbstractModel):
    """
    Ejemplo: Extender el Balance General nativo de Odoo.
    """
    _name = 'account.balance.sheet.extended.handler'
    _inherit = 'account.balance.sheet.report.handler'
    _description = 'Balance Sheet Colombia Extendido'

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        """Extiende las lineas del balance nativo."""
        # Llamar al metodo original
        lines = super()._dynamic_lines_generator(
            report, options, all_column_groups_expression_totals, warnings
        )

        # Agregar lineas adicionales
        lines.extend([
            (0, self._get_ratios_section(report, options)),
        ])

        return lines

    def _get_ratios_section(self, report, options):
        """Agrega seccion de ratios financieros."""
        return {
            'id': report._get_generic_line_id(None, None, markup='ratios'),
            'name': _('INDICADORES FINANCIEROS'),
            'level': 0,
            'unfoldable': True,
            'unfolded': False,
            'columns': [{'name': ''} for _ in options['columns']],
        }


class ProfitLossColombiaHandler(models.AbstractModel):
    """
    Ejemplo: Handler para Estado de Resultados Colombia.
    """
    _name = 'profit.loss.colombia.handler'
    _inherit = ['account.report.custom.handler', 'sql.helper.mixin', 'report.formulas.mixin']
    _description = 'Estado de Resultados Colombia'

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        """Genera lineas del P&L Colombia."""
        lines = []
        data = self._get_pl_data(report, options)

        # Estructura PUC Colombia
        sections = [
            ('4', 'INGRESOS OPERACIONALES', 'income'),
            ('41', '  Ventas', 'detail'),
            ('42', '  Otros Ingresos', 'detail'),
            ('6', 'COSTO DE VENTAS', 'expense'),
            ('51', 'GASTOS DE ADMINISTRACION', 'expense'),
            ('52', 'GASTOS DE VENTAS', 'expense'),
            ('53', 'GASTOS FINANCIEROS', 'expense'),
        ]

        for code, name, section_type in sections:
            balance = self.compute_balance_section([code], data)
            lines.append((0, {
                'id': report._get_generic_line_id(None, None, markup=code),
                'name': name,
                'level': 1 if code.startswith('4') or code.startswith('5') or code.startswith('6') else 2,
                'columns': self._build_pl_columns(report, options, balance, section_type),
            }))

        # Utilidad Neta
        net_income = self.compute_net_income(data)
        lines.append((0, {
            'id': report._get_generic_line_id(None, None, markup='net_income'),
            'name': 'UTILIDAD NETA',
            'level': 0,
            'columns': self._build_pl_columns(report, options, net_income, 'total'),
            'class': 'o_account_reports_totals_below_sections font-weight-bold',
        }))

        return lines

    def _get_pl_data(self, report, options):
        """Obtiene datos del P&L."""
        # Similar a _get_report_data pero filtrado para P&L
        pass

    def _build_pl_columns(self, report, options, balance, section_type):
        """Construye columnas del P&L."""
        cols = []
        for col in options['columns']:
            if col['expression_label'] == 'balance':
                # Ajustar signo segun tipo de seccion
                if section_type in ('income', 'detail'):
                    val = abs(balance) if balance < 0 else balance
                else:
                    val = balance
            else:
                val = None
            cols.append(report._build_column_dict(val, col, options=options))
        return cols


# =====================================================
# CODIGOS PUC COLOMBIA REFERENCIA
# =====================================================

PUC_CODES = {
    # ACTIVOS (1)
    '1': 'ACTIVO',
    '11': 'Disponible (Efectivo)',
    '1105': 'Caja',
    '1110': 'Bancos',
    '12': 'Inversiones',
    '13': 'Deudores (Cuentas por Cobrar)',
    '1305': 'Clientes',
    '14': 'Inventarios',
    '15': 'Propiedades, Planta y Equipo',
    '16': 'Intangibles',
    '17': 'Diferidos',

    # PASIVOS (2)
    '2': 'PASIVO',
    '21': 'Obligaciones Financieras',
    '22': 'Proveedores',
    '23': 'Cuentas por Pagar',
    '24': 'Impuestos por Pagar',
    '25': 'Obligaciones Laborales',

    # PATRIMONIO (3)
    '3': 'PATRIMONIO',
    '31': 'Capital Social',
    '32': 'Superavit de Capital',
    '33': 'Reservas',
    '34': 'Revalorizacion del Patrimonio',
    '36': 'Resultados del Ejercicio',
    '37': 'Resultados de Ejercicios Anteriores',

    # INGRESOS (4)
    '4': 'INGRESOS',
    '41': 'Ingresos Operacionales',
    '42': 'Ingresos No Operacionales',

    # GASTOS (5)
    '5': 'GASTOS',
    '51': 'Gastos de Administracion',
    '52': 'Gastos de Ventas',
    '53': 'Gastos No Operacionales',
    '5305': 'Gastos Financieros',
    '54': 'Impuesto de Renta',

    # COSTOS (6)
    '6': 'COSTO DE VENTAS',
    '61': 'Costo de Ventas',
}
