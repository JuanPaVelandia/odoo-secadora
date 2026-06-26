# -*- coding: utf-8 -*-
"""
Wizard para reintentar envío de Nómina Electrónica a DIAN.
Muestra comparación de valores y opciones de consulta/reenvío.
"""
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HrPayslipEdiRetryWizard(models.TransientModel):
    _name = 'hr.payslip.edi.retry.wizard'
    _description = 'Wizard Reintentar Envío DIAN'

    payslip_edi_id = fields.Many2one(
        'hr.payslip.edi', string='Nómina Electrónica',
        required=True, ondelete='cascade'
    )
    comparison_text = fields.Text(
        string='Comparación de Valores',
        readonly=True
    )
    has_zipkey = fields.Boolean(string='Tiene ZipKey')
    zipkey = fields.Char(string='ZipKey', readonly=True)

    action_type = fields.Selection([
        ('consult', 'Consultar Estado en DIAN'),
        ('retry', 'Reintentar Envío'),
        ('recover', 'Recuperar y Reenviar'),
    ], string='Acción', default='consult',
        help='Consultar: Verificar si el documento ya fue procesado en DIAN.\n'
             'Reintentar: Enviar nuevamente el documento.\n'
             'Recuperar: Limpiar errores y preparar para reenvío.')

    def action_execute(self):
        """Ejecuta la acción seleccionada."""
        self.ensure_one()
        payslip = self.payslip_edi_id

        if self.action_type == 'consult':
            return payslip.action_consult_dian_status()

        elif self.action_type == 'retry':
            if payslip.state_dian == 'exitoso':
                raise UserError(_('Este documento ya fue validado. No se puede reenviar.'))
            payslip.write({'resend': True})
            generator = self.env['nomina.xml.generator']
            generator.send_to_dian(payslip)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Envío Completado'),
                    'message': _('El documento fue enviado. Revise el estado DIAN.'),
                    'type': 'success',
                    'sticky': False,
                    'next': {'type': 'ir.actions.client', 'tag': 'reload'},
                }
            }

        elif self.action_type == 'recover':
            payslip.write({
                'state_dian': 'por_notificar',
                'resend': True,
                'response_message_dian': (payslip.response_message_dian or '') +
                    '\n--- Recuperado para reenvío ---\n',
                'xml_sended': False,
                'xml_response_dian': False,
                'current_cune': False,
                'ZipKey': False,
                'name_xml': False,
                'name_zip': False,
            })
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Documento Recuperado'),
                    'message': _('El documento fue limpiado y está listo para reenvío.'),
                    'type': 'success',
                    'sticky': False,
                    'next': {'type': 'ir.actions.client', 'tag': 'reload'},
                }
            }
