from odoo import fields, models


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    x_whatsapp_comprobante_link = fields.Char(
        string='Enlace comprobante Whatsapp',
        help='URL del comprobante de WhatsApp (Drive)',
    )
    x_whatsapp_mensaje = fields.Char(
        string='Mensaje de Whatsapp',
    )
