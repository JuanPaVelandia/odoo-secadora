from odoo import api, fields, models


class MrpBomByProduct(models.Model):
    """Costeo conjunto en molienda. Extiende el cost_share nativo del subproducto con
    un método de reparto: manual, por peso físico o por valor de mercado (VNR).
    """

    _inherit = "mrp.bom.byproduct"

    paramo_share_method = fields.Selection(
        [
            ("manual", "Manual"),
            ("weight", "Peso físico"),
            ("nrv", "Valor de mercado (VNR)"),
        ],
        string="Método de reparto",
        default="manual",
        help="Cómo se recalcula el cost_share al ejecutar 'Recalcular reparto' en la LdM.",
    )
    paramo_market_price = fields.Monetary(
        string="Precio de mercado (VNR)",
        help="Precio de venta de referencia por unidad, usado cuando el método es VNR.",
    )
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self.env.company.currency_id
    )


class MrpBom(models.Model):
    _inherit = "mrp.bom"

    paramo_main_market_price = fields.Monetary(
        string="Precio de mercado producto principal (VNR)",
        help="Precio de venta de referencia del producto principal de la LdM, usado en "
        "el reparto conjunto por VNR. Si está vacío se usa el precio de venta del "
        "producto.",
    )
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self.env.company.currency_id
    )

    def action_recompute_cost_share(self):
        """Recalcula el cost_share de los subproductos según su método de reparto,
        incluyendo al PRODUCTO PRINCIPAL en la base: Odoo asigna al principal el
        remanente (100 − Σ cost_share de subproductos), así que aquí cada subproducto
        recibe su proporción y el principal hereda la suya implícitamente.
        """
        for bom in self:
            byproducts = bom.byproduct_ids
            if not byproducts:
                continue
            method = byproducts[0].paramo_share_method
            main_qty = bom.product_qty
            if method == "weight":
                total = main_qty + sum(b.product_qty for b in byproducts)
                if total:
                    for b in byproducts:
                        b.cost_share = 100.0 * b.product_qty / total
            elif method == "nrv":
                main_price = (
                    bom.paramo_main_market_price
                    or bom.product_tmpl_id.list_price
                    or 0.0
                )
                total = main_price * main_qty + sum(
                    b.paramo_market_price * b.product_qty for b in byproducts
                )
                if total:
                    for b in byproducts:
                        b.cost_share = (
                            100.0 * (b.paramo_market_price * b.product_qty) / total
                        )
            # 'manual' no toca nada: respeta lo que puso el usuario.
        return True
