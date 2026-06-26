# -*- coding: utf-8 -*-
"""
Balance de Prueba por Tercero con Jerarquía PUC - Colombia
==========================================================

Estructura jerárquica del reporte:

NIVEL 1: Clase (1 dígito)       → 1 ACTIVO
NIVEL 2: Grupo (2 dígitos)      →   11 DISPONIBLE
NIVEL 3: Cuenta (4 dígitos)     →     1110 BANCOS
NIVEL 4: Subcuenta (6+ dígitos) →       111005 BANCOS NACIONALES
NIVEL 5: Tercero                →         NIT 890903938 - BANCOLOMBIA
NIVEL 6: Movimientos            →           01/12/2024 - RC-001 - Recaudo

Columnas:
- Cuenta | Nombre | Sdo.Inicial | Débitos | Créditos | Sdo.Final

La columna "Nombre" muestra:
- En niveles PUC: Nombre de la cuenta
- En nivel Tercero: "TipoDoc NIT/CC - Nombre Tercero"
- En nivel Movimiento: Referencia del movimiento
"""

from collections import defaultdict
from datetime import timedelta
import re
import logging

from odoo import models, fields, api, _
from odoo.tools import SQL
from odoo.tools.misc import format_date

_logger = logging.getLogger(__name__)

# Mapeo de longitud de código a nivel PUC
PUC_LEVEL_MAP = {
    1: 1,   # Clase
    2: 2,   # Grupo
    4: 3,   # Cuenta
    6: 4,   # Subcuenta
    8: 5,   # Auxiliar
    10: 6,  # Detalle
}

# Nombres de las clases del PUC Colombiano
PUC_CLASS_NAMES = {
    '1': 'ACTIVO',
    '2': 'PASIVO',
    '3': 'PATRIMONIO',
    '4': 'INGRESOS',
    '5': 'GASTOS',
    '6': 'COSTOS DE VENTAS',
    '7': 'COSTOS DE PRODUCCIÓN',
    '8': 'CUENTAS DE ORDEN DEUDORAS',
    '9': 'CUENTAS DE ORDEN ACREEDORAS',
}


