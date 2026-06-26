# -*- coding: utf-8 -*-
"""Mixin para construccion de consultas SQL especializadas."""

from odoo import models
from odoo.tools import SQL


class QueryBuilderMixin(models.AbstractModel):
    """Mixin para construir consultas SQL de reportes contables."""

    _name = 'query.builder.mixin'
    _description = 'Mixin Constructor de Consultas SQL'

    def _get_base_domain(self, options):
        """Dominio base para todas las consultas."""
        return [
            ('move_id.state', '=', 'posted'),
            ('display_type', 'not in', ('line_section', 'line_note')),
        ]

    def _apply_account_filter(self, domain, options):
        """Aplica filtro de rango de cuentas."""
        if options.get('account_from'):
            domain.append(('account_id.code', '>=', options['account_from']))
        if options.get('account_to'):
            domain.append(('account_id.code', '<=', options['account_to'] + 'z'))
        return domain

    def _apply_partner_filter(self, domain, options):
        """Aplica filtro de terceros."""
        if options.get('partner_ids'):
            domain.append(('partner_id', 'in', options['partner_ids']))
        if options.get('partner_categories'):
            domain.append(('partner_id.category_id', 'in', options['partner_categories']))
        return domain

    def _apply_journal_filter(self, domain, options):
        """Aplica filtro de diarios."""
        if options.get('journal_ids'):
            domain.append(('journal_id', 'in', options['journal_ids']))
        return domain

    def _apply_analytic_filter(self, domain, options):
        """Aplica filtro de cuentas analiticas/centros de costo."""
        if options.get('analytic_account_ids'):
            domain.append(('analytic_distribution', '!=', False))
        return domain

    def build_partner_query(self, report, options, date_scope='strict_range',
                            include_zero_balance=False):
        """
        Construye consulta agrupada por tercero.

        Args:
            report: Objeto account.report
            options: Opciones del reporte
            date_scope: Alcance de fechas
            include_zero_balance: Incluir terceros con saldo cero

        Returns:
            SQL: Consulta SQL
        """
        domain = self._get_base_domain(options)
        domain = self._apply_account_filter(domain, options)
        domain = self._apply_partner_filter(domain, options)

        query = report._get_report_query(options, date_scope, domain=domain)

        account_alias = query.join(
            lhs_alias='account_move_line',
            lhs_column='account_id',
            rhs_table='account_account',
            rhs_column='id',
            link='account_id'
        )

        partner_alias = query.join(
            lhs_alias='account_move_line',
            lhs_column='partner_id',
            rhs_table='res_partner',
            rhs_column='id',
            link='partner_id'
        )

        account_code = self.env['account.account']._field_to_sql(account_alias, 'code', query)
        account_name = self.env['account.account']._field_to_sql(account_alias, 'name')
        partner_name = self.env['res.partner']._field_to_sql(partner_alias, 'name')

        having_clause = SQL("") if include_zero_balance else SQL("HAVING COALESCE(SUM(account_move_line.balance), 0) != 0")

        return SQL(
            """
            SELECT
                account_move_line.account_id,
                %(account_code)s AS account_code,
                %(account_name)s AS account_name,
                account_move_line.partner_id,
                %(partner_name)s AS partner_name,
                COALESCE(rp.vat, '') AS partner_vat,
                COALESCE(SUM(%(debit)s), 0) AS debit,
                COALESCE(SUM(%(credit)s), 0) AS credit,
                COALESCE(SUM(%(balance)s), 0) AS balance
            FROM %(from_clause)s
            %(currency_join)s
            WHERE %(where_clause)s
            GROUP BY
                account_move_line.account_id,
                %(account_code)s,
                %(account_name)s,
                account_move_line.partner_id,
                %(partner_name)s,
                rp.vat
            %(having)s
            ORDER BY %(account_code)s, %(partner_name)s
            """,
            account_code=account_code,
            account_name=account_name,
            partner_name=partner_name,
            from_clause=query.from_clause,
            currency_join=report._currency_table_aml_join(options),
            where_clause=query.where_clause,
            debit=report._currency_table_apply_rate(SQL("account_move_line.debit")),
            credit=report._currency_table_apply_rate(SQL("account_move_line.credit")),
            balance=report._currency_table_apply_rate(SQL("account_move_line.balance")),
            having=having_clause,
        )

    def build_journal_query(self, report, options, date_scope='strict_range'):
        """
        Construye consulta agrupada por diario.

        Args:
            report: Objeto account.report
            options: Opciones del reporte
            date_scope: Alcance de fechas

        Returns:
            SQL: Consulta SQL
        """
        domain = self._get_base_domain(options)
        domain = self._apply_journal_filter(domain, options)

        query = report._get_report_query(options, date_scope, domain=domain)

        journal_alias = query.join(
            lhs_alias='account_move_line',
            lhs_column='journal_id',
            rhs_table='account_journal',
            rhs_column='id',
            link='journal_id'
        )

        journal_name = self.env['account.journal']._field_to_sql(journal_alias, 'name')

        return SQL(
            """
            SELECT
                account_move_line.journal_id,
                aj.code AS journal_code,
                %(journal_name)s AS journal_name,
                aj.type AS journal_type,
                COUNT(DISTINCT account_move_line.move_id) AS move_count,
                COALESCE(SUM(%(debit)s), 0) AS debit,
                COALESCE(SUM(%(credit)s), 0) AS credit,
                COALESCE(SUM(%(balance)s), 0) AS balance
            FROM %(from_clause)s
            %(currency_join)s
            WHERE %(where_clause)s
            GROUP BY
                account_move_line.journal_id,
                aj.code,
                %(journal_name)s,
                aj.type
            ORDER BY aj.code
            """,
            journal_name=journal_name,
            from_clause=query.from_clause,
            currency_join=report._currency_table_aml_join(options),
            where_clause=query.where_clause,
            debit=report._currency_table_apply_rate(SQL("account_move_line.debit")),
            credit=report._currency_table_apply_rate(SQL("account_move_line.credit")),
            balance=report._currency_table_apply_rate(SQL("account_move_line.balance")),
        )

    def build_date_query(self, report, options, group_by='day'):
        """
        Construye consulta agrupada por fecha.

        Args:
            report: Objeto account.report
            options: Opciones del reporte
            group_by: Agrupacion ('day', 'week', 'month', 'year')

        Returns:
            SQL: Consulta SQL
        """
        domain = self._get_base_domain(options)
        query = report._get_report_query(options, 'strict_range', domain=domain)

        date_trunc = {
            'day': "DATE(account_move_line.date)",
            'week': "DATE_TRUNC('week', account_move_line.date)",
            'month': "DATE_TRUNC('month', account_move_line.date)",
            'year': "DATE_TRUNC('year', account_move_line.date)",
        }.get(group_by, "DATE(account_move_line.date)")

        return SQL(
            """
            SELECT
                %(date_group)s AS period_date,
                COUNT(DISTINCT account_move_line.move_id) AS move_count,
                COUNT(account_move_line.id) AS line_count,
                COALESCE(SUM(%(debit)s), 0) AS debit,
                COALESCE(SUM(%(credit)s), 0) AS credit,
                COALESCE(SUM(%(balance)s), 0) AS balance
            FROM %(from_clause)s
            %(currency_join)s
            WHERE %(where_clause)s
            GROUP BY %(date_group)s
            ORDER BY %(date_group)s
            """,
            date_group=SQL(date_trunc),
            from_clause=query.from_clause,
            currency_join=report._currency_table_aml_join(options),
            where_clause=query.where_clause,
            debit=report._currency_table_apply_rate(SQL("account_move_line.debit")),
            credit=report._currency_table_apply_rate(SQL("account_move_line.credit")),
            balance=report._currency_table_apply_rate(SQL("account_move_line.balance")),
        )

    def build_document_query(self, report, options, date_scope='strict_range'):
        """
        Construye consulta agrupada por documento/movimiento.

        Args:
            report: Objeto account.report
            options: Opciones del reporte
            date_scope: Alcance de fechas

        Returns:
            SQL: Consulta SQL
        """
        domain = self._get_base_domain(options)
        domain = self._apply_account_filter(domain, options)
        domain = self._apply_journal_filter(domain, options)

        query = report._get_report_query(options, date_scope, domain=domain)

        move_alias = query.join(
            lhs_alias='account_move_line',
            lhs_column='move_id',
            rhs_table='account_move',
            rhs_column='id',
            link='move_id'
        )

        journal_alias = query.join(
            lhs_alias='account_move_line',
            lhs_column='journal_id',
            rhs_table='account_journal',
            rhs_column='id',
            link='journal_id'
        )

        partner_alias = query.join(
            lhs_alias='account_move_line',
            lhs_column='partner_id',
            rhs_table='res_partner',
            rhs_column='id',
            link='partner_id'
        )

        journal_name = self.env['account.journal']._field_to_sql(journal_alias, 'name')
        partner_name = self.env['res.partner']._field_to_sql(partner_alias, 'name')

        return SQL(
            """
            SELECT
                account_move_line.move_id,
                am.name AS move_name,
                am.ref AS move_ref,
                am.date AS move_date,
                account_move_line.journal_id,
                aj.code AS journal_code,
                %(journal_name)s AS journal_name,
                account_move_line.partner_id,
                %(partner_name)s AS partner_name,
                COALESCE(SUM(%(debit)s), 0) AS debit,
                COALESCE(SUM(%(credit)s), 0) AS credit
            FROM %(from_clause)s
            %(currency_join)s
            WHERE %(where_clause)s
            GROUP BY
                account_move_line.move_id,
                am.name,
                am.ref,
                am.date,
                account_move_line.journal_id,
                aj.code,
                %(journal_name)s,
                account_move_line.partner_id,
                %(partner_name)s
            ORDER BY am.date, am.name
            """,
            journal_name=journal_name,
            partner_name=partner_name,
            from_clause=query.from_clause,
            currency_join=report._currency_table_aml_join(options),
            where_clause=query.where_clause,
            debit=report._currency_table_apply_rate(SQL("account_move_line.debit")),
            credit=report._currency_table_apply_rate(SQL("account_move_line.credit")),
        )

    def build_tax_query(self, report, options, date_scope='strict_range'):
        """
        Construye consulta agrupada por impuesto.

        Args:
            report: Objeto account.report
            options: Opciones del reporte
            date_scope: Alcance de fechas

        Returns:
            SQL: Consulta SQL
        """
        domain = self._get_base_domain(options)
        domain.append(('tax_line_id', '!=', False))

        query = report._get_report_query(options, date_scope, domain=domain)

        tax_alias = query.join(
            lhs_alias='account_move_line',
            lhs_column='tax_line_id',
            rhs_table='account_tax',
            rhs_column='id',
            link='tax_line_id'
        )

        tax_name = self.env['account.tax']._field_to_sql(tax_alias, 'name')

        return SQL(
            """
            SELECT
                account_move_line.tax_line_id AS tax_id,
                %(tax_name)s AS tax_name,
                at.amount AS tax_rate,
                at.type_tax_use AS tax_type,
                COALESCE(SUM(%(debit)s), 0) AS debit,
                COALESCE(SUM(%(credit)s), 0) AS credit,
                COALESCE(SUM(%(balance)s), 0) AS tax_amount,
                COALESCE(SUM(account_move_line.tax_base_amount), 0) AS tax_base
            FROM %(from_clause)s
            %(currency_join)s
            WHERE %(where_clause)s
            GROUP BY
                account_move_line.tax_line_id,
                %(tax_name)s,
                at.amount,
                at.type_tax_use
            ORDER BY at.type_tax_use, %(tax_name)s
            """,
            tax_name=tax_name,
            from_clause=query.from_clause,
            currency_join=report._currency_table_aml_join(options),
            where_clause=query.where_clause,
            debit=report._currency_table_apply_rate(SQL("account_move_line.debit")),
            credit=report._currency_table_apply_rate(SQL("account_move_line.credit")),
            balance=report._currency_table_apply_rate(SQL("account_move_line.balance")),
        )

    def build_analytic_query(self, report, options, date_scope='strict_range'):
        """
        Construye consulta agrupada por cuenta analitica/centro de costo.

        Args:
            report: Objeto account.report
            options: Opciones del reporte
            date_scope: Alcance de fechas

        Returns:
            SQL: Consulta SQL
        """
        domain = self._get_base_domain(options)
        domain.append(('analytic_distribution', '!=', False))

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

        return SQL(
            """
            WITH analytic_lines AS (
                SELECT
                    aml.id AS line_id,
                    aml.account_id,
                    (jsonb_each_text(aml.analytic_distribution)).key::int AS analytic_account_id,
                    ((jsonb_each_text(aml.analytic_distribution)).value::numeric / 100) AS percentage,
                    aml.debit,
                    aml.credit,
                    aml.balance
                FROM account_move_line aml
                JOIN account_move am ON am.id = aml.move_id
                WHERE am.state = 'posted'
                  AND aml.analytic_distribution IS NOT NULL
                  AND aml.display_type NOT IN ('line_section', 'line_note')
            )
            SELECT
                al.analytic_account_id,
                aa_an.name AS analytic_name,
                aa_an.code AS analytic_code,
                al.account_id,
                %(account_code)s AS account_code,
                %(account_name)s AS account_name,
                COALESCE(SUM(al.debit * al.percentage), 0) AS debit,
                COALESCE(SUM(al.credit * al.percentage), 0) AS credit,
                COALESCE(SUM(al.balance * al.percentage), 0) AS balance
            FROM analytic_lines al
            JOIN account_analytic_account aa_an ON aa_an.id = al.analytic_account_id
            JOIN account_account aa ON aa.id = al.account_id
            GROUP BY
                al.analytic_account_id,
                aa_an.name,
                aa_an.code,
                al.account_id,
                %(account_code)s,
                %(account_name)s
            ORDER BY aa_an.code, %(account_code)s
            """,
            account_code=account_code,
            account_name=account_name,
        )

    def build_custom_query(self, report, options, select_fields, group_by_fields,
                           joins=None, additional_domain=None, order_by=None):
        """
        Construye consulta personalizada.

        Args:
            report: Objeto account.report
            options: Opciones del reporte
            select_fields: Lista de campos para SELECT
            group_by_fields: Lista de campos para GROUP BY
            joins: Lista de joins adicionales
            additional_domain: Dominio adicional
            order_by: Campos para ORDER BY

        Returns:
            SQL: Consulta SQL personalizada
        """
        domain = self._get_base_domain(options)
        if additional_domain:
            domain.extend(additional_domain)

        query = report._get_report_query(options, 'strict_range', domain=domain)

        aliases = {'account_move_line': 'account_move_line'}

        if joins:
            for join_def in joins:
                aliases[join_def['alias']] = query.join(
                    lhs_alias=join_def.get('lhs', 'account_move_line'),
                    lhs_column=join_def['column'],
                    rhs_table=join_def['table'],
                    rhs_column='id',
                    link=join_def.get('link', join_def['column'])
                )

        select_sql = []
        for field in select_fields:
            if field.get('model'):
                alias = aliases.get(field.get('table_alias', 'account_move_line'))
                field_sql = self.env[field['model']]._field_to_sql(alias, field['field'], query)
                if field.get('aggregate'):
                    select_sql.append(SQL(
                        "%(agg)s(%(field)s) AS %(alias)s",
                        agg=SQL(field['aggregate']),
                        field=field_sql,
                        alias=SQL.identifier(field.get('as', field['field']))
                    ))
                else:
                    select_sql.append(SQL(
                        "%(field)s AS %(alias)s",
                        field=field_sql,
                        alias=SQL.identifier(field.get('as', field['field']))
                    ))
            else:
                full_field = field.get('table_alias', 'account_move_line') + '.' + field['field']
                if field.get('aggregate'):
                    select_sql.append(SQL(
                        "%(agg)s(%(field)s) AS %(alias)s",
                        agg=SQL(field['aggregate']),
                        field=SQL(full_field),
                        alias=SQL.identifier(field.get('as', field['field']))
                    ))
                else:
                    select_sql.append(SQL(
                        "%(field)s AS %(alias)s",
                        field=SQL(full_field),
                        alias=SQL.identifier(field.get('as', field['field']))
                    ))

        group_sql = []
        for field in group_by_fields:
            if field.get('model'):
                alias = aliases.get(field.get('table_alias', 'account_move_line'))
                group_sql.append(self.env[field['model']]._field_to_sql(alias, field['field'], query))
            else:
                full_field = field.get('table_alias', 'account_move_line') + '.' + field['field']
                group_sql.append(SQL(full_field))

        order_sql = SQL(order_by) if order_by else SQL("1")

        return SQL(
            """
            SELECT %(select)s
            FROM %(from_clause)s
            %(currency_join)s
            WHERE %(where_clause)s
            GROUP BY %(group_by)s
            ORDER BY %(order_by)s
            """,
            select=SQL(", ").join(select_sql),
            from_clause=query.from_clause,
            currency_join=report._currency_table_aml_join(options),
            where_clause=query.where_clause,
            group_by=SQL(", ").join(group_sql),
            order_by=order_sql,
        )
