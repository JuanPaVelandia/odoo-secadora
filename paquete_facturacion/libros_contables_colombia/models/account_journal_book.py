# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import models, fields, api, _
from odoo.tools.misc import format_date
from odoo.tools import get_lang, SQL
from odoo.exceptions import UserError
from collections import defaultdict
from datetime import datetime, timedelta
import logging
_logger = logging.getLogger(__name__)


class AccountJournalBookColombiaHandler(models.AbstractModel):
    _name = 'account.journal.book.colombia.handler'
    _inherit = ['account.report.custom.handler', 'sql.helper.mixin']
    _description = 'Libro Diario Colombia - Múltiples Niveles'

    def _get_custom_display_config(self):
        return {
            'css_custom_class': 'journal_book_colombia_report',
            'templates': {
                'AccountReportLineName': 'account_reports.JournalReportLineName',
            },
            'components': {
                'AccountReportFilters': 'libros_contables_colombia.TrialBalancePartnerFilters',
            },
        }

    def _custom_options_initializer(self, report, options, previous_options=None):
        super()._custom_options_initializer(report, options, previous_options=previous_options)

        # Configurar opciones específicas para el libro diario
        options.setdefault('sort_by_date', True)
        options.setdefault('group_by_journal', True)
        options.setdefault('show_document_detail', True)

        if previous_options:
            for key in ['sort_by_date', 'group_by_journal', 'show_document_detail']:
                if key in previous_options:
                    options[key] = previous_options[key]

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        """
        Genera las líneas del reporte del libro diario con jerarquía de 4 niveles:
        NIVEL 0: Diario (ej: Ventas, Compras, Banco)
        NIVEL 1: Fecha específica
        NIVEL 2: Documento contable (ej: FACTURA FAC/2024/0001)
        NIVEL 3: Líneas individuales del documento
        """
        lines = []

        try:
            # Obtener datos del diario agrupados
            journal_data = self._get_journal_data_grouped(report, options)

            if not journal_data:
                return [(0, self._get_no_data_line(report, options))]

            # Generar líneas por diario
            total_debit = 0
            total_credit = 0

            for journal_name, date_groups in journal_data.items():
                if date_groups:
                    # NIVEL 0: Línea de diario
                    lines.append(self._get_journal_header_line(report, options, journal_name))

                    for date_str, doc_groups in date_groups.items():
                        # NIVEL 1: Línea de fecha
                        lines.append(self._get_date_header_line(report, options, date_str, journal_name))

                        for doc_name, doc_data in doc_groups.items():
                            # NIVEL 2: Línea de documento
                            doc_line = self._get_document_line(report, options, doc_name, doc_data, journal_name, date_str)
                            lines.append(doc_line)

                            # NIVEL 3: Si está expandido, mostrar líneas del documento
                            if doc_line['unfolded']:
                                for line_data in doc_data['lines']:
                                    detail_line = self._get_journal_detail_line(report, options, line_data, journal_name, date_str, doc_name)
                                    lines.append(detail_line)
                                    total_debit += line_data['debit']
                                    total_credit += line_data['credit']
                            else:
                                # Solo acumular totales si no está expandido
                                total_debit += doc_data['total_debit']
                                total_credit += doc_data['total_credit']

            # Línea de totales
            if lines:
                lines.append(self._get_total_line(report, options, total_debit, total_credit))

        except Exception as e:
            _logger.error(f"Error generando libro diario: {str(e)}")
            lines = [(0, self._get_error_line(report, options, str(e)))]

        return [(0, line) for line in lines]

    def _get_journal_data_grouped(self, report, options):
        """Obtener datos del diario agrupados por diario, fecha y documento"""
        query = self._get_journal_query(report, options)

        if not query:
            return {}

        self._cr.execute(query)
        results = self._cr.dictfetchall()

        # Agrupar por diario → fecha → documento
        grouped = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: {
            'total_debit': 0,
            'total_credit': 0,
            'lines': [],
            'move_id': None,
            'move_type': '',
            'state': '',
        })))

        for row in results:
            journal_name = row['journal_name']
            date_str = format_date(self.env, row['date'])
            doc_name = row['move_name']

            doc_data = grouped[journal_name][date_str][doc_name]
            doc_data['total_debit'] += row['debit']
            doc_data['total_credit'] += row['credit']
            doc_data['lines'].append(row)
            doc_data['move_id'] = row['move_id']
            doc_data['move_type'] = row['move_type']
            doc_data['state'] = row['state']

        return grouped

    def _get_journal_query(self, report, options) -> SQL:
        """Construye la consulta SQL para el libro diario usando Odoo 18 API"""
        # Configurar traducción de nombres usando helpers para JSONB
        lang = self.env.user.lang or get_lang(self.env).code
        # Dominio base para movimientos válidos
        query_domain = [
            ('move_id.state', '=', 'posted'),
            ('display_type', 'not in', ('line_section', 'line_note')),
        ]

        # =====================================================================
        # FILTRO POR RANGO DE CUENTAS (account_from, account_to, account_exclude)
        # =====================================================================
        account_from = options.get('account_from', '').strip()
        account_to = options.get('account_to', '').strip()
        account_exclude = options.get('account_exclude', [])

        if account_from:
            query_domain.append(('account_id.code', '>=', account_from))
        if account_to:
            query_domain.append(('account_id.code', '<=', account_to + 'z'))
        if account_exclude:
            for exclude_code in account_exclude:
                if exclude_code:
                    query_domain.append(('account_id.code', 'not ilike', exclude_code.strip() + '%'))

        queries = []

        for column_group_key, options_group in report._split_options_per_column_group(options).items():
            query = report._get_report_query(options_group, 'strict_range', domain=query_domain)

            # Usar patrón nativo Odoo 18: query.join + _field_to_sql
            account_alias = query.join(
                lhs_alias='account_move_line',
                lhs_column='account_id',
                rhs_table='account_account',
                rhs_column='id',
                link='account_id'
            )
            account_code = self.env['account.account']._field_to_sql(account_alias, 'code', query)
            account_name = self.env['account.account']._field_to_sql(account_alias, 'name')
            journal_name = self.env['account.journal']._field_to_sql('account_journal', 'name')

            queries.append(SQL(
                """
                SELECT
                    account_move_line.id AS move_line_id,
                    account_move_line.date AS date,
                    account_move_line.date AS date,
                    account_move_line.name AS line_name,
                    account_move_line.account_id AS account_id,
                    %(account_code)s AS account_code,
                    %(account_name)s AS account_name,
                    account_move.id AS move_id,
                    account_move.name AS move_name,
                    account_move.move_type AS move_type,
                    account_move.state AS state,
                    account_move.ref AS move_ref,
                    %(journal_name)s AS journal_name,
                    account_journal.code AS journal_code,
                    COALESCE(partner.name, '') AS partner_name,
                    %(debit_select)s AS debit,
                    %(credit_select)s AS credit,
                    %(balance_select)s AS balance,
                    CASE
                        WHEN account_move.move_type = 'entry' THEN 'ASIENTO'
                        WHEN account_move.move_type = 'out_invoice' THEN 'FACTURA'
                        WHEN account_move.move_type = 'out_refund' THEN 'NC CLIENTE'
                        WHEN account_move.move_type = 'in_invoice' THEN 'FAC PROVEEDOR'
                        WHEN account_move.move_type = 'in_refund' THEN 'NC PROVEEDOR'
                        ELSE 'OTRO'
                    END as doc_type_name
                FROM %(table_references)s
                JOIN account_move ON account_move.id = account_move_line.move_id
                JOIN account_journal ON account_journal.id = account_move_line.journal_id
                LEFT JOIN res_partner partner ON partner.id = account_move_line.partner_id
                %(currency_table_join)s
                WHERE %(search_condition)s
                ORDER BY %(journal_name)s, account_move_line.date, account_move.name, account_move_line.id
                """,
                account_code=account_code,
                account_name=account_name,
                journal_name=journal_name,
                table_references=query.from_clause,
                debit_select=report._currency_table_apply_rate(SQL("account_move_line.debit")),
                credit_select=report._currency_table_apply_rate(SQL("account_move_line.credit")),
                balance_select=report._currency_table_apply_rate(SQL("account_move_line.balance")),
                currency_table_join=report._currency_table_aml_join(options_group),
                search_condition=query.where_clause,
            ))

        return SQL(" UNION ALL ").join(queries)

    def _get_journal_header_line(self, report, options, journal_name):
        """NIVEL 0: Crear línea de encabezado de diario"""
        return {
            'id': report._get_generic_line_id(None, None, markup=f'journal_{journal_name}'),
            'name': f'DIARIO: {journal_name}',
            'level': 0,
            'unfoldable': False,
            'unfolded': True,
            'columns': [{'name': ''} for _ in options['columns']],
            'class': 'total o_account_reports_totals_below_sections',
        }

    def _get_date_header_line(self, report, options, date_str, journal_name):
        """NIVEL 1: Crear línea de encabezado de fecha"""
        parent_line_id = report._get_generic_line_id(None, None, markup=f'journal_{journal_name}')

        return {
            'id': report._get_generic_line_id(None, None, markup=f'date_{date_str}', parent_line_id=parent_line_id),
            'name': f'FECHA: {date_str}',
            'level': 1,
            'parent_id': parent_line_id,
            'unfoldable': False,
            'unfolded': True,
            'columns': [{'name': ''} for _ in options['columns']],
            'class': 'o_account_reports_level_1',
        }

    def _get_document_line(self, report, options, doc_name, doc_data, journal_name, date_str):
        """NIVEL 2: Crear línea para un documento contable"""
        parent_line_id = report._get_generic_line_id(None, None, markup=f'date_{date_str}',
                        parent_line_id=report._get_generic_line_id(None, None, markup=f'journal_{journal_name}'))
        line_id = report._get_generic_line_id('account.move', doc_data['move_id'], parent_line_id=parent_line_id)

        # Construir nombre del documento
        doc_type_name = self._get_move_type_display(doc_data['move_type'])
        name_parts = [f"[{doc_type_name}] {doc_name}"]

        if doc_data.get('state') == 'draft':
            name_parts.append('(BORRADOR)')

        # Construir columnas
        line_columns = []
        for column in options['columns']:
            col_expr_label = column['expression_label']
            col_value = None

            if col_expr_label == 'debit':
                col_value = doc_data['total_debit']
            elif col_expr_label == 'credit':
                col_value = doc_data['total_credit']
            elif col_expr_label == 'balance':
                col_value = doc_data['total_debit'] - doc_data['total_credit']

            line_columns.append(report._build_column_dict(col_value, column, options=options))

        return {
            'id': line_id,
            'name': ' '.join(name_parts),
            'level': 2,
            'parent_id': parent_line_id,
            'unfoldable': True,
            'unfolded': line_id in options.get('unfolded_lines', []),
            'expand_function': '_report_expand_unfoldable_line_journal_book_colombia',
            'columns': line_columns,
            'caret_options': 'account.move',
            'class': 'text-muted' if doc_data['state'] == 'draft' else '',
        }

    def _get_journal_detail_line(self, report, options, line_data, journal_name, date_str, doc_name):
        """NIVEL 3: Crear linea de detalle - cada dato en su columna"""
        journal_parent = report._get_generic_line_id(None, None, markup=f'journal_{journal_name}')
        date_parent = report._get_generic_line_id(None, None, markup=f'date_{date_str}', parent_line_id=journal_parent)
        doc_parent = report._get_generic_line_id('account.move', line_data['move_id'], parent_line_id=date_parent)

        # Incrementar contador de linea
        self._line_counter = getattr(self, '_line_counter', 0) + 1

        # Construir columnas - cada dato en su columna correspondiente
        line_columns = []
        for column in options['columns']:
            col_expr_label = column['expression_label']
            col_value = None

            if col_expr_label in ('numero', 'line_number'):
                col_value = self._line_counter
            elif col_expr_label == 'date':
                col_value = line_data.get('date', '')
            elif col_expr_label == 'account_code':
                col_value = line_data.get('account_code', '')
            elif col_expr_label == 'account_name':
                col_value = line_data.get('account_name', '')
            elif col_expr_label == 'partner_name':
                col_value = line_data.get('partner_name', '')
            elif col_expr_label == 'name':
                col_value = line_data.get('line_name', '') or line_data.get('name', '')
            elif col_expr_label == 'ref':
                col_value = line_data.get('ref', '')
            elif col_expr_label == 'debit':
                col_value = line_data.get('debit', 0)
            elif col_expr_label == 'credit':
                col_value = line_data.get('credit', 0)
            elif col_expr_label == 'balance':
                col_value = line_data.get('balance', 0)

            line_columns.append(report._build_column_dict(col_value, column, options=options))

        line_name = line_data.get('line_name', '') or f"Linea {self._line_counter}"

        return {
            'id': report._get_generic_line_id('account.move.line', line_data['move_line_id'], parent_line_id=doc_parent),
            'name': line_name,
            'level': 3,
            'parent_id': doc_parent,
            'unfoldable': False,
            'columns': line_columns,
            'caret_options': 'account.move.line',
        }

    def _get_total_line(self, report, options, total_debit, total_credit):
        """Crear línea de totales"""
        line_columns = []
        for column in options['columns']:
            col_expr_label = column['expression_label']
            col_value = None

            if col_expr_label == 'debit':
                col_value = total_debit
            elif col_expr_label == 'credit':
                col_value = total_credit
            elif col_expr_label == 'balance':
                col_value = total_debit - total_credit

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
        """Crear línea cuando no hay datos"""
        return {
            'id': report._get_generic_line_id(None, None, markup='no_data'),
            'name': _('No hay movimientos en el período seleccionado'),
            'level': 0,
            'unfoldable': False,
            'columns': [{'name': ''} for _ in options['columns']],
        }

    def _get_error_line(self, report, options, error_message):
        """Crear línea de error"""
        return {
            'id': report._get_generic_line_id(None, None, markup='error'),
            'name': _('Error: %s') % error_message,
            'level': 0,
            'unfoldable': False,
            'columns': [{'name': ''} for _ in options['columns']],
            'class': 'text-danger',
        }

    def _report_expand_unfoldable_line_journal_book_colombia(self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None):
        """
        Método de expansión para jerarquía completa del libro diario:
        NIVEL 2 (documento) → NIVEL 3 (líneas del documento)
        """
        _logger.info(f"Expanding journal line: {line_dict_id}")

        report = self.env['account.report'].browse(options['report_id'])
        lines = []

        try:
            model, model_id = report._get_model_info_from_id(line_dict_id)

            if model == 'account.move':
                # NIVEL 3: Expandir documento → mostrar líneas del documento
                lines = self._get_move_detail_lines_journal(report, options, model_id, line_dict_id)

        except Exception as e:
            _logger.error(f"Error expanding journal line {line_dict_id}: {str(e)}")
            lines = [{
                'id': report._get_generic_line_id(None, None, markup=f'error_expand_{line_dict_id}'),
                'name': _('Error cargando detalles: %s') % str(e),
                'level': 3,
                'unfoldable': False,
                'columns': [{'name': ''} for _ in options['columns']],
                'class': 'text-danger',
            }]

        return {
            'lines': lines,
            'offset_increment': 0,
            'has_more': False,
            'progress': progress or {},
        }

    def _get_move_detail_lines_journal(self, report, options, move_id, parent_line_id):
        """NIVEL 3: Obtener lineas de detalle - cada dato en su columna"""
        query = self._get_move_detail_query_journal(report, options, move_id)

        if not query:
            return []

        self._cr.execute(query)
        detail_data = self._cr.dictfetchall()

        lines = []
        # Inicializar contador si no existe
        if not hasattr(self, '_detail_line_counter'):
            self._detail_line_counter = 0

        for detail in detail_data:
            self._detail_line_counter += 1

            # Construir columnas - cada dato en su columna correspondiente
            line_columns = []
            for column in options['columns']:
                col_expr_label = column['expression_label']
                col_value = None

                if col_expr_label in ('numero', 'line_number'):
                    col_value = self._detail_line_counter
                elif col_expr_label == 'date':
                    col_value = detail.get('date', '')
                elif col_expr_label == 'account_code':
                    col_value = detail.get('account_code', '')
                elif col_expr_label == 'account_name':
                    col_value = detail.get('account_name', '')
                elif col_expr_label == 'partner_name':
                    col_value = detail.get('partner_name', '')
                elif col_expr_label == 'name':
                    col_value = detail.get('line_name', '') or detail.get('name', '')
                elif col_expr_label == 'ref':
                    col_value = detail.get('ref', '')
                elif col_expr_label == 'debit':
                    col_value = detail.get('debit', 0)
                elif col_expr_label == 'credit':
                    col_value = detail.get('credit', 0)
                elif col_expr_label == 'balance':
                    col_value = detail.get('balance', 0)

                line_columns.append(report._build_column_dict(col_value, column, options=options))

            # El nombre de la linea muestra cuenta y descripcion breve
            line_name = detail.get('line_name', '') or f"{detail.get('account_code', '')} - {detail.get('account_name', '')}"

            lines.append({
                'id': report._get_generic_line_id('account.move.line', detail['move_line_id'], parent_line_id=parent_line_id),
                'name': line_name[:60],  # Limitar longitud del nombre
                'level': 3,
                'parent_id': parent_line_id,
                'unfoldable': False,
                'columns': line_columns,
                'caret_options': 'account.move.line',
            })

        return lines

    def _get_move_detail_query_journal(self, report, options, move_id) -> SQL:
        """Construye la consulta SQL para los detalles de un movimiento usando Odoo 18 API"""
        query_domain = [
            ('move_id', '=', move_id),
            ('display_type', 'not in', ('line_section', 'line_note')),
        ]

        queries = []

        for column_group_key, options_group in report._split_options_per_column_group(options).items():
            query = report._get_report_query(options_group, 'strict_range', domain=query_domain)

            # Usar patrón nativo Odoo 18: query.join + _field_to_sql
            account_alias = query.join(
                lhs_alias='account_move_line',
                lhs_column='account_id',
                rhs_table='account_account',
                rhs_column='id',
                link='account_id'
            )
            account_code = self.env['account.account']._field_to_sql(account_alias, 'code', query)
            account_name = self.env['account.account']._field_to_sql(account_alias, 'name')

            queries.append(SQL(
                """
                SELECT
                    account_move_line.id AS move_line_id,
                    account_move_line.date AS date,
                    account_move_line.account_id AS account_id,
                    %(account_code)s AS account_code,
                    %(account_name)s AS account_name,
                    account_move_line.name AS line_name,
                    COALESCE(partner.name, '') AS partner_name,
                    %(debit_select)s AS debit,
                    %(credit_select)s AS credit,
                    %(balance_select)s AS balance
                FROM %(table_references)s
                LEFT JOIN res_partner partner ON partner.id = account_move_line.partner_id
                %(currency_table_join)s
                WHERE %(search_condition)s
                ORDER BY account_move_line.id
                """,
                account_code=account_code,
                account_name=account_name,
                table_references=query.from_clause,
                debit_select=report._currency_table_apply_rate(SQL("account_move_line.debit")),
                credit_select=report._currency_table_apply_rate(SQL("account_move_line.credit")),
                balance_select=report._currency_table_apply_rate(SQL("account_move_line.balance")),
                currency_table_join=report._currency_table_aml_join(options_group),
                search_condition=query.where_clause,
            ))

        return SQL(" UNION ALL ").join(queries)

    def _get_move_type_display(self, move_type):
        """Convierte el tipo de movimiento a texto legible"""
        move_types = {
            'entry': 'ASIENTO',
            'out_invoice': 'FACTURA',
            'out_refund': 'NC CLIENTE',
            'in_invoice': 'FAC PROVEEDOR',
            'in_refund': 'NC PROVEEDOR',
            'out_receipt': 'RECIBO VENTA',
            'in_receipt': 'RECIBO COMPRA',
        }
        return move_types.get(move_type, move_type.upper())

    def _custom_unfold_all_batch_data_generator(self, report, options, lines_to_expand_by_function):
        """Genera datos en lote para expansión optimizada"""
        move_ids_to_expand = []

        for line_dict in lines_to_expand_by_function.get('_report_expand_unfoldable_line_journal_book_colombia', []):
            model, model_id = report._get_model_info_from_id(line_dict['id'])
            if model == 'account.move':
                move_ids_to_expand.append(model_id)

        # Pre-cargar datos de movimientos para optimizar
        move_details_cache = {}
        if move_ids_to_expand:
            try:
                for move_id in move_ids_to_expand:
                    query = self._get_move_detail_query_journal(report, options, move_id)
                    if query:
                        self._cr.execute(query)
                        move_details_cache[move_id] = self._cr.dictfetchall()
            except Exception as e:
                _logger.error(f"Error pre-cargando datos de movimientos: {str(e)}")

        return {
            'move_ids': move_ids_to_expand,
            'move_details_cache': move_details_cache,
            'options_cache': options.copy(),
        }

    def _caret_options_initializer(self):
        """Opciones de caret para navegación"""
        return {
            'account.move': [
                {'name': _("View Journal Entry"), 'action': 'caret_option_open_record_form'},
            ],
            'account.move.line': [
                {'name': _("View Journal Entry"), 'action': 'caret_option_open_record_form', 'action_param': 'move_id'},
            ],
        }
