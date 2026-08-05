# -*- coding: utf-8 -*-
import base64
import io
import logging
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from odoo import api, fields, models, _, Command
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class L10nCoExogenousPartnerAuditWizard(models.TransientModel):
    """Wizard de auditoria auxiliar que muestra movimientos agrupados por tercero"""
    _name = 'l10n_co.exogenous_partner_audit_wizard'
    _description = 'Auxiliar por tercero de exogena'

    format_setting_id = fields.Many2one(
        'l10n_co.exogenous_format_setting',
        string='Configuracion',
        required=True)
    format_id = fields.Many2one(
        'l10n_co.exogenous_format',
        string='Formato',
        related='format_setting_id.format_id',
        readonly=True)
    company_id = fields.Many2one(
        'res.company',
        string='Compania',
        related='format_setting_id.company_id',
        readonly=True)
    partner_filter_id = fields.Many2one(
        'res.partner',
        string='Filtrar por tercero',
        help='Opcional: muestra solo movimientos de este tercero')

    summary_line_ids = fields.One2many(
        'l10n_co.exogenous_partner_audit_wizard.summary',
        'wizard_id',
        string='Resumen por tercero')
    detail_line_ids = fields.One2many(
        'l10n_co.exogenous_partner_audit_wizard.line',
        'wizard_id',
        string='Detalle por tercero')

    total_partners = fields.Integer(string='Total terceros', readonly=True)
    total_lines = fields.Integer(string='Total lineas', readonly=True)
    total_debit = fields.Float(string='Total debito', readonly=True, digits=(16, 2))
    total_credit = fields.Float(string='Total credito', readonly=True, digits=(16, 2))
    total_formula = fields.Float(string='Total formula', readonly=True, digits=(16, 2))

    binary_file = fields.Binary(string='Archivo Excel')
    binary_file_name = fields.Char(string='Nombre del archivo')

    def action_generate_partner_detail(self):
        """Genera el auxiliar agrupado por tercero"""
        self.ensure_one()
        self.detail_line_ids = [Command.clear()]
        self.summary_line_ids = [Command.clear()]

        setting = self.format_setting_id
        detail_lines = []
        # key: (partner_id, concept_code, field_name) -> summary data
        summary_data = {}
        filter_partner = self.partner_filter_id

        for setting_line in setting.format_setting_line_ids:
            field = setting_line.format_field_id
            concept = setting_line.concept_id if setting.apply_concepts else False

            concept_code = concept.code if concept else ''
            field_name = field.name
            formula = field.nature_account or 'db_cr'

            accounts = setting._get_accounts(setting_line)
            if not accounts:
                continue

            partner_ids, move_lines = setting._get_information_by_account_move_line(
                accounts.ids, format_field=field, setting_line=setting_line)
            move_lines, partner_ids = setting._resolve_partner_grouping(move_lines, partner_ids)

            if not move_lines:
                continue

            for aml in move_lines:
                partner_info = aml.get('partner_id', [False, ''])
                pid = partner_info[0] if isinstance(partner_info, (list, tuple)) else partner_info
                pname = partner_info[1] if isinstance(partner_info, (list, tuple)) else str(partner_info)

                if not pid:
                    continue

                # Filtrar por tercero si se selecciono
                if filter_partner and pid != filter_partner.id:
                    continue

                # Obtener VAT del partner (lazy, solo una vez por partner)
                debit = aml.get('debit', 0) or 0
                credit = aml.get('credit', 0) or 0
                formula_value = setting._compute_formula(aml, formula)

                account_info = aml.get('account_id', [False, ''])
                move_info = aml.get('move_id', [False, ''])
                aml_date = aml.get('date', False)

                detail_lines.append(Command.create({
                    'partner_id': pid,
                    'partner_name': pname[:100] if pname else '',
                    'concept_code': concept_code,
                    'field_name': field_name,
                    'account_display': account_info[1] if isinstance(account_info, (list, tuple)) else str(account_info),
                    'move_display': move_info[1] if isinstance(move_info, (list, tuple)) else str(move_info),
                    'date': aml_date,
                    'debit': debit,
                    'credit': credit,
                    'formula_value': formula_value,
                    'formula_type': formula,
                }))

                summary_key = (pid, concept_code, field_name)
                if summary_key not in summary_data:
                    summary_data[summary_key] = {
                        'partner_id': pid,
                        'partner_name': pname[:100] if pname else '',
                        'concept_code': concept_code,
                        'field_name': field_name,
                        'formula': formula,
                        'total_debit': 0,
                        'total_credit': 0,
                        'total_formula': 0,
                        'line_count': 0,
                    }

                summary_data[summary_key]['total_debit'] += debit
                summary_data[summary_key]['total_credit'] += credit
                summary_data[summary_key]['total_formula'] += formula_value
                summary_data[summary_key]['line_count'] += 1

        # Obtener VATs de los partners
        all_partner_ids = list({k[0] for k in summary_data.keys()})
        partner_vats = {}
        if all_partner_ids:
            partners = self.env['res.partner'].browse(all_partner_ids)
            for p in partners:
                partner_vats[p.id] = p.vat or ''

        summary_lines = []
        for data in summary_data.values():
            data['partner_vat'] = partner_vats.get(data['partner_id'], '')
            summary_lines.append((0, 0, data))

        for dl in detail_lines:
            dl[2]['partner_vat'] = partner_vats.get(dl[2].get('partner_id'), '')

        grand_total_debit = sum(d['total_debit'] for d in summary_data.values())
        grand_total_credit = sum(d['total_credit'] for d in summary_data.values())
        grand_total_formula = sum(d['total_formula'] for d in summary_data.values())

        self.write({
            'detail_line_ids': detail_lines,
            'summary_line_ids': summary_lines,
            'total_partners': len(all_partner_ids),
            'total_lines': len(detail_lines),
            'total_debit': grand_total_debit,
            'total_credit': grand_total_credit,
            'total_formula': grand_total_formula,
        })

        return {
            'type': 'ir.actions.act_window',
            'name': _('Auxiliar por tercero - %s') % self.format_id.code,
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
            'context': {'dialog_size': 'extra-large'},
        }

    def action_export_excel(self):
        """Exporta el auxiliar por tercero a Excel con 2 hojas"""
        self.ensure_one()

        wb = Workbook()
        header_font = Font(bold=True, color='FFFFFF')
        header_fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
        summary_fill = PatternFill(start_color='D9E2F3', end_color='D9E2F3', fill_type='solid')
        total_font = Font(bold=True)
        thin_border = Border(
            left=Side(style='thin'), right=Side(style='thin'),
            top=Side(style='thin'), bottom=Side(style='thin'))

        formula_labels = {
            'debit': 'DB', 'credit': 'CR', 'db_cr': 'DB-CR', 'cr_db': 'CR-DB',
            'base_calc_db': 'Base DB', 'base_calc_cr': 'Base CR',
            'base_calc_db_cr': 'Base DB-CR', 'base_calc_cr_db': 'Base CR-DB',
            'tax_base_amount': 'Base almacenada', 'balance': 'Saldo',
        }

        # Hoja 1: Resumen por Tercero
        ws1 = wb.active
        ws1.title = "Resumen por Tercero"

        headers1 = ['NIT/CC', 'Tercero', 'Concepto', 'Columna', 'Formula',
                     'Total debito', 'Total credito', 'Total formula', 'Lineas']
        for col, header in enumerate(headers1, 1):
            cell = ws1.cell(row=1, column=col, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.border = thin_border

        widths1 = [15, 40, 12, 30, 15, 18, 18, 18, 10]
        for i, w in enumerate(widths1, 1):
            ws1.column_dimensions[get_column_letter(i)].width = w

        for idx, line in enumerate(self.summary_line_ids, 2):
            ws1.cell(row=idx, column=1, value=line.partner_vat).border = thin_border
            ws1.cell(row=idx, column=2, value=line.partner_name[:60] if line.partner_name else '').border = thin_border
            ws1.cell(row=idx, column=3, value=line.concept_code).border = thin_border
            ws1.cell(row=idx, column=4, value=line.field_name).border = thin_border
            ws1.cell(row=idx, column=5, value=formula_labels.get(line.formula, line.formula)).border = thin_border
            ws1.cell(row=idx, column=6, value=round(line.total_debit, 2)).border = thin_border
            ws1.cell(row=idx, column=7, value=round(line.total_credit, 2)).border = thin_border
            ws1.cell(row=idx, column=8, value=round(line.total_formula, 2)).border = thin_border
            ws1.cell(row=idx, column=9, value=line.line_count).border = thin_border

        total_row = len(self.summary_line_ids) + 2
        ws1.cell(row=total_row, column=1, value='TOTAL').font = total_font
        ws1.cell(row=total_row, column=1).fill = summary_fill
        ws1.cell(row=total_row, column=6, value=round(self.total_debit, 2)).font = total_font
        ws1.cell(row=total_row, column=6).fill = summary_fill
        ws1.cell(row=total_row, column=7, value=round(self.total_credit, 2)).font = total_font
        ws1.cell(row=total_row, column=7).fill = summary_fill
        ws1.cell(row=total_row, column=8, value=round(self.total_formula, 2)).font = total_font
        ws1.cell(row=total_row, column=8).fill = summary_fill
        ws1.cell(row=total_row, column=9, value=self.total_lines).font = total_font
        ws1.cell(row=total_row, column=9).fill = summary_fill

        # Hoja 2: Detalle
        ws2 = wb.create_sheet("Detalle")

        headers2 = ['NIT/CC', 'Tercero', 'Concepto', 'Columna', 'Cuenta',
                     'Asiento', 'Fecha', 'Debito', 'Credito', 'Formula', 'Valor']
        for col, header in enumerate(headers2, 1):
            cell = ws2.cell(row=1, column=col, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.border = thin_border

        widths2 = [15, 35, 12, 25, 30, 20, 12, 16, 16, 12, 16]
        for i, w in enumerate(widths2, 1):
            ws2.column_dimensions[get_column_letter(i)].width = w

        for idx, line in enumerate(self.detail_line_ids, 2):
            ws2.cell(row=idx, column=1, value=line.partner_vat).border = thin_border
            ws2.cell(row=idx, column=2, value=line.partner_name[:50] if line.partner_name else '').border = thin_border
            ws2.cell(row=idx, column=3, value=line.concept_code).border = thin_border
            ws2.cell(row=idx, column=4, value=line.field_name).border = thin_border
            ws2.cell(row=idx, column=5, value=line.account_display).border = thin_border
            ws2.cell(row=idx, column=6, value=line.move_display).border = thin_border
            ws2.cell(row=idx, column=7, value=str(line.date) if line.date else '').border = thin_border
            ws2.cell(row=idx, column=8, value=round(line.debit, 2)).border = thin_border
            ws2.cell(row=idx, column=9, value=round(line.credit, 2)).border = thin_border
            ws2.cell(row=idx, column=10, value=formula_labels.get(line.formula_type, line.formula_type)).border = thin_border
            ws2.cell(row=idx, column=11, value=round(line.formula_value, 2)).border = thin_border

        output = io.BytesIO()
        wb.save(output)

        file_name = f"auxiliar_tercero_{self.format_id.code}.xlsx"
        self.binary_file = base64.b64encode(output.getvalue())
        self.binary_file_name = file_name

        return {
            'type': 'ir.actions.act_window',
            'name': _('Auxiliar por tercero - %s') % self.format_id.code,
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }


class L10nCoExogenousPartnerAuditSummary(models.TransientModel):
    """Resumen por tercero del auxiliar"""
    _name = 'l10n_co.exogenous_partner_audit_wizard.summary'
    _description = 'Resumen por tercero auxiliar'
    _order = 'partner_name, concept_code, field_name'

    wizard_id = fields.Many2one(
        'l10n_co.exogenous_partner_audit_wizard',
        required=True, ondelete='cascade')
    partner_id = fields.Integer(string='ID tercero')
    partner_vat = fields.Char(string='NIT/CC')
    partner_name = fields.Char(string='Tercero')
    concept_code = fields.Char(string='Concepto')
    field_name = fields.Char(string='Columna')
    formula = fields.Char(string='Formula')
    total_debit = fields.Float(string='Total debito', digits=(16, 2))
    total_credit = fields.Float(string='Total credito', digits=(16, 2))
    total_formula = fields.Float(string='Total formula', digits=(16, 2))
    line_count = fields.Integer(string='Lineas')


class L10nCoExogenousPartnerAuditLine(models.TransientModel):
    """Linea de detalle del auxiliar por tercero"""
    _name = 'l10n_co.exogenous_partner_audit_wizard.line'
    _description = 'Linea de detalle auxiliar por tercero'
    _order = 'partner_name, concept_code, field_name, date'

    wizard_id = fields.Many2one(
        'l10n_co.exogenous_partner_audit_wizard',
        required=True, ondelete='cascade')
    partner_id = fields.Integer(string='ID tercero')
    partner_vat = fields.Char(string='NIT/CC')
    partner_name = fields.Char(string='Tercero')
    concept_code = fields.Char(string='Concepto')
    field_name = fields.Char(string='Columna')
    account_display = fields.Char(string='Cuenta')
    move_display = fields.Char(string='Asiento')
    date = fields.Date(string='Fecha')
    debit = fields.Float(string='Debito', digits=(16, 2))
    credit = fields.Float(string='Credito', digits=(16, 2))
    formula_value = fields.Float(string='Valor formula', digits=(16, 2))
    formula_type = fields.Char(string='Formula')
