# -*- coding: utf-8 -*-
"""
Handler para Estado de Cambios en el Patrimonio (EEF) - Colombia
Segun NIIF para PYMES Seccion 6
"""

from odoo import models, fields, api, _
from odoo.tools import SQL
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)


class EquityChangesReportHandler(models.AbstractModel):
    """
    Handler para Estado de Cambios en el Patrimonio Colombia.
    Muestra movimientos en cada componente del patrimonio.
    """
    _name = 'co.equity.changes.report.handler'
    _inherit = ['account.report.custom.handler', 'sql.helper.mixin', 'report.formulas.mixin']
    _description = 'Estado de Cambios en el Patrimonio Colombia'

    # =====================================================
    # COMPONENTES DEL PATRIMONIO (PUC Colombia)
    # =====================================================

    EQUITY_COMPONENTS = [
        ('31', 'Capital Social', 'capital'),
        ('32', 'Superavit de Capital', 'surplus'),
        ('33', 'Reservas', 'reserves'),
        ('34', 'Revalorizacion del Patrimonio', 'revaluation'),
        ('35', 'Dividendos Decretados', 'dividends'),
        ('36', 'Resultados del Ejercicio', 'current_year'),
        ('37', 'Resultados de Ejercicios Anteriores', 'prior_years'),
        ('38', 'Superavit por Valorizaciones', 'valuation_surplus'),
    ]

    # =====================================================
    # CONFIGURACION
    # =====================================================

    def _get_custom_display_config(self):
        return {
            'css_custom_class': 'equity_changes_report_co',
            'templates': {
                'AccountReportLineName': 'account_reports.GeneralLedgerLineName',
            },
            'components': {
                'AccountReportFilters': 'libros_contables_colombia.TrialBalancePartnerFilters',
            },
        }

    def _custom_options_initializer(self, report, options, previous_options=None):
        super()._custom_options_initializer(report, options, previous_options=previous_options)

        options['show_movements_detail'] = True
        if previous_options:
            if 'show_movements_detail' in previous_options:
                options['show_movements_detail'] = previous_options['show_movements_detail']

    # =====================================================
    # GENERADOR DE LINEAS
    # =====================================================

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        lines = []

        # Obtener datos de cambios en patrimonio
        equity_data = self._get_equity_changes_data(report, options)

        # Encabezado
        lines.append(self._get_main_header(report, options))

        # Saldos Iniciales
        lines.append(self._get_section_line(report, options, 'SALDOS AL INICIO DEL PERIODO', 'begin', level=1))
        for code, name, tag in self.EQUITY_COMPONENTS:
            balance = equity_data['beginning'].get(tag, 0)
            if balance != 0:
                lines.append(self._get_component_line(report, options, name, balance, f'begin_{tag}', level=2))
        lines.append(self._get_subtotal_line(report, options, 'Total Patrimonio Inicial',
                                              equity_data['totals']['beginning'], 'begin_total'))

        # Cambios del Periodo
        lines.append(self._get_section_line(report, options, 'CAMBIOS EN EL PATRIMONIO', 'changes', level=1))

        # Aportes de Capital
        capital_increase = equity_data['changes'].get('capital_increase', 0)
        if capital_increase != 0:
            lines.append(self._get_change_line(report, options, '(+) Aportes de Capital',
                                               capital_increase, 'capital_inc', level=2))

        # Resultado del Ejercicio
        net_income = equity_data['changes'].get('net_income', 0)
        lines.append(self._get_change_line(report, options, '(+/-) Resultado del Ejercicio',
                                           net_income, 'net_income', level=2))

        # Dividendos Decretados
        dividends = equity_data['changes'].get('dividends', 0)
        if dividends != 0:
            lines.append(self._get_change_line(report, options, '(-) Dividendos Decretados',
                                               -abs(dividends), 'dividends', level=2))

        # Traslado a Reservas
        reserves_transfer = equity_data['changes'].get('reserves_transfer', 0)
        if reserves_transfer != 0:
            lines.append(self._get_change_line(report, options, '(+) Traslado a Reservas',
                                               reserves_transfer, 'reserves', level=2))

        # Otros Movimientos
        other_changes = equity_data['changes'].get('other', 0)
        if other_changes != 0:
            lines.append(self._get_change_line(report, options, '(+/-) Otros Cambios',
                                               other_changes, 'other', level=2))

        # Total Cambios
        total_changes = equity_data['totals']['changes']
        lines.append(self._get_subtotal_line(report, options, 'Total Cambios del Periodo',
                                              total_changes, 'changes_total'))

        # Saldos Finales
        lines.append(self._get_section_line(report, options, 'SALDOS AL FINAL DEL PERIODO', 'end', level=1))
        for code, name, tag in self.EQUITY_COMPONENTS:
            balance = equity_data['ending'].get(tag, 0)
            if balance != 0:
                lines.append(self._get_component_line(report, options, name, balance, f'end_{tag}', level=2))
        lines.append(self._get_total_line(report, options, 'TOTAL PATRIMONIO FINAL',
                                           equity_data['totals']['ending'], 'end_total'))

        return [(0, line) for line in lines]

    # =====================================================
    # CONSULTAS DE DATOS
    # =====================================================

    def _get_equity_changes_data(self, report, options):
        """Obtiene datos de cambios en patrimonio."""
        date_from = options.get('date', {}).get('date_from')
        date_to = options.get('date', {}).get('date_to')
        company_id = self._get_company_id_for_sql()

        data = {
            'beginning': {},
            'ending': {},
            'changes': {},
            'totals': {'beginning': 0, 'ending': 0, 'changes': 0}
        }

        # Fecha del dia anterior al inicio
        date_before = (fields.Date.from_string(date_from) - timedelta(days=1)).strftime('%Y-%m-%d')

        # Saldos iniciales y finales por componente
        total_beginning = 0
        total_ending = 0

        for code, name, tag in self.EQUITY_COMPONENTS:
            # Saldo inicial
            beginning = self._get_component_balance(code, date_before, company_id)
            data['beginning'][tag] = abs(beginning)
            total_beginning += abs(beginning)

            # Saldo final
            ending = self._get_component_balance(code, date_to, company_id)
            data['ending'][tag] = abs(ending)
            total_ending += abs(ending)

        data['totals']['beginning'] = total_beginning
        data['totals']['ending'] = total_ending

        # Cambios del periodo
        # Resultado del ejercicio (cuentas 4, 5, 6)
        income = self._get_range_balance(['4'], date_from, date_to, company_id)
        expenses = self._get_range_balance(['5', '6'], date_from, date_to, company_id)
        data['changes']['net_income'] = abs(income) - expenses

        # Aportes de capital (movimientos credito en 31)
        data['changes']['capital_increase'] = self._get_credit_movements('31', date_from, date_to, company_id)

        # Dividendos (movimientos debito en 35 o 36)
        data['changes']['dividends'] = self._get_debit_movements('35', date_from, date_to, company_id)

        # Reservas (movimientos credito en 33)
        data['changes']['reserves_transfer'] = self._get_credit_movements('33', date_from, date_to, company_id)

        # Otros cambios
        data['changes']['other'] = total_ending - total_beginning - data['changes']['net_income'] - \
                                   data['changes']['capital_increase'] + data['changes']['dividends'] - \
                                   data['changes']['reserves_transfer']

        data['totals']['changes'] = total_ending - total_beginning

        return data

    def _get_component_balance(self, code_prefix, date_to, company_id):
        """Obtiene saldo de componente del patrimonio."""
        query = f"""
            SELECT COALESCE(SUM(aml.balance), 0)
            FROM account_move_line aml
            JOIN account_move am ON am.id = aml.move_id
            JOIN account_account aa ON aa.id = aml.account_id
            WHERE am.state = 'posted'
              AND aml.date <= '{date_to}'
              AND COALESCE(aa.code_store->>'{company_id}', '') LIKE '{code_prefix}%'
        """
        self._cr.execute(query)
        result = self._cr.fetchone()
        return result[0] if result else 0.0

    def _get_range_balance(self, prefixes, date_from, date_to, company_id):
        """Obtiene saldo en rango de fechas."""
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

    def _get_credit_movements(self, code_prefix, date_from, date_to, company_id):
        """Obtiene movimientos credito del periodo."""
        query = f"""
            SELECT COALESCE(SUM(aml.credit), 0)
            FROM account_move_line aml
            JOIN account_move am ON am.id = aml.move_id
            JOIN account_account aa ON aa.id = aml.account_id
            WHERE am.state = 'posted'
              AND aml.date >= '{date_from}'
              AND aml.date <= '{date_to}'
              AND COALESCE(aa.code_store->>'{company_id}', '') LIKE '{code_prefix}%'
        """
        self._cr.execute(query)
        result = self._cr.fetchone()
        return result[0] if result else 0.0

    def _get_debit_movements(self, code_prefix, date_from, date_to, company_id):
        """Obtiene movimientos debito del periodo."""
        query = f"""
            SELECT COALESCE(SUM(aml.debit), 0)
            FROM account_move_line aml
            JOIN account_move am ON am.id = aml.move_id
            JOIN account_account aa ON aa.id = aml.account_id
            WHERE am.state = 'posted'
              AND aml.date >= '{date_from}'
              AND aml.date <= '{date_to}'
              AND COALESCE(aa.code_store->>'{company_id}', '') LIKE '{code_prefix}%'
        """
        self._cr.execute(query)
        result = self._cr.fetchone()
        return result[0] if result else 0.0

    # =====================================================
    # CONSTRUCCION DE LINEAS
    # =====================================================

    def _get_main_header(self, report, options):
        return {
            'id': report._get_generic_line_id(None, None, markup='main_header'),
            'name': _('ESTADO DE CAMBIOS EN EL PATRIMONIO'),
            'level': 0,
            'unfoldable': False,
            'columns': [{'name': ''} for _ in options['columns']],
            'class': 'o_account_reports_level0 font-weight-bold text-center',
        }

    def _get_section_line(self, report, options, name, tag, level=1):
        return {
            'id': report._get_generic_line_id(None, None, markup=f'section_{tag}'),
            'name': name,
            'level': level,
            'unfoldable': False,
            'columns': [{'name': ''} for _ in options['columns']],
            'class': 'o_account_reports_level1 font-weight-bold',
        }

    def _get_component_line(self, report, options, name, value, tag, level=2):
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

    def _get_change_line(self, report, options, name, value, tag, level=2):
        cols = []
        for col in options['columns']:
            if col['expression_label'] == 'balance':
                cols.append(report._build_column_dict(value, col, options=options))
            else:
                cols.append({'name': ''})

        return {
            'id': report._get_generic_line_id(None, None, markup=f'change_{tag}'),
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
