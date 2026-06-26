# -*- coding: utf-8 -*-
"""
Wizard para crear notas de ajuste parciales.
Permite seleccionar conceptos específicos a modificar.
"""
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HrPayslipEdiPartialAdjustment(models.TransientModel):
    _name = 'hr.payslip.edi.partial.adjustment'
    _description = 'Wizard Ajuste Parcial Nómina Electrónica'

    source_edi_id = fields.Many2one(
        'hr.payslip.edi', string='Documento Original',
        required=True, readonly=True,
    )
    employee_id = fields.Many2one(
        related='source_edi_id.employee_id', string='Empleado',
    )
    adjustment_reason = fields.Text(
        string='Razón del Ajuste', required=True,
    )
    line_ids = fields.One2many(
        'hr.payslip.edi.partial.adjustment.line', 'wizard_id',
        string='Líneas',
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        source_id = res.get('source_edi_id') or self.env.context.get('default_source_edi_id')
        if source_id:
            source = self.env['hr.payslip.edi'].browse(source_id)
            lines = []
            for line in source.line_ids.filtered(lambda l: l.line_type == 'normal'):
                lines.append((0, 0, {
                    'selected': False,
                    'name': line.name,
                    'code': line.code,
                    'salary_rule_id': line.salary_rule_id.id,
                    'original_quantity': line.quantity,
                    'original_amount': line.amount,
                    'original_total': line.total,
                    'new_quantity': line.quantity,
                    'new_amount': line.amount,
                }))
            res['line_ids'] = lines
        return res

    def action_create_partial_adjustment(self):
        """Crea la nota de ajuste con las modificaciones seleccionadas."""
        self.ensure_one()
        source = self.source_edi_id

        selected_lines = self.line_ids.filtered('selected')
        if not selected_lines:
            raise UserError(_('Debe seleccionar al menos una línea para modificar.'))

        # Obtener secuencia
        company = source.company_id
        sequence = company.sequence_payroll_note_id or company.sequence_payroll_id
        if not sequence:
            raise UserError(_('Configure la secuencia de notas de ajuste en la compañía.'))
        number = sequence.next_by_id()

        # Crear nota de ajuste
        adjustment = source.copy({
            'name': _('Ajuste Parcial - %s') % source.name,
            'number': number,
            'credit_note': True,
            'type_note': '1',  # Reemplazar
            'previous_cune': source.current_cune,
            'current_cune': False,
            'ZipKey': False,
            'state': 'draft',
            'state_dian': 'por_notificar',
            'response_message_dian': False,
            'xml_response_dian': False,
            'xml_send_query_dian': False,
            'xml_sended': False,
            'name_xml': False,
            'name_zip': False,
            'resend': False,
            'parent_edi_id': source.id,
            'origin_edi_id': (source.origin_edi_id or source).id,
            'adjustment_note_description': self.adjustment_reason,
        })

        # Copiar TODAS las líneas (DIAN requiere documento completo tipo Reemplazar)
        # Mapeo de código -> línea wizard para saber cuáles modificar
        modified_codes = {l.code: l for l in selected_lines}

        for line in source.line_ids:
            vals = {'slip_id': adjustment.id}
            wiz_line = modified_codes.get(line.code)
            if wiz_line:
                vals['quantity'] = wiz_line.new_quantity
                vals['amount'] = wiz_line.new_amount
            line.copy(vals)

        # Copiar días trabajados
        for wd in source.worked_days_line_ids:
            wd.copy({'payslip_id': adjustment.id})

        # Copiar nóminas relacionadas
        if source.payslip_ids:
            adjustment.payslip_ids = [(6, 0, source.payslip_ids.ids)]

        # Recalcular totales
        adjustment.update_total()

        # Postear en chatter del padre qué conceptos se modificaron
        modified_names = ', '.join(selected_lines.mapped('name'))
        source.message_post(
            body=_(
                'Se creó nota de ajuste parcial <b>%s</b>. '
                'Conceptos modificados: %s. Razón: %s'
            ) % (adjustment.number, modified_names, self.adjustment_reason),
            message_type='comment',
            subtype_xmlid='mail.mt_note',
        )

        return {
            'type': 'ir.actions.act_window',
            'name': _('Nota de Ajuste Parcial'),
            'res_model': 'hr.payslip.edi',
            'res_id': adjustment.id,
            'view_mode': 'form',
            'target': 'current',
        }


class HrPayslipEdiPartialAdjustmentLine(models.TransientModel):
    _name = 'hr.payslip.edi.partial.adjustment.line'
    _description = 'Línea Wizard Ajuste Parcial'

    wizard_id = fields.Many2one(
        'hr.payslip.edi.partial.adjustment', string='Wizard',
        required=True, ondelete='cascade',
    )
    selected = fields.Boolean(string='Modificar', default=False)
    name = fields.Char(string='Concepto', readonly=True)
    code = fields.Char(string='Código', readonly=True)
    salary_rule_id = fields.Many2one(
        'hr.salary.rule', string='Regla Salarial', readonly=True,
    )
    original_quantity = fields.Float(string='Cant. Original', readonly=True)
    original_amount = fields.Float(string='Monto Original', readonly=True)
    original_total = fields.Float(string='Total Original', readonly=True)
    new_quantity = fields.Float(string='Cant. Nueva')
    new_amount = fields.Float(string='Monto Nuevo')
    new_total = fields.Float(
        string='Total Nuevo', compute='_compute_new_total',
    )
    difference = fields.Float(
        string='Diferencia', compute='_compute_new_total',
    )

    @api.depends('new_quantity', 'new_amount')
    def _compute_new_total(self):
        for line in self:
            line.new_total = line.new_quantity * line.new_amount
            line.difference = line.new_total - line.original_total
