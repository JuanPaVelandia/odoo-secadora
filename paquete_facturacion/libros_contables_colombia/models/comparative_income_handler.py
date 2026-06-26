# -*- coding: utf-8 -*-
"""
Handler para Estado de Resultados Comparativo con Indicadores - Colombia
Incluye analisis horizontal, vertical y margenes
"""

from odoo import models, fields, api, _
from odoo.tools import SQL
from dateutil.relativedelta import relativedelta
import logging

_logger = logging.getLogger(__name__)


class ComparativeIncomeHandler(models.AbstractModel):
    """
    Handler para Estado de Resultados Comparativo Colombia.
    Compara periodos con variaciones, margenes e indicadores.
    """
    _name = 'co.comparative.income.report.handler'
    _inherit = ['account.report.custom.handler', 'sql.helper.mixin', 'financial.indicators.mixin', 'report.formulas.mixin']
    _description = 'Estado de Resultados Comparativo Colombia'

    # =====================================================
    # ESTRUCTURA DEL P&L (PUC Colombia)
    # =====================================================

    PL_STRUCTURE = [
        # INGRESOS
        {'code': '4', 'name': 'INGRESOS', 'level': 0, 'type': 'total', 'sign': -1},
        {'code': '41', 'name': 'Ingresos Operacionales', 'level': 1, 'type': 'subtotal', 'sign': -1},
        {'code': '4105', 'name': 'Ventas', 'level': 2, 'type': 'detail', 'sign': -1},
        {'code': '4110', 'name': 'Servicios', 'level': 2, 'type': 'detail', 'sign': -1},
        {'code': '4115', 'name': 'Actividades Inmobiliarias', 'level': 2, 'type': 'detail', 'sign': -1},
        {'code': '4120', 'name': 'Industria Manufacturera', 'level': 2, 'type': 'detail', 'sign': -1},
        {'code': '4125', 'name': 'Construccion', 'level': 2, 'type': 'detail', 'sign': -1},
        {'code': '4130', 'name': 'Comercio Mayor/Menor', 'level': 2, 'type': 'detail', 'sign': -1},
        {'code': '4135', 'name': 'Hoteles y Restaurantes', 'level': 2, 'type': 'detail', 'sign': -1},
        {'code': '4140', 'name': 'Transporte y Almacenamiento', 'level': 2, 'type': 'detail', 'sign': -1},
        {'code': '4145', 'name': 'Intermediacion Financiera', 'level': 2, 'type': 'detail', 'sign': -1},
        {'code': '4150', 'name': 'Agropecuarias', 'level': 2, 'type': 'detail', 'sign': -1},
        {'code': '4155', 'name': 'Arrendamientos', 'level': 2, 'type': 'detail', 'sign': -1},
        {'code': '4160', 'name': 'Enseñanza', 'level': 2, 'type': 'detail', 'sign': -1},
        {'code': '4165', 'name': 'Servicios Sociales y Salud', 'level': 2, 'type': 'detail', 'sign': -1},
        {'code': '4170', 'name': 'Otras Actividades', 'level': 2, 'type': 'detail', 'sign': -1},
        {'code': '4175', 'name': 'Devoluciones y Descuentos', 'level': 2, 'type': 'detail', 'sign': 1},
        {'code': '42', 'name': 'Ingresos No Operacionales', 'level': 1, 'type': 'subtotal', 'sign': -1},
        {'code': '4210', 'name': 'Financieros', 'level': 2, 'type': 'detail', 'sign': -1},
        {'code': '4215', 'name': 'Dividendos y Participaciones', 'level': 2, 'type': 'detail', 'sign': -1},
        {'code': '4220', 'name': 'Arrendamientos', 'level': 2, 'type': 'detail', 'sign': -1},
        {'code': '4250', 'name': 'Recuperaciones', 'level': 2, 'type': 'detail', 'sign': -1},

        # COSTOS
        {'code': '6', 'name': 'COSTO DE VENTAS', 'level': 0, 'type': 'total', 'sign': 1},
        {'code': '61', 'name': 'Costo de Ventas y Prestacion de Servicios', 'level': 1, 'type': 'subtotal', 'sign': 1},
        {'code': '6105', 'name': 'Costo Agricultura, Ganaderia, Caza', 'level': 2, 'type': 'detail', 'sign': 1},
        {'code': '6110', 'name': 'Costo Pesca', 'level': 2, 'type': 'detail', 'sign': 1},
        {'code': '6115', 'name': 'Costo Minas y Canteras', 'level': 2, 'type': 'detail', 'sign': 1},
        {'code': '6120', 'name': 'Costo Industrias Manufactureras', 'level': 2, 'type': 'detail', 'sign': 1},
        {'code': '6125', 'name': 'Costo Suministro Electricidad, Gas', 'level': 2, 'type': 'detail', 'sign': 1},
        {'code': '6135', 'name': 'Costo Comercio Mayor/Menor', 'level': 2, 'type': 'detail', 'sign': 1},
        {'code': '6140', 'name': 'Costo Hoteles y Restaurantes', 'level': 2, 'type': 'detail', 'sign': 1},
        {'code': '6145', 'name': 'Costo Transporte', 'level': 2, 'type': 'detail', 'sign': 1},

        # UTILIDAD BRUTA (calculada)
        {'code': 'UB', 'name': 'UTILIDAD BRUTA', 'level': 0, 'type': 'calculated', 'formula': '4-6'},

        # GASTOS OPERACIONALES
        {'code': '5', 'name': 'GASTOS OPERACIONALES', 'level': 0, 'type': 'total', 'sign': 1},
        {'code': '51', 'name': 'Gastos de Administracion', 'level': 1, 'type': 'subtotal', 'sign': 1},
        {'code': '5105', 'name': 'Gastos de Personal', 'level': 2, 'type': 'detail', 'sign': 1},
        {'code': '5110', 'name': 'Honorarios', 'level': 2, 'type': 'detail', 'sign': 1},
        {'code': '5115', 'name': 'Impuestos', 'level': 2, 'type': 'detail', 'sign': 1},
        {'code': '5120', 'name': 'Arrendamientos', 'level': 2, 'type': 'detail', 'sign': 1},
        {'code': '5125', 'name': 'Contribuciones y Afiliaciones', 'level': 2, 'type': 'detail', 'sign': 1},
        {'code': '5130', 'name': 'Seguros', 'level': 2, 'type': 'detail', 'sign': 1},
        {'code': '5135', 'name': 'Servicios', 'level': 2, 'type': 'detail', 'sign': 1},
        {'code': '5140', 'name': 'Gastos Legales', 'level': 2, 'type': 'detail', 'sign': 1},
        {'code': '5145', 'name': 'Mantenimiento y Reparaciones', 'level': 2, 'type': 'detail', 'sign': 1},
        {'code': '5150', 'name': 'Adecuacion e Instalacion', 'level': 2, 'type': 'detail', 'sign': 1},
        {'code': '5155', 'name': 'Gastos de Viaje', 'level': 2, 'type': 'detail', 'sign': 1},
        {'code': '5160', 'name': 'Depreciaciones', 'level': 2, 'type': 'detail', 'sign': 1},
        {'code': '5165', 'name': 'Amortizaciones', 'level': 2, 'type': 'detail', 'sign': 1},
        {'code': '5195', 'name': 'Diversos', 'level': 2, 'type': 'detail', 'sign': 1},
        {'code': '5199', 'name': 'Provisiones', 'level': 2, 'type': 'detail', 'sign': 1},
        {'code': '52', 'name': 'Gastos de Ventas', 'level': 1, 'type': 'subtotal', 'sign': 1},
        {'code': '5205', 'name': 'Gastos de Personal (Ventas)', 'level': 2, 'type': 'detail', 'sign': 1},
        {'code': '5210', 'name': 'Honorarios (Ventas)', 'level': 2, 'type': 'detail', 'sign': 1},
        {'code': '5220', 'name': 'Arrendamientos (Ventas)', 'level': 2, 'type': 'detail', 'sign': 1},
        {'code': '5235', 'name': 'Servicios (Ventas)', 'level': 2, 'type': 'detail', 'sign': 1},
        {'code': '5240', 'name': 'Gastos Legales (Ventas)', 'level': 2, 'type': 'detail', 'sign': 1},

        # UTILIDAD OPERACIONAL (calculada)
        {'code': 'UO', 'name': 'UTILIDAD OPERACIONAL', 'level': 0, 'type': 'calculated', 'formula': 'UB-5'},

        # OTROS GASTOS
        {'code': '53', 'name': 'GASTOS NO OPERACIONALES', 'level': 0, 'type': 'total', 'sign': 1},
        {'code': '5305', 'name': 'Gastos Financieros', 'level': 2, 'type': 'detail', 'sign': 1},
        {'code': '5310', 'name': 'Perdida en Venta de Activos', 'level': 2, 'type': 'detail', 'sign': 1},
        {'code': '5315', 'name': 'Gastos Extraordinarios', 'level': 2, 'type': 'detail', 'sign': 1},

        # UTILIDAD ANTES DE IMPUESTOS (calculada)
        {'code': 'UAI', 'name': 'UTILIDAD ANTES DE IMPUESTOS', 'level': 0, 'type': 'calculated', 'formula': 'UO-53'},

        # IMPUESTO DE RENTA
        {'code': '54', 'name': 'IMPUESTO DE RENTA', 'level': 0, 'type': 'total', 'sign': 1},
        {'code': '5405', 'name': 'Impuesto de Renta y Complementarios', 'level': 2, 'type': 'detail', 'sign': 1},

        # UTILIDAD NETA (calculada)
        {'code': 'UN', 'name': 'UTILIDAD NETA DEL EJERCICIO', 'level': 0, 'type': 'calculated', 'formula': 'UAI-54'},
    ]

    # =====================================================
    # CONFIGURACION
    # =====================================================

    def _get_custom_display_config(self):
        return {
            'css_custom_class': 'comparative_income_report_co',
            'components': {
                'AccountReportFilters': 'libros_contables_colombia.TrialBalancePartnerFilters',
            },
        }

    def _custom_options_initializer(self, report, options, previous_options=None):
        super()._custom_options_initializer(report, options, previous_options=previous_options)

        # Opciones de visualizacion
        options['show_variation'] = True
        options['show_variation_percent'] = True
        options['show_vertical_analysis'] = True
        options['show_margins'] = True
        options['show_indicators'] = True
        options['comparison_type'] = 'year'

        if previous_options:
            for key in ['show_variation', 'show_variation_percent', 'show_vertical_analysis',
                        'show_margins', 'show_indicators', 'comparison_type']:
                if key in previous_options:
                    options[key] = previous_options[key]

    # =====================================================
    # GENERADOR DE LINEAS
    # =====================================================

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        lines = []

        # Obtener datos comparativos con detalle de cuentas
        current_data, previous_data, current_accounts_detail, previous_accounts_detail = self._get_comparative_data(report, options)

        # Calcular totales e indicadores
        current_totals = self._calculate_pl_totals(current_data)
        previous_totals = self._calculate_pl_totals(previous_data)

        current_indicators = self._calculate_pl_indicators(current_totals)
        previous_indicators = self._calculate_pl_indicators(previous_totals)

        # Encabezado
        lines.append(self._get_main_header(report, options))

        # Generar lineas del P&L
        for item in self.PL_STRUCTURE:
            if item['type'] == 'calculated':
                # Linea calculada
                current_value = current_totals.get(item['code'], 0)
                previous_value = previous_totals.get(item['code'], 0)
            else:
                # Obtener balance de la cuenta
                current_value = current_data.get(item['code'], 0) * item.get('sign', 1)
                previous_value = previous_data.get(item['code'], 0) * item.get('sign', 1)

            # Solo mostrar si hay valores o es linea importante
            if current_value != 0 or previous_value != 0 or item['type'] in ['total', 'calculated']:
                lines.append(self._get_pl_line(
                    report, options, item, current_value, previous_value,
                    current_totals.get('4', 0), previous_totals.get('4', 0)  # Ingresos para analisis vertical
                ))

                # Agregar cuentas detalladas solo bajo items tipo 'detail' (4 dígitos)
                # Esto muestra las cuentas individuales (6+ dígitos) bajo su categoría de 4 dígitos
                if item['type'] == 'detail' and len(item['code']) == 4:
                    detail_accounts = self._get_accounts_for_prefix_from_dict(item['code'], current_accounts_detail)
                    for acc in detail_accounts:
                        acc_current = acc['balance'] * item.get('sign', 1)
                        # Obtener saldo anterior para esta cuenta específica
                        prev_acc = previous_accounts_detail.get(acc['code'], {})
                        acc_previous = prev_acc.get('balance', 0) * item.get('sign', 1) if prev_acc else 0
                        if acc_current != 0 or acc_previous != 0:
                            lines.append(self._get_account_line(
                                report, options, acc,
                                acc_current, acc_previous,
                                current_totals.get('4', 0), previous_totals.get('4', 0),
                                item['level'] + 1
                            ))

        # Seccion de Margenes e Indicadores
        if options.get('show_indicators'):
            lines.append(self._get_section_header(report, options, 'MARGENES E INDICADORES', 'indicators'))

            # Margenes
            lines.append(self._get_subsection_header(report, options, 'Margenes', 'margins'))
            lines.append(self._get_indicator_comparison_line(
                report, options, 'Margen Bruto (%)',
                current_indicators.get('gross_margin'),
                previous_indicators.get('gross_margin'),
                '> 30%', 'marg_bruto', is_percentage=True
            ))
            lines.append(self._get_indicator_comparison_line(
                report, options, 'Margen Operacional (%)',
                current_indicators.get('operating_margin'),
                previous_indicators.get('operating_margin'),
                '> 15%', 'marg_op', is_percentage=True
            ))
            lines.append(self._get_indicator_comparison_line(
                report, options, 'Margen Neto (%)',
                current_indicators.get('net_margin'),
                previous_indicators.get('net_margin'),
                '> 10%', 'marg_neto', is_percentage=True
            ))
            lines.append(self._get_indicator_comparison_line(
                report, options, 'Margen EBITDA (%)',
                current_indicators.get('ebitda_margin'),
                previous_indicators.get('ebitda_margin'),
                '> 20%', 'marg_ebitda', is_percentage=True
            ))

            # EBITDA
            lines.append(self._get_subsection_header(report, options, 'EBITDA', 'ebitda'))
            lines.append(self._get_indicator_comparison_line(
                report, options, 'EBITDA',
                current_indicators.get('ebitda'),
                previous_indicators.get('ebitda'),
                '> 0', 'ebitda_val', is_monetary=True
            ))
            lines.append(self._get_indicator_comparison_line(
                report, options, 'EBIT',
                current_indicators.get('ebit'),
                previous_indicators.get('ebit'),
                '> 0', 'ebit_val', is_monetary=True
            ))

            # Crecimiento
            lines.append(self._get_subsection_header(report, options, 'Crecimiento', 'growth'))
            revenue_growth = self._calculate_growth(current_totals.get('4', 0), previous_totals.get('4', 0))
            lines.append(self._get_indicator_comparison_line(
                report, options, 'Crecimiento Ingresos (%)',
                revenue_growth, None,
                '> 5%', 'growth_rev', is_percentage=True, single_value=True
            ))
            net_income_growth = self._calculate_growth(current_totals.get('UN', 0), previous_totals.get('UN', 0))
            lines.append(self._get_indicator_comparison_line(
                report, options, 'Crecimiento Utilidad Neta (%)',
                net_income_growth, None,
                '> 10%', 'growth_un', is_percentage=True, single_value=True
            ))

        return [(0, line) for line in lines]

    # =====================================================
    # CONSULTAS DE DATOS
    # =====================================================

    def _get_comparative_data(self, report, options):
        """
        Obtiene datos del P&L actual y anterior.

        Returns:
            tuple: (current_data, previous_data, current_accounts_detail, previous_accounts_detail)
        """
        date_from = fields.Date.from_string(options.get('date', {}).get('date_from'))
        date_to = fields.Date.from_string(options.get('date', {}).get('date_to'))

        company_id = self._get_company_id_for_sql()

        # Fechas del periodo anterior
        comparison_type = options.get('comparison_type', 'year')
        if comparison_type == 'year':
            prev_date_from = date_from - relativedelta(years=1)
            prev_date_to = date_to - relativedelta(years=1)
        elif comparison_type == 'quarter':
            prev_date_from = date_from - relativedelta(months=3)
            prev_date_to = date_to - relativedelta(months=3)
        else:
            prev_date_from = date_from - relativedelta(months=1)
            prev_date_to = date_to - relativedelta(months=1)

        # Obtener datos actuales con detalle de cuentas
        current_data, current_accounts_detail = self._get_pl_balances(str(date_from), str(date_to), company_id)

        # Obtener datos anteriores con detalle de cuentas
        previous_data, previous_accounts_detail = self._get_pl_balances(str(prev_date_from), str(prev_date_to), company_id)

        return current_data, previous_data, current_accounts_detail, previous_accounts_detail

    def _get_pl_balances(self, date_from, date_to, company_id):
        """
        Obtiene saldos del P&L en un rango.

        Returns:
            tuple: (data, accounts_detail)
                - data: dict con saldos agregados por prefijos
                - accounts_detail: dict con detalle de cada cuenta individual
        """
        data = {}
        accounts_detail = {}  # Para guardar detalle de cuentas

        # Consulta con detalle de cuentas
        query = f"""
            SELECT
                COALESCE(aa.code_store->>'{company_id}',
                    (SELECT value FROM jsonb_each_text(aa.code_store) LIMIT 1)) as code,
                COALESCE(aa.name->>'es_CO', aa.name->>'es_ES', aa.name->>'en_US',
                    (SELECT value FROM jsonb_each_text(aa.name) LIMIT 1)) as name,
                SUM(aml.balance) as balance
            FROM account_move_line aml
            JOIN account_move am ON am.id = aml.move_id
            JOIN account_account aa ON aa.id = aml.account_id
            WHERE am.state = 'posted'
              AND aml.date >= '{date_from}'
              AND aml.date <= '{date_to}'
              AND SUBSTRING(COALESCE(aa.code_store->>'{company_id}',
                  (SELECT value FROM jsonb_each_text(aa.code_store) LIMIT 1)), 1, 1) IN ('4', '5', '6')
            GROUP BY aa.id, aa.code_store, aa.name
            ORDER BY code
        """
        self._cr.execute(query)

        for row in self._cr.dictfetchall():
            code = row['code']
            name = row['name']
            balance = row['balance'] or 0

            if code:
                # Guardar detalle de la cuenta
                accounts_detail[code] = {
                    'code': code,
                    'name': name,
                    'balance': balance,
                }

                # Acumular por prefijos (1, 2, 4, 6 dígitos)
                for length in [1, 2, 4, 6]:
                    if len(code) >= length:
                        prefix = code[:length]
                        data[prefix] = data.get(prefix, 0) + balance

        return data, accounts_detail

    def _get_accounts_for_prefix_from_dict(self, prefix, accounts_detail, exact_children=True):
        """
        Obtiene las cuentas detalladas para un prefijo dado desde un diccionario.

        Args:
            prefix: Código de cuenta padre (ej: '41', '5105')
            accounts_detail: Diccionario con detalle de cuentas {code: {code, name, balance}}
            exact_children: Si True, solo retorna cuentas que son hijas directas
                           (cuentas completas que empiezan con el prefix)
        """
        if not accounts_detail:
            return []

        accounts = []
        prefix_len = len(prefix)

        for code, info in accounts_detail.items():
            if code.startswith(prefix) and code != prefix and info['balance'] != 0:
                # Solo incluir cuentas de nivel mayor (más dígitos)
                if exact_children:
                    # Solo mostrar bajo 'detail' items (4 dígitos) - cuentas de 6+ dígitos
                    if prefix_len == 4 and len(code) >= 6:
                        accounts.append(info)
                else:
                    accounts.append(info)

        return sorted(accounts, key=lambda x: x['code'])

    def _calculate_pl_totals(self, data):
        """Calcula totales del P&L incluyendo lineas calculadas."""
        totals = dict(data)

        # Ingresos (valor absoluto)
        totals['4'] = abs(data.get('4', 0))
        totals['41'] = abs(data.get('41', 0))
        totals['42'] = abs(data.get('42', 0))

        # Costo de ventas
        totals['6'] = data.get('6', 0)

        # Utilidad Bruta
        totals['UB'] = totals['4'] - totals['6']

        # Gastos operacionales
        totals['5'] = data.get('5', 0)
        totals['51'] = data.get('51', 0)
        totals['52'] = data.get('52', 0)

        # Utilidad Operacional
        totals['UO'] = totals['UB'] - totals['5']

        # Gastos no operacionales
        totals['53'] = data.get('53', 0)

        # Utilidad antes de impuestos
        totals['UAI'] = totals['UO'] - totals['53']

        # Impuesto de renta
        totals['54'] = data.get('54', 0)

        # Utilidad Neta
        totals['UN'] = totals['UAI'] - totals['54']

        return totals

    def _calculate_pl_indicators(self, totals):
        """Calcula indicadores del P&L."""
        indicators = {}
        revenue = totals.get('4', 0)

        if revenue:
            indicators['gross_margin'] = (totals.get('UB', 0) / revenue) * 100
            indicators['operating_margin'] = (totals.get('UO', 0) / revenue) * 100
            indicators['net_margin'] = (totals.get('UN', 0) / revenue) * 100

            # EBITDA = Utilidad Operacional + Depreciaciones
            depreciation = totals.get('5195', 0) + totals.get('5295', 0)
            ebitda = totals.get('UO', 0) + depreciation
            indicators['ebitda'] = ebitda
            indicators['ebitda_margin'] = (ebitda / revenue) * 100
            indicators['ebit'] = totals.get('UO', 0)
        else:
            indicators['gross_margin'] = 0
            indicators['operating_margin'] = 0
            indicators['net_margin'] = 0
            indicators['ebitda'] = 0
            indicators['ebitda_margin'] = 0
            indicators['ebit'] = 0

        return indicators

    def _calculate_growth(self, current, previous):
        """Calcula tasa de crecimiento."""
        if previous and previous != 0:
            return ((current - previous) / abs(previous)) * 100
        return 100 if current else 0

    # =====================================================
    # CONSTRUCCION DE LINEAS
    # =====================================================

    def _get_main_header(self, report, options):
        return {
            'id': report._get_generic_line_id(None, None, markup='main_header'),
            'name': _('ESTADO DE RESULTADOS COMPARATIVO'),
            'level': 0,
            'unfoldable': False,
            'columns': [{'name': ''} for _ in options['columns']],
            'class': 'o_account_reports_level0 font-weight-bold text-center',
        }

    def _get_section_header(self, report, options, name, tag):
        # Iconos para secciones
        section_icons = {
            'indicators': '<i class="fa fa-dashboard"></i>',
        }
        icon = section_icons.get(tag, '<i class="fa fa-folder-open"></i>')

        return {
            'id': report._get_generic_line_id(None, None, markup=f'section_{tag}'),
            'name': f'{icon} {name}',
            'level': 0,
            'unfoldable': True,
            'unfolded': True,
            'columns': [{'name': '', 'no_format': ''} for _ in options['columns']],
            'class': 'o_account_reports_level0 font-weight-bold',
        }

    def _get_subsection_header(self, report, options, name, tag):
        # Iconos para subsecciones
        subsection_icons = {
            'margins': '<i class="fa fa-percent"></i>',
            'ebitda': '<i class="fa fa-calculator"></i>',
            'growth': '<i class="fa fa-line-chart"></i>',
        }
        icon = subsection_icons.get(tag, '<i class="fa fa-list"></i>')

        return {
            'id': report._get_generic_line_id(None, None, markup=f'subsection_{tag}'),
            'name': f'{icon} {name}',
            'level': 1,
            'unfoldable': False,
            'columns': [{'name': '', 'no_format': ''} for _ in options['columns']],
            'class': 'o_account_reports_level1 font-weight-bold',
        }

    def _get_pl_line(self, report, options, item, current, previous, total_current, total_previous):
        """Construye linea del P&L con comparacion."""
        cols = []

        variation = current - previous
        variation_pct = ((current - previous) / abs(previous) * 100) if previous else (100 if current else 0)

        # Analisis vertical (% sobre ingresos)
        vertical_current = (current / total_current * 100) if total_current else 0

        # Icono de tendencia
        trend_icon = ''
        trend_class = ''
        if variation > 0:
            trend_icon = '↑'
            trend_class = 'text-success'
        elif variation < 0:
            trend_icon = '↓'
            trend_class = 'text-danger'

        for col in options['columns']:
            lbl = col['expression_label']

            if lbl == 'current_balance':
                cols.append(report._build_column_dict(current, col, options=options))
            elif lbl == 'previous_balance':
                cols.append(report._build_column_dict(previous, col, options=options))
            elif lbl == 'variation':
                col_dict = report._build_column_dict(variation, col, options=options)
                col_dict['class'] = trend_class
                cols.append(col_dict)
            elif lbl == 'variation_percent':
                # Usar figure_type percentage y agregar icono
                col_dict = report._build_column_dict(variation_pct / 100, col, options=options)
                col_dict['name'] = f"{trend_icon} {variation_pct:+.1f}%"
                col_dict['class'] = trend_class
                cols.append(col_dict)
            elif lbl == 'vertical_current':
                col_dict = report._build_column_dict(vertical_current / 100, col, options=options)
                col_dict['name'] = f"{vertical_current:.1f}%"
                cols.append(col_dict)
            elif lbl == 'target':
                cols.append({'name': '', 'no_format': ''})
            else:
                cols.append({'name': '', 'no_format': ''})

        css_class = ''
        if item['type'] in ['total', 'calculated']:
            css_class = 'o_account_reports_level0 font-weight-bold'
        elif item['type'] == 'subtotal':
            css_class = 'o_account_reports_level1 font-weight-bold'

        return {
            'id': report._get_generic_line_id(None, None, markup=f"pl_{item['code']}"),
            'name': item['name'],
            'level': item['level'],
            'unfoldable': item['type'] in ['total', 'subtotal'],
            'unfolded': True,
            'columns': cols,
            'class': css_class,
        }

    def _get_account_line(self, report, options, account, current, previous, total_current, total_previous, level):
        """
        Construye una línea de detalle para una cuenta individual.

        Args:
            report: Objeto del reporte
            options: Opciones del reporte
            account: Dict con 'code', 'name', 'balance'
            current: Saldo del periodo actual
            previous: Saldo del periodo anterior
            total_current: Total ingresos periodo actual (para análisis vertical)
            total_previous: Total ingresos periodo anterior
            level: Nivel de indentación
        """
        cols = []

        variation = current - previous
        variation_pct = ((current - previous) / abs(previous) * 100) if previous else (100 if current else 0)

        # Análisis vertical (% sobre ingresos)
        vertical_current = (current / total_current * 100) if total_current else 0

        # Icono de tendencia
        trend_icon = ''
        trend_class = ''
        if variation > 0:
            trend_icon = '↑'
            trend_class = 'text-success'
        elif variation < 0:
            trend_icon = '↓'
            trend_class = 'text-danger'

        for col in options['columns']:
            lbl = col['expression_label']

            if lbl == 'current_balance':
                cols.append(report._build_column_dict(current, col, options=options))
            elif lbl == 'previous_balance':
                cols.append(report._build_column_dict(previous, col, options=options))
            elif lbl == 'variation':
                col_dict = report._build_column_dict(variation, col, options=options)
                col_dict['class'] = trend_class
                cols.append(col_dict)
            elif lbl == 'variation_percent':
                col_dict = report._build_column_dict(variation_pct / 100, col, options=options)
                col_dict['name'] = f"{trend_icon} {variation_pct:+.1f}%"
                col_dict['class'] = trend_class
                cols.append(col_dict)
            elif lbl == 'vertical_current':
                col_dict = report._build_column_dict(vertical_current / 100, col, options=options)
                col_dict['name'] = f"{vertical_current:.1f}%"
                cols.append(col_dict)
            elif lbl == 'target':
                cols.append({'name': '', 'no_format': ''})
            else:
                cols.append({'name': '', 'no_format': ''})

        # Nombre de la cuenta con código
        account_name = f"{account['code']} - {account['name']}"

        return {
            'id': report._get_generic_line_id('account.account', None, markup=f"acc_{account['code']}"),
            'name': account_name,
            'level': level,
            'unfoldable': False,
            'columns': cols,
            'class': f'o_account_reports_level{level}',
        }

    def _get_indicator_comparison_line(self, report, options, name, current_value, previous_value,
                                        target, tag, is_percentage=False, is_monetary=False, single_value=False):
        """Construye linea de indicador con iconos de tendencia."""
        cols = []

        if current_value is not None and previous_value is not None and not single_value:
            variation = current_value - previous_value
        else:
            variation = 0

        # Icono de tendencia para la variación
        trend_icon = ''
        trend_class = ''
        if variation > 0:
            trend_icon = '↑'
            trend_class = 'text-success'
        elif variation < 0:
            trend_icon = '↓'
            trend_class = 'text-danger'

        # Icono de cumplimiento de meta
        def get_target_icon(value, target_str):
            """Determina si se cumple la meta y retorna icono."""
            if value is None:
                return '<i class="fa fa-minus text-muted"></i>', 'text-muted'
            try:
                # Parsear meta como "> 30%" o "< 50%"
                if '>' in target_str:
                    threshold = float(target_str.replace('>', '').replace('%', '').strip())
                    if value >= threshold:
                        return '<i class="fa fa-check-circle text-success"></i>', 'text-success'
                    else:
                        return '<i class="fa fa-times-circle text-danger"></i>', 'text-danger'
                elif '<' in target_str:
                    threshold = float(target_str.replace('<', '').replace('%', '').strip())
                    if value <= threshold:
                        return '<i class="fa fa-check-circle text-success"></i>', 'text-success'
                    else:
                        return '<i class="fa fa-times-circle text-danger"></i>', 'text-danger'
            except:
                pass
            return '<i class="fa fa-minus text-muted"></i>', 'text-muted'

        target_icon, target_class = get_target_icon(current_value, target)

        for col in options['columns']:
            lbl = col['expression_label']

            if lbl == 'current_balance':
                if current_value is None:
                    display = 'N/A'
                elif is_percentage:
                    display = f"{current_value:.2f}%"
                elif is_monetary:
                    col_dict = report._build_column_dict(current_value, col, options=options)
                    cols.append(col_dict)
                    continue
                else:
                    display = f"{current_value:,.2f}"
                cols.append({'name': display, 'no_format': current_value, 'class': ''})

            elif lbl == 'previous_balance':
                if single_value:
                    cols.append({'name': '-', 'no_format': '', 'class': 'text-muted'})
                elif previous_value is None:
                    cols.append({'name': 'N/A', 'no_format': '', 'class': 'text-muted'})
                elif is_percentage:
                    cols.append({'name': f"{previous_value:.2f}%", 'no_format': previous_value})
                elif is_monetary:
                    col_dict = report._build_column_dict(previous_value, col, options=options)
                    cols.append(col_dict)
                else:
                    cols.append({'name': f"{previous_value:,.2f}", 'no_format': previous_value})

            elif lbl == 'variation':
                if single_value:
                    cols.append({'name': '-', 'no_format': '', 'class': 'text-muted'})
                elif is_percentage:
                    cols.append({
                        'name': f"{trend_icon} {variation:+.2f}%",
                        'no_format': variation,
                        'class': trend_class
                    })
                elif is_monetary:
                    col_dict = report._build_column_dict(variation, col, options=options)
                    col_dict['name'] = f"{trend_icon} {col_dict.get('name', '')}"
                    col_dict['class'] = trend_class
                    cols.append(col_dict)
                else:
                    cols.append({
                        'name': f"{trend_icon} {variation:+,.2f}",
                        'no_format': variation,
                        'class': trend_class
                    })

            elif lbl == 'variation_percent':
                if single_value or previous_value is None or previous_value == 0:
                    cols.append({'name': '-', 'no_format': '', 'class': 'text-muted'})
                else:
                    var_pct = ((current_value - previous_value) / abs(previous_value)) * 100 if previous_value else 0
                    cols.append({
                        'name': f"{trend_icon} {var_pct:+.1f}%",
                        'no_format': var_pct / 100,
                        'class': trend_class
                    })

            elif lbl == 'vertical_current':
                cols.append({'name': '-', 'no_format': '', 'class': 'text-muted'})

            elif lbl == 'target':
                cols.append({
                    'name': f"{target_icon} {target}",
                    'no_format': target,
                    'class': target_class
                })

            else:
                cols.append({'name': '', 'no_format': ''})

        return {
            'id': report._get_generic_line_id(None, None, markup=f'ind_{tag}'),
            'name': f'<i class="fa fa-chart-line"></i> {name}',
            'level': 2,
            'unfoldable': False,
            'columns': cols,
        }
