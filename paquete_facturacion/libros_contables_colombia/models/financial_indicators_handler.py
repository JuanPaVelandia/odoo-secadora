# -*- coding: utf-8 -*-
"""
Handler para Indicadores de Rendimiento Financiero (KPIs) - Colombia
Incluye Liquidez, Solvencia, Rentabilidad y Eficiencia
"""

from odoo import models, fields, api, _
from odoo.tools import SQL
import logging

_logger = logging.getLogger(__name__)


class FinancialIndicatorsReportHandler(models.AbstractModel):
    """
    Handler para Indicadores Financieros Colombia.
    Calcula KPIs de Liquidez, Solvencia, Rentabilidad y Eficiencia.
    """
    _name = 'co.financial.indicators.report.handler'
    _inherit = ['account.report.custom.handler', 'sql.helper.mixin', 'financial.indicators.mixin']
    _description = 'Indicadores Financieros Colombia'

    # =====================================================
    # CONFIGURACION
    # =====================================================

    def _get_custom_display_config(self):
        return {
            'css_custom_class': 'financial_indicators_report_co',
            'templates': {
                'AccountReportLineName': 'account_reports.GeneralLedgerLineName',
            },
            'components': {
                'AccountReportFilters': 'libros_contables_colombia.TrialBalancePartnerFilters',
            },
        }

    def _custom_options_initializer(self, report, options, previous_options=None):
        super()._custom_options_initializer(report, options, previous_options=previous_options)

        options['show_formulas'] = True
        options['show_targets'] = True
        options['show_interpretation'] = True

        if previous_options:
            for key in ['show_formulas', 'show_targets', 'show_interpretation']:
                if key in previous_options:
                    options[key] = previous_options[key]

    # =====================================================
    # GENERADOR DE LINEAS
    # =====================================================

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        lines = []

        # Obtener datos base del balance y P&L
        balance_data = self._get_balance_data(report, options)
        income_data = self._get_income_data(report, options)

        # Calcular todos los indicadores
        indicators = self._calculate_all_indicators(balance_data, income_data)

        # === INDICADORES DE LIQUIDEZ ===
        lines.append(self._get_section_header(report, options, 'INDICADORES DE LIQUIDEZ', 'liq'))

        lines.append(self._get_indicator_line(
            report, options,
            name='Razon Corriente',
            value=indicators['liquidity']['current_ratio'],
            target='> 1.5',
            formula='AC / PC',
            interpretation='Mayor a 1 = capacidad de pago',
            tag='rc'
        ))

        lines.append(self._get_indicator_line(
            report, options,
            name='Prueba Acida',
            value=indicators['liquidity']['acid_test'],
            target='> 1.0',
            formula='(AC - Inv) / PC',
            interpretation='Mayor a 0.7 es aceptable',
            tag='pa'
        ))

        lines.append(self._get_indicator_line(
            report, options,
            name='Capital de Trabajo',
            value=indicators['liquidity']['working_capital'],
            target='> 0',
            formula='AC - PC',
            interpretation='Debe ser positivo',
            tag='ct',
            is_monetary=True
        ))

        lines.append(self._get_indicator_line(
            report, options,
            name='Razon de Efectivo',
            value=indicators['liquidity']['cash_ratio'],
            target='> 0.2',
            formula='Efectivo / PC',
            interpretation='Pago inmediato',
            tag='re'
        ))

        # === INDICADORES DE SOLVENCIA ===
        lines.append(self._get_section_header(report, options, 'INDICADORES DE SOLVENCIA', 'sol'))

        lines.append(self._get_indicator_line(
            report, options,
            name='Endeudamiento Total (%)',
            value=indicators['leverage']['debt_ratio'],
            target='< 60%',
            formula='PT / AT x 100',
            interpretation='Menor 60% saludable',
            tag='end',
            is_percentage=True
        ))

        lines.append(self._get_indicator_line(
            report, options,
            name='Apalancamiento Financiero',
            value=indicators['leverage']['financial_leverage'],
            target='< 2.5',
            formula='AT / Patrimonio',
            interpretation='Multiplicador capital',
            tag='apal'
        ))

        lines.append(self._get_indicator_line(
            report, options,
            name='Autonomia Financiera (%)',
            value=indicators['leverage']['equity_ratio'],
            target='> 40%',
            formula='Patrimonio / AT x 100',
            interpretation='Mayor 40% independencia',
            tag='aut',
            is_percentage=True
        ))

        # === INDICADORES DE RENTABILIDAD ===
        lines.append(self._get_section_header(report, options, 'INDICADORES DE RENTABILIDAD', 'rent'))

        lines.append(self._get_indicator_line(
            report, options,
            name='Margen Bruto (%)',
            value=indicators['profitability']['gross_margin'],
            target='> 30%',
            formula='Util. Bruta / Ing x 100',
            interpretation='Eficiencia costo ventas',
            tag='mb',
            is_percentage=True
        ))

        lines.append(self._get_indicator_line(
            report, options,
            name='Margen Operacional (%)',
            value=indicators['profitability']['operating_margin'],
            target='> 15%',
            formula='Util. Op / Ing x 100',
            interpretation='Eficiencia operativa',
            tag='mo',
            is_percentage=True
        ))

        lines.append(self._get_indicator_line(
            report, options,
            name='Margen Neto (%)',
            value=indicators['profitability']['net_margin'],
            target='> 10%',
            formula='Util. Neta / Ing x 100',
            interpretation='Rentabilidad final',
            tag='mn',
            is_percentage=True
        ))

        lines.append(self._get_indicator_line(
            report, options,
            name='ROA - Retorno sobre Activos (%)',
            value=indicators['profitability']['roa'],
            target='> 8%',
            formula='Util. Neta / AT x 100',
            interpretation='Eficiencia de activos',
            tag='roa',
            is_percentage=True
        ))

        lines.append(self._get_indicator_line(
            report, options,
            name='ROE - Retorno sobre Patrimonio (%)',
            value=indicators['profitability']['roe'],
            target='> 15%',
            formula='Util. Neta / Pat x 100',
            interpretation='Retorno accionistas',
            tag='roe',
            is_percentage=True
        ))

        # === INDICADORES DE EFICIENCIA ===
        lines.append(self._get_section_header(report, options, 'INDICADORES DE EFICIENCIA', 'ef'))

        lines.append(self._get_indicator_line(
            report, options,
            name='Rotacion de Cartera (veces)',
            value=indicators['efficiency']['receivables_turnover'],
            target='> 12',
            formula='Ingresos / CxC',
            interpretation='Veces cobro al ano',
            tag='rot_c'
        ))

        lines.append(self._get_indicator_line(
            report, options,
            name='Dias de Cartera',
            value=indicators['efficiency']['days_receivables'],
            target='< 30',
            formula='CxC / Ing x 360',
            interpretation='Dias promedio cobro',
            tag='dias_c'
        ))

        lines.append(self._get_indicator_line(
            report, options,
            name='Rotacion de Inventario (veces)',
            value=indicators['efficiency']['inventory_turnover'],
            target='> 6',
            formula='Costo Ventas / Inv',
            interpretation='Rotacion anual',
            tag='rot_i'
        ))

        lines.append(self._get_indicator_line(
            report, options,
            name='Dias de Inventario',
            value=indicators['efficiency']['days_inventory'],
            target='< 60',
            formula='Inv / CV x 360',
            interpretation='Dias en inventario',
            tag='dias_i'
        ))

        lines.append(self._get_indicator_line(
            report, options,
            name='Dias de Proveedores',
            value=indicators['efficiency']['days_payables'],
            target='> 30',
            formula='CxP / CV x 360',
            interpretation='Dias promedio pago',
            tag='dias_p'
        ))

        lines.append(self._get_indicator_line(
            report, options,
            name='Ciclo de Caja (dias)',
            value=indicators['efficiency']['cash_cycle'],
            target='< 60',
            formula='D.Cart + D.Inv - D.Prov',
            interpretation='Conversion a efectivo',
            tag='ciclo'
        ))

        return [(0, line) for line in lines]

    # =====================================================
    # CALCULO DE INDICADORES
    # =====================================================

    def _calculate_all_indicators(self, balance_data, income_data):
        """Calcula todos los indicadores financieros."""
        indicators = {
            'liquidity': {},
            'leverage': {},
            'profitability': {},
            'efficiency': {},
        }

        # Datos del Balance
        current_assets = balance_data.get('current_assets', 0)
        total_assets = balance_data.get('total_assets', 0)
        inventory = balance_data.get('inventory', 0)
        cash = balance_data.get('cash', 0)
        receivables = balance_data.get('receivables', 0)

        current_liabilities = balance_data.get('current_liabilities', 0)
        total_liabilities = balance_data.get('total_liabilities', 0)
        payables = balance_data.get('payables', 0)

        equity = balance_data.get('equity', 0)

        # Datos del P&L
        revenue = income_data.get('revenue', 0)
        cost_of_sales = income_data.get('cost_of_sales', 0)
        gross_profit = revenue - cost_of_sales
        operating_income = income_data.get('operating_income', 0)
        net_income = income_data.get('net_income', 0)

        # === LIQUIDEZ ===
        indicators['liquidity']['current_ratio'] = self.calculate_liquidity_ratio(current_assets, current_liabilities)
        indicators['liquidity']['acid_test'] = self.calculate_acid_test_ratio(current_assets, inventory, current_liabilities)
        indicators['liquidity']['working_capital'] = self.calculate_working_capital(current_assets, current_liabilities)
        indicators['liquidity']['cash_ratio'] = self.calculate_cash_ratio(cash, current_liabilities)

        # === SOLVENCIA ===
        indicators['leverage']['debt_ratio'] = self._safe_percentage(total_liabilities, total_assets)
        indicators['leverage']['financial_leverage'] = self.calculate_financial_leverage(total_assets, equity)
        indicators['leverage']['equity_ratio'] = self._safe_percentage(equity, total_assets)
        indicators['leverage']['debt_to_equity'] = self.calculate_debt_to_equity(total_liabilities, equity)

        # === RENTABILIDAD ===
        indicators['profitability']['gross_margin'] = self.calculate_gross_margin(revenue, cost_of_sales)
        indicators['profitability']['operating_margin'] = self.calculate_operating_margin(operating_income, revenue)
        indicators['profitability']['net_margin'] = self.calculate_net_margin(net_income, revenue)
        indicators['profitability']['roa'] = self.calculate_roa(net_income, total_assets)
        indicators['profitability']['roe'] = self.calculate_roe(net_income, equity)

        # === EFICIENCIA ===
        # Rotacion de Cartera
        receivables_turnover = self._safe_divide(revenue, receivables)
        indicators['efficiency']['receivables_turnover'] = receivables_turnover
        indicators['efficiency']['days_receivables'] = 360 / receivables_turnover if receivables_turnover else 0

        # Rotacion de Inventario
        inventory_turnover = self._safe_divide(cost_of_sales, inventory)
        indicators['efficiency']['inventory_turnover'] = inventory_turnover
        indicators['efficiency']['days_inventory'] = 360 / inventory_turnover if inventory_turnover else 0

        # Rotacion de Proveedores
        payables_turnover = self._safe_divide(cost_of_sales, payables)
        indicators['efficiency']['payables_turnover'] = payables_turnover
        indicators['efficiency']['days_payables'] = 360 / payables_turnover if payables_turnover else 0

        # Ciclo de Caja
        indicators['efficiency']['cash_cycle'] = (
            indicators['efficiency']['days_receivables'] +
            indicators['efficiency']['days_inventory'] -
            indicators['efficiency']['days_payables']
        )

        return indicators

    def _safe_divide(self, numerator, denominator):
        """Division segura."""
        if denominator and denominator != 0:
            return numerator / denominator
        return 0

    def _safe_percentage(self, part, whole):
        """Porcentaje seguro."""
        if whole and whole != 0:
            return (part / whole) * 100
        return 0

    # =====================================================
    # CONSULTAS DE DATOS
    # =====================================================

    def _get_balance_data(self, report, options):
        """Obtiene datos del Balance General."""
        date_to = options.get('date', {}).get('date_to')

        data = {}
        company_id = self._get_company_id_for_sql()

        # Activos
        data['cash'] = self._get_balance_by_prefix(['11'], date_to, company_id)
        data['receivables'] = self._get_balance_by_prefix(['13'], date_to, company_id)
        data['inventory'] = self._get_balance_by_prefix(['14'], date_to, company_id)
        data['current_assets'] = self._get_balance_by_prefix(['11', '12', '13', '14'], date_to, company_id)
        data['total_assets'] = self._get_balance_by_prefix(['1'], date_to, company_id)

        # Pasivos (valores absolutos)
        data['payables'] = abs(self._get_balance_by_prefix(['22'], date_to, company_id))
        data['current_liabilities'] = abs(self._get_balance_by_prefix(['21', '22', '23', '24', '25'], date_to, company_id))
        data['total_liabilities'] = abs(self._get_balance_by_prefix(['2'], date_to, company_id))

        # Patrimonio (valor absoluto)
        data['equity'] = abs(self._get_balance_by_prefix(['3'], date_to, company_id))

        return data

    def _get_income_data(self, report, options):
        """Obtiene datos del Estado de Resultados."""
        date_from = options.get('date', {}).get('date_from')
        date_to = options.get('date', {}).get('date_to')

        data = {}
        company_id = self._get_company_id_for_sql()

        # Ingresos (valor absoluto de creditos)
        data['revenue'] = abs(self._get_balance_by_prefix_range(['41', '42'], date_from, date_to, company_id))

        # Costos
        data['cost_of_sales'] = self._get_balance_by_prefix_range(['6'], date_from, date_to, company_id)

        # Gastos Operacionales
        operating_expenses = self._get_balance_by_prefix_range(['51', '52'], date_from, date_to, company_id)
        data['operating_income'] = data['revenue'] - data['cost_of_sales'] - operating_expenses

        # Utilidad Neta (aproximacion)
        other_expenses = self._get_balance_by_prefix_range(['53', '54'], date_from, date_to, company_id)
        data['net_income'] = data['operating_income'] - other_expenses

        return data

    def _get_balance_by_prefix(self, prefixes, date_to, company_id):
        """Obtiene saldo a una fecha por prefijos de cuenta."""
        prefix_conditions = " OR ".join([
            f"COALESCE(aa.code_store->>'{company_id}', '') LIKE '{p}%'"
            for p in prefixes
        ])

        query = f"""
            SELECT COALESCE(SUM(aml.balance), 0)
            FROM account_move_line aml
            JOIN account_move am ON am.id = aml.move_id
            JOIN account_account aa ON aa.id = aml.account_id
            WHERE am.state = 'posted'
              AND aml.date <= '{date_to}'
              AND ({prefix_conditions})
        """
        self._cr.execute(query)
        result = self._cr.fetchone()
        return result[0] if result else 0.0

    def _get_balance_by_prefix_range(self, prefixes, date_from, date_to, company_id):
        """Obtiene saldo en un rango de fechas."""
        prefix_conditions = " OR ".join([
            f"COALESCE(aa.code_store->>'{company_id}', '') LIKE '{p}%'"
            for p in prefixes
        ])

        query = f"""
            SELECT COALESCE(SUM(aml.balance), 0)
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

    # =====================================================
    # CONSTRUCCION DE LINEAS
    # =====================================================

    def _get_section_header(self, report, options, name, tag):
        return {
            'id': report._get_generic_line_id(None, None, markup=f'header_{tag}'),
            'name': name,
            'level': 0,
            'unfoldable': True,
            'unfolded': True,
            'columns': [{'name': ''} for _ in options['columns']],
            'class': 'o_account_reports_level0 font-weight-bold',
        }

    def _get_indicator_line(self, report, options, name, value, target, formula, interpretation, tag,
                            is_percentage=False, is_monetary=False):
        """Construye linea de indicador."""
        cols = []

        for col in options['columns']:
            lbl = col['expression_label']

            if lbl == 'balance':
                if value is False or value is None:
                    display_value = 'N/A'
                elif is_percentage:
                    display_value = f"{value:.2f}%"
                elif is_monetary:
                    display_value = self.env.company.currency_id.format(value)
                else:
                    display_value = f"{value:.2f}"
                cols.append({'name': display_value, 'no_format': True})

            elif lbl == 'target' and options.get('show_targets'):
                cols.append({'name': target, 'no_format': True})

            elif lbl == 'formula' and options.get('show_formulas'):
                cols.append({'name': formula, 'no_format': True})

            elif lbl == 'interpretation' and options.get('show_interpretation'):
                cols.append({'name': interpretation, 'no_format': True})

            else:
                cols.append({'name': ''})

        return {
            'id': report._get_generic_line_id(None, None, markup=f'indicator_{tag}'),
            'name': name,
            'level': 2,
            'unfoldable': False,
            'columns': cols,
        }
