from odoo import models, fields

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    x_numero_tiquete = fields.Char(string='Número de Tiquete')
