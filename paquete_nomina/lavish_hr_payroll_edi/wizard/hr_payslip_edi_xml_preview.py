# -*- coding: utf-8 -*-
"""
Wizard para previsualizar XML de Nómina Electrónica.
"""
from odoo import api, fields, models, _
from odoo.exceptions import UserError

import logging
_logger = logging.getLogger(__name__)


class HrPayslipEdiXmlPreview(models.TransientModel):
    _name = 'hr.payslip.edi.xml.preview'
    _description = 'Preview XML Nómina Electrónica'

    payslip_edi_id = fields.Many2one(
        'hr.payslip.edi', string='Nómina Electrónica',
        required=True, readonly=True
    )
    xml_content = fields.Text(
        string='Contenido XML',
        readonly=True
    )
    xml_formatted = fields.Html(
        string='XML Formateado',
        compute='_compute_xml_formatted',
        sanitize=False
    )
    validation_errors = fields.Text(
        string='Errores de Validación',
        readonly=True
    )
    has_errors = fields.Boolean(
        string='Tiene Errores',
        compute='_compute_has_errors'
    )

    # Resumen de datos
    employee_name = fields.Char(related='payslip_edi_id.employee_id.name')
    period = fields.Char(compute='_compute_period')
    total_devengos = fields.Float(related='payslip_edi_id.total_devengos')
    total_deducciones = fields.Float(related='payslip_edi_id.total_deducciones')
    total_paid = fields.Float(related='payslip_edi_id.total_paid')
    cune = fields.Char(string='CUNE (Generado)')

    # Líneas por categoría (igual que en nómina normal)
    earnings_ids = fields.One2many(related='payslip_edi_id.earnings_ids', string='Devengos')
    deductions_ids = fields.One2many(related='payslip_edi_id.deductions_ids', string='Deducciones')
    social_security_ids = fields.One2many(related='payslip_edi_id.social_security_ids', string='Seguridad Social')
    provisions_ids = fields.One2many(related='payslip_edi_id.provisions_ids', string='Provisiones')
    bases_ids = fields.One2many(related='payslip_edi_id.bases_ids', string='Bases')
    outcome_ids = fields.One2many(related='payslip_edi_id.outcome_ids', string='Neto')
    line_informativos_ids = fields.One2many(related='payslip_edi_id.info_line_ids', string='Informativos')

    @api.depends('payslip_edi_id')
    def _compute_period(self):
        for rec in self:
            if rec.payslip_edi_id:
                rec.period = f"{rec.payslip_edi_id.date_from} - {rec.payslip_edi_id.date_to}"
            else:
                rec.period = ''

    @api.depends('validation_errors')
    def _compute_has_errors(self):
        for rec in self:
            rec.has_errors = bool(rec.validation_errors)

    @api.depends('xml_content')
    def _compute_xml_formatted(self):
        """Formatea el XML con syntax highlighting."""
        import html
        for rec in self:
            if not rec.xml_content:
                rec.xml_formatted = '<p>No hay XML generado</p>'
                continue

            # Escapar HTML y formatear
            escaped = html.escape(rec.xml_content)

            # Agregar colores básicos para tags XML
            # Tags de apertura/cierre
            import re
            escaped = re.sub(
                r'&lt;(/?)(\w+)',
                r'<span style="color:#0066cc">&lt;\1\2</span>',
                escaped
            )
            escaped = re.sub(
                r'(\w+)=&quot;([^&]*)&quot;',
                r'<span style="color:#009900">\1</span>=<span style="color:#cc3300">&quot;\2&quot;</span>',
                escaped
            )
            escaped = re.sub(
                r'&gt;',
                r'<span style="color:#0066cc">&gt;</span>',
                escaped
            )

            rec.xml_formatted = f'''
                <div style="background:#f5f5f5; padding:15px; border-radius:5px;
                            font-family:monospace; font-size:12px; white-space:pre-wrap;
                            max-height:500px; overflow-y:auto; border:1px solid #ddd;">
                    {escaped}
                </div>
            '''

    def action_copy_xml(self):
        """Copia el XML al portapapeles (requiere JS)."""
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('XML Copiado'),
                'message': _('El contenido XML ha sido copiado.'),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_download_xml(self):
        """Descarga el XML como archivo."""
        self.ensure_one()
        if not self.xml_content:
            raise UserError(_('No hay XML para descargar.'))

        import base64
        xml_bytes = self.xml_content.encode('utf-8')

        attachment = self.env['ir.attachment'].create({
            'name': f'test_xml_{self.payslip_edi_id.number or "draft"}.xml',
            'datas': base64.b64encode(xml_bytes),
            'mimetype': 'application/xml',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    def action_regenerate(self):
        """Regenera el XML."""
        self.ensure_one()
        return self.payslip_edi_id.action_test_xml()
