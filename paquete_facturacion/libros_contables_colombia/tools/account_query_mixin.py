# -*- coding: utf-8 -*-
from odoo import models, fields
from odoo.tools import SQL
from datetime import timedelta


class AccountQueryMixin(models.AbstractModel):
    _name = 'account.query.mixin'
    _description = 'Mixin de Consultas SQL Contables'

    def _get_company_id_for_sql(self):
        return str(self.env.company.root_id.id or self.env.company.id)

    def get_account_balance_at_date(self, report, options, account_prefixes, target_date, before=False):
        company_id = self._get_company_id_for_sql()
        prefix_conditions = ' OR '.join([
            f"COALESCE(aa.code_store->>'{company_id}', '') LIKE '{p}%'"
            for p in account_prefixes
        ])
        date_op = '<' if before else '<='
        query = f'''
            SELECT COALESCE(SUM(aml.balance), 0) as balance
            FROM account_move_line aml
            JOIN account_move am ON am.id = aml.move_id
            JOIN account_account aa ON aa.id = aml.account_id
            WHERE am.state = 'posted'
              AND aml.date {date_op} %s
              AND am.company_id = %s
              AND ({prefix_conditions})
        '''
        self._cr.execute(query, (target_date, self.env.company.id))
        result = self._cr.fetchone()
        return result[0] if result else 0.0

    def get_account_balance_range(self, report, options, account_prefixes, date_from, date_to):
        company_id = self._get_company_id_for_sql()
        prefix_conditions = ' OR '.join([
            f"COALESCE(aa.code_store->>'{company_id}', '') LIKE '{p}%'"
            for p in account_prefixes
        ])
        query = f'''
            SELECT COALESCE(SUM(aml.balance), 0) as balance
            FROM account_move_line aml
            JOIN account_move am ON am.id = aml.move_id
            JOIN account_account aa ON aa.id = aml.account_id
            WHERE am.state = 'posted'
              AND aml.date BETWEEN %s AND %s
              AND am.company_id = %s
              AND ({prefix_conditions})
        '''
        self._cr.execute(query, (date_from, date_to, self.env.company.id))
        result = self._cr.fetchone()
        return result[0] if result else 0.0

    def get_account_balance_change(self, report, options, account_prefixes, date_from, date_to):
        balance_start = self.get_account_balance_at_date(report, options, account_prefixes, date_from, before=True)
        balance_end = self.get_account_balance_at_date(report, options, account_prefixes, date_to)
        return balance_end - balance_start

    def get_options_initial_balance(self, options):
        new_options = options.copy()
        date_from = fields.Date.from_string(options['date']['date_from'])
        new_date_to = date_from - timedelta(days=1)
        fiscalyear_dates = self.env.company.compute_fiscalyear_dates(date_from)
        if date_from == fiscalyear_dates['date_from']:
            prev_fiscalyear = self.env.company.compute_fiscalyear_dates(date_from - timedelta(days=1))
            new_date_from = prev_fiscalyear['date_from']
            include_unaff = True
        else:
            new_date_from = fiscalyear_dates['date_from']
            include_unaff = False
        new_options['date'] = self.env['account.report']._get_dates_period(new_date_from, new_date_to, 'range')
        new_options['include_current_year_in_unaff_earnings'] = include_unaff
        return new_options

    def build_account_query(self, report, options, date_scope='strict_range',
                            include_initial=False, group_by_partner=False, additional_domain=None):
        domain = [
            ('move_id.state', '=', 'posted'),
            ('display_type', 'not in', ('line_section', 'line_note')),
        ]
        if additional_domain:
            domain.extend(additional_domain)
        if options.get('account_from'):
            domain.append(('account_id.code', '>=', options['account_from']))
        if options.get('account_to'):
            domain.append(('account_id.code', '<=', options['account_to'] + 'z'))
        
        query = report._get_report_query(options, date_scope, domain=domain)
        account_alias = query.join(
            lhs_alias='account_move_line',
            lhs_column='account_id',
            rhs_table='account_account',
            rhs_column='id',
            link='account_id'
        )
        account_code = self.env['account.account']._field_to_sql(account_alias, 'code', query)
        account_name = self.env['account.account']._field_to_sql(account_alias, 'name')
        
        select_fields = [
            SQL('account_move_line.account_id AS account_id'),
            SQL('%(code)s AS account_code', code=account_code),
            SQL('%(name)s AS account_name', name=account_name),
            SQL("'period' AS data_type"),
            SQL('COALESCE(SUM(%(debit)s), 0) AS debit',
                debit=report._currency_table_apply_rate(SQL('account_move_line.debit'))),
            SQL('COALESCE(SUM(%(credit)s), 0) AS credit',
                credit=report._currency_table_apply_rate(SQL('account_move_line.credit'))),
            SQL('COALESCE(SUM(%(balance)s), 0) AS balance',
                balance=report._currency_table_apply_rate(SQL('account_move_line.balance'))),
        ]
        group_by = [
            SQL('account_move_line.account_id'),
            account_code,
            account_name,
        ]
        if group_by_partner:
            partner_alias = query.join(
                lhs_alias='account_move_line',
                lhs_column='partner_id',
                rhs_table='res_partner',
                rhs_column='id',
                link='partner_id'
            )
            select_fields.extend([
                SQL('account_move_line.partner_id AS partner_id'),
                SQL('%(name)s AS partner_name',
                    name=self.env['res.partner']._field_to_sql(partner_alias, 'name')),
            ])
            group_by.extend([
                SQL('account_move_line.partner_id'),
                self.env['res.partner']._field_to_sql(partner_alias, 'name'),
            ])
        return SQL(
            '''
            SELECT %(select)s
            FROM %(from_clause)s
            %(currency_join)s
            WHERE %(where)s
            GROUP BY %(group_by)s
            ''',
            select=SQL(', ').join(select_fields),
            from_clause=query.from_clause,
            currency_join=report._currency_table_aml_join(options),
            where=query.where_clause,
            group_by=SQL(', ').join(group_by),
        )
