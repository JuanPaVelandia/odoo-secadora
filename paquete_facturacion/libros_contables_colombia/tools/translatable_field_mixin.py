# -*- coding: utf-8 -*-
"""Mixin para extraccion de campos traducibles JSONB en Odoo 18."""

from odoo import models
from odoo.tools import SQL


class TranslatableFieldMixin(models.AbstractModel):
    """Mixin para manejo de campos JSONB traducibles en SQL."""

    _name = 'translatable.field.mixin'
    _description = 'Mixin de Campos Traducibles JSONB'

    def get_field_sql_native(self, model_name, field_name, table_alias, query=None):
        """
        Metodo NATIVO recomendado - usa _field_to_sql de Odoo 18.

        Args:
            model_name: Nombre del modelo (ej: 'account.account')
            field_name: Nombre del campo (ej: 'name', 'code')
            table_alias: Alias de la tabla en la query
            query: Objeto Query (requerido para campos computed)

        Returns:
            SQL: Expresion SQL nativa de Odoo

        Ejemplo:
            query = report._get_report_query(options, 'strict_range')
            account_alias = query.join(
                lhs_alias='account_move_line',
                lhs_column='account_id',
                rhs_table='account_account',
                rhs_column='id',
                link='account_id'
            )
            account_code = self.get_field_sql_native('account.account', 'code', account_alias, query)
            account_name = self.get_field_sql_native('account.account', 'name', account_alias)
        """
        model = self.env[model_name]
        if query is not None:
            return model._field_to_sql(table_alias, field_name, query)
        return model._field_to_sql(table_alias, field_name)

    def get_translatable_sql(self, table_alias, field_name, model_name=None):
        """
        Genera SQL manual para campo traducible JSONB.
        Usar SOLO cuando no hay objeto Query disponible.

        Args:
            table_alias: Alias de tabla en la query
            field_name: Nombre del campo
            model_name: Nombre del modelo (para verificar si es traducible)

        Returns:
            str: Expresion SQL con COALESCE para idiomas
        """
        user_lang = self.env.user.lang or 'es_CO'
        is_translatable = True

        if model_name:
            try:
                field = self.env[model_name]._fields.get(field_name)
                is_translatable = field and getattr(field, 'translate', False)
            except (KeyError, AttributeError):
                pass

        if not is_translatable:
            return table_alias + '.' + field_name

        lang_priority = [user_lang, 'es_CO', 'es_ES', 'en_US']
        coalesce_parts = []
        for lang in lang_priority:
            coalesce_parts.append(table_alias + '.' + field_name + "->>" + "'" + lang + "'")
        coalesce_parts.append(
            "(SELECT value FROM jsonb_each_text(" + table_alias + "." + field_name + ") LIMIT 1)"
        )
        coalesce_parts.append("''")

        return "COALESCE(" + ", ".join(coalesce_parts) + ")"

    def get_company_dependent_sql(self, table_alias, field_name):
        """
        Genera SQL para campo company_dependent JSONB.
        Usado principalmente para account.account.code

        Args:
            table_alias: Alias de tabla
            field_name: Nombre del campo (usualmente 'code_store')

        Returns:
            str: Expresion SQL
        """
        company_id = str(self.env.company.root_id.id or self.env.company.id)
        sql = "COALESCE(" + table_alias + "." + field_name + "->>'" + company_id + "', "
        sql += "(SELECT value FROM jsonb_each_text(" + table_alias + "." + field_name + ") LIMIT 1), '')"
        return sql

    def get_account_code_sql(self, alias='aa', with_alias=True):
        """SQL para codigo de cuenta (company_dependent)."""
        sql = self.get_company_dependent_sql(alias, 'code_store')
        if with_alias:
            return sql + " AS account_code"
        return sql

    def get_account_name_sql(self, alias='aa', with_alias=True):
        """SQL para nombre de cuenta (traducible)."""
        sql = self.get_translatable_sql(alias, 'name', 'account.account')
        if with_alias:
            return sql + " AS account_name"
        return sql

    def get_partner_name_sql(self, alias='rp', with_alias=True):
        """SQL para nombre de tercero (traducible)."""
        sql = self.get_translatable_sql(alias, 'name', 'res.partner')
        if with_alias:
            return sql + " AS partner_name"
        return sql

    def get_journal_name_sql(self, alias='aj', with_alias=True):
        """SQL para nombre de diario (traducible)."""
        sql = self.get_translatable_sql(alias, 'name', 'account.journal')
        if with_alias:
            return sql + " AS journal_name"
        return sql

    def get_tax_name_sql(self, alias='at', with_alias=True):
        """SQL para nombre de impuesto (traducible)."""
        sql = self.get_translatable_sql(alias, 'name', 'account.tax')
        if with_alias:
            return sql + " AS tax_name"
        return sql

    def get_product_name_sql(self, alias='pt', with_alias=True):
        """SQL para nombre de producto (traducible via product.template)."""
        sql = self.get_translatable_sql(alias, 'name', 'product.template')
        if with_alias:
            return sql + " AS product_name"
        return sql

    def build_select_with_translations(self, fields_config, base_query):
        """
        Construye SELECT con campos traducibles automaticamente.

        Args:
            fields_config: Lista de dicts con configuracion de campos
            base_query: Query base sin SELECT

        Returns:
            str: Query SQL completa

        Ejemplo:
            fields = [
                {'alias': 'aa', 'field': 'code', 'type': 'company_dependent', 'as': 'account_code'},
                {'alias': 'aa', 'field': 'name', 'type': 'translatable', 'model': 'account.account', 'as': 'account_name'},
                {'alias': 'rp', 'field': 'name', 'type': 'translatable', 'model': 'res.partner', 'as': 'partner_name'},
                {'alias': 'aml', 'field': 'debit', 'type': 'numeric', 'as': 'debit'},
            ]
            query = self.build_select_with_translations(fields, "FROM account_move_line aml ...")
        """
        select_parts = []

        for cfg in fields_config:
            alias = cfg.get('alias', '')
            field = cfg.get('field', '')
            field_type = cfg.get('type', 'simple')
            as_name = cfg.get('as', field)
            model = cfg.get('model')

            if field_type == 'company_dependent':
                sql = self.get_company_dependent_sql(alias, field + '_store')
            elif field_type == 'translatable':
                sql = self.get_translatable_sql(alias, field, model)
            elif field_type == 'numeric':
                sql = "COALESCE(" + alias + "." + field + ", 0)"
            else:
                sql = alias + "." + field

            select_parts.append(sql + " AS " + as_name)

        return "SELECT " + ", ".join(select_parts) + " " + base_query

    def build_report_query_with_fields(self, report, options, date_scope='strict_range',
                                       domain=None, joins=None, select_fields=None,
                                       group_by_fields=None):
        """
        Construye query completa para reportes usando el metodo nativo.

        Args:
            report: Objeto account.report
            options: Opciones del reporte
            date_scope: Alcance de fecha ('strict_range', 'from_beginning', etc.)
            domain: Dominio adicional
            joins: Lista de joins [{table, alias, on_column, link}]
            select_fields: Lista de campos para SELECT
            group_by_fields: Lista de campos para GROUP BY

        Returns:
            SQL: Query completa
        """
        base_domain = domain or []
        query = report._get_report_query(options, date_scope, domain=base_domain)

        aliases = {}
        if joins:
            for join_def in joins:
                aliases[join_def['alias']] = query.join(
                    lhs_alias='account_move_line',
                    lhs_column=join_def['on_column'],
                    rhs_table=join_def['table'],
                    rhs_column='id',
                    link=join_def.get('link', join_def['on_column'])
                )

        select_sql = []
        group_sql = []

        if select_fields:
            for sf in select_fields:
                model = sf.get('model')
                field = sf.get('field')
                alias = sf.get('alias')
                as_name = sf.get('as', field)
                is_sum = sf.get('sum', False)

                if model and alias in aliases:
                    field_sql = self.env[model]._field_to_sql(aliases[alias], field, query)
                    if is_sum:
                        select_sql.append(SQL(
                            "COALESCE(SUM(%(field)s), 0) AS %(alias)s",
                            field=field_sql, alias=SQL.identifier(as_name)
                        ))
                    else:
                        select_sql.append(SQL(
                            "%(field)s AS %(alias)s",
                            field=field_sql, alias=SQL.identifier(as_name)
                        ))
                        group_sql.append(field_sql)
                else:
                    full_field = alias + '.' + field if alias else field
                    if is_sum:
                        select_sql.append(SQL(
                            "COALESCE(SUM(%(field)s), 0) AS %(alias)s",
                            field=SQL(full_field), alias=SQL.identifier(as_name)
                        ))
                    else:
                        select_sql.append(SQL(
                            "%(field)s AS %(alias)s",
                            field=SQL(full_field), alias=SQL.identifier(as_name)
                        ))
                        if not is_sum:
                            group_sql.append(SQL(full_field))

        return SQL(
            """
            SELECT %(select)s
            FROM %(from)s
            %(currency_join)s
            WHERE %(where)s
            GROUP BY %(group_by)s
            """,
            select=SQL(", ").join(select_sql) if select_sql else SQL("*"),
            from_clause=query.from_clause,
            currency_join=report._currency_table_aml_join(options),
            where=query.where_clause,
            group_by=SQL(", ").join(group_sql) if group_sql else SQL("1"),
        )
