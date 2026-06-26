# -*- coding: utf-8 -*-
"""
Wizard para crear notas de ajuste masivas.
"""
from datetime import date

from odoo import api, fields, models, _
from odoo.exceptions import UserError

import logging
_logger = logging.getLogger(__name__)


class HrPayslipEdiBatchAdjustment(models.TransientModel):
    _name = 'hr.payslip.edi.batch.adjustment'
    _description = 'Wizard Ajuste Masivo Nómina Electrónica'

    source_ids = fields.Many2many(
        'hr.payslip.edi', string='Documentos a Ajustar',
        domain="[('state_dian', '=', 'exitoso'), ('credit_note', '=', False)]",
    )
    type_note = fields.Selection([
        ('1', 'Reemplazar'),
        ('2', 'Eliminar'),
    ], string='Tipo de Nota', default='1', required=True)
    adjustment_reason = fields.Text(
        string='Razón del Ajuste', required=True,
    )
    create_new_run = fields.Boolean(
        string='Crear Nuevo Lote', default=True,
    )
    new_run_name = fields.Char(string='Nombre del Lote')
    payslip_run_id = fields.Many2one(
        'hr.payslip.edi.run', string='Lote Existente',
        domain="[('state', '=', 'draft')]",
    )
    deadline_warning = fields.Char(
        string='Alerta de Plazo', compute='_compute_deadline_warning',
    )

    @api.depends('source_ids')
    def _compute_deadline_warning(self):
        today = date.today()
        for rec in self:
            if today.day > 10 and rec.source_ids:
                # Verificar si hay documentos de períodos anteriores
                prev_month_docs = rec.source_ids.filtered(
                    lambda s: s.date_to and s.date_to.month < today.month
                )
                if prev_month_docs:
                    rec.deadline_warning = _(
                        'Atención: Se recomienda enviar ajustes antes del día 10 '
                        'del mes siguiente al período. Hay %d documentos de períodos '
                        'anteriores seleccionados.'
                    ) % len(prev_month_docs)
                else:
                    rec.deadline_warning = False
            else:
                rec.deadline_warning = False

    def action_create_batch_adjustments(self):
        """Crea notas de ajuste para los documentos seleccionados."""
        self.ensure_one()
        if not self.source_ids:
            raise UserError(_('Debe seleccionar al menos un documento para ajustar.'))

        # Crear o usar lote existente
        run = False
        if self.create_new_run:
            if not self.new_run_name:
                raise UserError(_('Debe ingresar un nombre para el nuevo lote.'))
            run = self.env['hr.payslip.edi.run'].create({
                'name': self.new_run_name,
                'date_start': min(self.source_ids.mapped('date_from')),
                'date_end': max(self.source_ids.mapped('date_to')),
                'credit_note': True,
                'company_id': self.source_ids[0].company_id.id,
            })
        elif self.payslip_run_id:
            run = self.payslip_run_id

        adjustments = self.env['hr.payslip.edi']
        errors = []

        for source in self.source_ids:
            try:
                # Obtener secuencia
                company = source.company_id
                sequence = company.sequence_payroll_note_id or company.sequence_payroll_id
                if not sequence:
                    errors.append(_(
                        '%s: No hay secuencia de notas de ajuste configurada'
                    ) % source.employee_id.name)
                    continue

                number = sequence.next_by_id()

                copy_vals = {
                    'name': _('Ajuste Masivo - %s') % source.name,
                    'number': number,
                    'credit_note': True,
                    'type_note': self.type_note,
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
                }

                if run:
                    copy_vals['payslip_run_id'] = run.id

                adjustment = source.copy(copy_vals)

                # Para tipo Reemplazar: copiar líneas, worked_days, payslips
                if self.type_note == '1':
                    for line in source.line_ids:
                        line.copy({'slip_id': adjustment.id})

                    for wd in source.worked_days_line_ids:
                        wd.copy({'payslip_id': adjustment.id})

                    if source.payslip_ids:
                        adjustment.payslip_ids = [(6, 0, source.payslip_ids.ids)]

                    adjustment.update_total()

                adjustments |= adjustment

            except Exception as e:
                _logger.error(
                    "Error creando ajuste para %s (%s): %s",
                    source.employee_id.name, source.number, str(e)
                )
                errors.append('%s (%s): %s' % (
                    source.employee_id.name, source.number, str(e)
                ))

        # Mostrar resultado
        if errors:
            error_msg = _('Se crearon %d ajustes con %d errores:\n%s') % (
                len(adjustments), len(errors), '\n'.join(errors)
            )
            if run:
                run.message_post(body=error_msg)

        if run:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Lote de Ajustes'),
                'res_model': 'hr.payslip.edi.run',
                'res_id': run.id,
                'view_mode': 'form',
                'target': 'current',
            }
        elif adjustments:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Notas de Ajuste Creadas'),
                'res_model': 'hr.payslip.edi',
                'view_mode': 'list,form',
                'domain': [('id', 'in', adjustments.ids)],
                'target': 'current',
            }
        else:
            raise UserError(_('No se pudieron crear ajustes:\n%s') % '\n'.join(errors))
