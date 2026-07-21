from odoo import fields, models


class ParamoPuntoOperativo(models.Model):
    """Finca / punto operativo. Dimensión analítica que solo vive en el cultivo (1425).

    Si la finca es una compañía legal distinta de la secadora, la cosecha se resuelve
    como transferencia intercompañía (fase 4). En fase 1 basta con la cuenta analítica.
    """

    _name = "paramo.punto.operativo"
    _description = "Punto Operativo (finca)"
    _order = "name"

    name = fields.Char(required=True)
    code = fields.Char()
    analytic_account_id = fields.Many2one(
        "account.analytic.account",
        string="Cuenta analítica (Punto Operativo)",
        help="Cuenta del plan analítico 'Punto Operativo' asociada a esta finca. "
        "Todo costo de cultivo se distribuye a ella.",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Compañía-finca",
        help="Solo si la finca es una compañía legal distinta de la secadora. "
        "Deja vacío si el cultivo ocurre dentro de la misma compañía.",
    )
    active = fields.Boolean(default=True)
    cosecha_ids = fields.One2many("paramo.cosecha", "punto_operativo_id", string="Cosechas")
    cosecha_count = fields.Integer(compute="_compute_cosecha_count")

    def _compute_cosecha_count(self):
        for rec in self:
            rec.cosecha_count = len(rec.cosecha_ids)
