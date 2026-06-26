# -*- coding: utf-8 -*-
"""
Handler para Balance General Comparativo con Indicadores - Colombia
Incluye analisis horizontal, vertical y ratios financieros
"""

from odoo import models, fields, api, _
from odoo.tools import SQL
from datetime import timedelta
from dateutil.relativedelta import relativedelta
import logging

_logger = logging.getLogger(__name__)


class ComparativeBalanceHandler(models.AbstractModel):
    """
    Handler para Balance General Comparativo Colombia.
    Compara periodos con variaciones e indicadores.
    """
    _name = 'co.comparative.balance.report.handler'
    _inherit = ['account.report.custom.handler', 'sql.helper.mixin', 'financial.indicators.mixin', 'report.formulas.mixin']
    _description = 'Balance General Comparativo Colombia'

    # =====================================================
    # ESTRUCTURA DEL BALANCE (PUC Colombia)
    # =====================================================

    BALANCE_STRUCTURE = [
        # ACTIVOS
        {'code': '1', 'name': 'ACTIVOS', 'level': 0, 'type': 'total', 'parent': None},
        {'code': '11,12,13,14', 'name': 'Activo Corriente', 'level': 1, 'type': 'subtotal', 'parent': '1'},
        {'code': '11', 'name': 'Efectivo y Equivalentes', 'level': 2, 'type': 'detail', 'parent': '11,12,13,14'},
        {'code': '12', 'name': 'Inversiones Corrientes', 'level': 2, 'type': 'detail', 'parent': '11,12,13,14'},
        {'code': '13', 'name': 'Deudores Comerciales', 'level': 2, 'type': 'detail', 'parent': '11,12,13,14'},
        {'code': '14', 'name': 'Inventarios', 'level': 2, 'type': 'detail', 'parent': '11,12,13,14'},
        {'code': '15,16,17,18,19', 'name': 'Activo No Corriente', 'level': 1, 'type': 'subtotal', 'parent': '1'},
        {'code': '15', 'name': 'Propiedades, Planta y Equipo', 'level': 2, 'type': 'detail', 'parent': '15,16,17,18,19'},
        {'code': '16', 'name': 'Intangibles', 'level': 2, 'type': 'detail', 'parent': '15,16,17,18,19'},
        {'code': '17', 'name': 'Diferidos', 'level': 2, 'type': 'detail', 'parent': '15,16,17,18,19'},

        # PASIVOS
        {'code': '2', 'name': 'PASIVOS', 'level': 0, 'type': 'total', 'parent': None},
        {'code': '21,22,23,24,25', 'name': 'Pasivo Corriente', 'level': 1, 'type': 'subtotal', 'parent': '2'},
        {'code': '21', 'name': 'Obligaciones Financieras CP', 'level': 2, 'type': 'detail', 'parent': '21,22,23,24,25'},
        {'code': '22', 'name': 'Proveedores', 'level': 2, 'type': 'detail', 'parent': '21,22,23,24,25'},
        {'code': '23', 'name': 'Cuentas por Pagar', 'level': 2, 'type': 'detail', 'parent': '21,22,23,24,25'},
        {'code': '24', 'name': 'Impuestos por Pagar', 'level': 2, 'type': 'detail', 'parent': '21,22,23,24,25'},
        {'code': '25', 'name': 'Obligaciones Laborales', 'level': 2, 'type': 'detail', 'parent': '21,22,23,24,25'},
        {'code': '26,27,28,29', 'name': 'Pasivo No Corriente', 'level': 1, 'type': 'subtotal', 'parent': '2'},
        {'code': '26', 'name': 'Obligaciones Financieras LP', 'level': 2, 'type': 'detail', 'parent': '26,27,28,29'},

        # PATRIMONIO
        {'code': '3', 'name': 'PATRIMONIO', 'level': 0, 'type': 'total', 'parent': None},
        {'code': '31', 'name': 'Capital Social', 'level': 2, 'type': 'detail', 'parent': '3'},
        {'code': '32', 'name': 'Superavit de Capital', 'level': 2, 'type': 'detail', 'parent': '3'},
        {'code': '33', 'name': 'Reservas', 'level': 2, 'type': 'detail', 'parent': '3'},
        {'code': '36', 'name': 'Resultados del Ejercicio', 'level': 2, 'type': 'detail', 'parent': '3'},
        {'code': '37', 'name': 'Resultados Anteriores', 'level': 2, 'type': 'detail', 'parent': '3'},
    ]

    # =====================================================
    # CONFIGURACION
    # =====================================================

    def _get_custom_display_config(self):
        return {
            'css_custom_class': 'comparative_balance_report_co',
            'components': {
                'AccountReportFilters': 'libros_contables_colombia.TrialBalancePartnerFilters',
            },
        }

    def _custom_options_initializer(self, report, options, previous_options=None):
        super()._custom_options_initializer(report, options, previous_options=previous_options)

        # Configurar comparacion de periodos
        options['comparison'] = options.get('comparison', {})
        options['comparison']['filter'] = 'previous_period'
        options['comparison']['number_period'] = 1

        # Opciones de visualizacion
        options['show_variation'] = True
        options['show_variation_percent'] = True
        options['show_vertical_analysis'] = True
        options['show_indicators'] = True
        options['comparison_type'] = 'year'  # year, quarter, month

        if previous_options:
            for key in ['show_variation', 'show_variation_percent', 'show_vertical_analysis',
                        'show_indicators', 'comparison_type']:
                if key in previous_options:
                    options[key] = previous_options[key]

        # Botones
        options['buttons'].append({
            'name': _('Exportar Comparativo'),
            'sequence': 30,
            'action': 'export_comparative_xlsx',
            'file_export_type': 'xlsx',
        })

    # =====================================================
    # GENERADOR DE LINEAS
    # =====================================================

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        lines = []

        # Obtener datos comparativos
        current_data, previous_data = self._get_comparative_data(report, options)

        # Calcular indicadores
        current_indicators = self._calculate_balance_indicators(current_data)
        previous_indicators = self._calculate_balance_indicators(previous_data)

        # Encabezado principal
        lines.append(self._get_main_header(report, options))

        # Generar lineas del balance
        for item in self.BALANCE_STRUCTURE:
            codes = item['code'].split(',')
            current_balance = sum(current_data.get(c, 0) for c in codes)
            previous_balance = sum(previous_data.get(c, 0) for c in codes)

            # Ajustar signo para pasivos y patrimonio
            if item['code'].startswith('2') or item['code'].startswith('3'):
                current_balance = abs(current_balance)
                previous_balance = abs(previous_balance)

            # Solo mostrar si hay valores
            if current_balance != 0 or previous_balance != 0 or item['type'] in ['total', 'subtotal']:
                lines.append(self._get_balance_line(
                    report, options, item, current_balance, previous_balance,
                    current_data.get('total_assets', 0), previous_data.get('total_assets', 0)
                ))

        # Verificacion de cuadre
        total_assets = current_data.get('1', 0)
        total_liab_equity = abs(current_data.get('2', 0)) + abs(current_data.get('3', 0))
        if abs(total_assets - total_liab_equity) > 0.01:
            lines.append(self._get_warning_line(report, options,
                f'Diferencia: {total_assets - total_liab_equity:,.2f}'))

        # Seccion de Indicadores
        if options.get('show_indicators'):
            lines.append(self._get_section_header(report, options, 'INDICADORES FINANCIEROS', 'indicators'))

            # Indicadores de Liquidez
            lines.append(self._get_subsection_header(report, options, 'Liquidez', 'liq'))
            lines.append(self._get_indicator_comparison_line(
                report, options, 'Razon Corriente',
                current_indicators.get('current_ratio'),
                previous_indicators.get('current_ratio'),
                '> 1.5', 'liq_rc'
            ))
            lines.append(self._get_indicator_comparison_line(
                report, options, 'Prueba Acida',
                current_indicators.get('acid_test'),
                previous_indicators.get('acid_test'),
                '> 1.0', 'liq_pa'
            ))
            lines.append(self._get_indicator_comparison_line(
                report, options, 'Capital de Trabajo',
                current_indicators.get('working_capital'),
                previous_indicators.get('working_capital'),
                '> 0', 'liq_ct', is_monetary=True
            ))

            # Indicadores de Solvencia
            lines.append(self._get_subsection_header(report, options, 'Solvencia', 'sol'))
            lines.append(self._get_indicator_comparison_line(
                report, options, 'Endeudamiento (%)',
                current_indicators.get('debt_ratio'),
                previous_indicators.get('debt_ratio'),
                '< 60%', 'sol_end', is_percentage=True
            ))
            lines.append(self._get_indicator_comparison_line(
                report, options, 'Apalancamiento',
                current_indicators.get('leverage'),
                previous_indicators.get('leverage'),
                '< 2.5', 'sol_apal'
            ))
            lines.append(self._get_indicator_comparison_line(
                report, options, 'Autonomia (%)',
                current_indicators.get('equity_ratio'),
                previous_indicators.get('equity_ratio'),
                '> 40%', 'sol_aut', is_percentage=True
            ))

        return [(0, line) for line in lines]

    # =====================================================
    # CONSULTAS DE DATOS
    # =====================================================

    def _get_comparative_data(self, report, options):
        """Obtiene datos del periodo actual y anterior."""
        date_to = fields.Date.from_string(options.get('date', {}).get('date_to'))
        date_from = fields.Date.from_string(options.get('date', {}).get('date_from'))

        company_id = self._get_company_id_for_sql()

        # Determinar fechas del periodo anterior segun tipo de comparacion
        comparison_type = options.get('comparison_type', 'year')
        if comparison_type == 'year':
            prev_date_to = date_to - relativedelta(years=1)
            prev_date_from = date_from - relativedelta(years=1)
        elif comparison_type == 'quarter':
            prev_date_to = date_to - relativedelta(months=3)
            prev_date_from = date_from - relativedelta(months=3)
        else:  # month
            prev_date_to = date_to - relativedelta(months=1)
            prev_date_from = date_from - relativedelta(months=1)

        # Obtener saldos actuales
        current_data = self._get_balances_at_date(str(date_to), company_id)

        # Obtener saldos anteriores
        previous_data = self._get_balances_at_date(str(prev_date_to), company_id)

        return current_data, previous_data

    def _get_balances_at_date(self, date_to, company_id):
        """Obtiene saldos a una fecha especifica."""
        data = {}

        # Consulta principal agrupada por prefijo de cuenta
        query = f"""
            SELECT
                SUBSTRING(COALESCE(aa.code_store->>'{company_id}', ''), 1, 2) as prefix,
                SUM(aml.balance) as balance
            FROM account_move_line aml
            JOIN account_move am ON am.id = aml.move_id
            JOIN account_account aa ON aa.id = aml.account_id
            WHERE am.state = 'posted'
              AND aml.date <= '{date_to}'
            GROUP BY SUBSTRING(COALESCE(aa.code_store->>'{company_id}', ''), 1, 2)
        """
        self._cr.execute(query)

        for row in self._cr.dictfetchall():
            prefix = row['prefix']
            balance = row['balance'] or 0

            if prefix:
                data[prefix] = balance

                # Acumular en clase principal
                class_code = prefix[0]
                data[class_code] = data.get(class_code, 0) + balance

        # Calcular total activos para analisis vertical
        data['total_assets'] = data.get('1', 0)

        return data

    def _calculate_balance_indicators(self, data):
        """Calcula indicadores del balance."""
        indicators = {}

        # Activos
        current_assets = sum(data.get(c, 0) for c in ['11', '12', '13', '14'])
        total_assets = data.get('1', 0)
        inventory = data.get('14', 0)
        cash = data.get('11', 0)

        # Pasivos
        current_liabilities = abs(sum(data.get(c, 0) for c in ['21', '22', '23', '24', '25']))
        total_liabilities = abs(data.get('2', 0))

        # Patrimonio
        equity = abs(data.get('3', 0))

        # Indicadores de Liquidez
        indicators['current_ratio'] = self.calculate_liquidity_ratio(current_assets, current_liabilities)
        indicators['acid_test'] = self.calculate_acid_test_ratio(current_assets, inventory, current_liabilities)
        indicators['working_capital'] = self.calculate_working_capital(current_assets, current_liabilities)
        indicators['cash_ratio'] = self.calculate_cash_ratio(cash, current_liabilities)

        # Indicadores de Solvencia
        indicators['debt_ratio'] = (total_liabilities / total_assets * 100) if total_assets else 0
        indicators['leverage'] = self.calculate_financial_leverage(total_assets, equity)
        indicators['equity_ratio'] = (equity / total_assets * 100) if total_assets else 0
        indicators['debt_to_equity'] = self.calculate_debt_to_equity(total_liabilities, equity)

        return indicators

    # =====================================================
    # CONSTRUCCION DE LINEAS
    # =====================================================

    def _get_main_header(self, report, options):
        return {
            'id': report._get_generic_line_id(None, None, markup='main_header'),
            'name': _('BALANCE GENERAL COMPARATIVO'),
            'level': 0,
            'unfoldable': False,
            'columns': [{'name': ''} for _ in options['columns']],
            'class': 'o_account_reports_level0 font-weight-bold text-center',
        }

    def _get_section_header(self, report, options, name, tag):
        return {
            'id': report._get_generic_line_id(None, None, markup=f'section_{tag}'),
            'name': name,
            'level': 0,
            'unfoldable': True,
            'unfolded': True,
            'columns': [{'name': ''} for _ in options['columns']],
            'class': 'o_account_reports_level0 font-weight-bold',
        }

    def _get_subsection_header(self, report, options, name, tag):
        return {
            'id': report._get_generic_line_id(None, None, markup=f'subsection_{tag}'),
            'name': name,
            'level': 1,
            'unfoldable': False,
            'columns': [{'name': ''} for _ in options['columns']],
            'class': 'o_account_reports_level1 font-weight-bold',
        }

    def _get_balance_line(self, report, options, item, current, previous, total_current, total_previous):
        """Construye linea del balance con comparacion."""
        cols = []

        # Calcular variaciones
        variation = current - previous
        variation_pct = ((current - previous) / abs(previous) * 100) if previous else (100 if current else 0)

        # Analisis vertical
        vertical_current = (current / total_current * 100) if total_current else 0
        vertical_previous = (previous / total_previous * 100) if total_previous else 0

        for col in options['columns']:
            lbl = col['expression_label']

            if lbl == 'current_balance':
                cols.append(report._build_column_dict(current, col, options=options))
            elif lbl == 'previous_balance':
                cols.append(report._build_column_dict(previous, col, options=options))
            elif lbl == 'variation' and options.get('show_variation'):
                cols.append(report._build_column_dict(variation, col, options=options))
            elif lbl == 'variation_percent' and options.get('show_variation_percent'):
                cols.append({'name': f"{variation_pct:.1f}%", 'no_format': True})
            elif lbl == 'vertical_current' and options.get('show_vertical_analysis'):
                cols.append({'name': f"{vertical_current:.1f}%", 'no_format': True})
            elif lbl == 'vertical_previous' and options.get('show_vertical_analysis'):
                cols.append({'name': f"{vertical_previous:.1f}%", 'no_format': True})
            else:
                cols.append({'name': ''})

        # Determinar clase CSS segun tipo
        css_class = ''
        if item['type'] == 'total':
            css_class = 'o_account_reports_level0 font-weight-bold'
        elif item['type'] == 'subtotal':
            css_class = 'o_account_reports_level1 font-weight-bold'

        return {
            'id': report._get_generic_line_id(None, None, markup=f"bal_{item['code']}"),
            'name': item['name'],
            'level': item['level'],
            'unfoldable': item['type'] in ['total', 'subtotal'],
            'unfolded': True,
            'columns': cols,
            'class': css_class,
        }

    def _get_indicator_comparison_line(self, report, options, name, current_value, previous_value,
                                        target, tag, is_percentage=False, is_monetary=False):
        """Construye linea de indicador con comparacion."""
        cols = []

        # Calcular variacion del indicador
        if current_value is not None and previous_value is not None:
            variation = current_value - previous_value
        else:
            variation = 0

        for col in options['columns']:
            lbl = col['expression_label']

            if lbl == 'current_balance':
                if current_value is None or current_value is False:
                    display = 'N/A'
                elif is_percentage:
                    display = f"{current_value:.2f}%"
                elif is_monetary:
                    display = self.env.company.currency_id.format(current_value)
                else:
                    display = f"{current_value:.2f}"
                cols.append({'name': display, 'no_format': True})

            elif lbl == 'previous_balance':
                if previous_value is None or previous_value is False:
                    display = 'N/A'
                elif is_percentage:
                    display = f"{previous_value:.2f}%"
                elif is_monetary:
                    display = self.env.company.currency_id.format(previous_value)
                else:
                    display = f"{previous_value:.2f}"
                cols.append({'name': display, 'no_format': True})

            elif lbl == 'variation':
                if is_percentage:
                    display = f"{variation:+.2f}%"
                elif is_monetary:
                    display = self.env.company.currency_id.format(variation)
                else:
                    display = f"{variation:+.2f}"
                cols.append({'name': display, 'no_format': True})

            elif lbl == 'target':
                cols.append({'name': target, 'no_format': True})

            else:
                cols.append({'name': ''})

        return {
            'id': report._get_generic_line_id(None, None, markup=f'ind_{tag}'),
            'name': name,
            'level': 2,
            'unfoldable': False,
            'columns': cols,
        }

    def _get_warning_line(self, report, options, message):
        return {
            'id': report._get_generic_line_id(None, None, markup='warning'),
            'name': f"ADVERTENCIA: {message}",
            'level': 0,
            'unfoldable': False,
            'columns': [{'name': ''} for _ in options['columns']],
            'class': 'text-danger font-weight-bold',
        }
