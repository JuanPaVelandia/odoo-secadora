# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api, _
from odoo.tools.misc import format_date
from odoo.tools import get_lang, SQL
from odoo.exceptions import UserError
from collections import defaultdict, OrderedDict
from datetime import datetime, timedelta
import calendar
import logging

_logger = logging.getLogger(__name__)


class AccountLedgerBookColombiaHandler(models.AbstractModel):
    _name = 'account.ledger.book.colombia.handler'
    _inherit = 'account.report.custom.handler'
    _description = 'Libro Mayor Colombia - Agrupado por Niveles PUC'

    # Configuración de niveles PUC Colombia
    PUC_LEVELS = {
        1: {'name': 'Clase', 'digits': 1},
        2: {'name': 'Grupo', 'digits': 2},
        3: {'name': 'Cuenta', 'digits': 4},
        4: {'name': 'Subcuenta', 'digits': 6},
        5: {'name': 'Auxiliar', 'digits': 8},
    }

    def _get_custom_display_config(self):
        """Configuración de display."""
        return {
            'templates': {
                'AccountReportLineName': 'account_reports.GeneralLedgerLineName',
            },
            'components': {
                'AccountReportFilters': 'libros_contables_colombia.TrialBalancePartnerFilters',
            },
            'css_custom_class': 'ledger_book_colombia',
        }

    def _caret_options_initializer(self):
        """Inicializar opciones de caret para navegación."""
        return {
            'account.account': [
                {'name': _("Ver Movimientos"), 'action': 'caret_option_open_journal_items'},
            ],
            'account.move.line': [
                {'name': _("Ver Asiento"), 'action': 'caret_option_open_record_form'},
            ],
        }

    def _custom_options_initializer(self, report, options, previous_options=None):
        super()._custom_options_initializer(report, options, previous_options=previous_options)
        options.setdefault('show_initial_balance', True)
        options.setdefault('group_by_level', True)  # Siempre agrupar por nivel

        if previous_options:
            if 'show_initial_balance' in previous_options:
                options['show_initial_balance'] = previous_options['show_initial_balance']

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        """Genera las líneas del reporte del libro mayor agrupado por niveles PUC."""
        lines = []

        try:
            # Obtener datos de cuentas
            accounts_data = self._query_ledger_values(report, options)

            if not accounts_data:
                return [(0, self._get_no_data_line(report, options))]

            # Agrupar por niveles PUC
            grouped_data = self._group_by_puc_levels(accounts_data)

            # Generar líneas jerárquicas
            lines = self._generate_hierarchical_lines(report, options, grouped_data)

            # Agregar línea de totales
            total_initial, total_debit, total_credit, total_final = self._calculate_totals(accounts_data)
            lines.append(self._get_total_line(report, options, total_initial, total_debit, total_credit, total_final))

        except Exception as e:
            _logger.error(f"Error generando reporte libro mayor: {str(e)}")
            import traceback
            _logger.error(traceback.format_exc())
            return [(0, self._get_error_line(report, options, str(e)))]

        return [(0, line) for line in lines]

    def _query_ledger_values(self, report, options):
        """Ejecuta la consulta SQL y combina los resultados por cuenta."""
        try:
            query = self._get_ledger_query(report, options)

            if not query:
                return []

            self._cr.execute(query)
            raw_results = self._cr.dictfetchall()

            # Combinar resultados por account_id (initial + period)
            accounts_data = {}
            for row in raw_results:
                account_id = row['account_id']
                if account_id not in accounts_data:
                    accounts_data[account_id] = {
                        'account_id': account_id,
                        'account_code': row['account_code'] or '',
                        'account_name': row['account_name'] or '',
                        'account_type': row['account_type'] or '',
                        'initial_balance': 0.0,
                        'debit': 0.0,
                        'credit': 0.0,
                        'final_balance': 0.0,
                    }

                if row['key'] == 'initial':
                    accounts_data[account_id]['initial_balance'] = row['balance'] or 0.0
                elif row['key'] == 'period':
                    accounts_data[account_id]['debit'] = row['debit'] or 0.0
                    accounts_data[account_id]['credit'] = row['credit'] or 0.0

            # Calcular saldo final y filtrar cuentas sin movimiento
            results = []
            for account_data in accounts_data.values():
                account_data['final_balance'] = (
                    account_data['initial_balance'] +
                    account_data['debit'] -
                    account_data['credit']
                )
                # Solo incluir cuentas con movimiento o saldo
                if (account_data['initial_balance'] != 0 or
                    account_data['debit'] != 0 or
                    account_data['credit'] != 0):
                    results.append(account_data)

            # Ordenar por código de cuenta
            results.sort(key=lambda x: x.get('account_code', '') or '')
            return results

        except Exception as e:
            _logger.error(f"Error en consulta libro mayor: {str(e)}")
            raise

    def _get_ledger_query(self, report, options) -> SQL:
        """Construye la consulta SQL para el libro mayor - Odoo 18 API."""
        date_from = options.get('date', {}).get('date_from')
        date_to = options.get('date', {}).get('date_to')

        if not date_from or not date_to:
            return SQL("")

        base_domain = [
            ('move_id.state', '=', 'posted'),
            ('display_type', 'not in', ('line_section', 'line_note')),
        ]

        # =====================================================================
        # FILTRO POR RANGO DE CUENTAS (account_from, account_to, account_exclude)
        # =====================================================================
        account_from = options.get('account_from', '').strip() if options.get('account_from') else ''
        account_to = options.get('account_to', '').strip() if options.get('account_to') else ''
        account_exclude = options.get('account_exclude', [])

        if account_from:
            base_domain.append(('account_id.code', '>=', account_from))
        if account_to:
            base_domain.append(('account_id.code', '<=', account_to + 'z'))
        if account_exclude:
            for exclude_code in account_exclude:
                if exclude_code:
                    base_domain.append(('account_id.code', 'not ilike', exclude_code.strip() + '%'))

        queries = []

        # Query para saldos iniciales
        initial_options = self._get_options_initial_balance(options)
        query_initial = report._get_report_query(initial_options, 'from_beginning', domain=base_domain)

        account_alias_init = query_initial.join(
            lhs_alias='account_move_line',
            lhs_column='account_id',
            rhs_table='account_account',
            rhs_column='id',
            link='account_id_ledger_init'
        )
        account_code_init = self.env['account.account']._field_to_sql(account_alias_init, 'code', query_initial)
        account_name_init = self.env['account.account']._field_to_sql(account_alias_init, 'name')
        account_type_init = self.env['account.account']._field_to_sql(account_alias_init, 'account_type')

        queries.append(SQL(
            """
            SELECT
                account_move_line.account_id AS account_id,
                %(account_code)s AS account_code,
                %(account_name)s AS account_name,
                %(account_type)s AS account_type,
                'initial' AS key,
                SUM(%(balance_select)s) AS balance,
                0.0 AS debit,
                0.0 AS credit
            FROM %(table_references)s
            %(currency_table_join)s
            WHERE %(search_condition)s
            GROUP BY account_move_line.account_id, %(account_code)s, %(account_name)s, %(account_type)s
            """,
            account_code=account_code_init,
            account_name=account_name_init,
            account_type=account_type_init,
            table_references=query_initial.from_clause,
            balance_select=report._currency_table_apply_rate(SQL("account_move_line.balance")),
            currency_table_join=report._currency_table_aml_join(initial_options),
            search_condition=query_initial.where_clause,
        ))

        # Query para movimientos del período
        query_period = report._get_report_query(options, 'strict_range', domain=base_domain)

        account_alias_period = query_period.join(
            lhs_alias='account_move_line',
            lhs_column='account_id',
            rhs_table='account_account',
            rhs_column='id',
            link='account_id_ledger_period'
        )
        account_code_period = self.env['account.account']._field_to_sql(account_alias_period, 'code', query_period)
        account_name_period = self.env['account.account']._field_to_sql(account_alias_period, 'name')
        account_type_period = self.env['account.account']._field_to_sql(account_alias_period, 'account_type')

        queries.append(SQL(
            """
            SELECT
                account_move_line.account_id AS account_id,
                %(account_code)s AS account_code,
                %(account_name)s AS account_name,
                %(account_type)s AS account_type,
                'period' AS key,
                0.0 AS balance,
                SUM(%(debit_select)s) AS debit,
                SUM(%(credit_select)s) AS credit
            FROM %(table_references)s
            %(currency_table_join)s
            WHERE %(search_condition)s
            GROUP BY account_move_line.account_id, %(account_code)s, %(account_name)s, %(account_type)s
            """,
            account_code=account_code_period,
            account_name=account_name_period,
            account_type=account_type_period,
            table_references=query_period.from_clause,
            debit_select=report._currency_table_apply_rate(SQL("account_move_line.debit")),
            credit_select=report._currency_table_apply_rate(SQL("account_move_line.credit")),
            currency_table_join=report._currency_table_aml_join(options),
            search_condition=query_period.where_clause,
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

        new_options['date'] = self.env['account.report']._get_dates_period(
            new_date_from,
            new_date_to,
            'range',
        )
        new_options['include_current_year_in_unaff_earnings'] = include_current_year_in_unaff_earnings

        return new_options

    def _get_account_level(self, account_code):
        """Determina el nivel PUC de una cuenta basado en su código."""
        if not account_code:
            return 5  # Default al nivel más bajo

        code_len = len(account_code.strip())

        if code_len == 1:
            return 1  # Clase
        elif code_len == 2:
            return 2  # Grupo
        elif code_len <= 4:
            return 3  # Cuenta
        elif code_len <= 6:
            return 4  # Subcuenta
        else:
            return 5  # Auxiliar

    def _get_parent_code(self, account_code, target_level):
        """Obtiene el código padre para un nivel específico."""
        if not account_code:
            return ''

        level_digits = self.PUC_LEVELS.get(target_level, {}).get('digits', 0)
        return account_code[:level_digits] if len(account_code) >= level_digits else account_code

    def _group_by_puc_levels(self, accounts_data):
        """
        Agrupa las cuentas por niveles PUC.
        Retorna una estructura jerárquica ordenada.
        """
        # Crear estructura jerárquica
        hierarchy = OrderedDict()

        for account in accounts_data:
            code = account.get('account_code', '')
            if not code:
                continue

            # Obtener códigos para cada nivel
            level1_code = code[:1] if len(code) >= 1 else code  # Clase
            level2_code = code[:2] if len(code) >= 2 else code  # Grupo
            level3_code = code[:4] if len(code) >= 4 else code  # Cuenta
            level4_code = code[:6] if len(code) >= 6 else code  # Subcuenta

            # Nivel 1: Clase
            if level1_code not in hierarchy:
                hierarchy[level1_code] = {
                    'code': level1_code,
                    'name': self._get_level_name(level1_code, 1),
                    'level': 1,
                    'initial_balance': 0.0,
                    'debit': 0.0,
                    'credit': 0.0,
                    'final_balance': 0.0,
                    'children': OrderedDict(),
                    'accounts': [],
                }

            # Nivel 2: Grupo
            if level2_code not in hierarchy[level1_code]['children']:
                hierarchy[level1_code]['children'][level2_code] = {
                    'code': level2_code,
                    'name': self._get_level_name(level2_code, 2),
                    'level': 2,
                    'initial_balance': 0.0,
                    'debit': 0.0,
                    'credit': 0.0,
                    'final_balance': 0.0,
                    'children': OrderedDict(),
                    'accounts': [],
                }

            # Nivel 3: Cuenta
            if len(code) >= 4:
                if level3_code not in hierarchy[level1_code]['children'][level2_code]['children']:
                    hierarchy[level1_code]['children'][level2_code]['children'][level3_code] = {
                        'code': level3_code,
                        'name': self._get_level_name(level3_code, 3),
                        'level': 3,
                        'initial_balance': 0.0,
                        'debit': 0.0,
                        'credit': 0.0,
                        'final_balance': 0.0,
                        'children': OrderedDict(),
                        'accounts': [],
                    }

                # Nivel 4: Subcuenta
                if len(code) >= 6:
                    if level4_code not in hierarchy[level1_code]['children'][level2_code]['children'][level3_code]['children']:
                        hierarchy[level1_code]['children'][level2_code]['children'][level3_code]['children'][level4_code] = {
                            'code': level4_code,
                            'name': self._get_level_name(level4_code, 4),
                            'level': 4,
                            'initial_balance': 0.0,
                            'debit': 0.0,
                            'credit': 0.0,
                            'final_balance': 0.0,
                            'accounts': [],
                        }
                        # Agregar cuenta al nivel 4
                        hierarchy[level1_code]['children'][level2_code]['children'][level3_code]['children'][level4_code]['accounts'].append(account)
                    else:
                        hierarchy[level1_code]['children'][level2_code]['children'][level3_code]['children'][level4_code]['accounts'].append(account)
                else:
                    # Cuenta de 4 dígitos sin subcuenta
                    hierarchy[level1_code]['children'][level2_code]['children'][level3_code]['accounts'].append(account)
            else:
                # Cuenta de 2 dígitos
                hierarchy[level1_code]['children'][level2_code]['accounts'].append(account)

            # Acumular totales hacia arriba
            hierarchy[level1_code]['initial_balance'] += account.get('initial_balance', 0.0)
            hierarchy[level1_code]['debit'] += account.get('debit', 0.0)
            hierarchy[level1_code]['credit'] += account.get('credit', 0.0)
            hierarchy[level1_code]['final_balance'] += account.get('final_balance', 0.0)

            hierarchy[level1_code]['children'][level2_code]['initial_balance'] += account.get('initial_balance', 0.0)
            hierarchy[level1_code]['children'][level2_code]['debit'] += account.get('debit', 0.0)
            hierarchy[level1_code]['children'][level2_code]['credit'] += account.get('credit', 0.0)
            hierarchy[level1_code]['children'][level2_code]['final_balance'] += account.get('final_balance', 0.0)

            if len(code) >= 4 and level3_code in hierarchy[level1_code]['children'][level2_code]['children']:
                hierarchy[level1_code]['children'][level2_code]['children'][level3_code]['initial_balance'] += account.get('initial_balance', 0.0)
                hierarchy[level1_code]['children'][level2_code]['children'][level3_code]['debit'] += account.get('debit', 0.0)
                hierarchy[level1_code]['children'][level2_code]['children'][level3_code]['credit'] += account.get('credit', 0.0)
                hierarchy[level1_code]['children'][level2_code]['children'][level3_code]['final_balance'] += account.get('final_balance', 0.0)

                if len(code) >= 6 and level4_code in hierarchy[level1_code]['children'][level2_code]['children'][level3_code]['children']:
                    hierarchy[level1_code]['children'][level2_code]['children'][level3_code]['children'][level4_code]['initial_balance'] += account.get('initial_balance', 0.0)
                    hierarchy[level1_code]['children'][level2_code]['children'][level3_code]['children'][level4_code]['debit'] += account.get('debit', 0.0)
                    hierarchy[level1_code]['children'][level2_code]['children'][level3_code]['children'][level4_code]['credit'] += account.get('credit', 0.0)
                    hierarchy[level1_code]['children'][level2_code]['children'][level3_code]['children'][level4_code]['final_balance'] += account.get('final_balance', 0.0)

        return hierarchy

    def _get_level_name(self, code, level):
        """Obtiene el nombre descriptivo para un nivel de cuenta."""
        level_names = {
            1: {
                '1': 'ACTIVO',
                '2': 'PASIVO',
                '3': 'PATRIMONIO',
                '4': 'INGRESOS',
                '5': 'GASTOS',
                '6': 'COSTOS DE VENTAS',
                '7': 'COSTOS DE PRODUCCIÓN',
                '8': 'CUENTAS DE ORDEN DEUDORAS',
                '9': 'CUENTAS DE ORDEN ACREEDORAS',
            },
            2: {
                '11': 'DISPONIBLE',
                '12': 'INVERSIONES',
                '13': 'DEUDORES',
                '14': 'INVENTARIOS',
                '15': 'PROPIEDAD PLANTA Y EQUIPO',
                '16': 'INTANGIBLES',
                '17': 'DIFERIDOS',
                '18': 'OTROS ACTIVOS',
                '21': 'OBLIGACIONES FINANCIERAS',
                '22': 'PROVEEDORES',
                '23': 'CUENTAS POR PAGAR',
                '24': 'IMPUESTOS GRAVÁMENES Y TASAS',
                '25': 'OBLIGACIONES LABORALES',
                '26': 'PASIVOS ESTIMADOS Y PROVISIONES',
                '27': 'DIFERIDOS',
                '28': 'OTROS PASIVOS',
                '31': 'CAPITAL SOCIAL',
                '32': 'SUPERÁVIT DE CAPITAL',
                '33': 'RESERVAS',
                '34': 'REVALORIZACIÓN DEL PATRIMONIO',
                '36': 'RESULTADOS DEL EJERCICIO',
                '37': 'RESULTADOS DE EJERCICIOS ANTERIORES',
                '38': 'SUPERÁVIT POR VALORIZACIONES',
                '41': 'OPERACIONALES',
                '42': 'NO OPERACIONALES',
                '51': 'OPERACIONALES DE ADMINISTRACIÓN',
                '52': 'OPERACIONALES DE VENTAS',
                '53': 'NO OPERACIONALES',
                '61': 'COSTO DE VENTAS',
            },
        }

        if level in level_names and code in level_names[level]:
            return level_names[level][code]

        return f"Nivel {level} - {code}"

    def _generate_hierarchical_lines(self, report, options, hierarchy):
        """Genera las líneas del reporte de forma jerárquica."""
        lines = []

        for level1_code, level1_data in hierarchy.items():
            # Línea de Clase (Nivel 1)
            lines.append(self._get_level_line(report, options, level1_data, 1))

            for level2_code, level2_data in level1_data.get('children', {}).items():
                # Línea de Grupo (Nivel 2)
                lines.append(self._get_level_line(report, options, level2_data, 2))

                for level3_code, level3_data in level2_data.get('children', {}).items():
                    # Línea de Cuenta (Nivel 3)
                    lines.append(self._get_level_line(report, options, level3_data, 3))

                    for level4_code, level4_data in level3_data.get('children', {}).items():
                        # Línea de Subcuenta (Nivel 4)
                        lines.append(self._get_level_line(report, options, level4_data, 4))

                        # Cuentas auxiliares (Nivel 5)
                        for account in level4_data.get('accounts', []):
                            lines.append(self._get_account_detail_line(report, options, account, 5))

                    # Cuentas directas de nivel 3 (sin subcuenta)
                    for account in level3_data.get('accounts', []):
                        lines.append(self._get_account_detail_line(report, options, account, 4))

                # Cuentas directas de nivel 2
                for account in level2_data.get('accounts', []):
                    lines.append(self._get_account_detail_line(report, options, account, 3))

        return lines

    def _get_level_line(self, report, options, level_data, level):
        """Crea una línea de nivel (Clase, Grupo, Cuenta, Subcuenta)."""
        code = level_data.get('code', '')
        name = level_data.get('name', '')

        line_columns = []
        for column in options['columns']:
            col_expr_label = column['expression_label']
            col_value = None

            # Mapear expression_labels del XML a los datos
            if col_expr_label == 'account_code':
                col_value = ''  # No mostrar código separado, ya está en el nombre
            elif col_expr_label == 'account_name':
                col_value = ''  # No mostrar nombre separado, ya está en el nombre
            elif col_expr_label == 'initial_balance':
                col_value = level_data.get('initial_balance', 0.0)
            elif col_expr_label == 'debit':
                col_value = level_data.get('debit', 0.0)
            elif col_expr_label == 'credit':
                col_value = level_data.get('credit', 0.0)
            elif col_expr_label in ('balance', 'final_balance'):
                col_value = level_data.get('final_balance', 0.0)

            line_columns.append(report._build_column_dict(col_value, column, options=options))

        # Estilo según nivel
        css_class = ''
        if level == 1:
            css_class = 'total o_account_reports_totals_below_sections'
        elif level == 2:
            css_class = 'o_account_reports_level1'

        return {
            'id': report._get_generic_line_id(None, None, markup=f'level_{level}_{code}'),
            'name': f"{code} {name}",
            'level': level,
            'unfoldable': False,
            'unfolded': True,
            'columns': line_columns,
            'class': css_class,
        }

    def _get_account_detail_line(self, report, options, account_data, level):
        """Crea una línea de cuenta auxiliar (nivel de detalle)."""
        account_code = account_data.get('account_code', '')
        account_name = account_data.get('account_name', '')

        line_columns = []
        for column in options['columns']:
            col_expr_label = column['expression_label']
            col_value = None

            # Mapear expression_labels del XML a los datos
            if col_expr_label == 'account_code':
                col_value = ''  # Ya está en el nombre
            elif col_expr_label == 'account_name':
                col_value = ''  # Ya está en el nombre
            elif col_expr_label == 'initial_balance':
                col_value = account_data.get('initial_balance', 0.0)
            elif col_expr_label == 'debit':
                col_value = account_data.get('debit', 0.0)
            elif col_expr_label == 'credit':
                col_value = account_data.get('credit', 0.0)
            elif col_expr_label in ('balance', 'final_balance'):
                col_value = account_data.get('final_balance', 0.0)

            line_columns.append(report._build_column_dict(col_value, column, options=options))

        account_line_id = report._get_generic_line_id('account.account', account_data.get('account_id'), markup='ledger_account')

        return {
            'id': account_line_id,
            'name': f"{account_code} {account_name}",
            'level': level,
            'unfoldable': True,
            'unfolded': account_line_id in options.get('unfolded_lines', []),
            'expand_function': '_report_expand_unfoldable_line_ledger_book_colombia',
            'columns': line_columns,
            'caret_options': 'account.account',
        }

    def _calculate_totals(self, accounts_data):
        """Calcula los totales generales."""
        total_initial = sum(a.get('initial_balance', 0.0) for a in accounts_data)
        total_debit = sum(a.get('debit', 0.0) for a in accounts_data)
        total_credit = sum(a.get('credit', 0.0) for a in accounts_data)
        total_final = sum(a.get('final_balance', 0.0) for a in accounts_data)
        return total_initial, total_debit, total_credit, total_final

    def _get_total_line(self, report, options, total_initial, total_debit, total_credit, total_final):
        """Crea la línea de totales generales."""
        line_columns = []
        for column in options['columns']:
            col_expr_label = column['expression_label']
            col_value = None

            if col_expr_label in ('account_code', 'account_name'):
                col_value = ''  # No aplica para totales
            elif col_expr_label == 'initial_balance':
                col_value = total_initial
            elif col_expr_label == 'debit':
                col_value = total_debit
            elif col_expr_label == 'credit':
                col_value = total_credit
            elif col_expr_label in ('balance', 'final_balance'):
                col_value = total_final

            line_columns.append(report._build_column_dict(col_value, column, options=options))

        return {
            'id': report._get_generic_line_id(None, None, markup='total'),
            'name': _('TOTAL GENERAL'),
            'level': 0,
            'unfoldable': False,
            'columns': line_columns,
            'class': 'total o_account_reports_totals_below_sections',
        }

    def _get_no_data_line(self, report, options):
        """Crea una línea cuando no hay datos."""
        return {
            'id': report._get_generic_line_id(None, None, markup='no_data'),
            'name': _('No hay movimientos en el período seleccionado'),
            'level': 1,
            'unfoldable': False,
            'columns': [{'name': ''} for _ in options['columns']],
        }

    def _get_error_line(self, report, options, error_message):
        """Crea una línea de error."""
        return {
            'id': report._get_generic_line_id(None, None, markup='error'),
            'name': _('Error: %s') % error_message,
            'level': 1,
            'unfoldable': False,
            'columns': [{'name': ''} for _ in options['columns']],
            'class': 'text-danger',
        }

    def _report_expand_unfoldable_line_ledger_book_colombia(self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None):
        """Expande una cuenta para mostrar sus movimientos."""
        report = self.env['account.report'].browse(options['report_id'])
        lines = []

        try:
            model, model_id = report._get_model_info_from_id(line_dict_id)

            if model == 'account.account':
                lines = self._get_account_movements(report, options, model_id, line_dict_id)

        except Exception as e:
            _logger.error(f"Error expanding line {line_dict_id}: {str(e)}")
            import traceback
            _logger.error(traceback.format_exc())
            lines = [{
                'id': report._get_generic_line_id(None, None, markup='ledger_error_expand', parent_line_id=line_dict_id),
                'name': _('Error cargando detalles: %s') % str(e),
                'level': 6,
                'unfoldable': False,
                'parent_id': line_dict_id,
                'columns': [report._build_column_dict('', col, options=options) for col in options['columns']],
                'class': 'text-danger',
            }]

        # Agregar línea de total al final para evitar que _add_totals_below_sections falle
        if lines:
            total_debit = sum(
                line.get('columns', [{}])[3].get('no_format', 0) or 0
                for line in lines
                if isinstance(line.get('columns', [{}])[3] if len(line.get('columns', [])) > 3 else {}, dict)
            )
            total_credit = sum(
                line.get('columns', [{}])[4].get('no_format', 0) or 0
                for line in lines
                if isinstance(line.get('columns', [{}])[4] if len(line.get('columns', [])) > 4 else {}, dict)
            )

            # Calcular saldo final del último movimiento
            final_balance = 0
            for line in reversed(lines):
                cols = line.get('columns', [])
                if len(cols) > 5 and isinstance(cols[5], dict):
                    final_balance = cols[5].get('no_format', 0) or 0
                    break

            total_columns = []
            for i, column in enumerate(options['columns']):
                col_expr_label = column['expression_label']
                col_value = ''
                if col_expr_label == 'debit':
                    col_value = total_debit
                elif col_expr_label == 'credit':
                    col_value = total_credit
                elif col_expr_label in ('balance', 'final_balance'):
                    col_value = final_balance
                total_columns.append(report._build_column_dict(col_value, column, options=options))

            lines.append({
                'id': report._get_generic_line_id(None, None, markup='ledger_subtotal', parent_line_id=line_dict_id),
                'name': _('Total Movimientos'),
                'level': 6,
                'unfoldable': False,
                'parent_id': line_dict_id,
                'columns': total_columns,
                'class': 'total',
            })

        return {
            'lines': lines,
            'offset_increment': len(lines),
            'has_more': False,
            'progress': progress or {},
        }

    def _get_account_movements(self, report, options, account_id, parent_line_id):
        """Obtiene los movimientos de una cuenta específica."""
        query_domain = [
            ('account_id', '=', account_id),
            ('move_id.state', '=', 'posted'),
            ('display_type', 'not in', ('line_section', 'line_note')),
        ]

        query = report._get_report_query(options, 'strict_range', domain=query_domain)

        sql_query = SQL(
            """
            SELECT
                account_move_line.id AS move_line_id,
                account_move_line.date AS date,
                account_move_line.name AS line_name,
                account_move.name AS move_name,
                account_move.move_type AS move_type,
                account_move.ref AS move_ref,
                partner.name AS partner_name,
                %(debit_select)s AS debit,
                %(credit_select)s AS credit,
                %(balance_select)s AS balance
            FROM %(table_references)s
            JOIN account_move ON account_move.id = account_move_line.move_id
            LEFT JOIN res_partner partner ON partner.id = account_move_line.partner_id
            %(currency_table_join)s
            WHERE %(search_condition)s
            ORDER BY account_move_line.date, account_move_line.id
            LIMIT 100
            """,
            table_references=query.from_clause,
            debit_select=report._currency_table_apply_rate(SQL("account_move_line.debit")),
            credit_select=report._currency_table_apply_rate(SQL("account_move_line.credit")),
            balance_select=report._currency_table_apply_rate(SQL("account_move_line.balance")),
            currency_table_join=report._currency_table_aml_join(options),
            search_condition=query.where_clause,
        )

        self._cr.execute(sql_query)
        movements = self._cr.dictfetchall()

        lines = []

        # Línea de saldo inicial
        initial_balance = self._get_account_initial_balance(report, options, account_id)
        if initial_balance != 0:
            initial_columns = []
            for column in options['columns']:
                col_expr_label = column['expression_label']
                col_value = None
                if col_expr_label in ('account_code', 'account_name'):
                    col_value = ''
                elif col_expr_label == 'initial_balance':
                    col_value = initial_balance
                elif col_expr_label in ('balance', 'final_balance'):
                    col_value = initial_balance
                initial_columns.append(report._build_column_dict(col_value, column, options=options))

            lines.append({
                'id': report._get_generic_line_id(None, None, markup='ledger_initial_balance', parent_line_id=parent_line_id),
                'name': _('Saldo Inicial'),
                'level': 6,
                'unfoldable': False,
                'parent_id': parent_line_id,
                'columns': initial_columns,
                'class': 'font-italic text-muted',
            })

        # Movimientos
        running_balance = initial_balance
        for move in movements:
            running_balance += move.get('debit', 0.0) - move.get('credit', 0.0)

            line_columns = []
            for column in options['columns']:
                col_expr_label = column['expression_label']
                col_value = None

                if col_expr_label in ('account_code', 'account_name', 'initial_balance'):
                    col_value = ''  # No aplica para movimientos
                elif col_expr_label == 'debit':
                    col_value = move.get('debit', 0.0)
                elif col_expr_label == 'credit':
                    col_value = move.get('credit', 0.0)
                elif col_expr_label in ('balance', 'final_balance'):
                    col_value = running_balance

                line_columns.append(report._build_column_dict(col_value, column, options=options))

            # Construir descripción
            description_parts = [format_date(self.env, move['date'])]
            description_parts.append(move.get('move_name', ''))
            if move.get('line_name'):
                description_parts.append(move.get('line_name'))
            if move.get('partner_name'):
                description_parts.append(f"({move.get('partner_name')})")

            lines.append({
                'id': report._get_generic_line_id('account.move.line', move['move_line_id'], markup='ledger_move', parent_line_id=parent_line_id),
                'name': ' - '.join(filter(None, description_parts)),
                'level': 6,
                'unfoldable': False,
                'parent_id': parent_line_id,
                'columns': line_columns,
                'caret_options': 'account.move.line',
            })

        return lines

    def _get_account_initial_balance(self, report, options, account_id):
        """Obtiene el saldo inicial de una cuenta."""
        initial_options = self._get_options_initial_balance(options)

        query_domain = [
            ('account_id', '=', account_id),
            ('move_id.state', '=', 'posted'),
            ('display_type', 'not in', ('line_section', 'line_note')),
        ]

        query = report._get_report_query(initial_options, 'from_beginning', domain=query_domain)

        sql_query = SQL(
            """
            SELECT COALESCE(SUM(%(balance_select)s), 0) AS balance
            FROM %(table_references)s
            %(currency_table_join)s
            WHERE %(search_condition)s
            """,
            table_references=query.from_clause,
            balance_select=report._currency_table_apply_rate(SQL("account_move_line.balance")),
            currency_table_join=report._currency_table_aml_join(initial_options),
            search_condition=query.where_clause,
        )

        self._cr.execute(sql_query)
        result = self._cr.fetchone()
        return result[0] if result else 0.0

    def caret_option_open_journal_items(self, options, params):
        """Abrir apuntes contables para la cuenta específica."""
        account_id = params.get('id')
        if not account_id:
            return {'type': 'ir.actions.act_window_close'}

        domain = [('account_id', '=', account_id)]

        if options.get('date', {}).get('date_from'):
            domain.append(('date', '>=', options['date']['date_from']))
        if options.get('date', {}).get('date_to'):
            domain.append(('date', '<=', options['date']['date_to']))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Movimientos de la Cuenta'),
            'res_model': 'account.move.line',
            'view_mode': 'list,form',
            'domain': domain,
            'context': {'search_default_group_by_move': 1},
        }

    def caret_option_open_record_form(self, options, params):
        """Abrir formulario del asiento contable."""
        model = params.get('model', 'account.move.line')
        res_id = params.get('id')

        if not res_id or not model:
            return {'type': 'ir.actions.act_window_close'}

        if model == 'account.move.line':
            line = self.env['account.move.line'].browse(res_id)
            if line.exists():
                return {
                    'type': 'ir.actions.act_window',
                    'name': _('Asiento Contable'),
                    'res_model': 'account.move',
                    'res_id': line.move_id.id,
                    'view_mode': 'form',
                    'views': [(False, 'form')],
                }

        return {'type': 'ir.actions.act_window_close'}
