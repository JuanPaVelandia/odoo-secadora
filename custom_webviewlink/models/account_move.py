from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    x_webviewlink = fields.Char(
        string='Enlace documento Drive',
        help='URL del documento en Google Drive',
    )
