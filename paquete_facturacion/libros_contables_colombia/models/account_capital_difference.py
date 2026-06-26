# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api, _
from odoo.tools import SQL
from odoo.exceptions import UserError
from datetime import timedelta


class AccountCapitalDifferenceHandler(models.AbstractModel):
    _name = 'account.capital.difference.handler'
    _inherit = ['account.report.custom.handler', 'sql.helper.mixin']
    _description = 'Diferencia en el Capital'

    def _get_custom_display_config(self):
        return {
            'css_custom_class': 'capital_difference_report',
            'templates': {
                'AccountReportLineName': 'account_reports.GeneralLedgerLineName',
            },
        }

    def _custom_options_initializer(self, report, options, previous_options=None):
        super()._custom_options_initializer(report, options, previous_options=previous_options)
        options['show_details'] = True
        if previous_options:
            if 'show_details' in previous_options:
                options['show_details'] = previous_options['show_details']

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        lines = []

        # Obtener datos de cuentas de patrimonio
        account_data = self._query_capital_values(report, options)

        if not account_data:
            return [(0, self._get_no_data_line(report, options))]

        # Procesar datos y aplicar lógica de cómputo
        processed_data = []
        total_initial_debit = 0
        total_initial_credit = 0
        total_final_debit = 0
        total_final_credit = 0
        total_variation_debit = 0
        total_variation_credit = 0

        for account, column_group_results in account_data:
            for column_group_key, results in column_group_results.items():
                initial_data = results.get('initial_balance', {})
                final_data = results.get('final_balance', {})

                initial_balance = initial_data.get('balance', 0.0)
                final_balance = final_data.get('balance', 0.0)
                variation = final_balance - initial_balance

                # Aplicar lógica de cómputo según la naturaleza de la cuenta
                account_info = {
                    'account': account,
                    'account_code': account.code,
                    'account_name': account.name,
                    'account_type': account.account_type,
                    'initial_balance': initial_balance,
                    'final_balance': final_balance,
                    'variation': variation,
                }

                # Calcular valores para débito/crédito según naturaleza de cuenta
                computed_values = self._compute_account_values(account_info)
                processed_data.append(computed_values)

                # Acumular totales
                total_initial_debit += computed_values['initial_debit']
                total_initial_credit += computed_values['initial_credit']
                total_final_debit += computed_values['final_debit']
                total_final_credit += computed_values['final_credit']
                total_variation_debit += computed_values['variation_debit']
                total_variation_credit += computed_values['variation_credit']

        # Construir líneas del reporte
        lines.append(self._get_main_header_line(report, options))

        # --- Capital Inicial ---
        lines.append(self._get_section_header_line(report, options, _('Capital Inicial'), 'initial'))
        if options['show_details']:
            for data in processed_data:
                if data['initial_debit'] != 0 or data['initial_credit'] != 0:
                    lines.append(self._get_capital_line(report, options, data, 'initial'))
        lines.append(self._get_subtotal_line(report, options, _('Total Capital Inicial'),
                                           total_initial_debit, total_initial_credit, 'initial'))

        # --- Variación del Capital ---
        lines.append(self._get_section_header_line(report, options, _('Variación del Capital'), 'variation'))
        if options['show_details']:
            for data in processed_data:
                if data['variation_debit'] != 0 or data['variation_credit'] != 0:
                    lines.append(self._get_capital_line(report, options, data, 'variation'))
        lines.append(self._get_subtotal_line(report, options, _('Total Variación'),
                                           total_variation_debit, total_variation_credit, 'variation'))

        # --- Capital Final ---
        lines.append(self._get_section_header_line(report, options, _('Capital Final'), 'final'))
        if options['show_details']:
            for data in processed_data:
                if data['final_debit'] != 0 or data['final_credit'] != 0:
                    lines.append(self._get_capital_line(report, options, data, 'final'))
        lines.append(self._get_subtotal_line(report, options, _('Total Capital Final'),
                                           total_final_debit, total_final_credit, 'final'))

        return [(0, line) for line in lines]

    def _compute_account_values(self, account_info):
        """Aplica la lógica de cómputo según la naturaleza de la cuenta."""
        initial_balance = account_info['initial_balance']
        final_balance = account_info['final_balance']
        variation = account_info['variation']

        # Las cuentas de patrimonio normalmente tienen naturaleza crédito
        # Si el balance es negativo, se muestra en crédito
        # Si el balance es positivo, se muestra en débito (caso excepcional)

        result = {
            'account': account_info['account'],
            'account_code': account_info['account_code'],
            'account_name': account_info['account_name'],
            'account_type': account_info['account_type'],
            # Saldo inicial
            'initial_debit': max(initial_balance, 0.0),
            'initial_credit': max(-initial_balance, 0.0),
            # Saldo final
            'final_debit': max(final_balance, 0.0),
            'final_credit': max(-final_balance, 0.0),
            # Variación
            'variation_debit': max(variation, 0.0),
            'variation_credit': max(-variation, 0.0),
        }

        return result

    def _query_capital_values(self, report, options):
        """Query usando el patrón estándar de Odoo 18 para cuentas de patrimonio."""
        query = self._get_capital_query(report, options)

        if not query:
            return []

        groupby_accounts = {}
        self._cr.execute(query)

        for res in self._cr.dictfetchall():
            if res['groupby'] is None:
                continue

            column_group_key = res['column_group_key']
            key = res['key']
            account_id = res['account_id']

            # Crear estructura anidada: account_id -> column_group_key -> key
            if account_id not in groupby_accounts:
                groupby_accounts[account_id] = {col_group_key: {} for col_group_key in options['column_groups']}

            groupby_accounts[account_id][column_group_key][key] = res

        # Obtener registros de cuentas
        result = []
        for account_id, column_group_results in groupby_accounts.items():
            account = self.env['account.account'].browse(account_id)
            result.append((account, column_group_results))

        return result

    def _get_capital_query(self, report, options) -> SQL:
        """Construye consultas para cuentas de patrimonio usando Odoo 18 API."""
        options_by_column_group = report._split_options_per_column_group(options)

        queries = []

        for column_group_key, options_group in options_by_column_group.items():
            # Dominio para cuentas de patrimonio
            domain = [
                ('account_id.account_type', 'in', ['equity', 'equity_unaffected']),
            ]

            # ============================================
            # 1) Saldo inicial: hasta date_from - 1 día
            # ============================================
            initial_options = self._get_options_initial_balance(options_group)
            query_initial = report._get_report_query(initial_options, 'from_beginning', domain=domain)

            queries.append(SQL(
                """
                SELECT
                    account_move_line.account_id                            AS account_id,
                    account_move_line.account_id                            AS groupby,
                    'initial_balance'                                       AS key,
                    %(column_group_key)s                                    AS column_group_key,
                    SUM(%(balance_select)s)                                 AS balance
                FROM %(table_references)s
                %(currency_table_join)s
                WHERE %(search_condition)s
                GROUP BY account_move_line.account_id
                """,
                column_group_key=column_group_key,
                table_references=query_initial.from_clause,
                balance_select=report._currency_table_apply_rate(SQL("account_move_line.balance")),
                currency_table_join=report._currency_table_aml_join(initial_options),
                search_condition=query_initial.where_clause,
            ))

            # ============================================
            # 2) Saldo final: hasta date_to
            # ============================================
            final_options = self._get_options_final_balance(options_group)
            query_final = report._get_report_query(final_options, 'from_beginning', domain=domain)

            queries.append(SQL(
                """
                SELECT
                    account_move_line.account_id                            AS account_id,
                    account_move_line.account_id                            AS groupby,
                    'final_balance'                                         AS key,
                    %(column_group_key)s                                    AS column_group_key,
                    SUM(%(balance_select)s)                                 AS balance
                FROM %(table_references)s
                %(currency_table_join)s
                WHERE %(search_condition)s
                GROUP BY account_move_line.account_id
                """,
                column_group_key=column_group_key,
                table_references=query_final.from_clause,
                balance_select=report._currency_table_apply_rate(SQL("account_move_line.balance")),
                currency_table_join=report._currency_table_aml_join(final_options),
                search_condition=query_final.where_clause,
            ))

        return SQL(" UNION ALL ").join(queries)

    def _get_options_initial_balance(self, options):
        """Crea opciones para saldo inicial usando el patrón de Odoo 18."""
        new_options = options.copy()
        date_to = new_options['comparison']['periods'][-1]['date_from'] if new_options.get('comparison', {}).get('periods') else new_options['date']['date_from']
        new_date_to = fields.Date.from_string(date_to) - timedelta(days=1)

        date_from = fields.Date.from_string(new_options['date']['date_from'])
        current_fiscalyear_dates = self.env.company.compute_fiscalyear_dates(date_from)

        if date_from == current_fiscalyear_dates['date_from']:
            previous_fiscalyear_dates = self.env.company.compute_fiscalyear_dates(date_from - timedelta(days=1))
            new_date_from = previous_fiscalyear_dates['date_from']
            include_current_year_in_unaff_earnings = True
        else:
            new_date_from = current_fiscalyear_dates['date_from']
            include_current_year_in_unaff_earnings = False

        # Usar _get_dates_period para crear las opciones de fecha correctamente
        new_options['date'] = self.env['account.report']._get_dates_period(
            new_date_from,
            new_date_to,
            'range',
        )
        new_options['include_current_year_in_unaff_earnings'] = include_current_year_in_unaff_earnings

        return new_options

    def _get_options_final_balance(self, options):
        """Crea opciones para saldo final usando el patrón de Odoo 18."""
        new_options = options.copy()
        date_to = fields.Date.from_string(new_options['date']['date_to'])
        current_fiscalyear_dates = self.env.company.compute_fiscalyear_dates(date_to)

        # Usar _get_dates_period para crear las opciones de fecha correctamente
        new_options['date'] = self.env['account.report']._get_dates_period(
            current_fiscalyear_dates['date_from'],
            date_to,
            'range',
        )

        return new_options

    def _get_main_header_line(self, report, options):
        return {
            'id': report._get_generic_line_id(None, None, markup='main_header'),
            'name': _('DIFERENCIA EN EL CAPITAL'),
            'level': 1,
            'unfoldable': False,
            'unfolded': True,
            'columns': [{'name': ''} for _ in options['columns']],
        }

    def _get_section_header_line(self, report, options, name, tag):
        return {
            'id': report._get_generic_line_id(None, None, markup=f'section_{tag}'),
            'name': name,
            'level': 2,
            'unfoldable': False,
            'unfolded': True,
            'columns': [{'name': ''} for _ in options['columns']],
        }

    def _get_capital_line(self, report, options, data, tag):
        """Crea línea de cuenta con lógica de cómputo aplicada."""
        cols = []
        for col in options['columns']:
            lbl = col['expression_label']
            val = None

            if lbl == 'account_code':
                val = data['account_code']
            elif lbl == 'account_name':
                val = data['account_name']
            elif lbl == 'initial_debit':
                val = data['initial_debit'] if tag == 'initial' else None
            elif lbl == 'initial_credit':
                val = data['initial_credit'] if tag == 'initial' else None
            elif lbl == 'variation_debit':
                val = data['variation_debit'] if tag == 'variation' else None
            elif lbl == 'variation_credit':
                val = data['variation_credit'] if tag == 'variation' else None
            elif lbl == 'final_debit':
                val = data['final_debit'] if tag == 'final' else None
            elif lbl == 'final_credit':
                val = data['final_credit'] if tag == 'final' else None

            cols.append(report._build_column_dict(val, col, options=options))

        return {
            'id': report._get_generic_line_id('account.account', data['account'].id, markup=tag),
            'name': f"{data['account_code']} - {data['account_name']}",
            'level': 3,
            'unfoldable': False,
            'columns': cols,
        }

    def _get_subtotal_line(self, report, options, name, debit_value, credit_value, tag):
        """Crea línea de subtotal con valores de débito y crédito."""
        cols = []
        for col in options['columns']:
            lbl = col['expression_label']
            val = None

            if lbl == 'account_code':
                val = None
            elif lbl == 'account_name':
                val = None
            elif lbl == 'initial_debit' and tag == 'initial':
                val = debit_value
            elif lbl == 'initial_credit' and tag == 'initial':
                val = credit_value
            elif lbl == 'variation_debit' and tag == 'variation':
                val = debit_value
            elif lbl == 'variation_credit' and tag == 'variation':
                val = credit_value
            elif lbl == 'final_debit' and tag == 'final':
                val = debit_value
            elif lbl == 'final_credit' and tag == 'final':
                val = credit_value

            cols.append(report._build_column_dict(val, col, options=options))

        return {
            'id': report._get_generic_line_id(None, None, markup=f'subtotal_{tag}'),
            'name': name,
            'level': 2,
            'unfoldable': False,
            'columns': cols,
            'class': 'font-weight-bold o_account_reports_totals_below_sections',
        }

    def _get_no_data_line(self, report, options):
        return {
            'id': report._get_generic_line_id(None, None, markup='no_data'),
            'name': _('No hay cuentas de patrimonio con movimientos en el período seleccionado'),
            'level': 1,
            'unfoldable': False,
            'columns': [{'name': ''} for _ in options['columns']],
        }

    def format_value(self, value):
        return self.env.company.currency_id.format(value)
