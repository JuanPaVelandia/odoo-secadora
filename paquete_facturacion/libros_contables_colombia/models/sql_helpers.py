# -*- coding: utf-8 -*-
"""
SQL Helpers para Odoo 18 - Campos JSONB
=======================================
Mixin y utilidades para generar expresiones SQL correctas
para campos company_dependent (JSONB) como code_store y name.

En Odoo 18, los campos como account.code ahora son computed
desde code_store que es un JSONB con formato {'company_id': 'value'}.

RECOMENDACIÓN: Usar el patrón nativo de Odoo 18 cuando sea posible:
    account_code = self.env['account.account']._field_to_sql(alias, 'code', query)
    account_name = self.env['account.account']._field_to_sql(alias, 'name')

Este mixin proporciona compatibilidad para casos donde no se usa Query object.
"""

from odoo import models, api
from odoo.tools import get_lang, SQL, Query


class SQLHelperMixin(models.AbstractModel):
    """
    Mixin que proporciona métodos helper para generar expresiones SQL
    compatibles con campos JSONB de Odoo 18.

    PATRÓN NATIVO RECOMENDADO:
        # Usando Query object (preferido)
        query = Query(self.env, 'account_move_line')
        account_alias = query.join(
            lhs_alias='account_move_line',
            lhs_column='account_id',
            rhs_table='account_account',
            rhs_column='id',
            link='account_id'
        )
        account_code = self.env['account.account']._field_to_sql(account_alias, 'code', query)
        account_name = self.env['account.account']._field_to_sql(account_alias, 'name')

    Este mixin provee fallback para casos simples sin Query object.
    """
    _name = 'sql.helper.mixin'
    _description = 'SQL Helper Mixin for Odoo 18 JSONB fields'

    def _get_company_id_for_sql(self):
        """Obtiene el ID de compañía para usar en expresiones SQL JSONB."""
        return str(self.env.company.root_id.id or self.env.company.id)

    def _get_account_field_sql(self, account_alias, field_name, query=None):
        """
        Obtiene expresión SQL para campo de cuenta usando el patrón nativo.

        Args:
            account_alias: Alias de la tabla account_account
            field_name: Nombre del campo ('code', 'name', etc.)
            query: Objeto Query (opcional, para _field_to_sql nativo)

        Returns:
            SQL expression usando _field_to_sql nativo si hay query,
            o expresión JSONB manual si no.
        """
        if query is not None:
            return self.env['account.account']._field_to_sql(account_alias, field_name, query)

        # Fallback manual para casos sin Query
        if field_name == 'code':
            return SQL(self._sql_account_code_inline(account_alias))
        elif field_name == 'name':
            return SQL(self._sql_translatable_inline(account_alias, 'name', 'account.account'))
        else:
            return SQL.identifier(account_alias, field_name)

    def _get_journal_name_sql(self, journal_alias, query=None):
        """Obtiene SQL para nombre de diario usando patrón nativo."""
        if query is not None:
            return self.env['account.journal']._field_to_sql(journal_alias, 'name')
        return SQL(self._sql_translatable_inline(journal_alias, 'name', 'account.journal'))

    def _sql_account_code(self, table_alias='account_account', field_alias='account_code'):
        """
        Genera expresión SQL para extraer el código de cuenta desde code_store.

        En Odoo 18, account.account.code es un campo computed que extrae
        desde code_store (JSONB con formato {'company_id': 'code'}).

        Args:
            table_alias: Alias de la tabla account_account en la query
            field_alias: Alias para el campo resultante

        Returns:
            str: Expresión SQL como "COALESCE(aa.code_store->>'1', ...) AS account_code"

        Ejemplo:
            >>> self._sql_account_code('aa', 'codigo')
            "COALESCE(aa.code_store->>'1', aa.code_store->>jsonb_object_keys(aa.code_store), '') AS codigo"
        """
        company_id = self._get_company_id_for_sql()
        return f"""COALESCE(
            {table_alias}.code_store->>'{company_id}',
            (SELECT value FROM jsonb_each_text({table_alias}.code_store) LIMIT 1),
            ''
        ) AS {field_alias}"""

    def _sql_account_code_inline(self, table_alias='account_account'):
        """
        Genera expresión SQL inline (sin AS) para usar en ORDER BY o WHERE.

        Args:
            table_alias: Alias de la tabla account_account

        Returns:
            str: Expresión SQL sin alias
        """
        company_id = self._get_company_id_for_sql()
        return f"""COALESCE(
            {table_alias}.code_store->>'{company_id}',
            (SELECT value FROM jsonb_each_text({table_alias}.code_store) LIMIT 1),
            ''
        )"""

    def _sql_translatable_field(self, table_alias, field_name, field_alias=None, model_name=None):
        """
        Genera expresión SQL para extraer campo translatable (JSONB).

        Los campos translate=True en Odoo 18 se almacenan como JSONB
        con formato {'lang_code': 'value'}.

        Args:
            table_alias: Alias de la tabla en la query
            field_name: Nombre del campo (ej: 'name')
            field_alias: Alias para el resultado (default: field_name)
            model_name: Nombre del modelo para verificar si es translate

        Returns:
            str: Expresión SQL con COALESCE para fallback de idiomas
        """
        if field_alias is None:
            field_alias = field_name

        lang = self.env.user.lang or get_lang(self.env).code

        # Verificar si el campo es translate
        is_translate = True
        if model_name:
            try:
                field = self.pool[model_name]._fields.get(field_name)
                is_translate = field and getattr(field, 'translate', False)
            except (KeyError, AttributeError):
                pass

        if is_translate:
            return f"""COALESCE(
                {table_alias}.{field_name}->>'{lang}',
                {table_alias}.{field_name}->>'es_CO',
                {table_alias}.{field_name}->>'es_ES',
                {table_alias}.{field_name}->>'en_US',
                (SELECT value FROM jsonb_each_text({table_alias}.{field_name}) LIMIT 1),
                ''
            ) AS {field_alias}"""
        else:
            return f"{table_alias}.{field_name} AS {field_alias}"

    def _sql_translatable_inline(self, table_alias, field_name, model_name=None):
        """
        Genera expresión SQL inline para campo translatable (sin AS).

        Útil para ORDER BY o WHERE clauses.
        """
        lang = self.env.user.lang or get_lang(self.env).code

        is_translate = True
        if model_name:
            try:
                field = self.pool[model_name]._fields.get(field_name)
                is_translate = field and getattr(field, 'translate', False)
            except (KeyError, AttributeError):
                pass

        if is_translate:
            return f"""COALESCE(
                {table_alias}.{field_name}->>'{lang}',
                {table_alias}.{field_name}->>'es_CO',
                {table_alias}.{field_name}->>'es_ES',
                {table_alias}.{field_name}->>'en_US',
                (SELECT value FROM jsonb_each_text({table_alias}.{field_name}) LIMIT 1),
                ''
            )"""
        else:
            return f"{table_alias}.{field_name}"

    def _sql_journal_name(self, table_alias='account_journal', field_alias='journal_name'):
        """Genera expresión SQL para nombre de diario (translatable)."""
        return self._sql_translatable_field(table_alias, 'name', field_alias, 'account.journal')

    def _sql_account_name(self, table_alias='account_account', field_alias='account_name'):
        """Genera expresión SQL para nombre de cuenta (translatable)."""
        return self._sql_translatable_field(table_alias, 'name', field_alias, 'account.account')

    def _sql_tax_name(self, table_alias='account_tax', field_alias='tax_name'):
        """Genera expresión SQL para nombre de impuesto (translatable)."""
        return self._sql_translatable_field(table_alias, 'name', field_alias, 'account.tax')

    def _sql_partner_doc_type(self, table_alias='l10n_latam_identification_type', field_alias='partner_doc_type'):
        """
        Genera expresión SQL para tipo de documento de partner.

        Mapea los códigos técnicos l10n_co_document_code a abreviaturas colombianas:
        - rut -> NIT (Número de Identificación Tributaria)
        - national_citizen_id -> CC (Cédula de Ciudadanía)
        - foreign_resident_card -> CE (Cédula de Extranjería)
        - foreign_colombian_card -> TE (Tarjeta de Extranjería)
        - passport -> PA (Pasaporte)
        - id_card -> TI (Tarjeta de Identidad)
        - civil_registration -> RC (Registro Civil)
        - foreign_id_card -> CEX (Cédula Extranjera)
        - external_id -> NE (NIT Extranjero)
        - niup_id -> NIUP
        - PPT -> PPT (Permiso Protección Temporal)
        - pep -> PEP (Permiso Especial de Permanencia)
        - vat -> CC (por defecto para VAT genérico)
        """
        return f"""
            CASE {table_alias}.l10n_co_document_code
                WHEN 'rut' THEN 'NIT'
                WHEN 'national_citizen_id' THEN 'CC'
                WHEN 'foreign_resident_card' THEN 'CE'
                WHEN 'foreign_colombian_card' THEN 'TE'
                WHEN 'passport' THEN 'PA'
                WHEN 'id_card' THEN 'TI'
                WHEN 'civil_registration' THEN 'RC'
                WHEN 'foreign_id_card' THEN 'CEX'
                WHEN 'external_id' THEN 'NE'
                WHEN 'niup_id' THEN 'NIUP'
                WHEN 'PPT' THEN 'PPT'
                WHEN 'pep' THEN 'PEP'
                WHEN 'vat' THEN 'CC'
                ELSE COALESCE({table_alias}.l10n_co_document_code, 'CC')
            END AS {field_alias}"""

    def _build_account_select_fields(self, account_alias='account_account'):
        """
        Construye los campos SELECT comunes para cuentas contables.

        Returns:
            dict: Diccionario con expresiones SQL nombradas
        """
        return {
            'account_code': self._sql_account_code_inline(account_alias),
            'account_name': self._sql_translatable_inline(account_alias, 'name', 'account.account'),
        }

    def _validate_jsonb_field_access(self, table_alias, field_name, company_id=None):
        """
        Valida y genera acceso seguro a campo JSONB company_dependent.

        Args:
            table_alias: Alias de la tabla
            field_name: Nombre del campo JSONB
            company_id: ID de compañía (default: compañía actual)

        Returns:
            str: Expresión SQL segura
        """
        if company_id is None:
            company_id = self._get_company_id_for_sql()

        return f"""COALESCE(
            {table_alias}.{field_name}->>'{company_id}',
            (SELECT value FROM jsonb_each_text({table_alias}.{field_name}) LIMIT 1)
        )"""


class SQLHelperOdoo18(models.AbstractModel):
    """
    Helper class con métodos estáticos para uso en queries sin herencia.

    Uso:
        helper = self.env['sql.helper.odoo18']
        code_expr = helper.get_account_code_sql('aa', self.env.company.id)
    """
    _name = 'sql.helper.odoo18'
    _description = 'SQL Helper for Odoo 18'

    def get_account_code_sql(self, table_alias, company_id):
        """Genera SQL para extraer código de cuenta."""
        return f"""COALESCE(
            {table_alias}.code_store->>'{company_id}',
            (SELECT value FROM jsonb_each_text({table_alias}.code_store) LIMIT 1),
            ''
        )"""

    def get_translatable_sql(self, table_alias, field_name, lang='es_CO'):
        """Genera SQL para extraer campo translatable."""
        return f"""COALESCE(
            {table_alias}.{field_name}->>'{lang}',
            {table_alias}.{field_name}->>'en_US',
            (SELECT value FROM jsonb_each_text({table_alias}.{field_name}) LIMIT 1),
            ''
        )"""
