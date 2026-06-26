# -*- coding: utf-8 -*-
"""
Handler para Estado de Flujos de Efectivo - NIC 7 Colombia
Metodo Indirecto y Metodo Directo
"""

from odoo import models, fields, api, _
from odoo.tools import SQL
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)


class CashFlowReportHandler(models.AbstractModel):
    """
    Handler para Estado de Flujos de Efectivo segun NIC 7.
    Soporta Metodo Indirecto y Metodo Directo.
    """
    _name = 'co.cash.flow.report.handler'
    _inherit = ['account.report.custom.handler', 'sql.helper.mixin', 'report.formulas.mixin']
    _description = 'Estado de Flujos de Efectivo Colombia'

    # =====================================================
    # CONFIGURACION
    # =====================================================

    def _get_custom_display_config(self):
        return {
            'css_custom_class': 'cash_flow_report_co',
            'templates': {
                'AccountReportLineName': 'account_reports.GeneralLedgerLineName',
            },
            'components': {
                'AccountReportFilters': 'libros_contables_colombia.TrialBalancePartnerFilters',
            },
        }

    def _custom_options_initializer(self, report, options, previous_options=None):
        super()._custom_options_initializer(report, options, previous_options=previous_options)

        # Opciones especificas del flujo de efectivo
        options['cash_flow_method'] = 'indirect'  # indirect o direct
        if previous_options:
            options['cash_flow_method'] = previous_options.get('cash_flow_method', 'indirect')

        # Boton para cambiar metodo
        options['buttons'].append({
            'name': _('Cambiar a Metodo Directo') if options['cash_flow_method'] == 'indirect' else _('Cambiar a Metodo Indirecto'),
            'sequence': 20,
            'action': 'action_toggle_cash_flow_method',
        })

    # =====================================================
    # GENERADOR DE LINEAS
    # =====================================================

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        lines = []

        # Obtener datos del flujo de efectivo
        cash_flow_data = self._get_cash_flow_data(report, options)

        if options.get('cash_flow_method') == 'direct':
            lines = self._generate_direct_method_lines(report, options, cash_flow_data)
        else:
            lines = self._generate_indirect_method_lines(report, options, cash_flow_data)

        return [(0, line) for line in lines]

    # =====================================================
    # METODO INDIRECTO
    # =====================================================

    def _generate_indirect_method_lines(self, report, options, data):
        """Genera lineas usando el Metodo Indirecto (NIC 7)."""
        lines = []

        # === ACTIVIDADES DE OPERACION ===
        lines.append(self._get_section_header(report, options, 'FLUJOS DE EFECTIVO DE ACTIVIDADES DE OPERACION', 'op'))

        # Utilidad Neta
        net_income = data.get('net_income', 0)
        lines.append(self._get_data_line(report, options, 'Utilidad (Perdida) Neta del Ejercicio', net_income, 'net_income', level=2))

        # Ajustes por partidas no monetarias
        lines.append(self._get_label_line(report, options, 'Ajustes por Partidas No Monetarias:', 'adj_header'))

        depreciation = data.get('depreciation', 0)
        lines.append(self._get_data_line(report, options, '(+) Depreciacion y Amortizacion', depreciation, 'depreciation', level=3))

        provisions = data.get('provisions', 0)
        lines.append(self._get_data_line(report, options, '(+) Provisiones', provisions, 'provisions', level=3))

        loss_sale = data.get('loss_on_sale', 0)
        lines.append(self._get_data_line(report, options, '(+) Perdida en Venta de Activos', loss_sale, 'loss_sale', level=3))

        gain_sale = data.get('gain_on_sale', 0)
        lines.append(self._get_data_line(report, options, '(-) Utilidad en Venta de Activos', -gain_sale, 'gain_sale', level=3))

        # Variaciones en Capital de Trabajo
        lines.append(self._get_label_line(report, options, 'Ajustes por Variaciones en Capital de Trabajo:', 'wc_header'))

        delta_receivables = data.get('delta_receivables', 0)
        lines.append(self._get_data_line(report, options, '(+/-) Cambio en Cuentas por Cobrar', -delta_receivables, 'delta_cxc', level=3))

        delta_inventory = data.get('delta_inventory', 0)
        lines.append(self._get_data_line(report, options, '(+/-) Cambio en Inventarios', -delta_inventory, 'delta_inv', level=3))

        delta_payables = data.get('delta_payables', 0)
        lines.append(self._get_data_line(report, options, '(+/-) Cambio en Cuentas por Pagar', delta_payables, 'delta_cxp', level=3))

        # Flujo Neto Operacion
        cfo = net_income + depreciation + provisions + loss_sale - gain_sale - delta_receivables - delta_inventory + delta_payables
        lines.append(self._get_subtotal_line(report, options, 'Flujo Neto de Efectivo por Actividades de Operacion', cfo, 'cfo'))

        # === ACTIVIDADES DE INVERSION ===
        lines.append(self._get_section_header(report, options, 'FLUJOS DE EFECTIVO DE ACTIVIDADES DE INVERSION', 'inv'))

        capex = data.get('capex', 0)
        lines.append(self._get_data_line(report, options, '(-) Pagos por Compra de Propiedad, Planta y Equipo', -capex, 'capex', level=2))

        asset_sales = data.get('asset_sales', 0)
        lines.append(self._get_data_line(report, options, '(+) Cobros por Venta de Activos', asset_sales, 'asset_sales', level=2))

        investment_purchases = data.get('investment_purchases', 0)
        lines.append(self._get_data_line(report, options, '(-) Pagos por Compra de Inversiones', -investment_purchases, 'inv_purchases', level=2))

        investment_sales = data.get('investment_sales', 0)
        lines.append(self._get_data_line(report, options, '(+) Cobros por Venta de Inversiones', investment_sales, 'inv_sales', level=2))

        # Flujo Neto Inversion
        cfi = -capex + asset_sales - investment_purchases + investment_sales
        lines.append(self._get_subtotal_line(report, options, 'Flujo Neto de Efectivo por Actividades de Inversion', cfi, 'cfi'))

        # === ACTIVIDADES DE FINANCIACION ===
        lines.append(self._get_section_header(report, options, 'FLUJOS DE EFECTIVO DE ACTIVIDADES DE FINANCIACION', 'fin'))

        new_debt = data.get('new_debt', 0)
        lines.append(self._get_data_line(report, options, '(+) Cobros por Emision de Prestamos', new_debt, 'new_debt', level=2))

        debt_repayment = data.get('debt_repayment', 0)
        lines.append(self._get_data_line(report, options, '(-) Pagos por Amortizacion de Prestamos', -debt_repayment, 'debt_repay', level=2))

        equity_issuance = data.get('equity_issuance', 0)
        lines.append(self._get_data_line(report, options, '(+) Cobros por Emision de Acciones', equity_issuance, 'equity_issue', level=2))

        dividends = data.get('dividends_paid', 0)
        lines.append(self._get_data_line(report, options, '(-) Pagos de Dividendos', -dividends, 'dividends', level=2))

        interest_paid = data.get('interest_paid', 0)
        lines.append(self._get_data_line(report, options, '(-) Intereses Pagados', -interest_paid, 'interest', level=2))

        # Flujo Neto Financiacion
        cff = new_debt - debt_repayment + equity_issuance - dividends - interest_paid
        lines.append(self._get_subtotal_line(report, options, 'Flujo Neto de Efectivo por Actividades de Financiacion', cff, 'cff'))

        # === RESUMEN ===
        net_change = cfo + cfi + cff
        lines.append(self._get_total_line(report, options, 'Aumento/(Disminucion) Neto de Efectivo', net_change, 'net_change'))

        beginning_cash = data.get('beginning_cash', 0)
        lines.append(self._get_data_line(report, options, '(+) Efectivo al Inicio del Periodo', beginning_cash, 'begin_cash', level=1))

        ending_cash = beginning_cash + net_change
        lines.append(self._get_total_line(report, options, '(=) Efectivo al Final del Periodo', ending_cash, 'end_cash'))

        return lines

    # =====================================================
    # METODO DIRECTO
    # =====================================================

    def _generate_direct_method_lines(self, report, options, data):
        """Genera lineas usando el Metodo Directo (NIC 7)."""
        lines = []

        # === ACTIVIDADES DE OPERACION ===
        lines.append(self._get_section_header(report, options, 'FLUJOS DE EFECTIVO DE ACTIVIDADES DE OPERACION', 'op'))

        collections = data.get('collections_from_customers', 0)
        lines.append(self._get_data_line(report, options, '(+) Cobros a Clientes', collections, 'collections', level=2))

        payments_suppliers = data.get('payments_to_suppliers', 0)
        lines.append(self._get_data_line(report, options, '(-) Pagos a Proveedores', -payments_suppliers, 'pay_suppliers', level=2))

        payments_employees = data.get('payments_to_employees', 0)
        lines.append(self._get_data_line(report, options, '(-) Pagos a Empleados', -payments_employees, 'pay_employees', level=2))

        payments_expenses = data.get('payments_operating_expenses', 0)
        lines.append(self._get_data_line(report, options, '(-) Pagos de Gastos Operativos', -payments_expenses, 'pay_expenses', level=2))

        payments_taxes = data.get('payments_taxes', 0)
        lines.append(self._get_data_line(report, options, '(-) Pagos de Impuestos', -payments_taxes, 'pay_taxes', level=2))

        cfo = collections - payments_suppliers - payments_employees - payments_expenses - payments_taxes
        lines.append(self._get_subtotal_line(report, options, 'Flujo Neto de Efectivo por Actividades de Operacion', cfo, 'cfo'))

        # Las secciones de Inversion y Financiacion son iguales al metodo indirecto
        # ... (similar structure)

        return lines

    # =====================================================
    # CONSULTAS SQL
    # =====================================================

    def _get_cash_flow_data(self, report, options):
        """Obtiene todos los datos necesarios para el flujo de efectivo."""
        date_from = options.get('date', {}).get('date_from')
        date_to = options.get('date', {}).get('date_to')

        data = {}

        # Saldo inicial de efectivo (cuentas clase 11)
        data['beginning_cash'] = self._get_account_balance_at_date(
            report, options, ['11'], date_from, before=True
        )

        # Utilidad Neta (Ingresos - Costos - Gastos)
        income = self._get_account_balance_range(report, options, ['4'], date_from, date_to)
        expenses = self._get_account_balance_range(report, options, ['5', '6'], date_from, date_to)
        data['net_income'] = abs(income) - expenses

        # Depreciacion y Amortizacion (cuentas 5195, 5295)
        data['depreciation'] = self._get_account_balance_range(
            report, options, ['5195', '5295'], date_from, date_to
        )

        # Provisiones
        data['provisions'] = self._get_account_balance_range(
            report, options, ['5199', '5299'], date_from, date_to
        )

        # Variaciones en Capital de Trabajo
        data['delta_receivables'] = self._get_account_balance_change(
            report, options, ['13'], date_from, date_to
        )
        data['delta_inventory'] = self._get_account_balance_change(
            report, options, ['14'], date_from, date_to
        )
        data['delta_payables'] = self._get_account_balance_change(
            report, options, ['22'], date_from, date_to
        )

        # Actividades de Inversion
        data['capex'] = self._get_account_balance_change(
            report, options, ['15'], date_from, date_to
        )
        data['investment_purchases'] = self._get_account_balance_change(
            report, options, ['12'], date_from, date_to
        )

        # Actividades de Financiacion
        data['new_debt'] = self._get_account_balance_change(
            report, options, ['21', '23'], date_from, date_to
        )
        data['equity_issuance'] = self._get_account_balance_change(
            report, options, ['31'], date_from, date_to
        )
        data['interest_paid'] = self._get_account_balance_range(
            report, options, ['5305'], date_from, date_to
        )

        # Para metodo directo
        data['collections_from_customers'] = self._get_cash_collections(
            report, options, date_from, date_to
        )
        data['payments_to_suppliers'] = self._get_cash_payments(
            report, options, ['22'], date_from, date_to
        )
        data['payments_to_employees'] = self._get_account_balance_range(
            report, options, ['51'], date_from, date_to
        )
        data['payments_operating_expenses'] = self._get_account_balance_range(
            report, options, ['52', '53'], date_from, date_to
        )
        data['payments_taxes'] = self._get_account_balance_range(
            report, options, ['54'], date_from, date_to
        )

        return data

    def _get_account_balance_at_date(self, report, options, account_prefixes, date, before=False):
        """Obtiene saldo de cuentas a una fecha especifica."""
        company_id = self._get_company_id_for_sql()
        prefix_conditions = " OR ".join([
            f"COALESCE(aa.code_store->>'{company_id}', '') LIKE '{p}%'"
            for p in account_prefixes
        ])

        date_condition = f"aml.date < '{date}'" if before else f"aml.date <= '{date}'"

        query = f"""
            SELECT COALESCE(SUM(aml.balance), 0) as balance
            FROM account_move_line aml
            JOIN account_move am ON am.id = aml.move_id
            JOIN account_account aa ON aa.id = aml.account_id
            WHERE am.state = 'posted'
              AND {date_condition}
              AND ({prefix_conditions})
        """
        self._cr.execute(query)
        result = self._cr.fetchone()
        return result[0] if result else 0.0

    def _get_account_balance_range(self, report, options, account_prefixes, date_from, date_to):
        """Obtiene saldo de cuentas en un rango de fechas."""
        company_id = self._get_company_id_for_sql()
        prefix_conditions = " OR ".join([
            f"COALESCE(aa.code_store->>'{company_id}', '') LIKE '{p}%'"
            for p in account_prefixes
        ])

        query = f"""
            SELECT COALESCE(SUM(aml.balance), 0) as balance
            FROM account_move_line aml
            JOIN account_move am ON am.id = aml.move_id
            JOIN account_account aa ON aa.id = aml.account_id
            WHERE am.state = 'posted'
              AND aml.date >= '{date_from}'
              AND aml.date <= '{date_to}'
              AND ({prefix_conditions})
        """
        self._cr.execute(query)
        result = self._cr.fetchone()
        return result[0] if result else 0.0

    def _get_account_balance_change(self, report, options, account_prefixes, date_from, date_to):
        """Obtiene cambio en saldo de cuentas entre dos fechas."""
        beginning = self._get_account_balance_at_date(report, options, account_prefixes, date_from, before=True)
        ending = self._get_account_balance_at_date(report, options, account_prefixes, date_to, before=False)
        return ending - beginning

    def _get_cash_collections(self, report, options, date_from, date_to):
        """Obtiene cobros en efectivo del periodo."""
        # Ventas + Reduccion en CxC
        sales = self._get_account_balance_range(report, options, ['41'], date_from, date_to)
        delta_cxc = self._get_account_balance_change(report, options, ['13'], date_from, date_to)
        return abs(sales) - delta_cxc

    def _get_cash_payments(self, report, options, account_prefixes, date_from, date_to):
        """Obtiene pagos en efectivo del periodo."""
        return abs(self._get_account_balance_range(report, options, account_prefixes, date_from, date_to))

    # =====================================================
    # CONSTRUCCION DE LINEAS
    # =====================================================

    def _get_section_header(self, report, options, name, tag):
        return {
            'id': report._get_generic_line_id(None, None, markup=f'header_{tag}'),
            'name': name,
            'level': 0,
            'unfoldable': False,
            'columns': [{'name': ''} for _ in options['columns']],
            'class': 'o_account_reports_level0 font-weight-bold',
        }

    def _get_label_line(self, report, options, name, tag):
        return {
            'id': report._get_generic_line_id(None, None, markup=f'label_{tag}'),
            'name': name,
            'level': 2,
            'unfoldable': False,
            'columns': [{'name': ''} for _ in options['columns']],
        }

    def _get_data_line(self, report, options, name, value, tag, level=2):
        cols = []
        for col in options['columns']:
            if col['expression_label'] == 'balance':
                cols.append(report._build_column_dict(value, col, options=options))
            else:
                cols.append({'name': ''})

        return {
            'id': report._get_generic_line_id(None, None, markup=tag),
            'name': name,
            'level': level,
            'unfoldable': False,
            'columns': cols,
        }

    def _get_subtotal_line(self, report, options, name, value, tag):
        cols = []
        for col in options['columns']:
            if col['expression_label'] == 'balance':
                cols.append(report._build_column_dict(value, col, options=options))
            else:
                cols.append({'name': ''})

        return {
            'id': report._get_generic_line_id(None, None, markup=f'subtotal_{tag}'),
            'name': name,
            'level': 1,
            'unfoldable': False,
            'columns': cols,
            'class': 'o_account_reports_level1 font-weight-bold',
        }

    def _get_total_line(self, report, options, name, value, tag):
        cols = []
        for col in options['columns']:
            if col['expression_label'] == 'balance':
                cols.append(report._build_column_dict(value, col, options=options))
            else:
                cols.append({'name': ''})

        return {
            'id': report._get_generic_line_id(None, None, markup=f'total_{tag}'),
            'name': name,
            'level': 0,
            'unfoldable': False,
            'columns': cols,
            'class': 'o_account_reports_level0 font-weight-bold o_account_reports_totals_below_sections',
        }
