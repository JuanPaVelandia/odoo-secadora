# -*- coding: utf-8 -*-
"""
Modelo hr.labor.certificate.history - Historial de certificados laborales.
"""
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import base64

class HrLaborCertificateHistory(models.Model):
    _name = 'hr.labor.certificate.history'
    _description = 'Historico de certificados laborales generados'
    _order = 'contract_id,date_generation'

    contract_id = fields.Many2one('hr.contract', 'Contrato', required=True, ondelete='cascade')
    sequence = fields.Char(string="Secuencia", default="/", readonly=True)
    date_generation = fields.Date('Fecha generación', required=True)
    info_to = fields.Char(string='Dirigido a', required=True)
    pdf = fields.Binary(string='Certificado')
    pdf_name = fields.Char(string='Filename Certificado')

    _labor_certificate_history_uniq = models.Constraint('unique(contract_id, sequence)', 'Ya existe un certificado con esta secuencia, por favor verificar.')

    @api.depends('sequence', 'contract_id', 'contract_id.name')
    def _compute_display_name(self):
        for record in self:
            contract_name = record.contract_id.name if record.contract_id else ''
            record.display_name = "Certificado {} de {}".format(record.sequence, contract_name)

    def get_hr_labor_certificate_template(self):
        obj = self.env['hr.labor.certificate.template'].search([('company_id','=',self.contract_id.employee_id.company_id.id)])
        if len(obj) == 0:
            raise ValidationError(_('No tiene configurada plantilla de certificado laboral. Por favor verifique!'))
        return obj

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals['sequence'] = self.env['ir.sequence'].next_by_code('hr.labor.certificate.history.seq') or ' '
        obj_contract = super().create(vals_list)
        return obj_contract

    def generate_report(self):
        datas = {
            'ids': self.contract_id.ids,
            'model': 'hr.labor.certificate.history'
        }

        report_name = 'lavish_hr_employee.report_certificacion_laboral'
        pdf = self.env['ir.actions.report']._render_qweb_pdf("lavish_hr_employee.report_certificacion_laboral_action", self.id)[0] #self.env.ref('lavish_hr_employee.report_certificacion_laboral_action',False)._render_qweb_pdf(self.id)[0]
        pdf = base64.b64encode(pdf)
        self.pdf = pdf#base64.encodebytes(pdf)
        self.pdf_name = f'Certificado - {self.contract_id.name} - {self.sequence}.pdf'

        #Guardar en documentos
        # Crear adjunto
        name = f'Certificado - {self.contract_id.name} - {self.sequence}.pdf'


        return {
            'type': 'ir.actions.report',
            'report_name': report_name,
            'report_type': 'qweb-pdf',
            'datas': datas,
            # 'context': self._context
        }
