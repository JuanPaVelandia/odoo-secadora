# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import json

from odoo import models, fields, api, _
from odoo.tools.misc import format_date
from odoo.tools import get_lang, SQL
from odoo.exceptions import UserError

from datetime import timedelta
from collections import defaultdict


class AccountInventoryBookHandler(models.AbstractModel):
    _name = 'account.inventory.book.colombia.handler'
    _inherit = 'account.report.custom.handler'
    _description = 'Libro de Inventario Colombia'

    def _get_custom_display_config(self):
        return {
            'css_custom_class': 'inventory_book_colombia',
            'templates': {
                'AccountReportLineName': 'account_reports.GeneralLedgerLineName',
            },
            'components': {
                'AccountReportFilters': 'libros_contables_colombia.TrialBalancePartnerFilters',
            },
        }

    def _custom_options_initializer(self, report, options, previous_options=None):
        super()._custom_options_initializer(report, options, previous_options=previous_options)
        # Configurar opciones específicas para el libro de inventario
        options['show_asset_details'] = True
        options['show_liability_details'] = True
        options['show_equity_details'] = True

        if previous_options:
            if 'show_asset_details' in previous_options:
                options['show_asset_details'] = previous_options['show_asset_details']
            if 'show_liability_details' in previous_options:
                options['show_liability_details'] = previous_options['show_liability_details']
            if 'show_equity_details' in previous_options:
                options['show_equity_details'] = previous_options['show_equity_details']

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        lines = []
        company_currency = self.env.company.currency_id

        # Obtener datos del inventario usando consultas SQL
        inventory_data = self._query_values(report, options)

        # Agrupar por tipo de cuenta
        assets_data = []
        liabilities_data = []
        equity_data = []

        # Totales por sección
        totals_by_section = {
            'assets': {'balance': 0.0},
            'liabilities': {'balance': 0.0},
            'equity': {'balance': 0.0},
        }

        # Procesar los datos obtenidos
        for account, column_group_results in inventory_data:
            eval_dict = {}
            for column_group_key, results in column_group_results.items():
                account_sum = results.get('sum', {})
                account_balance = account_sum.get('balance', 0.0)

                eval_dict[column_group_key] = {
                    'balance': account_balance,
                }

                # Clasificar por tipo de cuenta
                if account.account_type.startswith('asset'):
                    totals_by_section['assets']['balance'] += account_balance
                    assets_data.append((account, eval_dict))
                elif account.account_type.startswith('liability'):
                    totals_by_section['liabilities']['balance'] += account_balance
                    liabilities_data.append((account, eval_dict))
                elif account.account_type.startswith('equity'):
                    totals_by_section['equity']['balance'] += account_balance
                    equity_data.append((account, eval_dict))

        # Generar líneas del reporte

        # Sección de Activos
        lines.append(self._get_section_header_line(report, _('ACTIVOS')))

        if options.get('show_asset_details', True):
            for account, eval_dict in assets_data:
                lines.append(self._get_account_line(report, options, account, eval_dict))

        lines.append(self._get_section_total_line(report, options, _('Total Activos'), totals_by_section['assets']))

        # Sección de Pasivos
        lines.append(self._get_section_header_line(report, _('PASIVOS')))

        if options.get('show_liability_details', True):
            for account, eval_dict in liabilities_data:
                lines.append(self._get_account_line(report, options, account, eval_dict))

        lines.append(self._get_section_total_line(report, options, _('Total Pasivos'), totals_by_section['liabilities']))

        # Sección de Patrimonio
        lines.append(self._get_section_header_line(report, _('PATRIMONIO')))

        if options.get('show_equity_details', True):
            for account, eval_dict in equity_data:
                lines.append(self._get_account_line(report, options, account, eval_dict))

        lines.append(self._get_section_total_line(report, options, _('Total Patrimonio'), totals_by_section['equity']))

        # Línea de total general
        total_general = totals_by_section['assets']['balance'] - totals_by_section['liabilities']['balance'] - totals_by_section['equity']['balance']
        lines.append(self._get_general_total_line(report, options, _('DIFERENCIA'), {'balance': total_general}))

        return [(0, line) for line in lines]

    def _query_values(self, report, options):
        """ Ejecuta las consultas y realiza todos los cálculos.
        :return: [(record, values_by_column_group), ...], donde
                - record es un registro account.account.
                - values_by_column_group es un dict en la forma {column_group_key: values, ...}
                    - column_group_key es una cadena que identifica un grupo de columnas, como en options['column_groups']
                    - values es una lista de diccionarios, uno por período que contiene:
                        - sum: {'balance': float}
        """
        # Ejecutar las consultas y distribuir los resultados
        query = self._get_query_sums(report, options)

        groupby_accounts = {}

        if query:
            self._cr.execute(query)
            for res in self._cr.dictfetchall():
                # No hay resultado para agregar
                if res['groupby'] is None:
                    continue

                column_group_key = res['column_group_key']
                key = res['key']

                if key == 'sum':
                    groupby_accounts.setdefault(res['groupby'], {col_group_key: {} for col_group_key in options['column_groups']})
                    groupby_accounts[res['groupby']][column_group_key][key] = res

        # Obtener TODAS las cuentas de balance (activos, pasivos, patrimonio)
        # incluyendo las que no tienen movimientos
        balance_account_types = [
            'asset_receivable', 'asset_cash', 'asset_current', 'asset_non_current',
            'asset_prepayments', 'asset_fixed',
            'liability_payable', 'liability_credit_card', 'liability_current', 'liability_non_current',
            'equity', 'equity_unaffected',
        ]

        # Construir dominio base para búsqueda de cuentas
        account_search_domain = [
            ('account_type', 'in', balance_account_types),
            ('company_ids', 'in', self.env.company.ids),
        ]

        # =====================================================================
        # FILTRO POR RANGO DE CUENTAS (account_from, account_to, account_exclude)
        # =====================================================================
        account_from = options.get('account_from', '').strip() if options.get('account_from') else ''
        account_to = options.get('account_to', '').strip() if options.get('account_to') else ''
        account_exclude = options.get('account_exclude', [])

        if account_from:
            account_search_domain.append(('code', '>=', account_from))
        if account_to:
            account_search_domain.append(('code', '<=', account_to + 'z'))
        if account_exclude:
            for exclude_code in account_exclude:
                if exclude_code:
                    account_search_domain.append(('code', 'not ilike', exclude_code.strip() + '%'))

        # Obtener todas las cuentas de tipo balance (filtradas por rango si aplica)
        all_balance_accounts = self.env['account.account'].search(account_search_domain, order='code')

        result = []
        for account in all_balance_accounts:
            if account.id in groupby_accounts:
                # Cuenta con movimientos
                result.append((account, groupby_accounts[account.id]))
            else:
                # Cuenta sin movimientos - agregar con balance 0
                empty_values = {
                    col_group_key: {'sum': {'balance': 0.0}}
                    for col_group_key in options['column_groups']
                }
                result.append((account, empty_values))

        return result

    def _get_query_sums(self, report, options) -> SQL:
        """ Construye una consulta que recupera todas las sumas agregadas para construir el informe.
        :return: SQL object
        """
        options_by_column_group = report._split_options_per_column_group(options)

        queries = []

        # Obtener sumas para todas las cuentas
        for column_group_key, options_group in options_by_column_group.items():
            # Configurar opciones para saldo a la fecha del reporte
            sum_date_scope = 'from_beginning'

            query_domain = []

            # Filtrar por búsqueda si es necesario
            if options_group.get('export_mode') == 'print' and options_group.get('filter_search_bar'):
                query_domain.append(('account_id', 'ilike', options_group['filter_search_bar']))

            # =====================================================================
            # FILTRO POR RANGO DE CUENTAS (account_from, account_to, account_exclude)
            # =====================================================================
            account_from = options.get('account_from', '').strip() if options.get('account_from') else ''
            account_to = options.get('account_to', '').strip() if options.get('account_to') else ''
            account_exclude = options.get('account_exclude', [])

            if account_from:
                query_domain.append(('account_id.code', '>=', account_from))
            if account_to:
                query_domain.append(('account_id.code', '<=', account_to + 'z'))
            if account_exclude:
                for exclude_code in account_exclude:
                    if exclude_code:
                        query_domain.append(('account_id.code', 'not ilike', exclude_code.strip() + '%'))

            query = report._get_report_query(options_group, sum_date_scope, domain=query_domain)

            queries.append(SQL(
                """
                SELECT
                    account_move_line.account_id                            AS groupby,
                    'sum'                                                   AS key,
                    MAX(account_move_line.date)                             AS max_date,
                    %(column_group_key)s                                    AS column_group_key,
                    SUM(%(balance_select)s)                                 AS balance
                FROM %(table_references)s
                %(currency_table_join)s
                WHERE %(search_condition)s
                GROUP BY account_move_line.account_id
                """,
                column_group_key=column_group_key,
                table_references=query.from_clause,
                balance_select=report._currency_table_apply_rate(SQL("account_move_line.balance")),
                currency_table_join=report._currency_table_aml_join(options_group),
                search_condition=query.where_clause,
            ))

        return SQL(" UNION ALL ").join(queries)

    def _get_section_header_line(self, report, section_name):
        """Crea una línea de encabezado de sección."""
        return {
            'id': report._get_generic_line_id(None, None, markup=f'section_{section_name}'),
            'name': section_name,
            'level': 1,
            'unfoldable': False,
            'unfolded': False,
            'columns': [{} for _ in range(len(report.column_ids))],
        }

    def _get_account_line(self, report, options, account, eval_dict):
        """Crea una línea para una cuenta."""
        line_columns = []
        for column in options['columns']:
            col_value = eval_dict.get(column['column_group_key'], {}).get(column['expression_label'])

            line_columns.append(report._build_column_dict(
                col_value,
                column,
                options=options,
            ))

        return {
            'id': report._get_generic_line_id('account.account', account.id),
            'name': f'{account.code} {account.name}',
            'level': 2,
            'unfoldable': False,
            'columns': line_columns,
        }

    def _get_section_total_line(self, report, options, total_name, total_values):
        """Crea una línea de total para una sección."""
        line_columns = []
        for column in options['columns']:
            col_value = total_values.get(column['expression_label'])

            line_columns.append(report._build_column_dict(
                col_value,
                column,
                options=options,
            ))

        return {
            'id': report._get_generic_line_id(None, None, markup=f'total_{total_name}'),
            'name': total_name,
            'level': 1,
            'unfoldable': False,
            'columns': line_columns,
        }

    def _get_general_total_line(self, report, options, total_name, total_values):
        """Crea una línea de total general."""
        line_columns = []
        for column in options['columns']:
            col_value = total_values.get(column['expression_label'])

            line_columns.append(report._build_column_dict(
                col_value,
                column,
                options=options,
            ))

        return {
            'id': report._get_generic_line_id(None, None, markup='general_total'),
            'name': total_name,
            'level': 0,
            'unfoldable': False,
            'columns': line_columns,
        }
