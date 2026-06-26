from odoo import fields, models


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    method_payment_id = fields.Many2one(
        "account.payment.method.dian",
        string="Metodo de Pago",
    )
