# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""
Handlers para Reportes de Auditoría Contable Colombia

Este módulo contiene los handlers para los siguientes reportes:
1. Auditoría de Consecutivos - Detecta saltos en la numeración de documentos
2. Documentos Modificados - Muestra documentos que han sido editados después de su creación
3. Conteo Mensual de Documentos - Resumen mensual de documentos por diario
4. Auditoría de Cuentas Bancarias - Análisis de pagos por cuenta bancaria de terceros
"""

from odoo import models, fields, api, _
from odoo.tools import SQL, get_lang
from odoo.tools.misc import format_date
from collections import defaultdict
from datetime import datetime
import re
import logging

_logger = logging.getLogger(__name__)


# =============================================================================
# 1. AUDITORÍA DE CONSECUTIVOS
# =============================================================================

class AccountAuditSequencesReportHandler(models.AbstractModel):
    """
    Handler para el reporte de Auditoría de Consecutivos.

    Detecta saltos en la numeración de documentos contables por diario,
    identificando:
    - Consecutivos faltantes
    - Duplicados
    - Saltos en la secuencia
    """
    _name = 'account.audit.sequences.report.handler'
    _inherit = 'account.report.custom.handler'
    _description = 'Auditoría de Consecutivos - Handler'

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        """Genera las líneas del reporte de auditoría de consecutivos."""
        lines = []

        try:
            # Obtener datos de secuencias por diario con asientos
            journal_data_list = self._get_sequence_data_with_entries(report, options)

            if not journal_data_list:
                return [(0, self._get_no_data_line(report, options))]

            total_gaps = 0
            total_entries = 0

            for journal_data in journal_data_list:
                journal_id = journal_data['journal_id']
                journal_name = journal_data['journal_name']
                entries = journal_data['entries']
                gaps = journal_data['gaps']
                gap_count = len(gaps)
                total_gaps += gap_count

                # Línea de encabezado del diario
                journal_line_id = report._get_generic_line_id(
                    'account.journal', journal_id, markup=f'seq_journal_{journal_id}'
                )
                is_unfolded = options.get('unfold_all') or journal_line_id in options.get('unfolded_lines', [])

                lines.append({
                    'id': journal_line_id,
                    'name': journal_name,
                    'level': 0,
                    'unfoldable': True,
                    'unfolded': is_unfolded,
                    'expand_function': '_report_expand_unfoldable_line_seq_audit_journal',
                    'class': 'o_account_reports_level_total' + (' text-danger' if gap_count > 0 else ''),
                    'columns': [
                        {'name': len(entries), 'class': 'number'},
                        {'name': entries[0]['name'] if entries else '', 'class': ''},
                        {'name': entries[-1]['name'] if entries else '', 'class': ''},
                        {'name': f'{gap_count} saltos' if gap_count > 0 else 'OK',
                         'class': 'text-danger fw-bold' if gap_count > 0 else 'text-success'},
                    ],
                })

                # Solo mostrar asientos si el diario está desplegado
                if not is_unfolded:
                    continue

                # Crear set de números donde hay salto DESPUÉS de ese asiento
                gap_after_numbers = set()
                for gap in gaps:
                    # El salto está después del documento anterior
                    prev_numbers = re.findall(r'\d+', gap['previous_doc'])
                    if prev_numbers:
                        gap_after_numbers.add(int(prev_numbers[-1]))

                for i, entry in enumerate(entries):
                    total_entries += 1
                    entry_number = None
                    numbers = re.findall(r'\d+', entry['name'])
                    if numbers:
                        entry_number = int(numbers[-1])

                    # Verificar si hay un salto después de este asiento
                    has_gap_after = entry_number in gap_after_numbers

                    # Línea del asiento
                    entry_line = {
                        'id': report._get_generic_line_id(
                            'account.move', entry['move_id'],
                            parent_line_id=journal_line_id,
                            markup=f'seq_entry_{entry["move_id"]}'
                        ),
                        'name': f"  {entry['name']}",
                        'level': 2,
                        'parent_id': journal_line_id,
                        'caret_options': 'account.move',
                        'class': 'border-bottom border-danger' if has_gap_after else '',
                        'columns': [
                            {'name': format_date(self.env, entry['date']), 'class': ''},
                            {'name': entry['partner_name'] or '', 'class': 'text-muted'},
                            {'name': entry['amount_total'], 'class': 'number'},
                            {'name': '⚠️ SALTO' if has_gap_after else '',
                             'class': 'text-danger fw-bold' if has_gap_after else ''},
                        ],
                    }
                    lines.append(entry_line)

                    # Si hay salto, agregar línea de alerta
                    if has_gap_after:
                        gap_info = next((g for g in gaps if g['previous_doc'] == entry['name']), None)
                        if gap_info:
                            lines.append({
                                'id': report._get_generic_line_id(
                                    None, None,
                                    markup=f'seq_gap_alert_{entry["move_id"]}',
                                    parent_line_id=journal_line_id
                                ),
                                'name': f"    ⛔ ALERTA: {gap_info['gap_size']} documentos faltantes (desde #{gap_info['expected_number']} hasta #{gap_info['found_number'] - 1})",
                                'level': 3,
                                'parent_id': journal_line_id,
                                'class': 'text-white bg-danger fw-bold py-1',
                                'columns': [
                                    {'name': '', 'class': ''},
                                    {'name': '', 'class': ''},
                                    {'name': '', 'class': ''},
                                    {'name': '', 'class': ''},
                                ],
                            })

            # Línea de resumen
            lines.append(self._get_summary_line(report, options, total_gaps, total_entries))

        except Exception as e:
            _logger.error(f"Error en auditoría de consecutivos: {str(e)}")
            import traceback
            _logger.error(traceback.format_exc())
            lines = [self._get_error_line(report, options, str(e))]

        return [(0, line) for line in lines]

    
    def _report_expand_unfoldable_line_seq_audit_journal(self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None):
        """Expande una linea de diario para mostrar sus asientos."""
        report = self.env['account.report'].browse(options['report_id'])
        lines = []
        
        # Extraer journal_id del line_dict_id
        model_info = report._get_model_info_from_id(line_dict_id)
        if not model_info or model_info[0] != 'account.journal':
            return {'lines': [], 'offset_increment': 0, 'has_more': False}
        
        journal_id = model_info[1]
        
        # Obtener datos de secuencia
        sequence_data = self._get_sequence_data_with_entries(report, options)
        
        for journal_data in sequence_data:
            if journal_data['journal_id'] != journal_id:
                continue
            
            entries = journal_data['entries']
            gaps = journal_data['gaps']
            
            # Crear set de numeros donde hay salto
            gap_after_numbers = set()
            for gap in gaps:
                prev_numbers = re.findall(r'\d+', gap['previous_doc'])
                if prev_numbers:
                    gap_after_numbers.add(int(prev_numbers[-1]))
            
            for entry in entries:
                entry_numbers = re.findall(r'\d+', entry['name'])
                entry_num = int(entry_numbers[-1]) if entry_numbers else 0
                has_gap_after = entry_num in gap_after_numbers
                
                lines.append({
                    'id': report._get_generic_line_id(
                        'account.move', entry['move_id'],
                        markup=f'seq_entry_{entry["move_id"]}',
                        parent_line_id=line_dict_id
                    ),
                    'name': entry['name'],
                    'level': 2,
                    'parent_id': line_dict_id,
                    'class': 'text-danger' if has_gap_after else '',
                    'columns': [
                        {'name': '', 'class': ''},
                        {'name': entry['date'], 'class': ''},
                        {'name': entry.get('partner_name', ''), 'class': ''},
                        {'name': '', 'class': ''},
                    ],
                })
                
                # Linea de alerta si hay salto
                if has_gap_after:
                    gap_info = next((g for g in gaps if g['previous_doc'] == entry['name']), None)
                    if gap_info:
                        lines.append({
                            'id': report._get_generic_line_id(
                                None, None,
                                markup=f'seq_gap_alert_{entry["move_id"]}',
                                parent_line_id=line_dict_id
                            ),
                            'name': f"    ? ALERTA: {gap_info['gap_size']} documentos faltantes (desde #{gap_info['expected_number']} hasta #{gap_info['found_number'] - 1})",
                            'level': 3,
                            'parent_id': line_dict_id,
                            'class': 'text-white bg-danger fw-bold py-1',
                            'columns': [
                                {'name': '', 'class': ''},
                                {'name': '', 'class': ''},
                                {'name': '', 'class': ''},
                                {'name': '', 'class': ''},
                            ],
                        })
            break
        
        return {'lines': lines, 'offset_increment': len(lines), 'has_more': False}

    def _get_sequence_data_with_entries(self, report, options):
        """Obtiene los datos de secuencias con todos los asientos agrupados por diario."""
        date_from = options['date']['date_from']
        date_to = options['date']['date_to']

        # Obtener diarios seleccionados
        journal_ids = [j['id'] for j in options.get('journals', []) if j.get('selected', True)]

        query = """
            SELECT
                aj.id as journal_id,
                COALESCE(aj.name->>'es_CO', aj.name->>'en_US', aj.code) as journal_name,
                aj.code as journal_code,
                am.name as move_name,
                am.date as move_date,
                am.id as move_id,
                am.amount_total,
                rp.name as partner_name
            FROM account_move am
            JOIN account_journal aj ON aj.id = am.journal_id
            LEFT JOIN res_partner rp ON rp.id = am.partner_id
            WHERE am.date BETWEEN %s AND %s
            AND am.state = 'posted'
        """
        params = [date_from, date_to]

        if journal_ids:
            query += " AND am.journal_id IN %s"
            params.append(tuple(journal_ids))

        query += " ORDER BY aj.id, am.name"

        self._cr.execute(query, params)
        results = self._cr.dictfetchall()

        # Agrupar por diario
        journals = defaultdict(lambda: {'entries': [], 'journal_name': '', 'journal_id': None})
        for row in results:
            journal_id = row['journal_id']
            journals[journal_id]['journal_id'] = journal_id
            journals[journal_id]['journal_name'] = row['journal_name']
            journals[journal_id]['entries'].append({
                'name': row['move_name'],
                'date': row['move_date'],
                'move_id': row['move_id'],
                'amount_total': row['amount_total'] or 0,
                'partner_name': row['partner_name'],
            })

        # Analizar secuencias y detectar saltos
        journal_data_list = []
        for journal_id, data in journals.items():
            if not data['entries']:
                continue

            gaps = self._detect_sequence_gaps(data['entries'])

            journal_data_list.append({
                'journal_id': journal_id,
                'journal_name': data['journal_name'],
                'entries': data['entries'],
                'gaps': gaps,
            })

        # Ordenar por nombre de diario
        journal_data_list.sort(key=lambda x: x['journal_name'])

        return journal_data_list

    def _get_sequence_data(self, report, options):
        """Obtiene los datos de secuencias y detecta saltos (método legacy)."""
        date_from = options['date']['date_from']
        date_to = options['date']['date_to']

        # Obtener diarios seleccionados
        journal_ids = [j['id'] for j in options.get('journals', []) if j.get('selected', True)]

        query = """
            SELECT
                aj.id as journal_id,
                COALESCE(aj.name->>'es_CO', aj.name->>'en_US', aj.code) as journal_name,
                aj.code as journal_code,
                am.name as move_name,
                am.date as move_date,
                am.id as move_id
            FROM account_move am
            JOIN account_journal aj ON aj.id = am.journal_id
            WHERE am.date BETWEEN %s AND %s
            AND am.state = 'posted'
        """
        params = [date_from, date_to]

        if journal_ids:
            query += " AND am.journal_id IN %s"
            params.append(tuple(journal_ids))

        query += " ORDER BY aj.id, am.name"

        self._cr.execute(query, params)
        results = self._cr.dictfetchall()

        # Agrupar por diario
        journals = defaultdict(list)
        for row in results:
            journals[row['journal_id']].append({
                'name': row['move_name'],
                'date': row['move_date'],
                'move_id': row['move_id'],
                'journal_name': row['journal_name'],
            })

        # Analizar secuencias
        sequence_data = []
        for journal_id, moves in journals.items():
            if not moves:
                continue

            journal_name = moves[0]['journal_name']
            gaps = self._detect_sequence_gaps(moves)

            # Extraer prefijo del primer documento
            prefix = self._extract_prefix(moves[0]['name']) if moves else ''

            if gaps:
                sequence_data.append({
                    'journal_id': journal_id,
                    'journal_name': journal_name,
                    'prefix': prefix,
                    'gaps': gaps,
                })

        return sequence_data

    def _extract_prefix(self, move_name):
        """Extrae el prefijo del nombre del documento."""
        if not move_name:
            return ''
        # Buscar patrón de prefijo (letras seguidas de /)
        match = re.match(r'^([A-Z]+/\d+/)', move_name)
        if match:
            return match.group(1)
        # Si no hay patrón estándar, tomar todo antes del último número
        parts = move_name.rsplit('/', 1)
        if len(parts) > 1:
            return parts[0] + '/'
        return ''

    def _detect_sequence_gaps(self, moves):
        """Detecta saltos en la secuencia de documentos."""
        gaps = []

        if len(moves) < 2:
            return gaps

        # Extraer números de secuencia
        sequences = []
        for move in moves:
            # Extraer el último número del nombre
            numbers = re.findall(r'\d+', move['name'])
            if numbers:
                seq_num = int(numbers[-1])
                sequences.append({
                    'number': seq_num,
                    'name': move['name'],
                    'date': move['date'],
                })

        # Ordenar por número
        sequences.sort(key=lambda x: x['number'])

        # Detectar saltos
        for i in range(1, len(sequences)):
            expected = sequences[i-1]['number'] + 1
            found = sequences[i]['number']

            if found != expected and found > expected:
                gaps.append({
                    'expected_number': expected,
                    'found_number': found,
                    'previous_doc': sequences[i-1]['name'],
                    'next_doc': sequences[i]['name'],
                    'gap_size': found - expected,
                })

        return gaps

    def _get_journal_header_line(self, report, options, journal_name, prefix, gap_count):
        """Genera línea de encabezado para un diario."""
        safe_journal = re.sub(r'[^a-zA-Z0-9]', '_', journal_name or 'unknown')
        return {
            'id': report._get_generic_line_id(None, None, markup=f'seq_journal_{safe_journal}'),
            'name': journal_name,
            'level': 1,
            'unfoldable': True,
            'unfolded': options.get('unfold_all', False),
            'columns': [
                {'name': prefix},
                {'name': ''},
                {'name': ''},
                {'name': 'Con saltos' if gap_count > 0 else 'OK',
                 'class': 'text-danger' if gap_count > 0 else 'text-success'},
                {'name': gap_count},
            ],
        }

    def _get_gap_detail_line(self, report, options, journal_name, gap):
        """Genera línea de detalle para un salto de secuencia."""
        safe_journal = re.sub(r'[^a-zA-Z0-9]', '_', journal_name or 'unknown')
        parent_id = report._get_generic_line_id(None, None, markup=f'seq_journal_{safe_journal}')
        return {
            'id': report._get_generic_line_id(None, None, markup=f'seq_gap_{safe_journal}_{gap["expected_number"]}', parent_line_id=parent_id),
            'name': f"Salto: {gap['previous_doc']} → {gap['next_doc']}",
            'level': 2,
            'parent_id': parent_id,
            'columns': [
                {'name': ''},
                {'name': gap['expected_number']},
                {'name': gap['found_number']},
                {'name': f"Faltan {gap['gap_size']} documentos", 'class': 'text-danger'},
                {'name': gap['gap_size']},
            ],
        }

    def _get_summary_line(self, report, options, total_gaps, total_entries=0):
        """Genera línea de resumen."""
        return {
            'id': report._get_generic_line_id(None, None, markup='seq_summary_total'),
            'name': 'RESUMEN AUDITORÍA DE CONSECUTIVOS',
            'level': 0,
            'class': 'o_account_reports_level_total border-top border-2',
            'columns': [
                {'name': f'{total_entries} asientos', 'class': 'fw-bold'},
                {'name': '', 'class': ''},
                {'name': '', 'class': ''},
                {'name': f'{total_gaps} saltos detectados' if total_gaps > 0 else '✓ Sin saltos',
                 'class': 'text-danger fw-bold' if total_gaps > 0 else 'text-success fw-bold'},
            ],
        }

    def _get_no_data_line(self, report, options):
        """Línea cuando no hay datos."""
        return {
            'id': report._get_generic_line_id(None, None, markup='seq_no_data'),
            'name': 'No se encontraron documentos en el período seleccionado',
            'level': 0,
            'columns': [{'name': ''} for _ in range(5)],
        }

    def _get_error_line(self, report, options, error_msg):
        """Línea de error."""
        return {
            'id': report._get_generic_line_id(None, None, markup='seq_error'),
            'name': f'Error: {error_msg}',
            'level': 0,
            'class': 'text-danger',
            'columns': [{'name': ''} for _ in range(5)],
        }


# =============================================================================
# 2. DOCUMENTOS MODIFICADOS
# =============================================================================

class AccountAuditModifiedEntriesReportHandler(models.AbstractModel):
    """
    Handler para el reporte de Documentos Modificados.

    Muestra documentos contables que han sido modificados después de su creación,
    incluyendo información sobre quién realizó la modificación.
    """
    _name = 'account.audit.modified.entries.report.handler'
    _inherit = 'account.report.custom.handler'
    _description = 'Documentos Modificados - Handler'

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        """Genera las líneas del reporte de documentos modificados."""
        lines = []

        try:
            modified_docs = self._get_modified_documents(report, options)

            if not modified_docs:
                return [(0, self._get_no_data_line(report, options))]

            for doc in modified_docs:
                lines.append(self._get_document_line(report, options, doc))

            # Línea de total
            lines.append(self._get_total_line(report, options, len(modified_docs)))

        except Exception as e:
            _logger.error(f"Error en reporte de documentos modificados: {str(e)}")
            lines = [self._get_error_line(report, options, str(e))]

        return [(0, line) for line in lines]

    def _get_modified_documents(self, report, options):
        """Obtiene documentos que fueron modificados después de su creación."""
        date_from = options['date']['date_from']
        date_to = options['date']['date_to']

        # Obtener diarios seleccionados
        journal_ids = [j['id'] for j in options.get('journals', []) if j.get('selected', True)]

        query = """
            SELECT
                am.id,
                am.name as move_name,
                am.date as move_date,
                COALESCE(aj.name->>'es_CO', aj.name->>'en_US', aj.code) as journal_name,
                rp.name as partner_name,
                am.amount_total,
                am.create_date,
                am.write_date,
                creator.name as create_user,
                writer.name as write_user
            FROM account_move am
            JOIN account_journal aj ON aj.id = am.journal_id
            LEFT JOIN res_partner rp ON rp.id = am.partner_id
            LEFT JOIN res_users cu ON cu.id = am.create_uid
            LEFT JOIN res_partner creator ON creator.id = cu.partner_id
            LEFT JOIN res_users wu ON wu.id = am.write_uid
            LEFT JOIN res_partner writer ON writer.id = wu.partner_id
            WHERE am.date BETWEEN %s AND %s
            AND am.state = 'posted'
            AND am.write_date > am.create_date + interval '1 minute'
        """
        params = [date_from, date_to]

        if journal_ids:
            query += " AND am.journal_id IN %s"
            params.append(tuple(journal_ids))

        query += " ORDER BY am.write_date DESC"

        self._cr.execute(query, params)
        return self._cr.dictfetchall()

    def _get_document_line(self, report, options, doc):
        """Genera línea para un documento modificado."""
        return {
            'id': report._get_generic_line_id('account.move', doc['id']),
            'name': doc['move_name'],
            'level': 2,
            'caret_options': 'account.move',
            'columns': [
                {'name': format_date(self.env, doc['move_date'])},
                {'name': doc['move_name']},
                {'name': doc['journal_name']},
                {'name': doc['partner_name'] or ''},
                {'name': doc['amount_total'], 'class': 'number'},
                {'name': doc['create_date'].strftime('%Y-%m-%d %H:%M') if doc['create_date'] else ''},
                {'name': doc['write_date'].strftime('%Y-%m-%d %H:%M') if doc['write_date'] else ''},
                {'name': doc['write_user'] or ''},
            ],
        }

    def _get_total_line(self, report, options, count):
        """Genera línea de total."""
        return {
            'id': report._get_generic_line_id(None, None, markup='mod_total'),
            'name': f'TOTAL: {count} documentos modificados',
            'level': 0,
            'class': 'o_account_reports_level_total',
            'columns': [{'name': ''} for _ in range(7)],
        }

    def _get_no_data_line(self, report, options):
        """Línea cuando no hay datos."""
        return {
            'id': report._get_generic_line_id(None, None, markup='mod_no_data'),
            'name': 'No se encontraron documentos modificados en el período',
            'level': 0,
            'columns': [{'name': ''} for _ in range(7)],
        }

    def _get_error_line(self, report, options, error_msg):
        """Línea de error."""
        return {
            'id': report._get_generic_line_id(None, None, markup='mod_error'),
            'name': f'Error: {error_msg}',
            'level': 0,
            'class': 'text-danger',
            'columns': [{'name': ''} for _ in range(7)],
        }


# =============================================================================
# 3. CONTEO MENSUAL DE DOCUMENTOS
# =============================================================================

class AccountAuditMonthlyCountReportHandler(models.AbstractModel):
    """
    Handler para el reporte de Conteo Mensual de Documentos.

    Genera un resumen mensual de documentos por diario, incluyendo:
    - Cantidad de documentos
    - Primer y último consecutivo del mes
    - Total monetario
    """
    _name = 'account.audit.monthly.count.report.handler'
    _inherit = 'account.report.custom.handler'
    _description = 'Conteo Mensual de Documentos - Handler'

    MONTH_NAMES = {
        1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril',
        5: 'Mayo', 6: 'Junio', 7: 'Julio', 8: 'Agosto',
        9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'
    }

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        """Genera las líneas del reporte de conteo mensual con drill-down a asientos."""
        lines = []

        try:
            monthly_data = self._get_monthly_count_data_with_entries(report, options)

            if not monthly_data:
                return [(0, self._get_no_data_line(report, options))]

            grand_total_count = 0
            grand_total_amount = 0

            for journal_data in monthly_data:
                journal_id = journal_data['journal_id']
                journal_name = journal_data['journal_name']
                months = journal_data['months']

                # Calcular totales del diario
                journal_total = sum(m['doc_count'] for m in months.values())
                journal_amount = sum(m['total_amount'] for m in months.values())

                # Línea de encabezado del diario
                journal_line_id = report._get_generic_line_id(
                    'account.journal', journal_id, markup=f'mc_journal_{journal_id}'
                )
                lines.append({
                    'id': journal_line_id,
                    'name': journal_name,
                    'level': 0,
                    'unfoldable': True,
                    'unfolded': options.get('unfold_all', False) or journal_line_id in options.get('unfolded_lines', []),
                    'expand_function': '_report_expand_unfoldable_line_monthly_count_journal',
                    'class': 'o_account_reports_level_total',
                    'columns': [
                        {'name': '', 'class': ''},
                        {'name': journal_total, 'class': 'number fw-bold'},
                        {'name': '', 'class': ''},
                        {'name': '', 'class': ''},
                        {'name': journal_amount, 'class': 'number fw-bold'},
                    ],
                })

                # Si el diario está desplegado, mostrar los meses
                if options.get('unfold_all') or journal_line_id in options.get('unfolded_lines', []):
                    for month_key in sorted(months.keys()):
                        month_data = months[month_key]
                        grand_total_count += month_data['doc_count']
                        grand_total_amount += month_data['total_amount']

                        # Línea del mes
                        month_line_id = report._get_generic_line_id(
                            None, None,
                            markup=f'mc_month_{journal_id}_{month_data["year"]}_{month_data["month"]}',
                            parent_line_id=journal_line_id
                        )
                        lines.append({
                            'id': month_line_id,
                            'name': month_data['month_name'],
                            'level': 1,
                            'parent_id': journal_line_id,
                            'unfoldable': True,
                            'unfolded': options.get('unfold_all') or month_line_id in options.get('unfolded_lines', []),
                            'expand_function': '_report_expand_unfoldable_line_monthly_count_month',
                            'class': '',
                            'columns': [
                                {'name': '', 'class': ''},
                                {'name': month_data['doc_count'], 'class': 'number'},
                                {'name': month_data['first_sequence'], 'class': ''},
                                {'name': month_data['last_sequence'], 'class': ''},
                                {'name': month_data['total_amount'], 'class': 'number'},
                            ],
                        })

                        # Si el mes está desplegado, mostrar los asientos
                        if options.get('unfold_all') or month_line_id in options.get('unfolded_lines', []):
                            for entry in month_data.get('entries', []):
                                lines.append({
                                    'id': report._get_generic_line_id(
                                        'account.move', entry['move_id'],
                                        parent_line_id=month_line_id,
                                        markup=f'mc_entry_{entry["move_id"]}'
                                    ),
                                    'name': entry['name'],
                                    'level': 3,
                                    'parent_id': month_line_id,
                                    'caret_options': 'account.move',
                                    'class': '',
                                    'columns': [
                                        {'name': format_date(self.env, entry['date']), 'class': ''},
                                        {'name': '', 'class': ''},
                                        {'name': entry['partner_name'] or '', 'class': 'text-muted'},
                                        {'name': '', 'class': ''},
                                        {'name': entry['amount_total'], 'class': 'number'},
                                    ],
                                })

            # Línea de gran total
            lines.append(self._get_grand_total_line(report, options, grand_total_count, grand_total_amount))

        except Exception as e:
            _logger.error(f"Error en conteo mensual: {str(e)}")
            import traceback
            _logger.error(traceback.format_exc())
            lines = [self._get_error_line(report, options, str(e))]

        return [(0, line) for line in lines]


    def _report_expand_unfoldable_line_monthly_count_journal(self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None):
        """Expande un diario para mostrar sus meses."""
        report = self.env['account.report'].browse(options['report_id'])
        lines = []
        
        # Extraer journal_id del markup
        import re
        match = re.search(r'mc_journal_(\d+)', line_dict_id)
        if not match:
            return {'lines': [], 'offset_increment': 0, 'has_more': False}
        
        journal_id = int(match.group(1))
        monthly_data = self._get_monthly_count_data_with_entries(report, options)
        
        for journal_data in monthly_data:
            if journal_data['journal_id'] != journal_id:
                continue
            
            months = journal_data['months']
            for month_key in sorted(months.keys()):
                month_data = months[month_key]
                month_line_id = report._get_generic_line_id(
                    None, None,
                    markup=f'mc_month_{journal_id}_{month_data["year"]}_{month_data["month"]}',
                    parent_line_id=line_dict_id
                )
                lines.append({
                    'id': month_line_id,
                    'name': month_data['month_name'],
                    'level': 1,
                    'parent_id': line_dict_id,
                    'unfoldable': True,
                    'unfolded': False,
                    'expand_function': '_report_expand_unfoldable_line_monthly_count_month',
                    'columns': [
                        {'name': '', 'class': ''},
                        {'name': month_data['doc_count'], 'class': 'number'},
                        {'name': month_data['first_sequence'], 'class': ''},
                        {'name': month_data['last_sequence'], 'class': ''},
                        {'name': month_data['total_amount'], 'class': 'number'},
                    ],
                })
            break
        
        return {'lines': lines, 'offset_increment': len(lines), 'has_more': False}

    def _report_expand_unfoldable_line_monthly_count_month(self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None):
        """Expande un mes para mostrar sus asientos."""
        from odoo.tools.misc import format_date
        report = self.env['account.report'].browse(options['report_id'])
        lines = []
        
        # Extraer journal_id, year, month del markup
        import re
        match = re.search(r'mc_month_(\d+)_(\d+)_(\d+)', line_dict_id)
        if not match:
            return {'lines': [], 'offset_increment': 0, 'has_more': False}
        
        journal_id = int(match.group(1))
        year = int(match.group(2))
        month = int(match.group(3))
        month_key = f'{year}_{month:02d}'
        
        monthly_data = self._get_monthly_count_data_with_entries(report, options)
        
        for journal_data in monthly_data:
            if journal_data['journal_id'] != journal_id:
                continue
            
            months = journal_data['months']
            if month_key not in months:
                continue
            
            month_data = months[month_key]
            for entry in month_data.get('entries', []):
                lines.append({
                    'id': report._get_generic_line_id(
                        'account.move', entry['move_id'],
                        parent_line_id=line_dict_id,
                        markup=f'mc_entry_{entry["move_id"]}'
                    ),
                    'name': entry['name'],
                    'level': 3,
                    'parent_id': line_dict_id,
                    'caret_options': 'account.move',
                    'columns': [
                        {'name': format_date(self.env, entry['date']), 'class': ''},
                        {'name': '', 'class': ''},
                        {'name': entry['partner_name'] or '', 'class': 'text-muted'},
                        {'name': '', 'class': ''},
                        {'name': entry['amount_total'], 'class': 'number'},
                    ],
                })
            break
        
        return {'lines': lines, 'offset_increment': len(lines), 'has_more': False}

    def _get_monthly_count_data(self, report, options):
        """Obtiene datos de conteo mensual por diario."""
        date_from = options['date']['date_from']
        date_to = options['date']['date_to']

        journal_ids = [j['id'] for j in options.get('journals', []) if j.get('selected', True)]

        query = """
            SELECT
                COALESCE(aj.name->>'es_CO', aj.name->>'en_US', aj.code) as journal_name,
                EXTRACT(YEAR FROM am.date) as year,
                EXTRACT(MONTH FROM am.date) as month,
                COUNT(*) as doc_count,
                MIN(am.name) as first_sequence,
                MAX(am.name) as last_sequence,
                SUM(am.amount_total) as total_amount
            FROM account_move am
            JOIN account_journal aj ON aj.id = am.journal_id
            WHERE am.date BETWEEN %s AND %s
            AND am.state = 'posted'
        """
        params = [date_from, date_to]

        if journal_ids:
            query += " AND am.journal_id IN %s"
            params.append(tuple(journal_ids))

        query += """
            GROUP BY aj.name, aj.code, EXTRACT(YEAR FROM am.date), EXTRACT(MONTH FROM am.date)
            ORDER BY journal_name, year, month
        """

        self._cr.execute(query, params)
        results = self._cr.dictfetchall()

        # Organizar por diario y mes
        monthly_data = defaultdict(dict)
        for row in results:
            journal_name = row['journal_name']
            month_key = (int(row['year']), int(row['month']))

            monthly_data[journal_name][month_key] = {
                'year': int(row['year']),
                'month': int(row['month']),
                'month_name': f"{self.MONTH_NAMES[int(row['month'])]} {int(row['year'])}",
                'doc_count': row['doc_count'],
                'first_sequence': row['first_sequence'],
                'last_sequence': row['last_sequence'],
                'total_amount': row['total_amount'] or 0,
            }

        return dict(monthly_data)

    def _get_monthly_count_data_with_entries(self, report, options):
        """Obtiene datos de conteo mensual por diario con los asientos individuales."""
        date_from = options['date']['date_from']
        date_to = options['date']['date_to']

        journal_ids = [j['id'] for j in options.get('journals', []) if j.get('selected', True)]

        # Query para obtener todos los asientos con su información
        query = """
            SELECT
                aj.id as journal_id,
                COALESCE(aj.name->>'es_CO', aj.name->>'en_US', aj.code) as journal_name,
                am.id as move_id,
                am.name,
                am.date,
                am.amount_total,
                rp.name as partner_name,
                EXTRACT(YEAR FROM am.date) as year,
                EXTRACT(MONTH FROM am.date) as month
            FROM account_move am
            JOIN account_journal aj ON aj.id = am.journal_id
            LEFT JOIN res_partner rp ON rp.id = am.partner_id
            WHERE am.date BETWEEN %s AND %s
            AND am.state = 'posted'
        """
        params = [date_from, date_to]

        if journal_ids:
            query += " AND am.journal_id IN %s"
            params.append(tuple(journal_ids))

        query += " ORDER BY aj.id, am.date, am.name"

        self._cr.execute(query, params)
        results = self._cr.dictfetchall()

        # Organizar por diario y mes
        journals = defaultdict(lambda: {
            'journal_id': None,
            'journal_name': '',
            'months': defaultdict(lambda: {
                'year': 0,
                'month': 0,
                'month_name': '',
                'doc_count': 0,
                'first_sequence': '',
                'last_sequence': '',
                'total_amount': 0,
                'entries': []
            })
        })

        for row in results:
            journal_id = row['journal_id']
            year = int(row['year'])
            month = int(row['month'])
            month_key = (year, month)

            if journals[journal_id]['journal_id'] is None:
                journals[journal_id]['journal_id'] = journal_id
                journals[journal_id]['journal_name'] = row['journal_name']

            month_data = journals[journal_id]['months'][month_key]
            month_data['year'] = year
            month_data['month'] = month
            month_data['month_name'] = f"{self.MONTH_NAMES[month]} {year}"
            month_data['doc_count'] += 1
            month_data['total_amount'] += row['amount_total'] or 0

            # Actualizar primer y último consecutivo
            if not month_data['first_sequence']:
                month_data['first_sequence'] = row['name']
            month_data['last_sequence'] = row['name']

            # Agregar entrada
            month_data['entries'].append({
                'move_id': row['move_id'],
                'name': row['name'],
                'date': row['date'],
                'amount_total': row['amount_total'] or 0,
                'partner_name': row['partner_name'],
            })

        # Convertir a lista ordenada
        result = []
        for journal_id in sorted(journals.keys()):
            journal_data = journals[journal_id]
            result.append({
                'journal_id': journal_data['journal_id'],
                'journal_name': journal_data['journal_name'],
                'months': dict(journal_data['months']),
            })

        # Ordenar por nombre de diario
        result.sort(key=lambda x: x['journal_name'])

        return result

    def _get_journal_header_line(self, report, options, journal_name, total_count, total_amount):
        """Genera línea de encabezado del diario."""
        safe_journal = re.sub(r'[^a-zA-Z0-9]', '_', journal_name or 'unknown')
        return {
            'id': report._get_generic_line_id(None, None, markup=f'count_journal_{safe_journal}'),
            'name': journal_name,
            'level': 1,
            'unfoldable': True,
            'unfolded': options.get('unfold_all', False),
            'columns': [
                {'name': ''},
                {'name': total_count},
                {'name': ''},
                {'name': ''},
                {'name': total_amount, 'class': 'number'},
            ],
        }

    def _get_month_line(self, report, options, journal_name, month_data):
        """Genera línea para un mes específico."""
        safe_journal = re.sub(r'[^a-zA-Z0-9]', '_', journal_name or 'unknown')
        parent_id = report._get_generic_line_id(None, None, markup=f'count_journal_{safe_journal}')
        return {
            'id': report._get_generic_line_id(None, None, markup=f'count_month_{safe_journal}_{month_data["year"]}_{month_data["month"]}', parent_line_id=parent_id),
            'name': '',
            'level': 2,
            'parent_id': parent_id,
            'columns': [
                {'name': month_data['month_name']},
                {'name': month_data['doc_count']},
                {'name': month_data['first_sequence']},
                {'name': month_data['last_sequence']},
                {'name': month_data['total_amount'], 'class': 'number'},
            ],
        }

    def _get_grand_total_line(self, report, options, total_count, total_amount):
        """Genera línea de gran total."""
        return {
            'id': report._get_generic_line_id(None, None, markup='count_total'),
            'name': 'TOTAL GENERAL',
            'level': 0,
            'class': 'o_account_reports_level_total',
            'columns': [
                {'name': ''},
                {'name': total_count},
                {'name': ''},
                {'name': ''},
                {'name': total_amount, 'class': 'number'},
            ],
        }

    def _get_no_data_line(self, report, options):
        """Línea cuando no hay datos."""
        return {
            'id': report._get_generic_line_id(None, None, markup='count_no_data'),
            'name': 'No se encontraron documentos en el período seleccionado',
            'level': 0,
            'columns': [{'name': ''} for _ in range(5)],
        }

    def _get_error_line(self, report, options, error_msg):
        """Línea de error."""
        return {
            'id': report._get_generic_line_id(None, None, markup='count_error'),
            'name': f'Error: {error_msg}',
            'level': 0,
            'class': 'text-danger',
            'columns': [{'name': ''} for _ in range(5)],
        }


# =============================================================================
# 4. AUDITORÍA DE CUENTAS BANCARIAS
# =============================================================================

class AccountAuditBankAccountsReportHandler(models.AbstractModel):
    """
    Handler para el reporte de Auditoría de Cuentas Bancarias de Terceros.

    Analiza las cuentas bancarias registradas para terceros y los pagos
    realizados a cada cuenta.
    """
    _name = 'account.audit.bank.accounts.report.handler'
    _inherit = 'account.report.custom.handler'
    _description = 'Auditoría de Cuentas Bancarias - Handler'

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        """Genera las líneas del reporte de cuentas bancarias."""
        lines = []

        try:
            bank_data = self._get_bank_account_data(report, options)

            if not bank_data:
                return [(0, self._get_no_data_line(report, options))]

            total_payments = 0
            total_amount = 0

            for partner_data in bank_data:
                # Línea del tercero
                lines.append(self._get_partner_line(report, options, partner_data))

                # Líneas de cada cuenta bancaria
                for bank_account in partner_data['bank_accounts']:
                    lines.append(self._get_bank_account_line(
                        report, options, partner_data['partner_id'], bank_account
                    ))
                    total_payments += bank_account['payment_count']
                    total_amount += bank_account['total_paid']

            # Línea de total
            lines.append(self._get_total_line(report, options, total_payments, total_amount))

        except Exception as e:
            _logger.error(f"Error en auditoría de cuentas bancarias: {str(e)}")
            lines = [self._get_error_line(report, options, str(e))]

        return [(0, line) for line in lines]

    def _get_bank_account_data(self, report, options):
        """Obtiene datos de cuentas bancarias y pagos por tercero."""
        date_from = options['date']['date_from']
        date_to = options['date']['date_to']

        # Query para obtener pagos agrupados por tercero y cuenta bancaria
        query = """
            SELECT
                rp.id as partner_id,
                rp.name as partner_name,
                rp.vat as partner_vat,
                rb.name as bank_name,
                rpb.acc_number as bank_account,
                rpb.acc_type as account_type,
                COUNT(ap.id) as payment_count,
                SUM(ap.amount) as total_paid
            FROM account_payment ap
            JOIN res_partner rp ON rp.id = ap.partner_id
            LEFT JOIN res_partner_bank rpb ON rpb.id = ap.partner_bank_id
            LEFT JOIN res_bank rb ON rb.id = rpb.bank_id
            WHERE ap.date BETWEEN %s AND %s
            AND ap.state = 'posted'
            AND ap.payment_type = 'outbound'
            GROUP BY rp.id, rp.name, rp.vat, rb.name, rpb.acc_number, rpb.acc_type
            ORDER BY rp.name, rb.name
        """

        self._cr.execute(query, [date_from, date_to])
        results = self._cr.dictfetchall()

        # Organizar por tercero
        partners = defaultdict(lambda: {'bank_accounts': []})
        for row in results:
            partner_id = row['partner_id']
            if 'partner_name' not in partners[partner_id]:
                partners[partner_id].update({
                    'partner_id': partner_id,
                    'partner_name': row['partner_name'],
                    'partner_vat': row['partner_vat'],
                })

            partners[partner_id]['bank_accounts'].append({
                'bank_name': row['bank_name'] or 'Sin banco',
                'bank_account': row['bank_account'] or 'Sin cuenta',
                'account_type': row['account_type'] or '',
                'payment_count': row['payment_count'],
                'total_paid': row['total_paid'] or 0,
            })

        return list(partners.values())

    def _get_partner_line(self, report, options, partner_data):
        """Genera línea de encabezado del tercero."""
        total_payments = sum(ba['payment_count'] for ba in partner_data['bank_accounts'])
        total_amount = sum(ba['total_paid'] for ba in partner_data['bank_accounts'])
        partner_id = partner_data['partner_id']

        return {
            'id': report._get_generic_line_id('res.partner', partner_id),
            'name': partner_data['partner_name'],
            'level': 1,
            'unfoldable': True,
            'unfolded': options.get('unfold_all', False),
            'columns': [
                {'name': partner_data['partner_vat'] or ''},
                {'name': ''},
                {'name': ''},
                {'name': ''},
                {'name': total_payments},
                {'name': total_amount, 'class': 'number'},
            ],
        }

    def _get_bank_account_line(self, report, options, partner_id, bank_data):
        """Genera línea para una cuenta bancaria."""
        safe_account = re.sub(r'[^a-zA-Z0-9]', '_', bank_data['bank_account'] or 'unknown')
        parent_id = report._get_generic_line_id('res.partner', partner_id)
        return {
            'id': report._get_generic_line_id(None, None, markup=f'bank_{partner_id}_{safe_account}', parent_line_id=parent_id),
            'name': '',
            'level': 2,
            'parent_id': parent_id,
            'columns': [
                {'name': ''},
                {'name': bank_data['bank_name']},
                {'name': bank_data['bank_account']},
                {'name': bank_data['account_type']},
                {'name': bank_data['payment_count']},
                {'name': bank_data['total_paid'], 'class': 'number'},
            ],
        }

    def _get_total_line(self, report, options, total_payments, total_amount):
        """Genera línea de total."""
        return {
            'id': report._get_generic_line_id(None, None, markup='bank_audit_total'),
            'name': 'TOTAL GENERAL',
            'level': 0,
            'class': 'o_account_reports_level_total',
            'columns': [
                {'name': ''},
                {'name': ''},
                {'name': ''},
                {'name': ''},
                {'name': total_payments},
                {'name': total_amount, 'class': 'number'},
            ],
        }

    def _get_no_data_line(self, report, options):
        """Línea cuando no hay datos."""
        return {
            'id': report._get_generic_line_id(None, None, markup='bank_audit_no_data'),
            'name': 'No se encontraron pagos en el período seleccionado',
            'level': 0,
            'columns': [{'name': ''} for _ in range(6)],
        }

    def _get_error_line(self, report, options, error_msg):
        """Línea de error."""
        return {
            'id': report._get_generic_line_id(None, None, markup='bank_audit_error'),
            'name': f'Error: {error_msg}',
            'level': 0,
            'class': 'text-danger',
            'columns': [{'name': ''} for _ in range(6)],
        }


# =============================================================================
# 5. ERRORES Y DESCUADRES CONTABLES
# =============================================================================

class AccountAuditImbalancesReportHandler(models.AbstractModel):
    """
    Handler para el reporte de Errores y Descuadres Contables.

    Detecta:
    - Asientos descuadrados (débito != crédito)
    - Asientos sin líneas
    - Líneas huérfanas
    - Documentos sin tercero requerido
    """
    _name = 'account.audit.imbalances.report.handler'
    _inherit = 'account.report.custom.handler'
    _description = 'Errores y Descuadres Contables - Handler'

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        """Genera las líneas del reporte de errores y descuadres."""
        lines = []

        try:
            # 1. Asientos descuadrados
            imbalanced = self._get_imbalanced_entries(report, options)
            if imbalanced:
                lines.append(self._get_section_header(report, 'imbalanced', 'ASIENTOS DESCUADRADOS', len(imbalanced)))
                for entry in imbalanced:
                    lines.append(self._get_imbalance_line(report, options, entry))

            # 2. Asientos sin líneas
            empty_moves = self._get_empty_moves(report, options)
            if empty_moves:
                lines.append(self._get_section_header(report, 'empty', 'ASIENTOS SIN LÍNEAS', len(empty_moves)))
                for entry in empty_moves:
                    lines.append(self._get_empty_move_line(report, options, entry))

            # 3. Documentos sin tercero
            no_partner = self._get_moves_without_partner(report, options)
            if no_partner:
                lines.append(self._get_section_header(report, 'no_partner', 'DOCUMENTOS SIN TERCERO', len(no_partner)))
                for entry in no_partner:
                    lines.append(self._get_no_partner_line(report, options, entry))

            # 4. Líneas con valor cero
            zero_lines = self._get_zero_amount_lines(report, options)
            if zero_lines:
                lines.append(self._get_section_header(report, 'zero', 'LÍNEAS CON VALOR CERO', len(zero_lines)))
                for entry in zero_lines:
                    lines.append(self._get_zero_line(report, options, entry))

            if not lines:
                return [(0, self._get_no_issues_line(report, options))]

            # Resumen final
            total_issues = len(imbalanced) + len(empty_moves) + len(no_partner) + len(zero_lines)
            lines.append(self._get_summary_line(report, options, total_issues))

        except Exception as e:
            _logger.error(f"Error en reporte de descuadres: {str(e)}")
            lines = [self._get_error_line(report, options, str(e))]

        return [(0, line) for line in lines]

    def _get_imbalanced_entries(self, report, options):
        """Detecta asientos donde débito != crédito."""
        date_from = options['date']['date_from']
        date_to = options['date']['date_to']

        query = """
            SELECT
                am.id,
                am.name as move_name,
                am.date,
                COALESCE(aj.name->>'es_CO', aj.name->>'en_US', aj.code) as journal_name,
                SUM(aml.debit) as total_debit,
                SUM(aml.credit) as total_credit,
                ABS(SUM(aml.debit) - SUM(aml.credit)) as difference
            FROM account_move am
            JOIN account_journal aj ON aj.id = am.journal_id
            JOIN account_move_line aml ON aml.move_id = am.id
            WHERE am.date BETWEEN %s AND %s
            AND am.state = 'posted'
            GROUP BY am.id, am.name, am.date, aj.name, aj.code
            HAVING ABS(SUM(aml.debit) - SUM(aml.credit)) > 0.01
            ORDER BY ABS(SUM(aml.debit) - SUM(aml.credit)) DESC
            LIMIT 100
        """
        self._cr.execute(query, [date_from, date_to])
        return self._cr.dictfetchall()

    def _get_empty_moves(self, report, options):
        """Detecta asientos sin líneas."""
        date_from = options['date']['date_from']
        date_to = options['date']['date_to']

        query = """
            SELECT
                am.id,
                am.name as move_name,
                am.date,
                COALESCE(aj.name->>'es_CO', aj.name->>'en_US', aj.code) as journal_name,
                am.state
            FROM account_move am
            JOIN account_journal aj ON aj.id = am.journal_id
            LEFT JOIN account_move_line aml ON aml.move_id = am.id
            WHERE am.date BETWEEN %s AND %s
            GROUP BY am.id, am.name, am.date, aj.name, aj.code, am.state
            HAVING COUNT(aml.id) = 0
            ORDER BY am.date DESC
            LIMIT 50
        """
        self._cr.execute(query, [date_from, date_to])
        return self._cr.dictfetchall()

    def _get_moves_without_partner(self, report, options):
        """Detecta documentos que requieren tercero pero no lo tienen."""
        date_from = options['date']['date_from']
        date_to = options['date']['date_to']

        query = """
            SELECT
                am.id,
                am.name as move_name,
                am.date,
                COALESCE(aj.name->>'es_CO', aj.name->>'en_US', aj.code) as journal_name,
                am.move_type,
                am.amount_total
            FROM account_move am
            JOIN account_journal aj ON aj.id = am.journal_id
            WHERE am.date BETWEEN %s AND %s
            AND am.state = 'posted'
            AND am.partner_id IS NULL
            AND am.move_type IN ('out_invoice', 'in_invoice', 'out_refund', 'in_refund')
            ORDER BY am.date DESC
            LIMIT 100
        """
        self._cr.execute(query, [date_from, date_to])
        return self._cr.dictfetchall()

    def _get_zero_amount_lines(self, report, options):
        """Detecta líneas con débito y crédito en cero."""
        date_from = options['date']['date_from']
        date_to = options['date']['date_to']

        query = """
            SELECT
                am.id as move_id,
                am.name as move_name,
                am.date,
                COALESCE(aj.name->>'es_CO', aj.name->>'en_US', aj.code) as journal_name,
                aa.code as account_code,
                COALESCE(aa.name->>'es_CO', aa.name->>'en_US', aa.code) as account_name,
                COUNT(*) as zero_lines_count
            FROM account_move_line aml
            JOIN account_move am ON am.id = aml.move_id
            JOIN account_journal aj ON aj.id = am.journal_id
            JOIN account_account aa ON aa.id = aml.account_id
            WHERE am.date BETWEEN %s AND %s
            AND am.state = 'posted'
            AND aml.debit = 0 AND aml.credit = 0 AND aml.amount_currency = 0
            GROUP BY am.id, am.name, am.date, aj.name, aj.code, aa.code, aa.name
            ORDER BY am.date DESC
            LIMIT 100
        """
        self._cr.execute(query, [date_from, date_to])
        return self._cr.dictfetchall()

    def _get_section_header(self, report, section_id, title, count):
        """Genera encabezado de sección."""
        return {
            'id': report._get_generic_line_id(None, None, markup=f'imb_section_{section_id}'),
            'name': f"{title} ({count})",
            'level': 0,
            'class': 'o_account_reports_level_total text-danger',
            'unfoldable': True,
            'unfolded': True,
            'columns': [{'name': ''} for _ in range(6)],
        }

    def _get_imbalance_line(self, report, options, entry):
        """Línea para asiento descuadrado."""
        parent_id = report._get_generic_line_id(None, None, markup='imb_section_imbalanced')
        return {
            'id': report._get_generic_line_id('account.move', entry['id'], parent_line_id=parent_id),
            'name': entry['move_name'],
            'level': 2,
            'parent_id': parent_id,
            'caret_options': 'account.move',
            'columns': [
                {'name': format_date(self.env, entry['date'])},
                {'name': entry['journal_name']},
                {'name': entry['total_debit'], 'class': 'number'},
                {'name': entry['total_credit'], 'class': 'number'},
                {'name': entry['difference'], 'class': 'number text-danger'},
                {'name': 'Descuadre'},
            ],
        }

    def _get_empty_move_line(self, report, options, entry):
        """Línea para asiento vacío."""
        parent_id = report._get_generic_line_id(None, None, markup='imb_section_empty')
        return {
            'id': report._get_generic_line_id(None, None, markup=f'imb_empty_{entry["id"]}', parent_line_id=parent_id),
            'name': entry['move_name'],
            'level': 2,
            'parent_id': parent_id,
            'caret_options': 'account.move',
            'columns': [
                {'name': format_date(self.env, entry['date'])},
                {'name': entry['journal_name']},
                {'name': ''},
                {'name': ''},
                {'name': ''},
                {'name': 'Sin líneas'},
            ],
        }

    def _get_no_partner_line(self, report, options, entry):
        """Línea para documento sin tercero."""
        move_types = {
            'out_invoice': 'Factura Cliente',
            'in_invoice': 'Factura Proveedor',
            'out_refund': 'NC Cliente',
            'in_refund': 'NC Proveedor',
        }
        parent_id = report._get_generic_line_id(None, None, markup='imb_section_no_partner')
        return {
            'id': report._get_generic_line_id(None, None, markup=f'imb_nopartner_{entry["id"]}', parent_line_id=parent_id),
            'name': entry['move_name'],
            'level': 2,
            'parent_id': parent_id,
            'caret_options': 'account.move',
            'columns': [
                {'name': format_date(self.env, entry['date'])},
                {'name': entry['journal_name']},
                {'name': move_types.get(entry['move_type'], entry['move_type'])},
                {'name': entry['amount_total'], 'class': 'number'},
                {'name': ''},
                {'name': 'Sin tercero'},
            ],
        }

    def _get_zero_line(self, report, options, entry):
        """Línea para líneas con valor cero."""
        safe_code = re.sub(r'[^a-zA-Z0-9]', '_', entry['account_code'] or 'unknown')
        parent_id = report._get_generic_line_id(None, None, markup='imb_section_zero')
        return {
            'id': report._get_generic_line_id(None, None, markup=f'imb_zero_{entry["move_id"]}_{safe_code}', parent_line_id=parent_id),
            'name': entry['move_name'],
            'level': 2,
            'parent_id': parent_id,
            'caret_options': 'account.move',
            'columns': [
                {'name': format_date(self.env, entry['date'])},
                {'name': entry['journal_name']},
                {'name': entry['account_code']},
                {'name': entry['zero_lines_count']},
                {'name': ''},
                {'name': 'Valor cero'},
            ],
        }

    def _get_no_issues_line(self, report, options):
        """Línea cuando no hay problemas."""
        return {
            'id': report._get_generic_line_id(None, None, markup='imb_no_issues'),
            'name': '✓ No se encontraron errores ni descuadres en el período',
            'level': 0,
            'class': 'text-success',
            'columns': [{'name': ''} for _ in range(6)],
        }

    def _get_summary_line(self, report, options, total_issues):
        """Línea de resumen."""
        return {
            'id': report._get_generic_line_id(None, None, markup='imb_summary_total'),
            'name': f'TOTAL PROBLEMAS DETECTADOS: {total_issues}',
            'level': 0,
            'class': 'o_account_reports_level_total text-danger',
            'columns': [{'name': ''} for _ in range(6)],
        }

    def _get_error_line(self, report, options, error_msg):
        """Línea de error."""
        return {
            'id': report._get_generic_line_id(None, None, markup='imb_error'),
            'name': f'Error: {error_msg}',
            'level': 0,
            'class': 'text-danger',
            'columns': [{'name': ''} for _ in range(6)],
        }


# =============================================================================
# 6. INCONSISTENCIAS CONTABLES
# =============================================================================

class AccountAuditInconsistenciesReportHandler(models.AbstractModel):
    """
    Handler para el reporte de Inconsistencias Contables.

    Detecta:
    - Cuentas con saldo contrario a su naturaleza
    - Cuentas de balance con saldo acumulado negativo incorrecto
    - Terceros con saldo en cuentas que no deberían
    - Movimientos en cuentas inactivas
    """
    _name = 'account.audit.inconsistencies.report.handler'
    _inherit = 'account.report.custom.handler'
    _description = 'Inconsistencias Contables - Handler'

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        """Genera las líneas del reporte de inconsistencias."""
        lines = []

        try:
            # 1. Cuentas con saldo contrario
            wrong_balance = self._get_wrong_balance_accounts(report, options)
            if wrong_balance:
                lines.append(self._get_section_header(report, 'wrong_balance',
                    'CUENTAS CON SALDO CONTRARIO A SU NATURALEZA', len(wrong_balance)))
                for acc in wrong_balance:
                    lines.append(self._get_wrong_balance_line(report, options, acc))

            # 2. Movimientos en cuentas inactivas
            inactive = self._get_inactive_account_movements(report, options)
            if inactive:
                lines.append(self._get_section_header(report, 'inactive',
                    'MOVIMIENTOS EN CUENTAS INACTIVAS', len(inactive)))
                for acc in inactive:
                    lines.append(self._get_inactive_line(report, options, acc))

            # 3. Terceros duplicados potenciales
            duplicates = self._get_duplicate_partners(report, options)
            if duplicates:
                lines.append(self._get_section_header(report, 'duplicates',
                    'POSIBLES TERCEROS DUPLICADOS', len(duplicates)))
                for dup in duplicates:
                    lines.append(self._get_duplicate_line(report, options, dup))

            # 4. Cuentas bancarias sin movimiento
            dormant_banks = self._get_dormant_bank_accounts(report, options)
            if dormant_banks:
                lines.append(self._get_section_header(report, 'dormant',
                    'CUENTAS BANCARIAS SIN MOVIMIENTO', len(dormant_banks)))
                for bank in dormant_banks:
                    lines.append(self._get_dormant_line(report, options, bank))

            if not lines:
                return [(0, self._get_no_issues_line(report, options))]

            # Resumen
            total = len(wrong_balance) + len(inactive) + len(duplicates) + len(dormant_banks)
            lines.append(self._get_summary_line(report, options, total))

        except Exception as e:
            _logger.error(f"Error en reporte de inconsistencias: {str(e)}")
            lines = [self._get_error_line(report, options, str(e))]

        return [(0, line) for line in lines]

    def _get_wrong_balance_accounts(self, report, options):
        """Detecta cuentas con saldo contrario a su naturaleza."""
        date_to = options['date']['date_to']

        # En Odoo 18, account_type es un campo selection directamente en account_account
        query = """
            SELECT
                aa.code,
                COALESCE(aa.name->>'es_CO', aa.name->>'en_US', aa.code) as account_name,
                aa.account_type,
                SUM(aml.balance) as balance
            FROM account_move_line aml
            JOIN account_move am ON am.id = aml.move_id
            JOIN account_account aa ON aa.id = aml.account_id
            WHERE am.date <= %s
            AND am.state = 'posted'
            GROUP BY aa.code, aa.name, aa.account_type
            HAVING (
                (aa.account_type LIKE 'asset%%' AND SUM(aml.balance) < -1000)
                OR
                (aa.account_type LIKE 'expense%%' AND SUM(aml.balance) < -1000)
                OR
                (aa.account_type LIKE 'liability%%' AND SUM(aml.balance) > 1000)
                OR
                (aa.account_type LIKE 'equity%%' AND SUM(aml.balance) > 1000)
                OR
                (aa.account_type LIKE 'income%%' AND SUM(aml.balance) > 1000)
            )
            ORDER BY ABS(SUM(aml.balance)) DESC
            LIMIT 50
        """
        self._cr.execute(query, [date_to])
        return self._cr.dictfetchall()

    def _get_inactive_account_movements(self, report, options):
        """Detecta movimientos en cuentas marcadas como inactivas."""
        date_from = options['date']['date_from']
        date_to = options['date']['date_to']

        query = """
            SELECT
                aa.code,
                COALESCE(aa.name->>'es_CO', aa.name->>'en_US', aa.code) as account_name,
                COUNT(DISTINCT am.id) as move_count,
                SUM(ABS(aml.balance)) as total_amount
            FROM account_move_line aml
            JOIN account_move am ON am.id = aml.move_id
            JOIN account_account aa ON aa.id = aml.account_id
            WHERE am.date BETWEEN %s AND %s
            AND am.state = 'posted'
            AND aa.deprecated = TRUE
            GROUP BY aa.code, aa.name
            ORDER BY COUNT(DISTINCT am.id) DESC
            LIMIT 50
        """
        self._cr.execute(query, [date_from, date_to])
        return self._cr.dictfetchall()

    def _get_duplicate_partners(self, report, options):
        """Detecta posibles terceros duplicados por NIT."""
        query = """
            SELECT
                vat,
                COUNT(*) as count,
                STRING_AGG(name, ' | ' ORDER BY id) as names,
                ARRAY_AGG(id ORDER BY id) as ids
            FROM res_partner
            WHERE vat IS NOT NULL
            AND vat != ''
            AND active = TRUE
            GROUP BY vat
            HAVING COUNT(*) > 1
            ORDER BY COUNT(*) DESC
            LIMIT 50
        """
        self._cr.execute(query)
        return self._cr.dictfetchall()

    def _get_dormant_bank_accounts(self, report, options):
        """Detecta cuentas bancarias sin movimiento en el período."""
        date_from = options['date']['date_from']
        date_to = options['date']['date_to']

        query = """
            SELECT
                aa.code,
                COALESCE(aa.name->>'es_CO', aa.name->>'en_US', aa.code) as account_name,
                (SELECT MAX(am2.date) FROM account_move_line aml2
                 JOIN account_move am2 ON am2.id = aml2.move_id
                 WHERE aml2.account_id = aa.id AND am2.state = 'posted') as last_movement
            FROM account_account aa
            WHERE aa.code LIKE '11%%'
            AND aa.deprecated = FALSE
            AND NOT EXISTS (
                SELECT 1 FROM account_move_line aml
                JOIN account_move am ON am.id = aml.move_id
                WHERE aml.account_id = aa.id
                AND am.date BETWEEN %s AND %s
                AND am.state = 'posted'
            )
            ORDER BY aa.code
            LIMIT 50
        """
        self._cr.execute(query, [date_from, date_to])
        return self._cr.dictfetchall()

    def _get_section_header(self, report, section_id, title, count):
        """Genera encabezado de sección."""
        return {
            'id': report._get_generic_line_id(None, None, markup=f'inc_section_{section_id}'),
            'name': f"{title} ({count})",
            'level': 0,
            'class': 'o_account_reports_level_total text-warning',
            'unfoldable': True,
            'unfolded': True,
            'columns': [{'name': ''} for _ in range(5)],
        }

    def _get_wrong_balance_line(self, report, options, acc):
        """Línea para cuenta con saldo incorrecto."""
        safe_code = re.sub(r'[^a-zA-Z0-9]', '_', acc['code'] or 'unknown')
        parent_id = report._get_generic_line_id(None, None, markup='inc_section_wrong_balance')
        return {
            'id': report._get_generic_line_id(None, None, markup=f'inc_wrong_{safe_code}', parent_line_id=parent_id),
            'name': f"{acc['code']} {acc['account_name']}",
            'level': 2,
            'parent_id': parent_id,
            'columns': [
                {'name': acc['account_type']},
                {'name': acc['balance'], 'class': 'number text-danger'},
                {'name': 'Saldo contrario' if acc['balance'] < 0 else 'Saldo positivo inusual'},
                {'name': ''},
                {'name': ''},
            ],
        }

    def _get_inactive_line(self, report, options, acc):
        """Línea para cuenta inactiva con movimientos."""
        safe_code = re.sub(r'[^a-zA-Z0-9]', '_', acc['code'] or 'unknown')
        parent_id = report._get_generic_line_id(None, None, markup='inc_section_inactive')
        return {
            'id': report._get_generic_line_id(None, None, markup=f'inc_inactive_{safe_code}', parent_line_id=parent_id),
            'name': f"{acc['code']} {acc['account_name']}",
            'level': 2,
            'parent_id': parent_id,
            'columns': [
                {'name': f"{acc['move_count']} movimientos"},
                {'name': acc['total_amount'], 'class': 'number'},
                {'name': 'Cuenta inactiva'},
                {'name': ''},
                {'name': ''},
            ],
        }

    def _get_duplicate_line(self, report, options, dup):
        """Línea para terceros duplicados."""
        safe_vat = re.sub(r'[^a-zA-Z0-9]', '_', dup['vat'] or 'unknown')
        parent_id = report._get_generic_line_id(None, None, markup='inc_section_duplicates')
        return {
            'id': report._get_generic_line_id(None, None, markup=f'inc_dup_{safe_vat}', parent_line_id=parent_id),
            'name': dup['vat'],
            'level': 2,
            'parent_id': parent_id,
            'columns': [
                {'name': f"{dup['count']} registros"},
                {'name': dup['names'][:100] + ('...' if len(dup['names']) > 100 else '')},
                {'name': 'Posible duplicado'},
                {'name': ''},
                {'name': ''},
            ],
        }

    def _get_dormant_line(self, report, options, bank):
        """Línea para cuenta sin movimiento."""
        safe_code = re.sub(r'[^a-zA-Z0-9]', '_', bank['code'] or 'unknown')
        parent_id = report._get_generic_line_id(None, None, markup='inc_section_dormant')
        return {
            'id': report._get_generic_line_id(None, None, markup=f'inc_dormant_{safe_code}', parent_line_id=parent_id),
            'name': f"{bank['code']} {bank['account_name']}",
            'level': 2,
            'parent_id': parent_id,
            'columns': [
                {'name': format_date(self.env, bank['last_movement']) if bank['last_movement'] else 'Sin movimientos'},
                {'name': ''},
                {'name': 'Sin movimiento en período'},
                {'name': ''},
                {'name': ''},
            ],
        }

    def _get_no_issues_line(self, report, options):
        """Línea cuando no hay problemas."""
        return {
            'id': report._get_generic_line_id(None, None, markup='inc_no_issues'),
            'name': '✓ No se encontraron inconsistencias en el período',
            'level': 0,
            'class': 'text-success',
            'columns': [{'name': ''} for _ in range(5)],
        }

    def _get_summary_line(self, report, options, total):
        """Línea de resumen."""
        return {
            'id': report._get_generic_line_id(None, None, markup='inc_summary_total'),
            'name': f'TOTAL INCONSISTENCIAS: {total}',
            'level': 0,
            'class': 'o_account_reports_level_total text-warning',
            'columns': [{'name': ''} for _ in range(5)],
        }

    def _get_error_line(self, report, options, error_msg):
        """Línea de error."""
        return {
            'id': report._get_generic_line_id(None, None, markup='inc_error'),
            'name': f'Error: {error_msg}',
            'level': 0,
            'class': 'text-danger',
            'columns': [{'name': ''} for _ in range(5)],
        }
