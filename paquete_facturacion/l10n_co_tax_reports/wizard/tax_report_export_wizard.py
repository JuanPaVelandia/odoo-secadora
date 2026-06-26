# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.safe_eval import safe_eval
from odoo.tools import SQL
import logging
import io
import base64
from datetime import datetime, date

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None

_logger = logging.getLogger(__name__)


class TaxReportExportWizard(models.TransientModel):
    _name = 'tax.report.export.wizard'
    _description = 'Exportación Reportes Fiscales Colombia'

    # ========== FILTROS BÁSICOS ==========
    company_id = fields.Many2one('res.company', string='Compañía',
                                 required=True, default=lambda s: s.env.company)
    date_from = fields.Date('Fecha Desde', required=True,
                           default=lambda s: fields.Date.today().replace(day=1))
    date_to = fields.Date('Fecha Hasta', required=True, default=fields.Date.today)

    # ========== TIPO DE REPORTE ==========
    report_type = fields.Selection([
        ('tax_detail', 'Detalle de Impuestos por Cuenta/Grupo/Impuesto/Tercero'),
        ('withholding_aux', 'Auxiliar de Retenciones (PJ/PN)'),
        ('income_base', 'Base sobre Ingresos del Mes'),
        ('account_search', 'Búsqueda por Cuentas Contables'),
    ], string='Tipo Reporte', required=True, default='tax_detail')

    # ========== AGRUPACIONES (para tax_detail) ==========
    group_level_1 = fields.Selection([
        ('tax_group', 'Grupo Impuesto'),
        ('tax', 'Impuesto'),
        ('account', 'Cuenta'),
        ('partner', 'Tercero'),
    ], string='Nivel 1', default='tax_group')

    group_level_2 = fields.Selection([
        ('tax', 'Impuesto'),
        ('account', 'Cuenta'),
        ('partner', 'Tercero'),
        ('none', 'Ninguno'),
    ], string='Nivel 2', default='tax')

    group_level_3 = fields.Selection([
        ('account', 'Cuenta'),
        ('partner', 'Tercero'),
        ('none', 'Ninguno'),
    ], string='Nivel 3', default='account')

    group_level_4 = fields.Selection([
        ('partner', 'Tercero'),
        ('none', 'Ninguno'),
    ], string='Nivel 4', default='partner')

    # ========== FILTROS ==========
    tax_group_ids = fields.Many2many('account.tax.group', string='Grupos de Impuesto')
    tax_ids = fields.Many2many('account.tax', string='Impuestos Específicos')

    partner_type = fields.Selection([
        ('all', 'Todos'),
        ('company', 'Solo Empresas (PJ)'),
        ('person', 'Solo Personas (PN)'),
    ], string='Tipo Tercero', default='all')

    # ========== BASE SOBRE INGRESOS ==========
    income_account_ids = fields.Many2many(
        'account.account',
        'wizard_income_account_rel',
        string='Cuentas de Ingresos',
        domain="[('account_type', 'in', ['income', 'other_income'])]"
    )

    income_formula = fields.Text(
        'Fórmula Cálculo',
        default="total_income * 0.10",
        help="Variables: total_income, total_expense, total_retention"
    )

    # ========== BÚSQUEDA POR CUENTAS ==========
    search_account_ids = fields.Many2many(
        'account.account',
        'wizard_search_account_rel',
        string='Cuentas para Buscar',
        domain="[('deprecated', '=', False)]"
    )

    # ========== OPCIONES ==========
    show_person_type = fields.Boolean('Separar PJ/PN', default=True)
    include_drafts = fields.Boolean('Incluir Borradores', default=False)
    include_credit_notes = fields.Boolean('Incluir Hoja Notas Crédito', default=True)
    include_returns = fields.Boolean('Incluir Hoja Devoluciones', default=True)
    compress_columns = fields.Boolean('Comprimir Columnas Vacías', default=True)

    # ========== EXPORTACIÓN ==========
    output_format = fields.Selection([
        ('xlsx', 'Excel (.xlsx)'),
        ('pdf', 'PDF (.pdf)'),
    ], string='Formato', default='xlsx', required=True)

    file_data = fields.Binary('Archivo', readonly=True)
    file_name = fields.Char('Nombre Archivo', readonly=True)

    # ==========================================================================
    # VALIDACIONES
    # ==========================================================================

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_from > rec.date_to:
                raise ValidationError('La fecha inicial no puede ser mayor a la final')

    # ==========================================================================
    # GENERACIÓN
    # ==========================================================================

    def action_generate_report(self):
        """Genera reporte según tipo seleccionado"""
        self.ensure_one()

        if self.output_format == 'xlsx' and not xlsxwriter:
            raise UserError('Debe instalar xlsxwriter: pip install xlsxwriter')

        # Obtener datos según tipo
        if self.report_type == 'tax_detail':
            data = self._get_tax_detail_data()
        elif self.report_type == 'withholding_aux':
            data = self._get_withholding_data()
        elif self.report_type == 'income_base':
            data = self._get_income_base_data()
        elif self.report_type == 'account_search':
            data = self._get_account_search_data()
        else:
            raise UserError('Tipo de reporte no válido')

        # Agregar datos de notas de crédito si está activado
        if self.include_credit_notes:
            data['credit_notes'] = self._get_credit_notes_data()

        # Agregar datos de devoluciones si está activado
        if self.include_returns:
            data['returns'] = self._get_returns_data()

        # Generar archivo según formato
        if self.output_format == 'xlsx':
            file_data = self._generate_excel(data)
            extension = 'xlsx'
        elif self.output_format == 'pdf':
            file_data = self._generate_pdf(data)
            extension = 'pdf'
        else:
            raise UserError('Formato no soportado')

        # Guardar
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.file_data = base64.b64encode(file_data)
        self.file_name = f'reporte_fiscal_{timestamp}.{extension}'

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    # ==========================================================================
    # REPORTE 1: DETALLE DE IMPUESTOS
    # ==========================================================================

    def _get_tax_detail_data(self):
        """Detalle con agrupación: cuenta → grupo → impuesto → cuenta → tercero"""
        self.ensure_one()

        domain = [
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('company_id', '=', self.company_id.id),
        ]

        if not self.include_drafts:
            domain.append(('parent_state', '=', 'posted'))

        if self.tax_ids:
            domain.append(('tax_ids', 'in', self.tax_ids.ids))
        elif self.tax_group_ids:
            domain.append(('tax_ids.tax_group_id', 'in', self.tax_group_ids.ids))

        if self.partner_type == 'company':
            domain.append(('partner_id.is_company', '=', True))
        elif self.partner_type == 'person':
            domain.append(('partner_id.is_company', '=', False))

        lines = self.env['account.move.line'].search(domain)

        # Agrupar datos
        grouped = {}
        for line in lines:
            # Si la línea es una línea de impuesto (tiene tax_repartition_line_id)
            if line.tax_repartition_line_id:
                # Es una línea de impuesto - el balance es el monto del impuesto
                tax = line.tax_line_id
                if not tax:
                    continue

                tax_amount = abs(line.balance)
                # La base está en las líneas relacionadas - buscarla
                base_lines = line.move_id.line_ids.filtered(
                    lambda l: not l.tax_repartition_line_id and tax in l.tax_ids
                )
                base_amount = sum(abs(bl.balance) for bl in base_lines)

            else:
                # Es una línea base - tiene impuestos asociados
                for tax in line.tax_ids:
                    base_amount = abs(line.balance)
                    # Buscar la línea de impuesto correspondiente
                    tax_lines = line.move_id.line_ids.filtered(
                        lambda l: l.tax_line_id == tax and l.tax_repartition_line_id
                    )
                    tax_amount = sum(abs(tl.balance) for tl in tax_lines)

                    # Clave de agrupación
                    key = (
                        tax.tax_group_id.name or 'Sin Grupo',
                        tax.name,
                        f"[{line.account_id.display_name}] {line.account_id.name}",
                        line.partner_id.name or 'Sin Tercero',
                        'PJ' if line.partner_id.is_company else 'PN' if self.show_person_type else ''
                    )

                    if key not in grouped:
                        grouped[key] = {'base': 0, 'tax': 0, 'lines': []}

                    grouped[key]['base'] += base_amount
                    grouped[key]['tax'] += tax_amount
                    grouped[key]['lines'].append({
                        'date': line.date,
                        'move': line.move_id.name,
                        'move_ref': line.move_id.ref or '',
                        'invoice_ref': line.move_id.invoice_origin or '',
                        'cufe': line.move_id.l10n_co_edi_cufe_cude_ref or '',
                        'description': line.name,
                        'debit': line.debit,
                        'credit': line.credit,
                        'base': base_amount,
                        'tax': tax_amount,
                        'state': line.parent_state,
                    })
                continue

            # Para líneas de impuesto, agregar entrada
            key = (
                tax.tax_group_id.name or 'Sin Grupo',
                tax.name,
                f"[{line.account_id.display_name}] {line.account_id.name}",
                line.partner_id.name or 'Sin Tercero',
                'PJ' if line.partner_id.is_company else 'PN' if self.show_person_type else ''
            )

            if key not in grouped:
                grouped[key] = {'base': 0, 'tax': 0, 'lines': []}

            grouped[key]['base'] += base_amount
            grouped[key]['tax'] += tax_amount
            grouped[key]['lines'].append({
                'date': line.date,
                'move': line.move_id.name,
                'move_ref': line.move_id.ref or '',
                'invoice_ref': line.move_id.invoice_origin or '',
                'cufe': line.move_id.l10n_co_edi_cufe_cude_ref or '',
                'description': line.name,
                'debit': line.debit,
                'credit': line.credit,
                'base': base_amount,
                'tax': tax_amount,
                'state': line.parent_state,
            })

        return {
            'title': 'Detalle de Impuestos',
            'period': f'{self.date_from} al {self.date_to}',
            'grouped_data': grouped,
        }

    # ==========================================================================
    # REPORTE 2: AUXILIAR RETENCIONES
    # ==========================================================================

    def _get_withholding_data(self):
        """Retenciones separadas PJ/PN"""
        self.ensure_one()

        query = """
            SELECT
                at.name as tax_name,
                at.amount as tax_rate,
                rp.name as partner_name,
                rp.vat as partner_vat,
                rp.is_company,
                aa.id as account_id,
                aa.name as account_name,
                SUM(CASE WHEN rp.is_company THEN ABS(aml.balance) ELSE 0 END) as amount_pj,
                SUM(CASE WHEN NOT rp.is_company THEN ABS(aml.balance) ELSE 0 END) as amount_pn,
                SUM(ABS(aml.balance)) as amount_total
            FROM account_move_line aml
            INNER JOIN account_account aa ON aa.id = aml.account_id
            LEFT JOIN res_partner rp ON rp.id = aml.partner_id
            INNER JOIN account_move_line_account_tax_rel amlat ON amlat.account_move_line_id = aml.id
            INNER JOIN account_tax at ON at.id = amlat.account_tax_id
            WHERE aml.date >= %s
              AND aml.date <= %s
              AND aml.company_id = %s
              AND aml.parent_state = 'posted'
              AND at.l10n_co_is_withholding = true
            GROUP BY at.name, at.amount, rp.name, rp.vat, rp.is_company, aa.id, aa.name
            ORDER BY at.name, rp.name
        """

        self.env.cr.execute(query, (self.date_from, self.date_to, self.company_id.id))
        data = self.env.cr.dictfetchall()

        # Obtener códigos de cuenta en Python (campos computados)
        account_ids = list(set(row['account_id'] for row in data))
        accounts = self.env['account.account'].browse(account_ids)
        account_codes = {acc.id: acc.code for acc in accounts}

        # Agregar códigos a los datos
        for row in data:
            row['account_code'] = account_codes.get(row['account_id'], '')

        return {
            'title': 'Auxiliar de Retenciones PJ/PN',
            'period': f'{self.date_from} al {self.date_to}',
            'data': data,
        }

    # ==========================================================================
    # REPORTE 3: BASE SOBRE INGRESOS
    # ==========================================================================

    def _get_income_base_data(self):
        """Calcula base aplicando fórmula sobre ingresos"""
        self.ensure_one()

        # Ingresos
        income_domain = [
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('move_id.state', '=', 'posted'),
            ('company_id', '=', self.company_id.id),
        ]

        if self.income_account_ids:
            income_domain.append(('account_id', 'in', self.income_account_ids.ids))
        else:
            income_domain.append(('account_id.account_type', 'in', ['income', 'other_income']))

        income_lines = self.env['account.move.line'].search(income_domain)
        total_income = abs(sum(income_lines.mapped('balance')))

        # Gastos
        expense_lines = self.env['account.move.line'].search([
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('move_id.state', '=', 'posted'),
            ('company_id', '=', self.company_id.id),
            ('account_id.account_type', 'in', ['expense', 'expense_direct_cost']),
        ])
        total_expense = abs(sum(expense_lines.mapped('balance')))

        # Retenciones
        retention_lines = self.env['account.move.line'].search([
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('move_id.state', '=', 'posted'),
            ('company_id', '=', self.company_id.id),
            ('account_id.code', '=ilike', '1355%'),
        ])
        total_retention = abs(sum(retention_lines.mapped('balance')))

        # Evaluar fórmula
        context = {
            'total_income': total_income,
            'total_expense': total_expense,
            'total_retention': total_retention,
        }

        try:
            calculated = safe_eval(self.income_formula or '0', context)
        except Exception as e:
            _logger.error(f'Error en fórmula: {e}')
            calculated = 0

        return {
            'title': 'Base sobre Ingresos del Mes',
            'period': f'{self.date_from} al {self.date_to}',
            'data': {
                'total_income': total_income,
                'total_expense': total_expense,
                'total_retention': total_retention,
                'formula': self.income_formula,
                'calculated': calculated,
            }
        }

    # ==========================================================================
    # REPORTE 4: BÚSQUEDA POR CUENTAS
    # ==========================================================================

    def _get_account_search_data(self):
        """Búsqueda simple por cuentas contables"""
        self.ensure_one()

        if not self.search_account_ids:
            raise UserError('Debe seleccionar al menos una cuenta')

        lines = self.env['account.move.line'].search([
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('move_id.state', '=', 'posted'),
            ('company_id', '=', self.company_id.id),
            ('account_id', 'in', self.search_account_ids.ids),
        ])

        # Agrupar por cuenta y tercero
        grouped = {}
        for line in lines:
            key = (
                f"[{line.account_id.code}] {line.account_id.name}",
                line.partner_id.name or 'Sin Tercero'
            )

            if key not in grouped:
                grouped[key] = {'debit': 0, 'credit': 0, 'balance': 0, 'count': 0}

            grouped[key]['debit'] += line.debit
            grouped[key]['credit'] += line.credit
            grouped[key]['balance'] += line.balance
            grouped[key]['count'] += 1

        return {
            'title': 'Búsqueda por Cuentas Contables',
            'period': f'{self.date_from} al {self.date_to}',
            'grouped_data': grouped,
        }

    # ==========================================================================
    # REPORTE 5: NOTAS DE CRÉDITO
    # ==========================================================================

    def _get_credit_notes_data(self):
        """Obtiene notas de crédito con fecha origen y montos descontados"""
        self.ensure_one()

        domain = [
            ('move_type', '=', 'out_refund'),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('company_id', '=', self.company_id.id),
        ]

        if not self.include_drafts:
            domain.append(('state', '=', 'posted'))

        credit_notes = self.env['account.move'].search(domain)

        data = []
        for cn in credit_notes:
            # Buscar factura origen
            origin_invoice = None
            if cn.reversed_entry_id:
                origin_invoice = cn.reversed_entry_id
            elif cn.invoice_origin:
                origin_invoice = self.env['account.move'].search([
                    ('name', '=', cn.invoice_origin),
                    ('company_id', '=', self.company_id.id)
                ], limit=1)

            # Calcular impuestos descontados
            tax_amount = sum(cn.line_ids.filtered(lambda l: l.tax_line_id).mapped('balance'))

            data.append({
                'credit_note': cn.name,
                'date': cn.date,
                'partner': cn.partner_id.name,
                'partner_vat': cn.partner_id.vat or '',
                'origin_invoice': origin_invoice.name if origin_invoice else cn.invoice_origin or '',
                'origin_date': origin_invoice.date if origin_invoice else None,
                'amount_untaxed': abs(cn.amount_untaxed),
                'amount_tax': abs(tax_amount),
                'amount_total': abs(cn.amount_total),
                'state': cn.state,
                'cufe': cn.l10n_co_edi_cufe_cude_ref or '',
                'reason': cn.ref or cn.narration or '',
            })

        return data

    # ==========================================================================
    # REPORTE 6: DEVOLUCIONES
    # ==========================================================================

    def _get_returns_data(self):
        """Obtiene devoluciones con detalle de impuestos afectados"""
        self.ensure_one()

        domain = [
            ('move_type', 'in', ['out_refund', 'in_refund']),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('company_id', '=', self.company_id.id),
        ]

        if not self.include_drafts:
            domain.append(('state', '=', 'posted'))

        returns = self.env['account.move'].search(domain)

        data = []
        for ret in returns:
            # Agrupar por impuesto
            for line in ret.line_ids.filtered(lambda l: l.tax_line_id):
                tax = line.tax_line_id

                # Buscar línea base correspondiente
                base_lines = ret.line_ids.filtered(lambda l: tax in l.tax_ids)
                base_amount = sum(base_lines.mapped('balance'))

                data.append({
                    'document': ret.name,
                    'document_type': dict(ret._fields['move_type'].selection).get(ret.move_type),
                    'date': ret.date,
                    'partner': ret.partner_id.name,
                    'partner_vat': ret.partner_id.vat or '',
                    'tax': tax.name,
                    'tax_group': tax.tax_group_id.name or '',
                    'base_amount': abs(base_amount),
                    'tax_amount': abs(line.balance),
                    'origin': ret.invoice_origin or '',
                    'state': ret.state,
                    'cufe': ret.l10n_co_edi_cufe_cude_ref or '',
                })

        return data

    # ==========================================================================
    # GENERACIÓN EXCEL
    # ==========================================================================

    def _generate_excel(self, data):
        """Genera archivo Excel mejorado con encabezado y múltiples hojas"""
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})

        # ========== FORMATOS ==========
        title_format = workbook.add_format({
            'bold': True,
            'font_size': 16,
            'bg_color': '#002060',
            'font_color': 'white',
            'align': 'center',
            'valign': 'vcenter',
        })

        subtitle_format = workbook.add_format({
            'bold': True,
            'font_size': 11,
            'bg_color': '#D9E1F2',
            'border': 1,
        })

        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#4472C4',
            'font_color': 'white',
            'border': 1,
            'align': 'center',
            'text_wrap': True,
        })

        currency_format = workbook.add_format({'num_format': '#,##0.00', 'border': 1})
        date_format = workbook.add_format({'num_format': 'yyyy-mm-dd', 'border': 1})
        text_format = workbook.add_format({'border': 1})
        bold_format = workbook.add_format({'bold': True})

        # ========== HOJA PRINCIPAL ==========
        worksheet = workbook.add_worksheet('Reporte Principal')

        # Encabezado mejorado
        row = self._write_enhanced_header(worksheet, data, title_format, subtitle_format)
        row += 1

        # Escribir según tipo de reporte
        formats = {
            'header': header_format,
            'currency': currency_format,
            'date': date_format,
            'text': text_format,
            'bold': bold_format,
        }

        if self.report_type == 'tax_detail':
            row = self._write_tax_detail_enhanced(worksheet, data, row, formats)
        elif self.report_type == 'withholding_aux':
            row = self._write_withholding(worksheet, data, row, header_format, currency_format)
        elif self.report_type == 'income_base':
            row = self._write_income_base(worksheet, data, row, header_format, currency_format)
        elif self.report_type == 'account_search':
            row = self._write_account_search(worksheet, data, row, header_format, currency_format)

        # Comprimir columnas vacías
        if self.compress_columns:
            self._compress_empty_columns(worksheet, row)

        # ========== HOJA NOTAS DE CRÉDITO ==========
        if data.get('credit_notes'):
            ws_credit = workbook.add_worksheet('Notas de Crédito')
            self._write_credit_notes_sheet(ws_credit, data, formats)

        # ========== HOJA DEVOLUCIONES ==========
        if data.get('returns'):
            ws_returns = workbook.add_worksheet('Devoluciones')
            self._write_returns_sheet(ws_returns, data, formats)

        workbook.close()
        output.seek(0)
        return output.read()

    def _write_enhanced_header(self, ws, data, title_fmt, subtitle_fmt):
        """Escribe encabezado mejorado con información de compañía"""
        # Título principal (merge A1:J1)
        ws.merge_range('A1:J1', data.get('title', 'REPORTE FISCAL COLOMBIA'), title_fmt)
        ws.set_row(0, 30)  # Altura fila título

        row = 1

        # Información de la compañía
        ws.write(row, 0, 'NIT:', subtitle_fmt)
        ws.write(row, 1, self.company_id.vat or '', subtitle_fmt)
        ws.write(row, 2, 'Compañía:', subtitle_fmt)
        ws.merge_range(row, 3, row, 5, self.company_id.name, subtitle_fmt)
        row += 1

        # Periodo
        ws.write(row, 0, 'Período:', subtitle_fmt)
        ws.write(row, 1, data.get('period', ''), subtitle_fmt)
        ws.write(row, 2, 'Generado:', subtitle_fmt)
        ws.write(row, 3, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), subtitle_fmt)
        row += 1

        # Filtros aplicados
        ws.write(row, 0, 'Filtros:', subtitle_fmt)
        filters = []
        if self.tax_group_ids:
            filters.append(f"Grupos: {', '.join(self.tax_group_ids.mapped('name'))}")
        if self.tax_ids:
            filters.append(f"Impuestos: {', '.join(self.tax_ids.mapped('name'))}")
        if self.partner_type != 'all':
            filters.append(f"Tipo: {dict(self._fields['partner_type'].selection).get(self.partner_type)}")
        if self.include_drafts:
            filters.append("Incluye Borradores")

        filter_text = '; '.join(filters) if filters else 'Ninguno'
        ws.merge_range(row, 1, row, 5, filter_text, subtitle_fmt)
        row += 1

        return row

    def _write_tax_detail_enhanced(self, ws, data, row, formats):
        """Escribe detalle de impuestos con columnas extendidas y auto-ajuste"""
        hfmt = formats['header']
        cfmt = formats['currency']
        dfmt = formats['date']
        tfmt = formats['text']

        # Headers con columnas adicionales
        headers = [
            'Fecha',
            'Asiento',
            'Referencia',
            'Factura Origen',
            'CUFE/CUDE',
            'Grupo Impuesto',
            'Impuesto',
            'Cuenta',
            'Tercero',
        ]

        if self.show_person_type:
            headers.append('Tipo')

        headers.extend([
            'Estado',
            'Descripción',
            'Débito',
            'Crédito',
            'Base',
            'Impuesto',
        ])

        # Tracker para medir contenido de cada columna
        column_tracker = {i: [headers[i]] for i in range(len(headers))}

        # Escribir headers
        for col, header in enumerate(headers):
            ws.write(row, col, header, hfmt)

        row += 1

        # Datos detallados línea por línea
        for key, vals in data['grouped_data'].items():
            group, tax, account, partner, person_type = key

            for line in vals.get('lines', []):
                col = 0

                # Fecha
                ws.write(row, col, line['date'], dfmt)
                column_tracker[col].append(line['date']); col += 1

                # Asiento
                ws.write(row, col, line['move'], tfmt)
                column_tracker[col].append(line['move']); col += 1

                # Referencia
                ref = line.get('move_ref', '')
                ws.write(row, col, ref, tfmt)
                column_tracker[col].append(ref); col += 1

                # Factura Origen
                inv_ref = line.get('invoice_ref', '')
                ws.write(row, col, inv_ref, tfmt)
                column_tracker[col].append(inv_ref); col += 1

                # CUFE
                cufe = line.get('cufe', '')
                ws.write(row, col, cufe, tfmt)
                column_tracker[col].append(cufe); col += 1

                # Grupo Impuesto
                ws.write(row, col, group, tfmt)
                column_tracker[col].append(group); col += 1

                # Impuesto
                ws.write(row, col, tax, tfmt)
                column_tracker[col].append(tax); col += 1

                # Cuenta
                ws.write(row, col, account, tfmt)
                column_tracker[col].append(account); col += 1

                # Tercero
                ws.write(row, col, partner, tfmt)
                column_tracker[col].append(partner); col += 1

                # Tipo (opcional)
                if self.show_person_type:
                    ws.write(row, col, person_type, tfmt)
                    column_tracker[col].append(person_type); col += 1

                # Estado
                state = line.get('state', 'posted')
                ws.write(row, col, state, tfmt)
                column_tracker[col].append(state); col += 1

                # Descripción
                desc = line.get('description', '')
                ws.write(row, col, desc, tfmt)
                column_tracker[col].append(desc); col += 1

                # Débito
                debit = line.get('debit', 0)
                ws.write(row, col, debit, cfmt)
                column_tracker[col].append(debit); col += 1

                # Crédito
                credit = line.get('credit', 0)
                ws.write(row, col, credit, cfmt)
                column_tracker[col].append(credit); col += 1

                # Base
                base = line.get('base', 0)
                ws.write(row, col, base, cfmt)
                column_tracker[col].append(base); col += 1

                # Impuesto
                tax_amt = line.get('tax', 0)
                ws.write(row, col, tax_amt, cfmt)
                column_tracker[col].append(tax_amt); col += 1

                row += 1

        # Auto-ajustar anchos de columnas basándose en el contenido
        if self.compress_columns:
            self._auto_adjust_column_width(ws, column_tracker, min_width=5, max_width=50)

        return row

    def _write_tax_detail(self, ws, data, row, hfmt, cfmt):
        """Escribe detalle de impuestos (versión resumida - deprecated)"""
        # Headers
        ws.write(row, 0, 'Grupo', hfmt)
        ws.write(row, 1, 'Impuesto', hfmt)
        ws.write(row, 2, 'Cuenta', hfmt)
        ws.write(row, 3, 'Tercero', hfmt)
        if self.show_person_type:
            ws.write(row, 4, 'Tipo', hfmt)
            ws.write(row, 5, 'Base', hfmt)
            ws.write(row, 6, 'Impuesto', hfmt)
            col_base, col_tax = 5, 6
        else:
            ws.write(row, 4, 'Base', hfmt)
            ws.write(row, 5, 'Impuesto', hfmt)
            col_base, col_tax = 4, 5

        row += 1

        # Datos
        for key, vals in data['grouped_data'].items():
            col = 0
            for item in key:
                ws.write(row, col, item)
                col += 1
            ws.write(row, col_base, vals['base'], cfmt)
            ws.write(row, col_tax, vals['tax'], cfmt)
            row += 1

        return row

    def _write_withholding(self, ws, data, row, hfmt, cfmt):
        """Escribe auxiliar retenciones"""
        headers = ['Impuesto', 'Tercero', 'NIT', 'Cuenta', 'PJ', 'PN', 'Total']
        for col, h in enumerate(headers):
            ws.write(row, col, h, hfmt)
        row += 1

        for item in data['data']:
            ws.write(row, 0, item['tax_name'])
            ws.write(row, 1, item['partner_name'])
            ws.write(row, 2, item['partner_vat'] or '')
            ws.write(row, 3, f"[{item['account_code']}] {item['account_name']}")
            ws.write(row, 4, item['amount_pj'], cfmt)
            ws.write(row, 5, item['amount_pn'], cfmt)
            ws.write(row, 6, item['amount_total'], cfmt)
            row += 1

        return row

    def _write_income_base(self, ws, data, row, hfmt, cfmt):
        """Escribe base sobre ingresos"""
        ws.write(row, 0, 'Concepto', hfmt)
        ws.write(row, 1, 'Valor', hfmt)
        row += 1

        d = data['data']
        ws.write(row, 0, 'Total Ingresos')
        ws.write(row, 1, d['total_income'], cfmt)
        row += 1

        ws.write(row, 0, 'Total Gastos')
        ws.write(row, 1, d['total_expense'], cfmt)
        row += 1

        ws.write(row, 0, 'Total Retenciones')
        ws.write(row, 1, d['total_retention'], cfmt)
        row += 1

        ws.write(row, 0, 'Fórmula Aplicada')
        ws.write(row, 1, d['formula'])
        row += 1

        ws.write(row, 0, 'Base Calculada')
        ws.write(row, 1, d['calculated'], cfmt)
        row += 1

        return row

    def _write_account_search(self, ws, data, row, hfmt, cfmt):
        """Escribe búsqueda por cuentas"""
        ws.write(row, 0, 'Cuenta', hfmt)
        ws.write(row, 1, 'Tercero', hfmt)
        ws.write(row, 2, 'Débito', hfmt)
        ws.write(row, 3, 'Crédito', hfmt)
        ws.write(row, 4, 'Saldo', hfmt)
        ws.write(row, 5, '# Movs', hfmt)
        row += 1

        for key, vals in data['grouped_data'].items():
            ws.write(row, 0, key[0])
            ws.write(row, 1, key[1])
            ws.write(row, 2, vals['debit'], cfmt)
            ws.write(row, 3, vals['credit'], cfmt)
            ws.write(row, 4, vals['balance'], cfmt)
            ws.write(row, 5, vals['count'])
            row += 1

        return row

    def _write_credit_notes_sheet(self, ws, data, formats):
        """Escribe hoja de notas de crédito con auto-ajuste"""
        hfmt = formats['header']
        cfmt = formats['currency']
        dfmt = formats['date']
        tfmt = formats['text']

        # Título
        ws.merge_range('A1:L1', 'NOTAS DE CRÉDITO - IMPUESTOS DESCONTADOS', formats['bold'])
        ws.set_row(0, 20)

        row = 2

        # Headers
        headers = [
            'Nota Crédito',
            'Fecha NC',
            'Tercero',
            'NIT',
            'Factura Origen',
            'Fecha Origen',
            'CUFE/CUDE',
            'Base',
            'Impuesto Descontado',
            'Total',
            'Estado',
            'Motivo',
        ]

        # Tracker para medir contenido
        column_tracker = {i: [headers[i]] for i in range(len(headers))}

        # Escribir headers
        for col, header in enumerate(headers):
            ws.write(row, col, header, hfmt)

        row += 1

        # Datos
        for item in data.get('credit_notes', []):
            col = 0
            ws.write(row, col, item['credit_note'], tfmt)
            column_tracker[col].append(item['credit_note']); col += 1

            ws.write(row, col, item['date'], dfmt)
            column_tracker[col].append(item['date']); col += 1

            ws.write(row, col, item['partner'], tfmt)
            column_tracker[col].append(item['partner']); col += 1

            ws.write(row, col, item['partner_vat'], tfmt)
            column_tracker[col].append(item['partner_vat']); col += 1

            ws.write(row, col, item['origin_invoice'], tfmt)
            column_tracker[col].append(item['origin_invoice']); col += 1

            origin_date = item['origin_date'] or ''
            ws.write(row, col, origin_date, dfmt if item['origin_date'] else tfmt)
            column_tracker[col].append(origin_date); col += 1

            ws.write(row, col, item['cufe'], tfmt)
            column_tracker[col].append(item['cufe']); col += 1

            ws.write(row, col, item['amount_untaxed'], cfmt)
            column_tracker[col].append(item['amount_untaxed']); col += 1

            ws.write(row, col, item['amount_tax'], cfmt)
            column_tracker[col].append(item['amount_tax']); col += 1

            ws.write(row, col, item['amount_total'], cfmt)
            column_tracker[col].append(item['amount_total']); col += 1

            ws.write(row, col, item['state'], tfmt)
            column_tracker[col].append(item['state']); col += 1

            ws.write(row, col, item['reason'], tfmt)
            column_tracker[col].append(item['reason']); col += 1

            row += 1

        # Totales
        if data.get('credit_notes'):
            row += 1
            ws.write(row, 6, 'TOTALES:', formats['bold'])
            total_base = sum(item['amount_untaxed'] for item in data['credit_notes'])
            total_tax = sum(item['amount_tax'] for item in data['credit_notes'])
            total_amount = sum(item['amount_total'] for item in data['credit_notes'])
            ws.write(row, 7, total_base, cfmt)
            ws.write(row, 8, total_tax, cfmt)
            ws.write(row, 9, total_amount, cfmt)

        # Auto-ajustar anchos
        if self.compress_columns:
            self._auto_adjust_column_width(ws, column_tracker, min_width=5, max_width=50)

    def _write_returns_sheet(self, ws, data, formats):
        """Escribe hoja de devoluciones con impuestos afectados y auto-ajuste de columnas"""
        hfmt = formats['header']
        cfmt = formats['currency']
        dfmt = formats['date']
        tfmt = formats['text']

        # Título
        ws.merge_range('A1:L1', 'DEVOLUCIONES - DETALLE DE IMPUESTOS AFECTADOS', formats['bold'])
        ws.set_row(0, 20)

        row = 2

        # Headers
        headers = [
            'Documento',
            'Tipo Doc',
            'Fecha',
            'Tercero',
            'NIT',
            'Impuesto',
            'Grupo Impuesto',
            'Base Afectada',
            'Impuesto Afectado',
            'Doc. Origen',
            'CUFE/CUDE',
            'Estado',
        ]

        # Tracker para medir contenido de cada columna
        column_tracker = {i: [headers[i]] for i in range(len(headers))}

        # Escribir headers
        for col, header in enumerate(headers):
            ws.write(row, col, header, hfmt)

        row += 1

        # Datos
        for item in data.get('returns', []):
            col = 0
            ws.write(row, col, item['document'], tfmt)
            column_tracker[col].append(item['document']); col += 1

            ws.write(row, col, item['document_type'], tfmt)
            column_tracker[col].append(item['document_type']); col += 1

            ws.write(row, col, item['date'], dfmt)
            column_tracker[col].append(item['date']); col += 1

            ws.write(row, col, item['partner'], tfmt)
            column_tracker[col].append(item['partner']); col += 1

            ws.write(row, col, item['partner_vat'], tfmt)
            column_tracker[col].append(item['partner_vat']); col += 1

            ws.write(row, col, item['tax'], tfmt)
            column_tracker[col].append(item['tax']); col += 1

            ws.write(row, col, item['tax_group'], tfmt)
            column_tracker[col].append(item['tax_group']); col += 1

            ws.write(row, col, item['base_amount'], cfmt)
            column_tracker[col].append(item['base_amount']); col += 1

            ws.write(row, col, item['tax_amount'], cfmt)
            column_tracker[col].append(item['tax_amount']); col += 1

            ws.write(row, col, item['origin'], tfmt)
            column_tracker[col].append(item['origin']); col += 1

            ws.write(row, col, item['cufe'], tfmt)
            column_tracker[col].append(item['cufe']); col += 1

            ws.write(row, col, item['state'], tfmt)
            column_tracker[col].append(item['state']); col += 1

            row += 1

        # Totales por impuesto
        if data.get('returns'):
            row += 2
            ws.write(row, 0, 'TOTALES POR IMPUESTO:', formats['bold'])
            row += 1

            # Agrupar por impuesto
            tax_totals = {}
            for item in data['returns']:
                tax_key = item['tax']
                if tax_key not in tax_totals:
                    tax_totals[tax_key] = {'base': 0, 'tax': 0}
                tax_totals[tax_key]['base'] += item['base_amount']
                tax_totals[tax_key]['tax'] += item['tax_amount']

            ws.write(row, 0, 'Impuesto', hfmt)
            ws.write(row, 1, 'Base Total', hfmt)
            ws.write(row, 2, 'Impuesto Total', hfmt)
            row += 1

            for tax_name, totals in sorted(tax_totals.items()):
                ws.write(row, 0, tax_name, tfmt)
                ws.write(row, 1, totals['base'], cfmt)
                ws.write(row, 2, totals['tax'], cfmt)
                row += 1

        # Auto-ajustar anchos
        if self.compress_columns:
            self._auto_adjust_column_width(ws, column_tracker, min_width=5, max_width=50)

    def _compress_empty_columns(self, ws, max_row):
        """
        Comprime columnas automáticamente basándose en el contenido
        Ajusta el ancho para que quepa el contenido con un mínimo de 5 caracteres
        """
        # Nota: xlsxwriter no permite leer datos ya escritos,
        # por lo tanto usamos un diccionario para trackear el contenido
        # Este método debe ser llamado ANTES de escribir los datos
        pass

    def _auto_adjust_column_width(self, worksheet, data_tracker, min_width=5, max_width=50):
        """
        Ajusta automáticamente el ancho de las columnas basándose en el contenido

        Args:
            worksheet: Hoja de xlsxwriter
            data_tracker: Dict con estructura {col_index: [list of values written]}
            min_width: Ancho mínimo en caracteres (default: 5)
            max_width: Ancho máximo en caracteres (default: 50)
        """
        for col_idx, values in data_tracker.items():
            if not values:
                # Columna vacía - ancho mínimo
                worksheet.set_column(col_idx, col_idx, min_width)
                continue

            # Calcular ancho máximo necesario
            max_length = min_width
            for value in values:
                if value is None:
                    continue

                # Convertir a string y medir
                str_value = str(value)

                # Para fechas, usar formato estándar
                if isinstance(value, date):
                    str_value = '2025-01-01'  # 10 caracteres

                # Para números con formato moneda
                elif isinstance(value, (int, float)):
                    # Formato: #,##0.00 necesita aproximadamente len(str) + 30%
                    str_value = f"{value:,.2f}"

                length = len(str_value)
                max_length = max(max_length, length)

            # Aplicar límites
            final_width = min(max(max_length + 2, min_width), max_width)  # +2 para padding
            worksheet.set_column(col_idx, col_idx, final_width)

    def _generate_pdf(self, data):
        """Genera reporte en formato PDF"""
        try:
            from reportlab.lib.pagesizes import letter, landscape
            from reportlab.lib import colors
            from reportlab.lib.units import inch
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        except ImportError:
            raise UserError('Debe instalar reportlab: pip install reportlab')

        output = io.BytesIO()
        doc = SimpleDocTemplate(output, pagesize=landscape(letter),
                               rightMargin=0.5*inch, leftMargin=0.5*inch,
                               topMargin=0.5*inch, bottomMargin=0.5*inch)

        elements = []
        styles = getSampleStyleSheet()

        # Título
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            textColor=colors.HexColor('#002060'),
            spaceAfter=30,
            alignment=1,  # Center
        )

        elements.append(Paragraph(data.get('title', 'REPORTE FISCAL'), title_style))
        elements.append(Paragraph(f"Período: {data.get('period', '')}", styles['Normal']))
        elements.append(Paragraph(f"Compañía: {self.company_id.name}", styles['Normal']))
        elements.append(Spacer(1, 0.3*inch))

        # Tabla de datos según tipo
        if self.report_type == 'tax_detail':
            table_data = [['Grupo', 'Impuesto', 'Cuenta', 'Tercero', 'Base', 'Impuesto']]

            for key, vals in data['grouped_data'].items():
                row_data = list(key[:4])  # grupo, impuesto, cuenta, tercero
                row_data.append(f"${vals['base']:,.2f}")
                row_data.append(f"${vals['tax']:,.2f}")
                table_data.append(row_data)

            table = Table(table_data, repeatRows=1)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4472C4')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('ALIGN', (4, 1), (5, -1), 'RIGHT'),
            ]))

            elements.append(table)

        doc.build(elements)
        output.seek(0)
        return output.read()
