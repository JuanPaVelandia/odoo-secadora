# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import json

from odoo import models, fields, api, _
from odoo.tools.misc import format_date
from odoo.tools import get_lang, SQL
from odoo.exceptions import UserError

from datetime import timedelta
from collections import defaultdict


class AccountAuxiliaryBookHandler(models.AbstractModel):
    _name = 'account.auxiliary.book.colombia.handler'
    _inherit = ['account.report.custom.handler', 'sql.helper.mixin']
    _description = 'Libro Auxiliar Colombia'

    def _get_custom_display_config(self):
        return {
            'css_custom_class': 'auxiliary_book_colombia',
            'templates': {
                'AccountReportLineName': 'account_reports.GeneralLedgerLineName',
            },
            'components': {
                'AccountReportFilters': 'libros_contables_colombia.TrialBalancePartnerFilters',
            },
        }

    def _custom_options_initializer(self, report, options, previous_options=None):
        from odoo import _
        import logging
        _logger = logging.getLogger(__name__)

        _logger.info("=== _custom_options_initializer (Libro Auxiliar) ===")
        _logger.info("  Report: %s (ID: %s)", report.name, report.id)
        _logger.info("  previous_options keys: %s", list(previous_options.keys()) if previous_options else 'None')

        super()._custom_options_initializer(report, options, previous_options=previous_options)
        # Configurar opciones específicas para el libro auxiliar
        options['show_initial_balance'] = True
        options['filter_accounts'] = []

        if previous_options:
            if 'show_initial_balance' in previous_options:
                options['show_initial_balance'] = previous_options['show_initial_balance']
            if 'filter_accounts' in previous_options:
                options['filter_accounts'] = previous_options['filter_accounts']

        # Automáticamente desplegar el informe al imprimirlo
        options['unfold_all'] = (options['export_mode'] == 'print' and not options.get('unfolded_lines')) or options['unfold_all']

    # =========================================================================
    # CONSTANTES PARA JERARQUÍA PUC
    # Estructura: Clase (1) > Grupo (2) > Cuenta (4) > Subcuenta (6) > Auxiliar (8+)
    # =========================================================================
    PUC_LEVELS = [
        (1, 'Clase'),      # 1 dígito: 1 Activo, 2 Pasivo, etc.
        (2, 'Grupo'),      # 2 dígitos: 11 Disponible, 13 Deudores, etc.
        (4, 'Cuenta'),     # 4 dígitos: 1105 Caja, 1110 Bancos, etc.
        (6, 'Subcuenta'),  # 6 dígitos: 110505 Caja General, etc.
        (8, 'Auxiliar'),   # 8+ dígitos: 11050501 Caja General ME, etc.
    ]

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        lines = []
        date_from = fields.Date.from_string(options['date']['date_from'])
        company_currency = self.env.company.currency_id

        # Obtener opciones de filtro
        hide_accounts_no_movement = options.get('hide_accounts_no_movement', False)
        use_puc_hierarchy = options.get('puc_hierarchy', False)

        # Recopilar datos de todas las cuentas
        account_data = []
        totals_by_column_group = defaultdict(lambda: {'debit': 0, 'credit': 0, 'balance': 0})

        for account, column_group_results in self._query_values(report, options):
            eval_dict = {}
            has_lines = False
            has_period_movement = False

            for column_group_key, results in column_group_results.items():
                account_sum = results.get('sum', {})
                account_un_earn = results.get('unaffected_earnings', {})
                account_initial = results.get('initial_balance', {})

                account_debit = account_sum.get('debit', 0.0) + account_un_earn.get('debit', 0.0)
                account_credit = account_sum.get('credit', 0.0) + account_un_earn.get('credit', 0.0)
                account_balance = account_sum.get('balance', 0.0) + account_un_earn.get('balance', 0.0)

                initial_debit = account_initial.get('debit', 0.0)
                initial_credit = account_initial.get('credit', 0.0)
                period_debit = account_debit - initial_debit
                period_credit = account_credit - initial_credit

                if company_currency.compare_amounts(period_debit, 0) != 0 or \
                   company_currency.compare_amounts(period_credit, 0) != 0:
                    has_period_movement = True

                eval_dict[column_group_key] = {
                    'debit': account_debit,
                    'credit': account_credit,
                    'balance': account_balance,
                }

                max_date = account_sum.get('max_date')
                has_lines = has_lines or (max_date and max_date >= date_from)

            # Filtrar cuentas sin movimiento
            if hide_accounts_no_movement and not has_period_movement:
                continue

            # Acumular totales
            for column_group_key in eval_dict:
                totals_by_column_group[column_group_key]['debit'] += eval_dict[column_group_key]['debit']
                totals_by_column_group[column_group_key]['credit'] += eval_dict[column_group_key]['credit']
                totals_by_column_group[column_group_key]['balance'] += eval_dict[column_group_key]['balance']

            account_data.append({
                'account': account,
                'has_lines': has_lines,
                'eval_dict': eval_dict,
            })

        # Generar líneas según modo de vista
        if use_puc_hierarchy and account_data:
            lines = self._generate_puc_hierarchy_lines(report, options, account_data)
        else:
            # Modo plano (sin jerarquía)
            for data in account_data:
                lines.append(self._get_account_title_line(
                    report, options, data['account'], data['has_lines'], data['eval_dict']
                ))

        # Redondear totales
        for totals in totals_by_column_group.values():
            totals['balance'] = company_currency.round(totals['balance'])

        # Línea de total
        lines.append(self._get_total_line(report, options, totals_by_column_group))

        return [(0, line) for line in lines]

    def _generate_puc_hierarchy_lines(self, report, options, account_data):
        """
        Genera líneas con jerarquía PUC colombiano.

        Estructura:
        - Clase (1 dígito): ej. 1 Activo
        - Grupo (2 dígitos): ej. 11 Disponible
        - Cuenta (4 dígitos): ej. 1105 Caja
        - Subcuenta (6 dígitos): ej. 110505 Caja General
        - Auxiliar (8+ dígitos): ej. 11050501 Caja General ME
        """
        lines = []
        hierarchy = self._build_puc_hierarchy_structure(account_data)

        # Generar líneas ordenadas jerárquicamente
        self._flatten_puc_hierarchy(report, options, hierarchy, lines, account_data)

        return lines

    def _build_puc_hierarchy_structure(self, account_data):
        """
        Construye la estructura de jerarquía PUC.

        Retorna un dict con:
        - Para cada nivel de agrupación (Clase, Grupo, Cuenta, Subcuenta)
        - Códigos y nombres de los grupos
        - Totales agregados de cada grupo
        """
        hierarchy = {}

        for data in account_data:
            account = data['account']
            code = account.code or ''
            if not code:
                continue

            eval_dict = data['eval_dict']

            # Crear entradas para cada nivel de la jerarquía
            for level_digits, level_name in self.PUC_LEVELS:
                if len(code) >= level_digits:
                    prefix = code[:level_digits]
                    if prefix not in hierarchy:
                        hierarchy[prefix] = {
                            'code': prefix,
                            'name': self._get_puc_level_name(prefix, level_name, account.name),
                            'level_name': level_name,
                            'level_digits': level_digits,
                            'totals': defaultdict(lambda: {'debit': 0, 'credit': 0, 'balance': 0}),
                            'accounts': [],  # Cuentas hijas directas
                        }

            # Determinar el nivel del código de cuenta
            account_level = self._get_account_level(code)

            # Agregar la cuenta al nivel correspondiente
            hierarchy[code]['accounts'].append(data)

            # Sumar totales a todos los niveles padre
            for level_digits, _ in self.PUC_LEVELS:
                if len(code) >= level_digits:
                    prefix = code[:level_digits]
                    for column_group_key, values in eval_dict.items():
                        hierarchy[prefix]['totals'][column_group_key]['debit'] += values['debit']
                        hierarchy[prefix]['totals'][column_group_key]['credit'] += values['credit']
                        hierarchy[prefix]['totals'][column_group_key]['balance'] += values['balance']

        return hierarchy

    def _get_account_level(self, code):
        """Determina el nivel PUC de un código de cuenta."""
        code_len = len(code)
        for level_digits, level_name in self.PUC_LEVELS:
            if code_len <= level_digits:
                return level_name
        return 'Auxiliar'

    def _get_puc_level_name(self, prefix, level_name, sample_account_name):
        """Obtiene el nombre para un nivel de jerarquía PUC.

        Busca en orden:
        1. account.group que coincida con el prefijo
        2. Cuenta que coincida exactamente con el prefijo
        3. Nombres descriptivos del PUC colombiano
        4. Nombre derivado de la primera cuenta hija
        """
        # 1. Buscar account.group que inicie con este prefijo
        matching_group = self.env['account.group'].search([
            ('code_prefix_start', '=', prefix)
        ], limit=1)
        if matching_group:
            return matching_group.name

        # 2. Buscar cuenta exacta con el código del prefijo
        matching_account = self.env['account.account'].search([
            ('code', '=', prefix)
        ], limit=1)
        if matching_account:
            return matching_account.name

        # 3. Nombres descriptivos del PUC colombiano
        PUC_NAMES = {
            # Clases (1 dígito)
            '1': 'Activo',
            '2': 'Pasivo',
            '3': 'Patrimonio',
            '4': 'Ingresos',
            '5': 'Gastos',
            '6': 'Costos de Ventas',
            '7': 'Costos de Producción',
            '8': 'Cuentas de Orden Deudoras',
            '9': 'Cuentas de Orden Acreedoras',
            # Grupos comunes (2 dígitos)
            '11': 'Disponible',
            '12': 'Inversiones',
            '13': 'Deudores',
            '14': 'Inventarios',
            '15': 'Propiedades, Planta y Equipo',
            '16': 'Intangibles',
            '17': 'Diferidos',
            '21': 'Obligaciones Financieras',
            '22': 'Proveedores',
            '23': 'Cuentas por Pagar',
            '24': 'Impuestos, Gravámenes y Tasas',
            '25': 'Obligaciones Laborales',
            '26': 'Pasivos Estimados y Provisiones',
            '27': 'Diferidos',
            '28': 'Otros Pasivos',
            '31': 'Capital Social',
            '32': 'Superávit de Capital',
            '33': 'Reservas',
            '34': 'Revalorización del Patrimonio',
            '36': 'Resultados del Ejercicio',
            '37': 'Resultados de Ejercicios Anteriores',
            '41': 'Operacionales',
            '42': 'No Operacionales',
            '51': 'Operacionales de Administración',
            '52': 'Operacionales de Ventas',
            '53': 'No Operacionales',
            '61': 'Costo de Ventas',
        }
        if prefix in PUC_NAMES:
            return PUC_NAMES[prefix]

        # 4. Fallback: usar nombre derivado
        if sample_account_name:
            return sample_account_name
        return f"{level_name} {prefix}"

    # Mapeo de nivel seleccionado a máximo número de dígitos
    PUC_LEVEL_MAX_DIGITS = {
        'all': 999,       # Mostrar todos
        'clase': 1,       # Solo clases (1 dígito)
        'grupo': 2,       # Hasta grupos (2 dígitos)
        'cuenta': 4,      # Hasta cuentas (4 dígitos)
        'subcuenta': 6,   # Hasta subcuentas (6 dígitos)
        'auxiliar': 8,    # Hasta auxiliares (8+ dígitos) = todos
    }

    def _flatten_puc_hierarchy(self, report, options, hierarchy, lines, account_data):
        """
        Convierte la jerarquía en líneas planas ordenadas jerárquicamente.

        La estructura usa los totales nativos de Odoo (auto-generados cuando unfoldable=True):
        1 ACTIVO (encabezado desplegable)
          11 Disponible (encabezado desplegable)
            1105 Caja (cuenta)
            1110 Bancos (cuenta)
          Total 11 Disponible (auto-generado por Odoo)
          13 Deudores
            ...
          Total 13 Deudores (auto-generado)
        Total 1 ACTIVO (auto-generado)
        2 PASIVO
          ...

        Respeta el nivel seleccionado en options['puc_hierarchy_level']:
        - 'all': Muestra todos los niveles
        - 'clase': Solo clases (1 dígito)
        - 'grupo': Hasta grupos (2 dígitos)
        - 'cuenta': Hasta cuentas (4 dígitos)
        - 'subcuenta': Hasta subcuentas (6 dígitos)
        - 'auxiliar': Hasta auxiliares (8+ dígitos)
        """
        # Obtener nivel máximo a mostrar
        selected_level = options.get('puc_hierarchy_level', 'all')
        max_digits = self.PUC_LEVEL_MAX_DIGITS.get(selected_level, 999)

        # Construir un set de códigos que son exactamente cuentas reales
        real_account_codes = {data['account'].code for data in account_data}

        # Ordenar códigos alfabéticamente (orden jerárquico natural)
        # 1 < 11 < 1105 < 110501 < 11050501 < 2 < 21 ...
        sorted_codes = sorted(hierarchy.keys())

        processed_accounts = set()

        for code in sorted_codes:
            entry = hierarchy[code]
            level_digits = entry['level_digits']

            # Filtrar por nivel máximo seleccionado
            if level_digits > max_digits:
                continue

            # Determinar si este código es una cuenta real o solo un grupo
            is_real_account = code in real_account_codes

            # Determinar nivel visual
            level = self._get_visual_level(level_digits)
            is_class = (level_digits == 1)

            if is_real_account:
                # Es una cuenta real, mostrar como cuenta desplegable
                if code not in processed_accounts:
                    account_entry = entry['accounts'][0] if entry['accounts'] else None
                    if account_entry:
                        lines.append(self._get_account_title_line(
                            report, options,
                            account_entry['account'],
                            account_entry['has_lines'],
                            account_entry['eval_dict'],
                            level=level
                        ))
                        processed_accounts.add(code)
            else:
                # Es un grupo jerárquico, mostrar como línea desplegable con totales
                # Odoo generará automáticamente la línea "Total X" cuando unfoldable=True
                lines.append(self._get_hierarchy_group_line(
                    report, options, entry, level=level, is_class=is_class
                ))

    def _get_visual_level(self, level_digits):
        """Determina el nivel visual basado en la longitud del código."""
        if level_digits == 1:
            return 0
        elif level_digits == 2:
            return 1
        elif level_digits == 4:
            return 2
        elif level_digits == 6:
            return 3
        else:
            return 4

    def _get_hierarchy_group_line(self, report, options, entry, level=0, is_class=False):
        """
        Genera una línea de grupo jerárquico con totales.

        Odoo generará automáticamente una línea "Total X" cuando unfoldable=True,
        pero también mostramos los totales en la línea del grupo para facilitar
        la lectura de la jerarquía.
        """
        line_columns = []

        # Obtener totales del grupo
        totals = dict(entry.get('totals', {}))

        for column in options['columns']:
            col_group_key = column['column_group_key']
            expr_label = column['expression_label']

            # Mostrar valores monetarios en el encabezado del grupo
            if expr_label in ('debit', 'credit', 'balance'):
                col_value = 0
                if col_group_key in totals:
                    col_value = totals[col_group_key].get(expr_label, 0)
                elif totals:
                    first_key = next(iter(totals.keys()))
                    col_value = totals[first_key].get(expr_label, 0)
            elif expr_label == 'account_code':
                col_value = entry.get('code', '')
            elif expr_label == 'account_name':
                col_value = entry.get('name', '')
            else:
                col_value = None

            line_columns.append(report._build_column_dict(
                col_value,
                column,
                options=options,
            ))

        line_id = report._get_generic_line_id(None, None, markup=f'puc_group_{entry["code"]}')

        return {
            'id': line_id,
            'name': f'{entry["code"]} {entry["name"]}',
            'columns': line_columns,
            'level': level,
            'unfoldable': True,  # Permitir expandir/contraer - genera línea "Total X" automática
            'unfolded': True,    # Expandido por defecto
            'class': 'o_account_coa_column_contrast' if is_class else 'o_account_coa_column_group',
        }

    def _custom_unfold_all_batch_data_generator(self, report, options, lines_to_expand_by_function):
        account_ids_to_expand = []
        for line_dict in lines_to_expand_by_function.get('_report_expand_unfoldable_line_auxiliary_book', []):
            model, model_id = report._get_model_info_from_id(line_dict['id'])
            if model == 'account.account':
                account_ids_to_expand.append(model_id)

        limit_to_load = report.load_more_limit if report.load_more_limit and not options.get('export_mode') else None
        has_more_per_account_id = {}

        unlimited_aml_results_per_account_id = self._get_aml_values(report, options, account_ids_to_expand)[0]
        if limit_to_load:
            # Aplicar el límite de carga
            aml_results_per_account_id = {}
            for account_id, account_aml_results in unlimited_aml_results_per_account_id.items():
                account_values = {}
                for key, value in account_aml_results.items():
                    if len(account_values) == limit_to_load:
                        has_more_per_account_id[account_id] = True
                        break
                    account_values[key] = value
                aml_results_per_account_id[account_id] = account_values
        else:
            aml_results_per_account_id = unlimited_aml_results_per_account_id

        return {
            'initial_balances': self._get_initial_balance_values(report, account_ids_to_expand, options),
            'aml_results': aml_results_per_account_id,
            'has_more': has_more_per_account_id,
        }

    def _query_values(self, report, options):
        """ Ejecuta las consultas y realiza todos los cálculos.
        :return: [(record, values_by_column_group), ...], donde
                - record es un registro account.account.
                - values_by_column_group es un dict en la forma {column_group_key: values, ...}
        """
        # Ejecutar las consultas y distribuir los resultados
        query = self._get_query_sums(report, options)

        if not query:
            return []

        groupby_accounts = {}
        groupby_companies = {}

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

            elif key == 'initial_balance':
                groupby_accounts.setdefault(res['groupby'], {col_group_key: {} for col_group_key in options['column_groups']})
                groupby_accounts[res['groupby']][column_group_key][key] = res

            elif key == 'unaffected_earnings':
                groupby_companies.setdefault(res['groupby'], {col_group_key: {} for col_group_key in options['column_groups']})
                groupby_companies[res['groupby']][column_group_key] = res

        # Afectar las ganancias no afectadas a la primera cuenta recuperada de tipo 'account.data_unaffected_earnings'
        if groupby_companies:
            unaffected_earnings_accounts = self.env['account.account'].search([
                ('display_name', 'ilike', options.get('filter_search_bar')),
                *self.env['account.account']._check_company_domain(list(groupby_companies.keys())),
                ('account_type', '=', 'equity_unaffected'),
            ])
            for company_id, groupby_company in groupby_companies.items():
                if equity_unaffected_account := unaffected_earnings_accounts.filtered(lambda a: self.env['res.company'].browse(company_id).root_id in a.company_ids):
                    for column_group_key in options['column_groups']:
                        groupby_accounts.setdefault(
                            equity_unaffected_account.id,
                            {col_group_key: {'unaffected_earnings': {}} for col_group_key in options['column_groups']},
                        )
                        if unaffected_earnings := groupby_company.get(column_group_key):
                            if groupby_accounts[equity_unaffected_account.id][column_group_key].get('unaffected_earnings'):
                                for key in ['debit', 'credit', 'balance']:
                                    groupby_accounts[equity_unaffected_account.id][column_group_key]['unaffected_earnings'][key] += unaffected_earnings.get(key, 0)
                            else:
                                groupby_accounts[equity_unaffected_account.id][column_group_key]['unaffected_earnings'] = unaffected_earnings

        # Recuperar las cuentas para navegar
        if groupby_accounts:
            # Filtrar por cuentas específicas si están configuradas
            domain = [('id', 'in', list(groupby_accounts.keys()))]
            filter_accounts = options.get('filter_accounts', [])
            if filter_accounts:
                domain = [('id', 'in', filter_accounts)]

            accounts = self.env['account.account'].search(domain)
        else:
            accounts = []

        return [(account, groupby_accounts[account.id]) for account in accounts]

    def _get_query_sums(self, report, options) -> SQL:
        """ Construye una consulta que recupera todas las sumas agregadas para construir el informe.
        :return: SQL object
        """
        options_by_column_group = report._split_options_per_column_group(options)

        queries = []

        # ============================================
        # 1) Obtener sumas para todas las cuentas
        # ============================================
        for column_group_key, options_group in options_by_column_group.items():
            # IMPORTANTE: Guardar opciones originales ANTES de modificarlas
            # para usarlas en el cálculo del saldo inicial
            original_options_group = options_group.copy()
            original_options_group['date'] = options_group['date'].copy()

            if not options.get('auxiliary_book_strict_range'):
                options_group = self._get_options_sum_balance(options_group)

            # La suma se calcula incluyendo el saldo inicial de las cuentas configuradas para hacerlo
            sum_date_scope = 'strict_range' if options_group.get('auxiliary_book_strict_range') else 'from_beginning'

            query_domain = []

            # Filtrar por búsqueda si es necesario
            if options.get('export_mode') == 'print' and options.get('filter_search_bar'):
                query_domain.append(('account_id', 'ilike', options['filter_search_bar']))

            # Filtrar por cuentas específicas si están configuradas
            filter_accounts = options.get('filter_accounts', [])
            if filter_accounts:
                query_domain.append(('account_id', 'in', filter_accounts))

            # ================================================================
            # FILTRO POR RANGO DE CUENTAS (account_from, account_to)
            # ================================================================
            account_from = options.get('account_from', '').strip()
            account_to = options.get('account_to', '').strip()
            account_exclude = options.get('account_exclude', [])

            if account_from:
                query_domain.append(('account_id.code', '>=', account_from))
            if account_to:
                query_domain.append(('account_id.code', '<=', account_to + 'z'))  # 'z' para incluir todas las subcuentas
            if account_exclude:
                for exclude_code in account_exclude:
                    query_domain.append(('account_id.code', 'not ilike', exclude_code + '%'))

            query = report._get_report_query(options_group, sum_date_scope, domain=query_domain)

            queries.append(SQL(
                """
                SELECT
                    account_move_line.account_id                            AS groupby,
                    'sum'                                                   AS key,
                    MAX(account_move_line.date)                             AS max_date,
                    %(column_group_key)s                                    AS column_group_key,
                    SUM(%(debit_select)s)                                   AS debit,
                    SUM(%(credit_select)s)                                  AS credit,
                    SUM(%(balance_select)s)                                 AS balance
                FROM %(table_references)s
                %(currency_table_join)s
                WHERE %(search_condition)s
                GROUP BY account_move_line.account_id
                """,
                column_group_key=column_group_key,
                table_references=query.from_clause,
                debit_select=report._currency_table_apply_rate(SQL("account_move_line.debit")),
                credit_select=report._currency_table_apply_rate(SQL("account_move_line.credit")),
                balance_select=report._currency_table_apply_rate(SQL("account_move_line.balance")),
                currency_table_join=report._currency_table_aml_join(options_group),
                search_condition=query.where_clause,
            ))

            # ============================================
            # 2) Obtener sumas para los saldos iniciales
            # ============================================
            # NOTA: Usar original_options_group para calcular fechas correctas del saldo inicial
            # (antes se usaba options_group que ya tenía date_from modificado al inicio del año fiscal)
            if options.get('show_initial_balance', True) and not original_options_group.get('auxiliary_book_strict_range'):
                # Configurar opciones para saldo inicial usando las opciones ORIGINALES
                new_options = self._get_options_initial_balance(original_options_group)
                query_initial = report._get_report_query(new_options, 'from_beginning', domain=query_domain)

                queries.append(SQL(
                    """
                    SELECT
                        account_move_line.account_id                            AS groupby,
                        'initial_balance'                                       AS key,
                        MAX(account_move_line.date)                             AS max_date,
                        %(column_group_key)s                                    AS column_group_key,
                        SUM(%(debit_select)s)                                   AS debit,
                        SUM(%(credit_select)s)                                  AS credit,
                        SUM(%(balance_select)s)                                 AS balance
                    FROM %(table_references)s
                    %(currency_table_join)s
                    WHERE %(search_condition)s
                    GROUP BY account_move_line.account_id
                    """,
                    column_group_key=column_group_key,
                    table_references=query_initial.from_clause,
                    debit_select=report._currency_table_apply_rate(SQL("account_move_line.debit")),
                    credit_select=report._currency_table_apply_rate(SQL("account_move_line.credit")),
                    balance_select=report._currency_table_apply_rate(SQL("account_move_line.balance")),
                    currency_table_join=report._currency_table_aml_join(new_options),
                    search_condition=query_initial.where_clause,
                ))

        return SQL(" UNION ALL ").join(queries)

    def _get_aml_values(self, report, options, account_ids, offset=0, limit=None):
        """ Obtiene los valores de las líneas de movimiento de cuenta para las cuentas dadas.
        """
        results = defaultdict(dict)
        has_more = False

        if not account_ids:
            return results, has_more

        # Construir la consulta para obtener las líneas de movimiento
        additional_domain = [('account_id', 'in', account_ids)]
        query = self._get_query_amls(report, options, additional_domain, offset=offset, limit=limit)

        self._cr.execute(query)
        for aml_result in self._cr.dictfetchall():
            results[aml_result['account_id']][aml_result['id']] = aml_result

        # Verificar si hay más líneas
        if limit and len(results) >= limit:
            has_more = True

        return results, has_more

    # Mapeo de tipos de diario a nombres legibles en español
    JOURNAL_TYPE_NAMES = {
        'sale': 'Venta',
        'purchase': 'Compra',
        'bank': 'Banco',
        'cash': 'Efectivo',
        'general': 'Varios',
        'credit': 'Nota Crédito',
    }

    def _get_query_amls(self, report, options, additional_domain=None, offset=0, limit=None) -> SQL:
        """Construye la consulta para obtener las líneas de movimiento de cuenta.

        Campos incluidos:
        - account_code, account_name: Código y nombre de la cuenta
        - date: Fecha del movimiento
        - journal_type: Tipo de diario (sale, purchase, bank, cash, general)
        - sequence: Secuencia del diario
        - move_name: Nombre del documento (número de factura, etc.)
        - name: Etiqueta de la línea
        - ref: Referencia del asiento
        - payment_ref: Referencia de pago del asiento
        - partner_name: Nombre del tercero
        - tax_base_amount: Base imponible
        - analytic_distribution: Distribución analítica (JSON)
        - debit, credit, balance: Valores monetarios
        """
        additional_domain = additional_domain or []

        queries = []

        lang = self.env.user.lang or get_lang(self.env).code
        company_id = self._get_company_id_for_sql()

        for column_group_key, group_options in report._split_options_per_column_group(options).items():
            # Obtener sumas para las líneas de movimiento de cuenta
            query = report._get_report_query(group_options, 'strict_range', domain=additional_domain)

            # Obtener código y nombre de cuenta usando SQL directo
            # Usamos account_account como alias directo para evitar conflictos con query.join()
            company_id = self._get_company_id_for_sql()
            account_code = SQL("COALESCE(account_account.code_store->>%s, '')", str(company_id))
            account_name = SQL("COALESCE(account_account.name->>'en_US', account_account.name->>'es_CO', '')")

            journal_name = SQL("COALESCE(journal.name->>'en_US', journal.name->>'es_CO', journal.code)")

            queries.append(SQL(
                """
                (SELECT
                    account_move_line.id,
                    account_move_line.date,
                    account_move_line.date_maturity,
                    account_move_line.name,
                    account_move_line.ref,
                    account_move_line.company_id,
                    account_move_line.account_id,
                    account_move_line.payment_id,
                    account_move_line.partner_id,
                    account_move_line.currency_id,
                    account_move_line.tax_base_amount,
                    account_move_line.analytic_distribution,
                    %(debit_select)s                        AS debit,
                    %(credit_select)s                       AS credit,
                    %(balance_select)s                      AS balance,
                    move.name                               AS move_name,
                    move.ref                                AS move_ref,
                    move.payment_reference                  AS payment_ref,
                    company.currency_id                     AS company_currency_id,
                    partner.name                            AS partner_name,
                    move.move_type                          AS move_type,
                    %(account_code)s                        AS account_code,
                    %(account_name)s                        AS account_name,
                    journal.code                            AS journal_code,
                    journal.type                            AS journal_type,
                    journal.sequence                        AS journal_sequence,
                    %(journal_name)s                        AS journal_name,
                    %(column_group_key)s                    AS column_group_key
                FROM %(table_references)s
                JOIN account_move move                      ON move.id = account_move_line.move_id
                JOIN account_account                        ON account_account.id = account_move_line.account_id
                %(currency_table_join)s
                LEFT JOIN res_company company               ON company.id = account_move_line.company_id
                LEFT JOIN res_partner partner               ON partner.id = account_move_line.partner_id
                LEFT JOIN account_journal journal           ON journal.id = account_move_line.journal_id
                WHERE %(search_condition)s
                ORDER BY account_move_line.date, account_move_line.id)
                """,
                column_group_key=column_group_key,
                table_references=query.from_clause,
                debit_select=report._currency_table_apply_rate(SQL("account_move_line.debit")),
                credit_select=report._currency_table_apply_rate(SQL("account_move_line.credit")),
                balance_select=report._currency_table_apply_rate(SQL("account_move_line.balance")),
                account_code=account_code,
                account_name=account_name,
                journal_name=journal_name,
                currency_table_join=report._currency_table_aml_join(group_options),
                search_condition=query.where_clause,
            ))

        full_query = SQL(" UNION ALL ").join(queries)

        if offset:
            full_query = SQL("%(query)s OFFSET %(offset)s", query=full_query, offset=offset)
        if limit:
            full_query = SQL("%(query)s LIMIT %(limit)s", query=full_query, limit=limit)

        return full_query

    def _get_initial_balance_values(self, report, account_ids, options):
        """Obtiene los valores de saldo inicial para las cuentas dadas."""
        queries = []

        for column_group_key, options_group in report._split_options_per_column_group(options).items():
            new_options = self._get_options_initial_balance(options_group)
            domain = [('account_id', 'in', account_ids)]

            # Filtrar por cuentas específicas si están configuradas
            filter_accounts = options.get('filter_accounts', [])
            if filter_accounts:
                domain.append(('account_id', 'in', filter_accounts))

            query = report._get_report_query(new_options, 'from_beginning', domain=domain)

            queries.append(SQL(
                """
                SELECT
                    account_move_line.account_id                            AS groupby,
                    'initial_balance'                                       AS key,
                    NULL                                                    AS max_date,
                    %(column_group_key)s                                    AS column_group_key,
                    SUM(%(debit_select)s)                                   AS debit,
                    SUM(%(credit_select)s)                                  AS credit,
                    SUM(%(balance_select)s)                                 AS balance
                FROM %(table_references)s
                %(currency_table_join)s
                WHERE %(search_condition)s
                GROUP BY account_move_line.account_id
                """,
                column_group_key=column_group_key,
                table_references=query.from_clause,
                debit_select=report._currency_table_apply_rate(SQL("account_move_line.debit")),
                credit_select=report._currency_table_apply_rate(SQL("account_move_line.credit")),
                balance_select=report._currency_table_apply_rate(SQL("account_move_line.balance")),
                currency_table_join=report._currency_table_aml_join(new_options),
                search_condition=query.where_clause,
            ))

        self._cr.execute(SQL(" UNION ALL ").join(queries))

        init_balance_by_col_group = {
            account_id: {column_group_key: {} for column_group_key in options['column_groups']}
            for account_id in account_ids
        }
        for result in self._cr.dictfetchall():
            init_balance_by_col_group[result['groupby']][result['column_group_key']] = result

        accounts = self.env['account.account'].browse(account_ids)
        return {
            account.id: (account, init_balance_by_col_group[account.id])
            for account in accounts
        }

    def _get_options_initial_balance(self, options):
        """Crea opciones utilizadas para calcular los saldos iniciales usando el patrón de Odoo 18."""
        new_options = options.copy()
        date_to = new_options['comparison']['periods'][-1]['date_from'] if new_options.get('comparison', {}).get('periods') else new_options['date']['date_from']
        new_date_to = fields.Date.from_string(date_to) - timedelta(days=1)

        # Cálculo de fecha desde
        date_from = fields.Date.from_string(new_options['date']['date_from'])
        current_fiscalyear_dates = self.env.company.compute_fiscalyear_dates(date_from)

        if date_from == current_fiscalyear_dates['date_from']:
            # Queremos el año fiscal anterior
            previous_fiscalyear_dates = self.env.company.compute_fiscalyear_dates(date_from - timedelta(days=1))
            new_date_from = previous_fiscalyear_dates['date_from']
            include_current_year_in_unaff_earnings = True
        else:
            # Queremos el año fiscal actual
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

    def _get_options_sum_balance(self, options):
        """Crea opciones utilizadas para calcular los saldos totales usando el patrón de Odoo 18."""
        new_options = options.copy()

        if not options.get('auxiliary_book_strict_range'):
            # Fecha desde
            date_from = fields.Date.from_string(new_options['date']['date_from'])
            current_fiscalyear_dates = self.env.company.compute_fiscalyear_dates(date_from)
            new_date_from = current_fiscalyear_dates['date_from']
            new_date_to = fields.Date.from_string(new_options['date']['date_to'])

            # Usar _get_dates_period para crear las opciones de fecha correctamente
            new_options['date'] = self.env['account.report']._get_dates_period(
                new_date_from,
                new_date_to,
                'range',
            )

        return new_options

    def _get_account_title_line(self, report, options, account, has_lines, eval_dict, level=1):
        """Crea una línea de título de cuenta.

        Args:
            level: Nivel de indentación (1=normal, 4=bajo jerarquía PUC)
        """
        line_columns = []
        for column in options['columns']:
            col_value = eval_dict.get(column['column_group_key'], {}).get(column['expression_label'])

            line_columns.append(report._build_column_dict(
                col_value,
                column,
                options=options,
            ))

        line_id = report._get_generic_line_id('account.account', account.id)
        is_in_unfolded_lines = any(
            report._get_res_id_from_line_id(line_id, 'account.account') == account.id
            for line_id in options.get('unfolded_lines', [])
        )
        return {
            'id': line_id,
            'name': f'{account.code} {account.name}',
            'columns': line_columns,
            'level': level,
            'unfoldable': has_lines,
            'unfolded': has_lines and (is_in_unfolded_lines or options.get('unfold_all')),
            'expand_function': '_report_expand_unfoldable_line_auxiliary_book',
        }

    def _get_journal_type_name(self, journal_type):
        """Obtiene el nombre legible del tipo de diario en español."""
        return self.JOURNAL_TYPE_NAMES.get(journal_type, journal_type or '')

    def _get_analytic_account_names(self, analytic_distribution):
        """Obtiene los nombres de las cuentas analíticas desde la distribución.

        En Odoo 18, analytic_distribution es un JSON con la estructura:
        {"analytic_account_id": percentage, ...}
        """
        if not analytic_distribution:
            return ''

        try:
            # analytic_distribution ya viene como dict desde la BD
            if isinstance(analytic_distribution, str):
                import json
                analytic_distribution = json.loads(analytic_distribution)

            if not analytic_distribution:
                return ''

            # Obtener los IDs de las cuentas analíticas
            analytic_ids = [int(k) for k in analytic_distribution.keys()]
            if not analytic_ids:
                return ''

            # Buscar los nombres de las cuentas analíticas
            analytic_accounts = self.env['account.analytic.account'].browse(analytic_ids)
            names = [acc.name for acc in analytic_accounts if acc.exists()]
            return ', '.join(names)
        except Exception:
            return ''

    def _get_aml_line(self, report, parent_line_id, options, eval_dict, init_bal_by_col_group):
        """Crea una línea para un movimiento de cuenta.

        Maneja todos los campos del Libro Auxiliar:
        - account_code, account_name: Cuenta
        - date: Fecha
        - journal_type: Tipo de operación (Venta, Compra, etc.)
        - sequence: Secuencia del diario
        - move_name: Documento
        - name: Etiqueta de la línea
        - ref: Referencia
        - payment_ref: Referencia de pago
        - partner_name: Tercero
        - last_move_date: Última fecha de movimiento (solo para saldo inicial)
        - analytic_account: Cuenta analítica (solo para Libro Auxiliar Analítico)
        - tax_base_amount: Base imponible
        - debit, credit, balance: Valores monetarios
        """
        line_columns = []

        # Obtener datos adicionales del primer grupo de columnas
        first_data = list(eval_dict.values())[0] if eval_dict else {}
        account_code = first_data.get('account_code', '')
        account_name = first_data.get('account_name', '')

        for column in options['columns']:
            col_expr_label = column['expression_label']
            col_value = eval_dict.get(column['column_group_key'], {}).get(col_expr_label)

            # Manejar columnas especiales
            if col_expr_label == 'account_code':
                col_value = account_code
            elif col_expr_label == 'account_name':
                col_value = account_name
            elif col_expr_label == 'journal_type':
                # Convertir tipo de diario a nombre legible
                journal_type = first_data.get('journal_type', '')
                col_value = self._get_journal_type_name(journal_type)
            elif col_expr_label == 'sequence':
                # Secuencia del diario
                col_value = first_data.get('journal_sequence', '')
            elif col_expr_label == 'ref':
                # Referencia del asiento (move.ref o aml.ref)
                col_value = first_data.get('move_ref', '') or first_data.get('ref', '')
            elif col_expr_label == 'payment_ref':
                # Referencia de pago
                col_value = first_data.get('payment_ref', '')
            elif col_expr_label == 'last_move_date':
                # Solo aplica para saldo inicial, en líneas normales queda vacío
                col_value = None
            elif col_expr_label == 'analytic_account':
                # Obtener nombres de cuentas analíticas
                analytic_dist = first_data.get('analytic_distribution')
                col_value = self._get_analytic_account_names(analytic_dist)
            elif col_expr_label == 'tax_base_amount':
                # Base imponible
                col_value = first_data.get('tax_base_amount', 0) or 0

            # Acumular balance con saldo inicial
            if col_value is not None and col_expr_label == 'balance':
                col_value += (init_bal_by_col_group.get(column['column_group_key']) or 0)

            line_columns.append(report._build_column_dict(
                col_value,
                column,
                options=options,
            ))

        aml_id = None
        move_name = None
        caret_type = None
        for column_group_dict in eval_dict.values():
            aml_id = column_group_dict.get('id', '')
            if aml_id:
                if column_group_dict.get('payment_id'):
                    caret_type = 'account.payment'
                else:
                    caret_type = 'account.move.line'
                move_name = column_group_dict['move_name']
                date = str(column_group_dict.get('date', ''))
                break

        return {
            'id': report._get_generic_line_id('account.move.line', aml_id, parent_line_id=parent_line_id, markup=date),
            'caret_options': caret_type,
            'parent_id': parent_line_id,
            'name': move_name,
            'columns': line_columns,
            'level': 3,
        }

    def _get_lines_for_pdf(self, report, options):
        """Obtiene todas las líneas expandidas para exportar a PDF/Excel.

        Estructura del Libro Auxiliar:
        - Nivel 1: Cuenta (account.account) con saldo inicial en la misma línea
        - Nivel 3: Movimientos (account.move.line) con balance acumulado
        - Línea de Total general

        El saldo inicial se muestra en el campo 'name' de la línea de cuenta
        para ahorrar espacio en el PDF/Excel.

        Devuelve lista de diccionarios con todos los campos necesarios.
        """
        lines = []
        date_from = fields.Date.from_string(options['date']['date_from'])

        # Determinar si es el reporte analítico
        # Verificar si es el reporte analítico (soporta "analytic" y "analítico")
        report_name_lower = (report.name or '').lower()
        is_analytic = 'analytic' in report_name_lower or 'analítico' in report_name_lower

        # Totales generales
        totals = {'debit': 0, 'credit': 0, 'balance': 0, 'initial': 0, 'tax_base': 0}

        # Obtener todas las cuentas con sus valores
        for account, column_group_results in self._query_values(report, options):
            account_initial = 0
            account_debit = 0
            account_credit = 0
            account_balance = 0

            for column_group_key, results in column_group_results.items():
                account_sum = results.get('sum', {})
                account_un_earn = results.get('unaffected_earnings', {})

                account_debit = account_sum.get('debit', 0.0) + account_un_earn.get('debit', 0.0)
                account_credit = account_sum.get('credit', 0.0) + account_un_earn.get('credit', 0.0)
                account_balance = account_sum.get('balance', 0.0) + account_un_earn.get('balance', 0.0)

                # Saldo inicial
                account_init = results.get('initial_balance', {})
                account_initial = account_init.get('balance', 0.0)

            # Obtener la fecha del último movimiento del saldo inicial
            last_move_date_initial = None
            for column_group_key, results in column_group_results.items():
                account_init = results.get('initial_balance', {})
                if account_init.get('max_date'):
                    last_move_date_initial = account_init.get('max_date')
                    break

            # Línea de cuenta con saldo inicial (una sola línea)
            # Muestra: Código, Cuenta, Etiqueta="Saldo Inicial", Últ.Mov=fecha, Saldo=saldo inicial
            lines.append({
                'level': 1,
                'is_account': True,
                'is_initial': True,
                'account_code': account.code,
                'account_name': account.name,
                'date': None,
                'journal_type': '',
                'sequence': '',
                'move_name': '',
                'name': 'Saldo Inicial',
                'ref': '',
                'payment_ref': '',
                'partner_name': '',
                'last_move_date': last_move_date_initial,  # Fecha del último movimiento antes del periodo
                'analytic_account': '',
                'tax_base_amount': 0,
                'initial_balance': account_initial,
                'debit': 0,
                'credit': 0,
                'balance': account_initial,
            })

            totals['initial'] += account_initial
            totals['debit'] += account_debit
            totals['credit'] += account_credit
            totals['balance'] += account_balance

            # Obtener movimientos de la cuenta
            aml_results, _ = self._get_aml_values(report, options, [account.id])
            running_balance = account_initial

            for aml_id, aml_data in aml_results.get(account.id, {}).items():
                debit_total = aml_data.get('debit', 0) or 0
                credit_total = aml_data.get('credit', 0) or 0
                tax_base_total = aml_data.get('tax_base_amount', 0) or 0

                # Si es reporte analítico y tiene distribución, dividir por cuenta analítica
                analytic_dist = aml_data.get('analytic_distribution')
                if is_analytic and analytic_dist and isinstance(analytic_dist, dict) and len(analytic_dist) > 0:
                    # Obtener las cuentas analíticas
                    analytic_ids = [int(k) for k in analytic_dist.keys()]
                    analytic_accounts = self.env['account.analytic.account'].browse(analytic_ids)
                    analytic_map = {acc.id: acc.name for acc in analytic_accounts if acc.exists()}

                    # Crear una línea por cada cuenta analítica con montos prorrateados
                    for analytic_id_str, percentage in analytic_dist.items():
                        analytic_id = int(analytic_id_str)
                        analytic_name = analytic_map.get(analytic_id, f'Analítica {analytic_id}')

                        # Calcular montos prorrateados según porcentaje
                        factor = (percentage or 0) / 100.0
                        debit_prorated = round(debit_total * factor, 2)
                        credit_prorated = round(credit_total * factor, 2)
                        tax_base_prorated = round(tax_base_total * factor, 2)

                        # Actualizar balance acumulado
                        running_balance += debit_prorated - credit_prorated

                        lines.append({
                            'level': 3,
                            'is_movement': True,
                            'account_code': '',  # Movimientos no muestran código
                            'account_name': '',  # Movimientos no muestran nombre cuenta
                            'date': aml_data.get('date'),
                            'journal_type': self._get_journal_type_name(aml_data.get('journal_type', '')),
                            'sequence': aml_data.get('journal_sequence', ''),
                            'move_name': aml_data.get('move_name', ''),
                            'name': aml_data.get('name', ''),
                            'ref': aml_data.get('move_ref', '') or aml_data.get('ref', ''),
                            'payment_ref': aml_data.get('payment_ref', ''),
                            'partner_name': aml_data.get('partner_name', ''),
                            'last_move_date': None,
                            'analytic_account': f'{analytic_name} ({percentage:.0f}%)',
                            'tax_base_amount': tax_base_prorated,
                            'initial_balance': 0,
                            'debit': debit_prorated,
                            'credit': credit_prorated,
                            'balance': running_balance,
                        })

                        totals['tax_base'] += tax_base_prorated
                else:
                    # Sin distribución analítica o reporte normal - una sola línea
                    running_balance += debit_total - credit_total

                    # Obtener nombre de cuenta analítica si aplica (para movimientos con una sola cuenta)
                    analytic_name = ''
                    if is_analytic and analytic_dist:
                        analytic_name = self._get_analytic_account_names(analytic_dist)

                    lines.append({
                        'level': 3,
                        'is_movement': True,
                        'account_code': '',  # Movimientos no muestran código
                        'account_name': '',  # Movimientos no muestran nombre cuenta
                        'date': aml_data.get('date'),
                        'journal_type': self._get_journal_type_name(aml_data.get('journal_type', '')),
                        'sequence': aml_data.get('journal_sequence', ''),
                        'move_name': aml_data.get('move_name', ''),
                        'name': aml_data.get('name', ''),
                        'ref': aml_data.get('move_ref', '') or aml_data.get('ref', ''),
                        'payment_ref': aml_data.get('payment_ref', ''),
                        'partner_name': aml_data.get('partner_name', ''),
                        'last_move_date': None,
                        'analytic_account': analytic_name,
                        'tax_base_amount': tax_base_total,
                        'initial_balance': 0,
                        'debit': debit_total,
                        'credit': credit_total,
                        'balance': running_balance,
                    })

                    totals['tax_base'] += tax_base_total

        # Línea de total general
        lines.append({
            'level': 0,
            'is_total': True,
            'account_code': '',
            'account_name': 'TOTAL GENERAL',
            'date': None,
            'journal_type': '',
            'sequence': '',
            'move_name': '',
            'name': '',
            'ref': '',
            'payment_ref': '',
            'partner_name': '',
            'last_move_date': None,
            'analytic_account': '',
            'tax_base_amount': totals['tax_base'],
            'initial_balance': totals['initial'],
            'debit': totals['debit'],
            'credit': totals['credit'],
            'balance': totals['balance'],
        })

        return lines

    def _get_total_line(self, report, options, eval_dict):
        """Crea una línea de total."""
        line_columns = []
        for column in options['columns']:
            col_value = eval_dict.get(column['column_group_key'], {}).get(column['expression_label'])

            line_columns.append(report._build_column_dict(col_value, column, options=options))

        return {
            'id': report._get_generic_line_id(None, None, markup='total'),
            'name': _('Total'),
            'level': 1,
            'columns': line_columns,
        }

    def _report_expand_unfoldable_line_auxiliary_book(self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None):
        """Expande una línea desplegable del libro auxiliar."""
        def init_load_more_progress(line_dict):
            return {
                column['column_group_key']: line_col.get('no_format', 0)
                for column, line_col in zip(options['columns'], line_dict['columns'])
                if column['expression_label'] == 'balance'
            }

        report = self.env['account.report'].browse(options['report_id'])
        model, model_id = report._get_model_info_from_id(line_dict_id)

        if model != 'account.account':
            raise UserError(_("ID incorrecto para la línea del libro auxiliar a expandir: %s", line_dict_id))

        lines = []

        # Obtener saldo inicial
        if offset == 0:
            if unfold_all_batch_data:
                account, init_balance_by_col_group = unfold_all_batch_data['initial_balances'][model_id]
            else:
                account, init_balance_by_col_group = self._get_initial_balance_values(report, [model_id], options)[model_id]

            initial_balance_line = report._get_partner_and_general_ledger_initial_balance_line(options, line_dict_id, init_balance_by_col_group, None)

            if initial_balance_line:
                lines.append(initial_balance_line)

                # Para la primera expansión de la línea, la línea de saldo inicial da el progreso
                progress = init_load_more_progress(initial_balance_line)

        # Obtener líneas de movimiento
        limit_to_load = report.load_more_limit + 1 if report.load_more_limit and options['export_mode'] != 'print' else None
        if unfold_all_batch_data:
            aml_results = unfold_all_batch_data['aml_results'].get(model_id, {})
            has_more = unfold_all_batch_data['has_more'].get(model_id, False)
        else:
            aml_results, has_more = self._get_aml_values(report, options, [model_id], offset=offset, limit=limit_to_load)
            aml_results = aml_results.get(model_id, {})

        next_progress = progress
        for aml_result in aml_results.values():
            new_line = self._get_aml_line(report, line_dict_id, options, {options['column_groups'].keys().__iter__().__next__(): aml_result}, next_progress)
            lines.append(new_line)

            for column, line_col in zip(options['columns'], new_line['columns']):
                if column['expression_label'] == 'balance':
                    next_progress[column['column_group_key']] = line_col.get('no_format', 0)

        return {
            'lines': lines,
            'offset_increment': len(aml_results),
            'has_more': has_more,
        }
