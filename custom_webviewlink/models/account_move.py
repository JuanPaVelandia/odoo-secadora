from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    x_webviewlink = fields.Char(
        string='Enlace documento Drive',
        help='URL del documento en Google Drive',
    )
    x_whatsapp_comprobante_link = fields.Char(
        string='Enlace comprobante Whatsapp',
        help='URL del comprobante de WhatsApp (Drive)',
    )
    x_whatsapp_mensaje = fields.Char(
        string='Mensaje de Whatsapp',
    )
