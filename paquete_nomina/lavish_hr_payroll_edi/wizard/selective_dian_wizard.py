# -*- coding: utf-8 -*-
"""
Wizard para validación parcial/selectiva de envío a DIAN.
Permite seleccionar documentos específicos para enviar y ver errores de validación.
"""
from odoo import api, fields, models, _
from odoo.exceptions import UserError

import logging
_logger = logging.getLogger(__name__)


class HrPayslipEdiSelectiveDian(models.TransientModel):
    _name = 'hr.payslip.edi.selective.dian'
    _description = 'Wizard Envío Selectivo DIAN'

    run_id = fields.Many2one(
        'hr.payslip.edi.run', string='Lote',
    )
    line_ids = fields.One2many(
        'hr.payslip.edi.selective.dian.line', 'wizard_id',
        string='Documentos',
    )
    total_selected = fields.Integer(
        string='Seleccionados', compute='_compute_totals',
    )
    total_ready = fields.Integer(
        string='Listos para enviar', compute='_compute_totals',
    )
    total_errors = fields.Integer(
        string='Con errores', compute='_compute_totals',
    )

    @api.depends('line_ids', 'line_ids.selected', 'line_ids.validation_status')
    def _compute_totals(self):
        for rec in self:
            selected = rec.line_ids.filtered('selected')
            rec.total_selected = len(selected)
            rec.total_ready = len(selected.filtered(
                lambda l: l.validation_status == 'ok'
            ))
            rec.total_errors = len(selected.filtered(
                lambda l: l.validation_status == 'error'
            ))

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        run_id = res.get('run_id') or self.env.context.get('default_run_id')
        if run_id:
            run = self.env['hr.payslip.edi.run'].browse(run_id)
            slips = run.slip_ids.filtered(
                lambda s: s.state == 'done' and s.state_dian in ('por_notificar', 'error', 'rechazado')
            )
            lines = []
            for slip in slips:
                lines.append((0, 0, {
                    'payslip_edi_id': slip.id,
                    'selected': slip.state_dian == 'por_notificar',
                    'validation_status': 'pending',
                    'validation_errors': '',
                }))
            res['line_ids'] = lines
        return res

    def action_validate_selected(self):
        """Valida datos de los documentos seleccionados sin enviar."""
        self.ensure_one()
        generator = self.env['nomina.xml.generator']
        EdiLog = self.env['hr.payslip.edi.log']

        for line in self.line_ids.filtered('selected'):
            slip = line.payslip_edi_id
            errors = generator.validate_all(slip, raise_error=False)
            if errors:
                line.validation_status = 'error'
                line.validation_errors = '\n'.join(errors)
                EdiLog.log_validation(slip, errors)
            else:
                line.validation_status = 'ok'
                line.validation_errors = ''

        return {
            'type': 'ir.actions.act_window',
            'name': _('Envío Selectivo DIAN'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_send_selected(self):
        """Envía a DIAN solo los documentos seleccionados y listos."""
        self.ensure_one()
        selected = self.line_ids.filtered(
            lambda l: l.selected and l.validation_status != 'error'
        )
        if not selected:
            raise UserError(_(
                'No hay documentos seleccionados listos para enviar. '
                'Primero valide los datos.'
            ))

        errors_summary = []
        success_count = 0

        for line in selected:
            slip = line.payslip_edi_id
            try:
                slip.action_send_dian()
                success_count += 1
                line.validation_status = 'ok'
                line.validation_errors = 'Enviado exitosamente'
            except Exception as e:
                error_msg = str(e)
                _logger.error("Error enviando %s: %s", slip.number, error_msg)
                line.validation_status = 'error'
                line.validation_errors = error_msg
                errors_summary.append('%s (%s): %s' % (
                    slip.employee_id.name, slip.number, error_msg
                ))

        # Notificación
        msg = _('Enviados: %d/%d') % (success_count, len(selected))
        if errors_summary:
            msg += _('\nErrores:\n') + '\n'.join(errors_summary)

        if self.run_id:
            self.run_id.message_post(
                body='<strong>Envío selectivo DIAN:</strong><br/>' + msg.replace('\n', '<br/>'),
                message_type='comment',
                subtype_xmlid='mail.mt_note',
            )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Envío DIAN completado'),
                'message': msg,
                'type': 'success' if not errors_summary else 'warning',
                'sticky': bool(errors_summary),
            }
        }


class HrPayslipEdiSelectiveDianLine(models.TransientModel):
    _name = 'hr.payslip.edi.selective.dian.line'
    _description = 'Línea Wizard Envío Selectivo DIAN'

    wizard_id = fields.Many2one(
        'hr.payslip.edi.selective.dian', string='Wizard',
        required=True, ondelete='cascade',
    )
    payslip_edi_id = fields.Many2one(
        'hr.payslip.edi', string='Documento', required=True,
    )
    employee_id = fields.Many2one(
        related='payslip_edi_id.employee_id',
    )
    number = fields.Char(related='payslip_edi_id.number')
    state_dian = fields.Selection(
        related='payslip_edi_id.state_dian',
    )
    total_paid = fields.Float(related='payslip_edi_id.total_paid')
    selected = fields.Boolean(string='Enviar', default=True)
    validation_status = fields.Selection([
        ('pending', 'Pendiente'),
        ('ok', 'Listo'),
        ('error', 'Error'),
    ], string='Validación', default='pending')
    validation_errors = fields.Text(string='Errores')
