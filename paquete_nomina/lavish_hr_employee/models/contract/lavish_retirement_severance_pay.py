# -*- coding: utf-8 -*-
"""
Modelo lavish.retirement.severance.pay - Carta para retiro de cesantias.
"""
from odoo import models, fields
import base64

class LavishRetirementSeverancePay(models.Model):
    _name = 'lavish.retirement.severance.pay'
    _description = 'Carta para retiro de cesantías'

    def get_contrib_id(self):
        return self.env['hr.contribution.register'].search([('type_entities', '=', 'cesantias')], limit=1).id

    contract_id = fields.Many2one('hr.contract',string='Contrato')
    contrib_id = fields.Many2one('hr.contribution.register', 'Tipo Entidad', help='Concepto de aporte', required=True, default=get_contrib_id)
    directed_to = fields.Many2one('hr.employee.entities',string='Dirigido a', domain="[('types_entities','in',[contrib_id])]", required=True)
    withdrawal_value = fields.Float(string='Valor del retiro')
    withdrawal_concept_partial = fields.Selection([
        ('1', 'Educación Superior'),
        ('2', 'Educación para el Trabajo y el Desarrollo Humano'),
        ('3', 'Créditos del ICETEX'),
        ('4', 'Compra de lote o vivienda'),
        ('5', 'Reparaciones locativas'),
        ('6', 'Pago de créditos hipotecarios'),
        ('7', 'Pago de impuesto predial o de valorización')
    ], string="Concepto de retiro parcial")
    withdrawal_concept_total = fields.Selection([
        ('1', 'Terminación del contrato'),
        ('2', 'Llamamiento al servicio militar'),
        ('3', 'Adopción del sistema de salario integral'),
        ('4', 'Sustitución patronal'),
        ('5', 'Fallecimiento del afiliado')
    ],string="Concepto de retiro total")
    withdrawal_type = fields.Selection([
        ('termination', 'Retiro por terminación'),
        ('partial', 'Retiro parcial')
    ], string='Tipo de retiro')
    pdf = fields.Binary(string='Carta para retiro de cesantías')
    pdf_name = fields.Char(string='Filename Carta para retiro de cesantías')

    def generate_report_severance_pay(self):
        datas = {
            'id': self.id,
            'model': 'lavish.retirement.severance.pay'
        }

        report_name = 'lavish_hr_employee.report_retirement_severance_pay'
        pdf = self.env['ir.actions.report']._render_qweb_pdf("lavish_hr_employee.report_retirement_severance_pay_action", self.id)[0] #self.env.ref('lavish_hr_employee.report_retirement_severance_pay_action', False)._render_qweb_pdf(self.id)[0]
        pdf = base64.b64encode(pdf)
        self.pdf = pdf  # base64.encodebytes(pdf)
        self.pdf_name = f'Carta para retiro de cesantías - {self.contract_id.name}.pdf'

        # Guardar en documentos
        # Crear adjunto
        name = f'Carta para retiro de cesantías - {self.contract_id.name}.pdf'
        obj_attachment = self.env['ir.attachment'].create({
            'name': name,
            'store_fname': name,
            'res_name': name,
            'type': 'binary',
            'res_model': 'res.partner',
            'res_id': self.contract_id.employee_id.work_contact_id.id,
            'datas': pdf,
        })
        # Asociar adjunto a documento de Odoo
        cert = self.env.user.company_id.validated_certificate
        tag_ids = [int(cert)] if cert and cert.isdigit() else []
        doc_vals = {
            'name': name,
            'owner_id': self.contract_id.employee_id.user_id.id if self.contract_id.employee_id.user_id else self.env.user.id,
            'partner_id': self.contract_id.employee_id.work_contact_id.id,
            'folder_id': self.env.user.company_id.documents_hr_folder.id,
            'tag_ids': tag_ids,
            'type': 'binary',
            'attachment_id': obj_attachment.id
        }
        self.env['documents.document'].sudo().create(doc_vals)

        return {
            'type': 'ir.actions.report',
            'report_name': 'lavish_hr_employee.report_retirement_severance_pay',
            'report_type': 'qweb-pdf',
            'datas': datas
        }