class TrialBalancePartnerCustomHandler(models.AbstractModel):
    _name = 'account.trial.balance.partner.report.handler'
    _inherit = ['account.report.custom.handler', 'sql.helper.mixin']
    _description = 'Balance de Prueba por Tercero con Jerarquía PUC'

    # =========================================================================
    # CONFIGURACIÓN DEL REPORTE
    # =========================================================================

    def _get_custom_display_config(self):
        return {
            'css_custom_class': 'trial_balance_partner_report',
            'templates': {
                'AccountReportLineName': 'account_reports.GeneralLedgerLineName',
            },
            'components': {
                'AccountReportFilters': 'libros_contables_colombia.TrialBalancePartnerFilters',
            },
            'pdf_export': {
                'pdf_export_main': 'libros_contables_colombia.pdf_trial_balance_partner_main',
            },
        }

    def _get_lines_for_pdf(self, report, options):
        """
        Genera todas las líneas expandidas para el PDF.
        Expande automáticamente todos los niveles hasta terceros (nivel 5).
        """
        all_lines = []

        # Obtener todos los datos
        raw_data = self._get_all_account_partner_data(report, options)
        if not raw_data:
            return all_lines

        # Filtrar líneas con saldo cero si está activada la opción
        hide_zero = options.get('filter_hide_0_lines') == 'always'
        if hide_zero:
            raw_data = [d for d in raw_data if not self._is_zero_balance(d)]

        # Calcular totales generales
        totals = {'initial': 0, 'debit': 0, 'credit': 0, 'final': 0}

        # Nivel 1: Clases
        grouped_l1 = self._group_by_puc_prefix(raw_data, prefix_length=1)

        for class_code in sorted(grouped_l1.keys()):
            class_data = grouped_l1[class_code]
            class_name = PUC_CLASS_NAMES.get(class_code, class_data['name'])

            # Línea de Clase
            all_lines.append(self._build_line(
                report, options,
                code=class_code, name=class_name,
                initial=class_data['initial'], debit=class_data['debit'],
                credit=class_data['credit'], final=class_data['final'],
                level=1, has_children=False, parent_line_id=None,
                markup=f'puc_{class_code}',
                last_move_date=class_data.get('last_move_date'),
                account_code=class_code, account_name=class_name,
            ))

            totals['initial'] += class_data['initial']
            totals['debit'] += class_data['debit']
            totals['credit'] += class_data['credit']
            totals['final'] += class_data['final']

            # Nivel 2: Grupos (2 dígitos)
            filtered_l2 = [d for d in raw_data if (d.get('account_code') or '').startswith(class_code)]
            grouped_l2 = self._group_by_puc_prefix(filtered_l2, prefix_length=2, parent_prefix=class_code)

            for group_code in sorted(grouped_l2.keys()):
                if not group_code.startswith(class_code) or group_code == class_code:
                    continue
                group_data = grouped_l2[group_code]

                all_lines.append(self._build_line(
                    report, options,
                    code=group_code, name=group_data['name'],
                    initial=group_data['initial'], debit=group_data['debit'],
                    credit=group_data['credit'], final=group_data['final'],
                    level=2, has_children=False, parent_line_id=None,
                    markup=f'puc_{group_code}',
                    last_move_date=group_data.get('last_move_date'),
                    account_code=group_code, account_name=group_data['name'],
                ))

                # Nivel 3: Cuentas (4 dígitos)
                filtered_l3 = [d for d in filtered_l2 if (d.get('account_code') or '').startswith(group_code)]
                grouped_l3 = self._group_by_puc_prefix(filtered_l3, prefix_length=4, parent_prefix=group_code)

                for cuenta_code in sorted(grouped_l3.keys()):
                    if not cuenta_code.startswith(group_code) or cuenta_code == group_code:
                        continue
                    cuenta_data = grouped_l3[cuenta_code]

                    all_lines.append(self._build_line(
                        report, options,
                        code=cuenta_code, name=cuenta_data['name'],
                        initial=cuenta_data['initial'], debit=cuenta_data['debit'],
                        credit=cuenta_data['credit'], final=cuenta_data['final'],
                        level=3, has_children=False, parent_line_id=None,
                        markup=f'puc_{cuenta_code}',
                        last_move_date=cuenta_data.get('last_move_date'),
                        account_code=cuenta_code, account_name=cuenta_data['name'],
                    ))

                    # Nivel 4: Subcuentas (6 dígitos)
                    filtered_l4 = [d for d in filtered_l3 if (d.get('account_code') or '').startswith(cuenta_code)]
                    grouped_l4 = self._group_by_puc_prefix(filtered_l4, prefix_length=6, parent_prefix=cuenta_code)

                    for subcuenta_code in sorted(grouped_l4.keys()):
                        if not subcuenta_code.startswith(cuenta_code) or subcuenta_code == cuenta_code:
                            continue
                        subcuenta_data = grouped_l4[subcuenta_code]

                        all_lines.append(self._build_line(
                            report, options,
                            code=subcuenta_code, name=subcuenta_data['name'],
                            initial=subcuenta_data['initial'], debit=subcuenta_data['debit'],
                            credit=subcuenta_data['credit'], final=subcuenta_data['final'],
                            level=4, has_children=False, parent_line_id=None,
                            markup=f'puc_{subcuenta_code}',
                            last_move_date=subcuenta_data.get('last_move_date'),
                            account_code=subcuenta_code, account_name=subcuenta_data['name'],
                        ))

                        # Nivel 5: Terceros
                        account_data = [d for d in filtered_l4 if (d.get('account_code') or '').startswith(subcuenta_code)]
                        partners = {}
                        for data in account_data:
                            partner_id = data.get('partner_id')
                            key = partner_id or 'no_partner'
                            if key not in partners:
                                partners[key] = {
                                    'partner_id': partner_id,
                                    'partner_name': data.get('partner_name', _('Sin Tercero')),
                                    'partner_vat': data.get('partner_vat', ''),
                                    'partner_doc_type': data.get('partner_doc_type', 'CC'),
                                    'account_code': data.get('account_code', ''),
                                    'initial': 0, 'debit': 0, 'credit': 0, 'final': 0,
                                    'last_move_date': None,
                                }
                            partners[key]['initial'] += data.get('initial', 0)
                            partners[key]['debit'] += data.get('debit', 0)
                            partners[key]['credit'] += data.get('credit', 0)
                            partners[key]['final'] += data.get('final', 0)
                            if data.get('last_move_date'):
                                if not partners[key]['last_move_date'] or data['last_move_date'] > partners[key]['last_move_date']:
                                    partners[key]['last_move_date'] = data['last_move_date']

                        # Filtrar terceros sin movimiento si está activa la opción
                        hide_no_movement = options.get('hide_partners_no_movement', False)

                        for partner_data in sorted(partners.values(), key=lambda x: x.get('partner_name', '')):
                            # Si está activo el filtro, omitir terceros sin movimiento en el período
                            if hide_no_movement:
                                if partner_data['debit'] == 0 and partner_data['credit'] == 0:
                                    _logger.debug(f"Filtrando tercero sin movimiento: {partner_data['partner_name']} en cuenta {subcuenta_code}")
                                    continue

                            doc_type = partner_data['partner_doc_type']
                            vat = partner_data['partner_vat']
                            partner_vat_display = f"{doc_type} {vat}" if vat else ''

                            all_lines.append(self._build_line(
                                report, options,
                                code=partner_data['account_code'],
                                name=partner_data['partner_name'],
                                initial=partner_data['initial'], debit=partner_data['debit'],
                                credit=partner_data['credit'], final=partner_data['final'],
                                level=5, has_children=False, parent_line_id=None,
                                markup=f'partner_{partner_data["partner_id"] or 0}',
                                last_move_date=partner_data.get('last_move_date'),
                                account_code=partner_data['account_code'],
                                account_name='',
                                partner_name=partner_data['partner_name'],
                                partner_vat=partner_vat_display,
                            ))

        # Línea de TOTAL GENERAL
        if all_lines:
            all_lines.append(self._get_total_line(report, options, totals))

        return all_lines

    def _custom_options_initializer(self, report, options, previous_options=None):
        super()._custom_options_initializer(report, options, previous_options=previous_options)

        # Deshabilitar totales automáticos - manejamos el total manualmente
        options['ignore_totals_below_sections'] = True

        # Nivel inicial de expansión (1-6, default 1 = solo clases)
        options['puc_initial_level'] = (previous_options or {}).get('puc_initial_level', 1)

        # Filtro de líneas con saldo cero
        if not options.get('filter_hide_0_lines'):
            options['filter_hide_0_lines'] = 'optional'
        if previous_options and 'filter_hide_0_lines' in previous_options:
            options['filter_hide_0_lines'] = previous_options['filter_hide_0_lines']

        # Nota: El filtro hide_partners_no_movement se inicializa en account_report_extend.py
        # mediante el método _init_options_hide_partners_no_movement

    # =========================================================================
    # GENERACIÓN DE LÍNEAS DINÁMICAS
    # =========================================================================

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        """
        Genera las líneas del Balance de Prueba con jerarquía PUC.
        Muestra inicialmente solo las Clases (nivel 1) que son expandibles.
        """
        lines = []

        # Obtener todos los datos de cuenta/tercero
        raw_data = self._get_all_account_partner_data(report, options)

        if not raw_data:
            return [(0, self._get_no_data_line(report, options))]

        # Filtrar líneas con saldo cero si está activada la opción
        hide_zero = options.get('filter_hide_0_lines') == 'always'
        if hide_zero:
            raw_data = [d for d in raw_data if not self._is_zero_balance(d)]

        # Agrupar por nivel 1 (Clase - 1 dígito)
        grouped = self._group_by_puc_prefix(raw_data, prefix_length=1)

        # Calcular totales generales
        totals = {'initial': 0, 'debit': 0, 'credit': 0, 'final': 0}

        for class_code in sorted(grouped.keys()):
            class_data = grouped[class_code]
            class_name = PUC_CLASS_NAMES.get(class_code, class_data['name'])

            # Crear línea de Clase (Nivel 1)
            line = self._build_line(
                report, options,
                code=class_code,
                name=class_name,
                initial=class_data['initial'],
                debit=class_data['debit'],
                credit=class_data['credit'],
                final=class_data['final'],
                level=1,
                has_children=True,
                parent_line_id=None,
                markup=f'puc_{class_code}',
                expand_function='_report_expand_unfoldable_line_puc',
                last_move_date=class_data.get('last_move_date'),
                account_code=class_code,
                account_name=class_name,
            )
            lines.append(line)

            totals['initial'] += class_data['initial']
            totals['debit'] += class_data['debit']
            totals['credit'] += class_data['credit']
            totals['final'] += class_data['final']

        # Línea de TOTAL GENERAL
        if lines:
            lines.append(self._get_total_line(report, options, totals))

        return [(0, line) for line in lines]

    # =========================================================================
    # OBTENCIÓN DE DATOS
    # =========================================================================

    def _get_all_account_partner_data(self, report, options):
        """
        Obtiene todos los datos de cuenta/tercero usando patrón SQL nativo de Odoo 18.
        Retorna lista de diccionarios con saldos por cuenta y tercero.
        """
        queries = []

        for column_group_key, options_group in report._split_options_per_column_group(options).items():
            # ========== SALDOS DEL PERÍODO ==========
            query = report._get_report_query(options_group, date_scope='strict_range')

            # JOIN con account_account
            account_alias = query.join(
                lhs_alias='account_move_line',
                lhs_column='account_id',
                rhs_table='account_account',
                rhs_column='id',
                link='account_id'
            )

            # JOIN con res_partner
            partner_alias = query.left_join(
                lhs_alias='account_move_line',
                lhs_column='partner_id',
                rhs_table='res_partner',
                rhs_column='id',
                link='partner_id'
            )

            # JOIN con tipo de documento
            doc_type_alias = query.left_join(
                lhs_alias=partner_alias,
                lhs_column='l10n_latam_identification_type_id',
                rhs_table='l10n_latam_identification_type',
                rhs_column='id',
                link='doc_type'
            )

            # Expresiones SQL para campos JSONB
            account_code = self.env['account.account']._field_to_sql(account_alias, 'code', query)
            account_name = self.env['account.account']._field_to_sql(account_alias, 'name')

            queries.append(SQL(
                """
                SELECT
                    account_move_line.account_id,
                    %(account_code)s AS account_code,
                    %(account_name)s AS account_name,
                    account_move_line.partner_id,
                    %(partner_alias)s.name AS partner_name,
                    %(partner_alias)s.vat AS partner_vat,
                    CASE %(doc_type_alias)s.l10n_co_document_code
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
                        ELSE COALESCE(%(doc_type_alias)s.l10n_co_document_code, 'CC')
                    END AS partner_doc_type,
                    'period' AS data_type,
                    0 AS balance,
                    COALESCE(SUM(%(debit_select)s), 0) AS debit,
                    COALESCE(SUM(%(credit_select)s), 0) AS credit,
                    MAX(account_move_line.date) AS last_move_date
                FROM %(table_references)s
                %(currency_table_join)s
                WHERE %(search_condition)s
                GROUP BY
                    account_move_line.account_id,
                    %(account_code)s,
                    %(account_name)s,
                    account_move_line.partner_id,
                    %(partner_alias)s.name,
                    %(partner_alias)s.vat,
                    %(doc_type_alias)s.l10n_co_document_code
                HAVING COALESCE(SUM(%(debit_select)s), 0) != 0
                    OR COALESCE(SUM(%(credit_select)s), 0) != 0
                """,
                account_code=account_code,
                account_name=account_name,
                partner_alias=SQL.identifier(partner_alias),
                doc_type_alias=SQL.identifier(doc_type_alias),
                table_references=query.from_clause,
                search_condition=query.where_clause,
                debit_select=report._currency_table_apply_rate(SQL("account_move_line.debit")),
                credit_select=report._currency_table_apply_rate(SQL("account_move_line.credit")),
                currency_table_join=report._currency_table_aml_join(options_group),
            ))

            # ========== SALDOS INICIALES ==========
            initial_options = self._get_options_initial_balance(options_group)
            query_init = report._get_report_query(initial_options, date_scope='from_beginning')

            account_alias_init = query_init.join(
                lhs_alias='account_move_line',
                lhs_column='account_id',
                rhs_table='account_account',
                rhs_column='id',
                link='account_id'
            )

            partner_alias_init = query_init.left_join(
                lhs_alias='account_move_line',
                lhs_column='partner_id',
                rhs_table='res_partner',
                rhs_column='id',
                link='partner_id'
            )

            doc_type_alias_init = query_init.left_join(
                lhs_alias=partner_alias_init,
                lhs_column='l10n_latam_identification_type_id',
                rhs_table='l10n_latam_identification_type',
                rhs_column='id',
                link='doc_type'
            )

            account_code_init = self.env['account.account']._field_to_sql(account_alias_init, 'code', query_init)
            account_name_init = self.env['account.account']._field_to_sql(account_alias_init, 'name')

            queries.append(SQL(
                """
                SELECT
                    account_move_line.account_id,
                    %(account_code)s AS account_code,
                    %(account_name)s AS account_name,
                    account_move_line.partner_id,
                    %(partner_alias)s.name AS partner_name,
                    %(partner_alias)s.vat AS partner_vat,
                    CASE %(doc_type_alias)s.l10n_co_document_code
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
                        ELSE COALESCE(%(doc_type_alias)s.l10n_co_document_code, 'CC')
                    END AS partner_doc_type,
                    'initial' AS data_type,
                    COALESCE(SUM(%(balance_select)s), 0) AS balance,
                    0 AS debit,
                    0 AS credit,
                    NULL::date AS last_move_date
                FROM %(table_references)s
                %(currency_table_join)s
                WHERE %(search_condition)s
                GROUP BY
                    account_move_line.account_id,
                    %(account_code)s,
                    %(account_name)s,
                    account_move_line.partner_id,
                    %(partner_alias)s.name,
                    %(partner_alias)s.vat,
                    %(doc_type_alias)s.l10n_co_document_code
                HAVING COALESCE(SUM(%(balance_select)s), 0) != 0
                """,
                account_code=account_code_init,
                account_name=account_name_init,
                partner_alias=SQL.identifier(partner_alias_init),
                doc_type_alias=SQL.identifier(doc_type_alias_init),
                table_references=query_init.from_clause,
                search_condition=query_init.where_clause,
                balance_select=report._currency_table_apply_rate(SQL("account_move_line.balance")),
                currency_table_join=report._currency_table_aml_join(initial_options),
            ))

        full_query = SQL(" UNION ALL ").join(SQL("(%s)", q) for q in queries)
        self._cr.execute(full_query)

        # Procesar resultados - agrupar por cuenta/tercero
        results = {}
        for row in self._cr.dictfetchall():
            key = (row['account_id'], row['partner_id'])

            if key not in results:
                results[key] = {
                    'account_id': row['account_id'],
                    'account_code': row['account_code'] or '',
                    'account_name': row['account_name'] or '',
                    'partner_id': row['partner_id'],
                    'partner_name': row['partner_name'] or _('Sin Tercero'),
                    'partner_vat': row['partner_vat'] or '',
                    'partner_doc_type': row['partner_doc_type'] or 'CC',
                    'initial': 0.0,
                    'debit': 0.0,
                    'credit': 0.0,
                    'last_move_date': None,
                }

            if row['data_type'] == 'initial':
                results[key]['initial'] = float(row.get('balance', 0) or 0)
            else:
                results[key]['debit'] = float(row.get('debit', 0) or 0)
                results[key]['credit'] = float(row.get('credit', 0) or 0)
                if row.get('last_move_date'):
                    current = results[key]['last_move_date']
                    if not current or row['last_move_date'] > current:
                        results[key]['last_move_date'] = row['last_move_date']

        # Calcular saldo final
        for data in results.values():
            data['final'] = data['initial'] + data['debit'] - data['credit']

        return list(results.values())

    def _get_options_initial_balance(self, options):
        """Crea opciones para obtener saldo inicial (antes del período)."""
        new_options = options.copy()
        date_from = fields.Date.from_string(options['date']['date_from'])
        new_date_to = date_from - timedelta(days=1)

        fiscalyear_dates = self.env.company.compute_fiscalyear_dates(date_from)

        if date_from == fiscalyear_dates['date_from']:
            prev_fiscalyear = self.env.company.compute_fiscalyear_dates(date_from - timedelta(days=1))
            new_date_from = prev_fiscalyear['date_from']
        else:
            new_date_from = fiscalyear_dates['date_from']

        new_options['date'] = self.env['account.report']._get_dates_period(
            new_date_from, new_date_to, 'range'
        )

        return new_options

    # =========================================================================
    # AGRUPACIÓN POR JERARQUÍA PUC
    # =========================================================================

    def _group_by_puc_prefix(self, data_list, prefix_length, parent_prefix=''):
        """
        Agrupa datos por prefijo de código de cuenta.

        Args:
            data_list: Lista de diccionarios con datos cuenta/tercero
            prefix_length: Longitud del prefijo para agrupar
            parent_prefix: Prefijo padre para filtrar (opcional)

        Returns:
            Dict con prefijos como claves y datos agregados como valores
        """
        grouped = defaultdict(lambda: {
            'name': '',
            'initial': 0.0,
            'debit': 0.0,
            'credit': 0.0,
            'final': 0.0,
            'last_move_date': None,  # Fecha del último movimiento
            'accounts': [],  # Cuentas hoja dentro de este grupo
            'has_children': False,
            'has_partners': False,
        })

        for data in data_list:
            code = data.get('account_code', '') or ''

            # Filtrar por prefijo padre si se especifica
            if parent_prefix and not code.startswith(parent_prefix):
                continue

            # Obtener prefijo según longitud
            if len(code) >= prefix_length:
                prefix = code[:prefix_length]
            else:
                prefix = code

            # Agregar valores
            grouped[prefix]['initial'] += data.get('initial', 0)
            grouped[prefix]['debit'] += data.get('debit', 0)
            grouped[prefix]['credit'] += data.get('credit', 0)
            grouped[prefix]['final'] += data.get('final', 0)
            grouped[prefix]['accounts'].append(data)

            # Trackear la fecha más reciente de movimiento
            data_last_date = data.get('last_move_date')
            if data_last_date:
                current_last = grouped[prefix]['last_move_date']
                if not current_last or data_last_date > current_last:
                    grouped[prefix]['last_move_date'] = data_last_date

            # Nombre del grupo (usar el primero encontrado o nombre de clase)
            if not grouped[prefix]['name']:
                if prefix_length == 1:
                    grouped[prefix]['name'] = PUC_CLASS_NAMES.get(prefix, data.get('account_name', ''))
                else:
                    grouped[prefix]['name'] = data.get('account_name', '')

            # Verificar si tiene terceros
            if data.get('partner_id'):
                grouped[prefix]['has_partners'] = True

        # Determinar si tiene hijos (códigos más largos)
        for prefix, group_data in grouped.items():
            group_data['has_children'] = any(
                len(acc.get('account_code', '')) > len(prefix)
                for acc in group_data['accounts']
            )

        return grouped

    # =========================================================================
    # CONSTRUCCIÓN DE LÍNEAS - ESTRUCTURA UNIFICADA
    # =========================================================================

    def _build_line(self, report, options, code, name, initial, debit, credit, final,
                    level, has_children, parent_line_id, markup, expand_function=None,
                    css_class='', caret_options=None, last_move_date=None,
                    account_code='', account_name='', partner_name='', partner_vat=''):
        """
        Construye una línea con estructura de columnas unificada.
        Usada para todos los niveles: PUC, Terceros y Movimientos.

        Columnas: Código | Nombre Cuenta | Tercero | NIT | Últ.Mov | Sdo.Inicial | Débitos | Créditos | Sdo.Final

        Para niveles PUC (1-4):
        - Código: código de la cuenta
        - Nombre Cuenta: nombre de la cuenta
        - Tercero: vacío
        - NIT: vacío

        Para nivel Tercero (5):
        - Código: código de la cuenta padre
        - Nombre Cuenta: vacío (ya está arriba)
        - Tercero: nombre del tercero
        - NIT: tipo doc + número

        Para nivel Movimiento (6):
        - Código: número de asiento
        - Nombre Cuenta: descripción/referencia
        - Tercero: vacío
        - NIT: vacío
        """
        line_id = report._get_generic_line_id(None, None, markup=markup, parent_line_id=parent_line_id)
        is_unfolded = line_id in options.get('unfolded_lines', [])

        # Determinar valores según el nivel
        # Para niveles PUC (1-4): código y nombre de cuenta van en las primeras columnas
        # Para nivel Tercero (5): el nombre del tercero y NIT van en las columnas correspondientes
        # Para nivel Movimiento (6): número de asiento y descripción

        final_account_code = account_code if account_code else code
        final_account_name = account_name if account_name else name
        final_partner_name = partner_name
        final_partner_vat = partner_vat

        # Calcular variación
        initial_val = initial or 0
        final_val = final or 0
        variation = final_val - initial_val
        variation_percent = (variation / initial_val * 100) if initial_val != 0 else 0.0

        columns = []
        for col in options['columns']:
            label = col['expression_label']
            value = None

            if label == 'account_code':
                value = final_account_code
            elif label == 'account_name':
                value = final_account_name
            elif label == 'partner_name':
                value = final_partner_name
            elif label == 'partner_vat':
                value = final_partner_vat
            elif label == 'last_move_date':
                value = last_move_date
            elif label == 'initial_balance':
                value = initial
            elif label == 'debit':
                value = debit
            elif label == 'credit':
                value = credit
            elif label == 'final_balance':
                value = final
            elif label == 'variation':
                value = variation
            elif label == 'variation_percent':
                value = variation_percent / 100  # Odoo espera 0.15 para 15%

            columns.append(report._build_column_dict(value, col, options=options))

        # La columna expandible queda vacía (solo muestra la flechita)
        display_name = ''

        line = {
            'id': line_id,
            'name': display_name,
            'level': level,
            'parent_id': parent_line_id,
            'unfoldable': has_children,
            'unfolded': is_unfolded,
            'columns': columns,
        }

        if expand_function:
            line['expand_function'] = expand_function

        if css_class:
            line['class'] = css_class

        if caret_options:
            line['caret_options'] = caret_options

        return line

    def _get_total_line(self, report, options, totals):
        """Crea la línea de TOTAL GENERAL."""
        return self._build_line(
            report, options,
            code='',
            name='',
            initial=totals['initial'],
            debit=totals['debit'],
            credit=totals['credit'],
            final=totals['final'],
            level=1,
            has_children=False,
            parent_line_id=None,
            markup='total',
            css_class='font-weight-bold o_account_reports_totals_below_sections',
            account_code='',
            account_name=_('TOTAL GENERAL'),
        )

    def _get_no_data_line(self, report, options):
        """Crea línea cuando no hay datos."""
        return {
            'id': report._get_generic_line_id(None, None, markup='no_data'),
            'name': _('No hay movimientos en el período seleccionado'),
            'level': 1,
            'unfoldable': False,
            'columns': [{'name': ''} for _ in options['columns']],
        }

    # =========================================================================
    # EXPANSIÓN DE LÍNEAS PUC
    # =========================================================================

    def _report_expand_unfoldable_line_puc(self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None):
        """
        Expande una línea PUC al siguiente nivel.

        Lógica:
        - Si código tiene 1 dígito → expandir a 2 dígitos (Grupos)
        - Si código tiene 2 dígitos → expandir a 4 dígitos (Cuentas)
        - Si código tiene 4 dígitos → expandir a 6+ dígitos (Subcuentas)
        - Si código tiene 6+ dígitos → expandir a TERCEROS
        """
        report = self.env['account.report'].browse(options['report_id'])
        lines = []

        # Extraer código PUC del line_id
        matches = re.findall(r'puc_(\d+)', line_dict_id)
        if not matches:
            return {'lines': [], 'offset_increment': 0, 'has_more': False}

        parent_code = matches[-1]
        parent_len = len(parent_code)

        # Determinar siguiente nivel
        if parent_len == 1:
            next_len = 2
            next_level = 2
        elif parent_len == 2:
            next_len = 4
            next_level = 3
        elif parent_len == 4:
            next_len = 6
            next_level = 4
        else:
            # Ya estamos en subcuenta (6+ dígitos)
            # Verificar si se deben mostrar terceros
            if options.get('puc_show_partners', True):
                return self._expand_to_partners(report, options, parent_code, line_dict_id)
            else:
                # Si no se muestran terceros, no expandir más
                return {'lines': [], 'offset_increment': 0, 'has_more': False}

        # Obtener datos y filtrar por código padre
        raw_data = self._get_all_account_partner_data(report, options)

        # Filtrar líneas con saldo cero si está activada la opción
        hide_zero = options.get('filter_hide_0_lines') == 'always'
        if hide_zero:
            raw_data = [d for d in raw_data if not self._is_zero_balance(d)]

        # Filtrar por prefijo padre
        filtered_data = [d for d in raw_data if (d.get('account_code') or '').startswith(parent_code)]

        if not filtered_data:
            return {'lines': [], 'offset_increment': 0, 'has_more': False}

        # Agrupar por siguiente nivel
        grouped = self._group_by_puc_prefix(filtered_data, prefix_length=next_len, parent_prefix=parent_code)

        for code in sorted(grouped.keys()):
            if not code.startswith(parent_code) or code == parent_code:
                continue

            group_data = grouped[code]

            line = self._build_line(
                report, options,
                code=code,
                name=group_data['name'],
                initial=group_data['initial'],
                debit=group_data['debit'],
                credit=group_data['credit'],
                final=group_data['final'],
                level=next_level,
                has_children=group_data['has_children'] or group_data['has_partners'],
                parent_line_id=line_dict_id,
                markup=f'puc_{code}',
                expand_function='_report_expand_unfoldable_line_puc',
                css_class='font-weight-bold' if next_level <= 2 else '',
                last_move_date=group_data.get('last_move_date'),
                account_code=code,
                account_name=group_data['name'],
            )
            lines.append(line)

        return {
            'lines': lines,
            'offset_increment': len(lines),
            'has_more': False,
        }

    def _expand_to_partners(self, report, options, account_code, parent_line_id):
        """Expande una subcuenta para mostrar sus terceros."""
        lines = []

        # Obtener datos
        raw_data = self._get_all_account_partner_data(report, options)

        # Filtrar por código de cuenta exacto o que empiece con el código
        account_data = [
            d for d in raw_data
            if (d.get('account_code') or '').startswith(account_code)
        ]

        # Filtrar líneas con saldo cero
        hide_zero = options.get('filter_hide_0_lines') == 'always'
        if hide_zero:
            account_data = [d for d in account_data if not self._is_zero_balance(d)]

        # Agrupar por tercero
        partners = defaultdict(lambda: {
            'partner_id': None,
            'partner_name': '',
            'partner_vat': '',
            'partner_doc_type': 'CC',
            'account_id': None,
            'account_code': '',
            'initial': 0.0,
            'debit': 0.0,
            'credit': 0.0,
            'final': 0.0,
            'last_move_date': None,
        })

        for data in account_data:
            partner_id = data.get('partner_id')
            key = partner_id or 'no_partner'

            partners[key]['partner_id'] = partner_id
            partners[key]['partner_name'] = data.get('partner_name', _('Sin Tercero'))
            partners[key]['partner_vat'] = data.get('partner_vat', '')
            partners[key]['partner_doc_type'] = data.get('partner_doc_type', 'CC')
            partners[key]['account_id'] = data.get('account_id')
            partners[key]['account_code'] = data.get('account_code', '')
            partners[key]['initial'] += data.get('initial', 0)
            partners[key]['debit'] += data.get('debit', 0)
            partners[key]['credit'] += data.get('credit', 0)
            partners[key]['final'] += data.get('final', 0)

            # Trackear última fecha de movimiento
            data_last_date = data.get('last_move_date')
            if data_last_date:
                current_last = partners[key]['last_move_date']
                if not current_last or data_last_date > current_last:
                    partners[key]['last_move_date'] = data_last_date

        # Ordenar por nombre de tercero
        sorted_partners = sorted(partners.values(), key=lambda x: x.get('partner_name', ''))

        # Filtrar terceros sin movimiento si está activa la opción
        hide_no_movement = options.get('hide_partners_no_movement', False)

        for partner_data in sorted_partners:
            # Si está activo el filtro, omitir terceros sin movimiento en el período
            if hide_no_movement:
                if partner_data['debit'] == 0 and partner_data['credit'] == 0:
                    continue

            partner_id = partner_data['partner_id']
            account_id = partner_data['account_id']
            account_code = partner_data['account_code']
            doc_type = partner_data['partner_doc_type']
            vat = partner_data['partner_vat']
            partner_name = partner_data['partner_name']

            # Construir NIT con tipo de documento
            partner_vat_display = f"{doc_type} {vat}" if vat else ''

            # Verificar si se deben mostrar movimientos
            show_movements = options.get('puc_show_movements', True)

            line = self._build_line(
                report, options,
                code=account_code,
                name=partner_name,  # Nombre para navegación
                initial=partner_data['initial'],
                debit=partner_data['debit'],
                credit=partner_data['credit'],
                final=partner_data['final'],
                level=5,
                has_children=show_movements,  # Puede expandir a movimientos solo si está habilitado
                parent_line_id=parent_line_id,
                markup=f'partner_{partner_id or 0}_account_{account_id}',
                expand_function='_report_expand_unfoldable_line_partner_moves' if show_movements else None,
                last_move_date=partner_data.get('last_move_date'),
                account_code=account_code,  # Columna Código
                account_name='',  # Vacío para terceros
                partner_name=partner_name,  # Columna Tercero
                partner_vat=partner_vat_display,  # Columna NIT
            )
            lines.append(line)

        return {
            'lines': lines,
            'offset_increment': len(lines),
            'has_more': False,
        }

    # =========================================================================
    # EXPANSIÓN DE TERCEROS A MOVIMIENTOS
    # =========================================================================

    def _report_expand_unfoldable_line_partner_moves(self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None):
        """Expande un tercero para mostrar sus movimientos individuales."""
        report = self.env['account.report'].browse(options['report_id'])
        lines = []

        # Extraer partner_id y account_id del line_id
        partner_id = None
        account_id = None

        partner_match = re.search(r'partner_(\d+)', line_dict_id)
        if partner_match:
            partner_id = int(partner_match.group(1))
            if partner_id == 0:
                partner_id = None  # 0 significa sin tercero

        account_match = re.search(r'account_(\d+)', line_dict_id)
        if account_match:
            account_id = int(account_match.group(1))

        if not account_id:
            return {'lines': [], 'offset_increment': 0, 'has_more': False}

        # Línea de saldo inicial
        initial_balance = self._get_partner_initial_balance(options, account_id, partner_id)
        running_balance = initial_balance

        if initial_balance != 0:
            initial_line = self._build_line(
                report, options,
                code='',
                name=_('Saldo Inicial'),
                initial=initial_balance,
                debit=0,
                credit=0,
                final=initial_balance,
                level=6,
                has_children=False,
                parent_line_id=line_dict_id,
                markup=f'initial_{account_id}_{partner_id or 0}',
                css_class='font-italic text-muted',
            )
            lines.append(initial_line)

        # Obtener movimientos del período
        moves = self._get_partner_moves(options, account_id, partner_id)

        for move in moves:
            debit = move.get('debit', 0)
            credit = move.get('credit', 0)
            running_balance += debit - credit

            # Construir descripción del movimiento
            move_name = move.get('move_name', '')
            ref = move.get('ref', '')
            line_name = move.get('name', '')

            # Mostrar referencia y nombre si existen
            description = ref if ref else line_name
            if ref and line_name and ref != line_name:
                description = f"{ref} - {line_name}"

            move_line = self._build_line(
                report, options,
                code=move_name,  # Número de asiento en columna "Cuenta"
                name=description,  # Descripción en columna "Nombre"
                initial=0,
                debit=debit,
                credit=credit,
                final=running_balance,
                level=6,
                has_children=False,
                parent_line_id=line_dict_id,
                markup=f'aml_{move["move_line_id"]}',
                caret_options='account.move.line',
                last_move_date=move.get('date'),  # Fecha del movimiento
            )
            lines.append(move_line)

        return {
            'lines': lines,
            'offset_increment': len(lines),
            'has_more': False,
        }

    def _get_partner_initial_balance(self, options, account_id, partner_id):
        """Obtiene el saldo inicial de un tercero en una cuenta."""
        date_from = options.get('date', {}).get('date_from')
        date_from_obj = fields.Date.from_string(date_from)

        fiscalyear_dates = self.env.company.compute_fiscalyear_dates(date_from_obj)
        fiscal_year_start = fiscalyear_dates['date_from']

        domain = [
            ('move_id.state', '=', 'posted'),
            ('account_id', '=', account_id),
            ('date', '>=', fiscal_year_start),
            ('date', '<', date_from),
            ('company_id', '=', self.env.company.id),
        ]

        if partner_id:
            domain.append(('partner_id', '=', partner_id))
        else:
            domain.append(('partner_id', '=', False))

        return sum(self.env['account.move.line'].search(domain).mapped('balance'))

    def _get_partner_moves(self, options, account_id, partner_id):
        """Obtiene movimientos de un tercero en una cuenta."""
        date_from = options.get('date', {}).get('date_from')
        date_to = options.get('date', {}).get('date_to')

        domain = [
            ('move_id.state', '=', 'posted'),
            ('account_id', '=', account_id),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('company_id', '=', self.env.company.id),
        ]

        if partner_id:
            domain.append(('partner_id', '=', partner_id))
        else:
            domain.append(('partner_id', '=', False))

        move_lines = self.env['account.move.line'].search(domain, order='date, id', limit=500)

        return [{
            'move_line_id': ml.id,
            'move_id': ml.move_id.id,
            'move_name': ml.move_id.name,
            'date': ml.date,
            'ref': ml.ref or '',
            'name': ml.name or '',
            'debit': ml.debit,
            'credit': ml.credit,
        } for ml in move_lines]

    # =========================================================================
    # UTILIDADES
    # =========================================================================

    def _is_zero_balance(self, data):
        """Verifica si todos los saldos son cero."""
        return (
            data.get('initial', 0) == 0 and
            data.get('debit', 0) == 0 and
            data.get('credit', 0) == 0 and
            data.get('final', 0) == 0
        )

    # =========================================================================
    # CARET OPTIONS
    # =========================================================================

    def _caret_options_initializer(self):
        return {
            'account.move.line': [
                {'name': _("Ver Apunte"), 'action': 'caret_option_open_move_line'},
                {'name': _("Ver Asiento"), 'action': 'caret_option_open_move'},
            ],
        }

    def caret_option_open_move_line(self, options, params):
        """Abre el apunte contable."""
        line_id = params.get('line_id', '')

        match = re.search(r'aml_(\d+)', line_id)
        if match:
            move_line_id = int(match.group(1))
            return {
                'type': 'ir.actions.act_window',
                'name': _('Apunte Contable'),
                'res_model': 'account.move.line',
                'res_id': move_line_id,
                'view_mode': 'form',
                'views': [(False, 'form')],
            }
        return False

    def caret_option_open_move(self, options, params):
        """Abre el asiento contable."""
        line_id = params.get('line_id', '')

        match = re.search(r'aml_(\d+)', line_id)
        if match:
            move_line_id = int(match.group(1))
            move_line = self.env['account.move.line'].browse(move_line_id)
            if move_line.exists():
                return {
                    'type': 'ir.actions.act_window',
                    'name': _('Asiento Contable'),
                    'res_model': 'account.move',
                    'res_id': move_line.move_id.id,
                    'view_mode': 'form',
                    'views': [(False, 'form')],
                }
        return False
