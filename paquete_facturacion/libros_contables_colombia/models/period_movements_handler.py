# -*- coding: utf-8 -*-
"""
Handler para Balance de Movimientos del Periodo - Colombia
Muestra debitos, creditos, saldo neto y numero de asientos por cuenta.
"""
from odoo import models, _
from odoo.tools import SQL
from collections import defaultdict
import logging

_logger = logging.getLogger(__name__)


class PeriodMovementsReportHandler(models.AbstractModel):
    """Handler para Balance de Movimientos del Periodo."""
    _name = 'co.period.movements.report.handler'
    _inherit = 'account.report.custom.handler'
    _description = 'Balance de Movimientos del Periodo - Handler'

    def _get_custom_display_config(self):
        return {
            'css_custom_class': 'period_movements_report_co',
        }

    def _custom_options_initializer(self, report, options, previous_options):
        """Inicializa opciones del reporte."""
        super()._custom_options_initializer(report, options, previous_options=previous_options)
        options.setdefault('unfold_all', False)

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        """Genera lineas del reporte de movimientos del periodo."""
        lines = []
        try:
            movements_data = self._get_period_movements_data(report, options)

            if not movements_data:
                lines.append((0, self._get_no_data_line(report, options)))
                return lines

            totals = {'debit': 0, 'credit': 0, 'balance': 0, 'moves': 0}

            for account_data in movements_data:
                line = self._build_account_line(report, options, account_data)
                lines.append((0, line))
                totals['debit'] += account_data['debit']
                totals['credit'] += account_data['credit']
                totals['balance'] += account_data['balance']
                totals['moves'] += account_data['moves']

            # Linea de totales
            lines.append((0, self._build_total_line(report, options, totals)))

        except Exception as e:
            _logger.error(f"Error en Balance de Movimientos: {str(e)}")
            lines.append((0, self._get_error_line(report, options, str(e))))

        return lines

    def _get_period_movements_data(self, report, options):
        """Obtiene datos de movimientos por cuenta en el periodo."""
        company_id = str(self.env.company.root_id.id or self.env.company.id)

        date_from = options['date'].get('date_from')
        date_to = options['date'].get('date_to')

        query = f"""
            SELECT
                aml.account_id,
                COALESCE(aa.code_store->>'{company_id}', '') as account_code,
                aa.name->>'es_CO' as account_name,
                COALESCE(SUM(aml.debit), 0) as debit,
                COALESCE(SUM(aml.credit), 0) as credit,
                COALESCE(SUM(aml.balance), 0) as balance,
                COUNT(DISTINCT aml.move_id) as moves
            FROM account_move_line aml
            JOIN account_account aa ON aa.id = aml.account_id
            JOIN account_move am ON am.id = aml.move_id
            WHERE am.state = 'posted'
              AND am.company_id = {self.env.company.id}
              AND aml.date BETWEEN '{date_from}' AND '{date_to}'
            GROUP BY aml.account_id, aa.code_store, aa.name
            HAVING SUM(aml.debit) != 0 OR SUM(aml.credit) != 0
            ORDER BY COALESCE(aa.code_store->>'{company_id}', '')
        """

        self._cr.execute(query)
        return self._cr.dictfetchall()

    def _build_account_line(self, report, options, account_data):
        """Construye una linea de cuenta."""
        account_id = account_data['account_id']
        code = account_data['account_code'] or ''
        name = account_data['account_name'] or ''

        # Determinar nivel basado en longitud del codigo
        level = 2
        if len(code) <= 2:
            level = 0
        elif len(code) <= 4:
            level = 1

        columns = self._build_columns(report, options, account_data)

        return {
            'id': report._get_generic_line_id('account.account', account_id, markup=f'pm_{account_id}'),
            'name': f"{code} {name}",
            'level': level,
            'unfoldable': True,
            'unfolded': options.get('unfold_all', False),
            'expand_function': '_report_expand_unfoldable_line_period_movements',
            'columns': columns,
            'caret_options': 'account.account',
        }

    def _build_total_line(self, report, options, totals):
        """Construye la linea de totales."""
        columns = self._build_columns(report, options, totals)

        return {
            'id': report._get_generic_line_id(None, None, markup='pm_total'),
            'name': _('TOTAL'),
            'level': 0,
            'class': 'total o_account_reports_level0',
            'columns': columns,
        }

    def _build_columns(self, report, options, data):
        """Construye las columnas usando options['columns']."""
        columns = []
        for col in options.get('columns', []):
            expr_label = col.get('expression_label', '')

            if expr_label == 'debit':
                value = data.get('debit', 0)
            elif expr_label == 'credit':
                value = data.get('credit', 0)
            elif expr_label == 'balance':
                value = data.get('balance', 0)
            elif expr_label == 'moves':
                value = data.get('moves', 0)
            else:
                value = 0

            columns.append(report._build_column_dict(value, col, options=options))

        return columns

    def _report_expand_unfoldable_line_period_movements(self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None):
        """Expande una linea para mostrar los asientos de la cuenta."""
        report = self.env['account.report'].browse(options['report_id'])
        lines = []

        # Extraer account_id del markup
        model_info = report._get_model_info_from_id(line_dict_id)
        if not model_info or model_info[0] != 'account.account':
            return {'lines': [], 'offset_increment': 0, 'has_more': False}

        account_id = model_info[1]
        company_id = str(self.env.company.root_id.id or self.env.company.id)
        date_from = options['date'].get('date_from')
        date_to = options['date'].get('date_to')

        # Obtener movimientos de la cuenta
        query = f"""
            SELECT
                am.id as move_id,
                am.name as move_name,
                am.date,
                COALESCE(rp.name, '') as partner_name,
                COALESCE(SUM(aml.debit), 0) as debit,
                COALESCE(SUM(aml.credit), 0) as credit,
                COALESCE(SUM(aml.balance), 0) as balance
            FROM account_move_line aml
            JOIN account_move am ON am.id = aml.move_id
            LEFT JOIN res_partner rp ON rp.id = aml.partner_id
            WHERE am.state = 'posted'
              AND aml.account_id = {account_id}
              AND am.company_id = {self.env.company.id}
              AND aml.date BETWEEN '{date_from}' AND '{date_to}'
            GROUP BY am.id, am.name, am.date, rp.name
            ORDER BY am.date, am.name
            LIMIT 100 OFFSET {offset}
        """

        self._cr.execute(query)
        moves = self._cr.dictfetchall()

        for move in moves:
            col_map = {
                'debit': move['debit'],
                'credit': move['credit'],
                'balance': move['balance'],
                'moves': 1,
            }
            columns = self._build_columns(report, options, col_map)

            lines.append({
                'id': report._get_generic_line_id('account.move', move['move_id'], parent_line_id=line_dict_id),
                'name': f"{move['move_name']} - {move['date']} - {move['partner_name']}",
                'level': 3,
                'parent_id': line_dict_id,
                'caret_options': 'account.move',
                'columns': columns,
            })

        return {
            'lines': lines,
            'offset_increment': len(lines),
            'has_more': len(lines) == 100,
        }

    def _get_no_data_line(self, report, options):
        """Linea cuando no hay datos."""
        return {
            'id': report._get_generic_line_id(None, None, markup='pm_no_data'),
            'name': _('No hay movimientos en el periodo seleccionado'),
            'level': 0,
            'columns': [{'name': '', 'class': ''} for _ in options.get('columns', [])],
        }

    def _get_error_line(self, report, options, error_msg):
        """Linea de error."""
        return {
            'id': report._get_generic_line_id(None, None, markup='pm_error'),
            'name': f"Error: {error_msg}",
            'level': 0,
            'class': 'text-danger',
            'columns': [{'name': '', 'class': ''} for _ in options.get('columns', [])],
        }
