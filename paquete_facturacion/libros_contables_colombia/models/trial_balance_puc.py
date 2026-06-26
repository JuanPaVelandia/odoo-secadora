# -*- coding: utf-8 -*-
"""
Balance de Prueba Colombiano (PUC) - Refactorizado
==================================================
Version optimizada usando mixins reutilizables.
Reduce ~50% del codigo original (712 -> ~350 lineas).
"""

import re
import logging
from odoo import models, fields, _
from odoo.tools import SQL

_logger = logging.getLogger(__name__)


class TrialBalancePUCHandler(models.AbstractModel):
    _name = 'account.trial.balance.puc.report.handler'
    _inherit = [
        'account.report.custom.handler',
        'report.line.mixin',
        'puc.hierarchy.mixin',
        'account.query.mixin',
        'translatable.field.mixin',
    ]
    _description = 'Balance de Prueba PUC Colombia Handler'

    _report_css_class = 'trial_balance_puc_report'

    def _custom_options_initializer(self, report, options, previous_options=None):
        """Inicializa opciones personalizadas."""
        super()._custom_options_initializer(report, options, previous_options=previous_options)
        options['puc_level'] = previous_options.get('puc_level', 4) if previous_options else 4
        options['account_codes'] = previous_options.get('account_codes', '') if previous_options else ''
        options.setdefault('buttons', []).append({
            'name': _('Exportar Excel'),
            'sequence': 50,
            'action': 'export_to_xlsx',
        })

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        """Genera lineas del Balance de Prueba."""
        lines = []
        puc_level = options.get('puc_level', 4)
        account_data = self._get_account_balances(report, options)

        if not account_data:
            return [(0, self._get_no_data_line(report, options))]

        grouped_data = self.group_by_puc_level(account_data, puc_level)
        totals = {'initial': 0, 'debit': 0, 'credit': 0, 'final': 0, 'last_move_date': None}

        for code, data in sorted(grouped_data.items()):
            line = self._get_account_line(report, options, code, data, puc_level)
            lines.append((0, line))
            self._accumulate_totals(totals, data)

        if lines:
            lines.append((0, self._build_total_line(report, options, totals)))

        return lines

    def _get_account_balances(self, report, options):
        """Obtiene saldos de cuentas usando patron nativo Odoo 18."""
        queries = []

        for column_group_key, options_group in report._split_options_per_column_group(options).items():
            queries.append(self._build_period_query(report, options_group, column_group_key))
            queries.append(self._build_initial_query(report, options_group, column_group_key))

        full_query = SQL(" UNION ALL ").join(SQL("(%s)", q) for q in queries)
        self._cr.execute(full_query)

        return self._process_balance_results(self._cr.dictfetchall())

    def _build_period_query(self, report, options, column_group_key):
        """Construye query para saldos del periodo."""
        query = report._get_report_query(options, date_scope='strict_range')
        account_alias = query.join(
            lhs_alias='account_move_line', lhs_column='account_id',
            rhs_table='account_account', rhs_column='id', link='account_id'
        )

        account_code = self.get_field_sql_native('account.account', 'code', account_alias, query)
        account_name = self.get_field_sql_native('account.account', 'name', account_alias)

        return SQL(
            """
            SELECT
                account_move_line.account_id AS account_id,
                %(account_code)s AS account_code,
                %(account_name)s AS account_name,
                'period' AS data_type,
                %(column_group_key)s AS column_group_key,
                COALESCE(SUM(%(debit)s), 0) AS debit,
                COALESCE(SUM(%(credit)s), 0) AS credit,
                COALESCE(SUM(%(balance)s), 0) AS balance,
                MAX(account_move_line.date) AS last_move_date
            FROM %(from_clause)s
            %(currency_join)s
            WHERE %(where_clause)s
            GROUP BY account_move_line.account_id, %(account_code)s, %(account_name)s
            HAVING COALESCE(SUM(%(debit)s), 0) != 0 OR COALESCE(SUM(%(credit)s), 0) != 0
            """,
            account_code=account_code,
            account_name=account_name,
            column_group_key=column_group_key,
            from_clause=query.from_clause,
            where_clause=query.where_clause,
            debit=report._currency_table_apply_rate(SQL("account_move_line.debit")),
            credit=report._currency_table_apply_rate(SQL("account_move_line.credit")),
            balance=report._currency_table_apply_rate(SQL("account_move_line.balance")),
            currency_join=report._currency_table_aml_join(options),
        )

    def _build_initial_query(self, report, options, column_group_key):
        """Construye query para saldos iniciales."""
        initial_options = self.get_options_initial_balance(options)
        query = report._get_report_query(initial_options, date_scope='from_beginning')
        account_alias = query.join(
            lhs_alias='account_move_line', lhs_column='account_id',
            rhs_table='account_account', rhs_column='id', link='account_id'
        )

        account_code = self.get_field_sql_native('account.account', 'code', account_alias, query)
        account_name = self.get_field_sql_native('account.account', 'name', account_alias)

        return SQL(
            """
            SELECT
                account_move_line.account_id AS account_id,
                %(account_code)s AS account_code,
                %(account_name)s AS account_name,
                'initial' AS data_type,
                %(column_group_key)s AS column_group_key,
                0 AS debit, 0 AS credit,
                COALESCE(SUM(%(balance)s), 0) AS balance,
                NULL::date AS last_move_date
            FROM %(from_clause)s
            %(currency_join)s
            WHERE %(where_clause)s
            GROUP BY account_move_line.account_id, %(account_code)s, %(account_name)s
            HAVING COALESCE(SUM(%(balance)s), 0) != 0
            """,
            account_code=account_code,
            account_name=account_name,
            column_group_key=column_group_key,
            from_clause=query.from_clause,
            where_clause=query.where_clause,
            balance=report._currency_table_apply_rate(SQL("account_move_line.balance")),
            currency_join=report._currency_table_aml_join(initial_options),
        )

    def _process_balance_results(self, rows):
        """Procesa resultados de la query."""
        accounts = {}
        for row in rows:
            account_id = row['account_id']
            if account_id not in accounts:
                accounts[account_id] = {
                    'code': row['account_code'],
                    'name': row['account_name'],
                    'initial': 0.0, 'debit': 0.0, 'credit': 0.0, 'last_move_date': None,
                }

            if row['data_type'] == 'initial':
                accounts[account_id]['initial'] = float(row['balance'] or 0)
            else:
                accounts[account_id]['debit'] = float(row['debit'] or 0)
                accounts[account_id]['credit'] = float(row['credit'] or 0)
                if row['last_move_date']:
                    accounts[account_id]['last_move_date'] = row['last_move_date']

        for acc in accounts.values():
            acc['final'] = acc['initial'] + acc['debit'] - acc['credit']

        return accounts

    def _accumulate_totals(self, totals, data):
        """Acumula valores en totales."""
        totals['initial'] += data.get('initial', 0) or 0
        totals['debit'] += data.get('debit', 0) or 0
        totals['credit'] += data.get('credit', 0) or 0
        totals['final'] += data.get('final', 0) or 0
        if data.get('last_move_date'):
            if not totals['last_move_date'] or data['last_move_date'] > totals['last_move_date']:
                totals['last_move_date'] = data['last_move_date']

    def _get_account_line(self, report, options, code, data, current_level):
        """Crea linea de cuenta."""
        line_id = report._get_generic_line_id(None, None, markup=f'puc_{code}')
        has_children = data.get('has_children', False)
        is_unfolded = line_id in options.get('unfolded_lines', [])
        level = self.get_puc_level(code)

        return {
            'id': line_id,
            'name': f"{code} - {data.get('name', '')}",
            'level': min(level, 4),
            'unfoldable': has_children,
            'unfolded': is_unfolded,
            'expand_function': '_report_expand_unfoldable_line_puc' if has_children else None,
            'columns': self._build_columns(report, options, data),
            'class': 'font-weight-bold' if len(code) <= 2 else '',
        }

    def _build_columns(self, report, options, data):
        """Construye columnas para linea."""
        columns = []
        initial = data.get('initial', 0) or 0
        final = data.get('final', 0) or 0
        variation = final - initial
        variation_pct = (variation / initial) if initial != 0 else 0.0

        col_map = {
            'initial_balance': data.get('initial', 0),
            'debit': data.get('debit', 0),
            'credit': data.get('credit', 0),
            'final_balance': data.get('final', 0),
            'variation': variation,
            'variation_percent': variation_pct,
            'last_move_date': data.get('last_move_date'),
        }

        for col in options['columns']:
            value = col_map.get(col['expression_label'])
            columns.append(report._build_column_dict(value, col, options=options))

        return columns

    def _build_total_line(self, report, options, totals):
        """Crea linea de totales."""
        return {
            'id': report._get_generic_line_id(None, None, markup='total'),
            'name': _('TOTAL'),
            'level': 1,
            'unfoldable': False,
            'columns': self._build_columns(report, options, totals),
            'class': 'font-weight-bold o_account_reports_totals_below_sections',
        }

    def _report_expand_unfoldable_line_puc(self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None):
        """Expande linea para mostrar subcuentas."""
        report = self.env['account.report'].browse(options['report_id'])
        matches = re.findall(r'puc_(\d+)', line_dict_id)
        if not matches:
            return {'lines': [], 'offset_increment': 0, 'has_more': False}

        parent_code = matches[-1]
        account_data = self._get_account_balances(report, options)

        child_accounts = {
            aid: data for aid, data in account_data.items()
            if (data['code'] or '').startswith(parent_code) and len(data['code'] or '') > len(parent_code)
        }

        if not child_accounts:
            return {'lines': [], 'offset_increment': 0, 'has_more': False}

        next_level_length = len(parent_code) + 2
        grouped = self._group_children(child_accounts, next_level_length, parent_code)

        lines = [
            self._get_child_line(report, options, code, data, line_dict_id)
            for code, data in sorted(grouped.items())
        ]

        return {'lines': lines, 'offset_increment': len(lines), 'has_more': False}

    def _group_children(self, account_data, code_length, parent_code):
        """Agrupa cuentas hijas por nivel."""
        from collections import defaultdict
        grouped = defaultdict(lambda: {
            'name': '', 'initial': 0, 'debit': 0, 'credit': 0, 'final': 0,
            'last_move_date': None, 'accounts': [], 'has_children': False,
        })

        for account_id, data in account_data.items():
            code = data['code'] or ''
            if not code.startswith(parent_code):
                continue

            prefix = code[:code_length] if len(code) >= code_length else code
            grouped[prefix]['initial'] += data['initial']
            grouped[prefix]['debit'] += data['debit']
            grouped[prefix]['credit'] += data['credit']
            grouped[prefix]['final'] += data['final']
            grouped[prefix]['accounts'].append({'id': account_id, 'code': code, 'name': data['name']})

            if data.get('last_move_date'):
                if not grouped[prefix]['last_move_date'] or data['last_move_date'] > grouped[prefix]['last_move_date']:
                    grouped[prefix]['last_move_date'] = data['last_move_date']

            if not grouped[prefix]['name']:
                grouped[prefix]['name'] = data['name']

        for code, data in grouped.items():
            data['has_children'] = any(len(a['code']) > len(code) for a in data['accounts'])

        return grouped

    def _get_child_line(self, report, options, code, data, parent_line_id):
        """Crea linea hija."""
        line_id = report._get_generic_line_id(None, None, markup=f'puc_{code}', parent_line_id=parent_line_id)
        has_children = data.get('has_children', False)
        level = min(self.get_puc_level(code), 4)

        return {
            'id': line_id,
            'name': f"{code} - {data['name']}",
            'level': level,
            'parent_id': parent_line_id,
            'unfoldable': has_children,
            'unfolded': line_id in options.get('unfolded_lines', []),
            'expand_function': '_report_expand_unfoldable_line_puc' if has_children else None,
            'columns': self._build_columns(report, options, data),
        }

    def _get_lines_for_pdf(self, report, options):
        """Obtiene lineas expandidas para PDF."""
        lines = []
        account_data = self._get_account_balances(report, options)

        if not account_data:
            return lines

        hierarchy = self.build_puc_hierarchy(account_data)
        totals = {'initial': 0, 'debit': 0, 'credit': 0, 'final': 0, 'last_move_date': None}

        for code in sorted(hierarchy.keys()):
            data = hierarchy[code]
            level = self.get_puc_level(code)

            lines.append({
                'code': code,
                'name': data.get('name', ''),
                'level': level,
                'is_total': False,
                'initial': data.get('totals', {}).get('initial', 0),
                'debit': data.get('totals', {}).get('debit', 0),
                'credit': data.get('totals', {}).get('credit', 0),
                'final': data.get('totals', {}).get('final', 0),
            })

            if level == 1:
                for key in ['initial', 'debit', 'credit', 'final']:
                    totals[key] += data.get('totals', {}).get(key, 0)

        lines.append({
            'name': 'TOTAL',
            'level': 1,
            'is_total': True,
            **totals
        })

        return lines
