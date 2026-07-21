from odoo import api, fields, models
from odoo.exceptions import UserError


class ParamoCosecha(models.Model):
    """Activo biológico vivo: una campaña de cultivo que acumula en 1425 y termina
    en un evento de cosecha que crea el costo/kg (D 1430 / C 1425) y da de baja el
    Punto Operativo, conservando la Cosecha como lote.
    """

    _name = "paramo.cosecha"
    _description = "Cosecha (activo biológico)"
    _inherit = ["mail.thread"]
    _order = "campaign desc, id desc"

    name = fields.Char(required=True, default="Nueva cosecha", tracking=True)
    campaign = fields.Char(
        string="Cosecha (campaña)",
        required=True,
        help="Dimensión Cosecha, p.ej. 2026-Secano. Sobrevive la mezcla del silo "
        "como lote del paddy si no se mezclan cosechas distintas.",
    )
    punto_operativo_id = fields.Many2one(
        "paramo.punto.operativo", string="Punto Operativo (finca)", required=True
    )
    analytic_cosecha_id = fields.Many2one(
        "account.analytic.account", string="Cuenta analítica (Cosecha)"
    )
    company_id = fields.Many2one(
        "res.company",
        string="Compañía-finca (cultivo)",
        required=True,
        default=lambda self: self.env.company,
        help="Compañía donde se acumula el cultivo en 1425.",
    )
    currency_id = fields.Many2one(related="company_id.currency_id")
    company_destino_id = fields.Many2one(
        "res.company",
        string="Compañía secadora (destino)",
        help="Compañía que recibe el paddy. Si difiere de la compañía-finca, la cosecha "
        "se transfiere intercompañía AL COSTO (sin margen intragrupo). "
        "Vacío = flujo interno en la misma compañía.",
    )
    is_intercompany = fields.Boolean(compute="_compute_is_intercompany", store=True)

    state = fields.Selection(
        [
            ("en_cultivo", "En cultivo"),
            ("cosechada", "Cosechada"),
            ("cerrada", "Cerrada"),
        ],
        default="en_cultivo",
        required=True,
        tracking=True,
    )

    account_biologico_id = fields.Many2one(
        "account.account",
        string="Cuenta activo biológico (1425)",
        help="Cuenta de balance donde se acumula el cultivo y desde la que se relieva "
        "en la cosecha.",
    )
    product_paddy_id = fields.Many2one(
        "product.product",
        string="Producto arroz seco (paddy)",
        domain="[('is_storable', '=', True)]",
        help="Producto almacenable que representa el arroz seco resultante de la cosecha.",
    )
    account_cxc_intercia_id = fields.Many2one(
        "account.account",
        string="CxC intercompañía (finca)",
        help="Cuenta por cobrar de la finca contra la secadora; recibe el débito que "
        "relieva 1425. Solo intercompañía.",
    )
    account_cxp_intercia_id = fields.Many2one(
        "account.account",
        string="CxP intercompañía (secadora)",
        help="Cuenta por pagar de la secadora contra la finca; contrapartida del ingreso "
        "del paddy a 1430. Solo intercompañía.",
    )

    kg_a_secadora = fields.Float(
        string="Kg húmedos a secadora", digits="Product Unit of Measure"
    )
    kg_secos = fields.Float(
        string="Kg secos (tras merma)", digits="Product Unit of Measure", readonly=True
    )

    acumulado_1425 = fields.Monetary(
        string="Acumulado 1425",
        compute="_compute_acumulado",
        help="Costo de cultivo acumulado en la analítica de esta finca + cosecha.",
    )
    acumulado_cierre = fields.Monetary(
        string="Acumulado al cierre",
        readonly=True,
        help="Foto del acumulado 1425 en el momento del cierre (el compute vuelve a 0 "
        "cuando la 1425 se relieva).",
    )
    costo_kg = fields.Monetary(string="Costo por kg", compute="_compute_costo_kg")
    merma_pct = fields.Float(string="Merma %", compute="_compute_merma")

    picking_id = fields.Many2one("stock.picking", readonly=True)
    lot_id = fields.Many2one("stock.lot", string="Lote (Cosecha)", readonly=True)
    account_move_id = fields.Many2one(
        "account.move", string="Asiento de cosecha (secadora)", readonly=True
    )
    move_finca_id = fields.Many2one(
        "account.move", string="Asiento relieve 1425 (finca)", readonly=True
    )

    @api.depends("company_destino_id", "company_id")
    def _compute_is_intercompany(self):
        for rec in self:
            rec.is_intercompany = bool(
                rec.company_destino_id and rec.company_destino_id != rec.company_id
            )

    @api.depends(
        "punto_operativo_id.analytic_account_id",
        "analytic_cosecha_id",
        "account_biologico_id",
        "state",
    )
    def _compute_acumulado(self):
        """Agrega los apuntes posteados en la cuenta 1425 cuya distribución analítica
        incluye la finca (y la cosecha, si está definida). No recalcula peso a peso:
        lee lo que Odoo ya registró al capitalizar el cultivo.
        """
        AML = self.env["account.move.line"]
        for rec in self:
            total = 0.0
            po = rec.punto_operativo_id.analytic_account_id
            if rec.account_biologico_id and po:
                lines = AML.search(
                    [
                        ("account_id", "=", rec.account_biologico_id.id),
                        ("company_id", "=", rec.company_id.id),
                        ("parent_state", "=", "posted"),
                    ]
                )
                cosecha_id = rec.analytic_cosecha_id.id
                for line in lines:
                    dist = line.analytic_distribution or {}
                    keys = set()
                    for combo in dist:
                        # las claves pueden ser "41" o "41,52" (multi-plan)
                        keys.update(int(k) for k in str(combo).split(","))
                    if po.id in keys and (not cosecha_id or cosecha_id in keys):
                        total += line.balance
            rec.acumulado_1425 = total

    @api.depends("acumulado_1425", "acumulado_cierre", "kg_secos", "state")
    def _compute_costo_kg(self):
        for rec in self:
            base = rec.acumulado_cierre if rec.state == "cerrada" else rec.acumulado_1425
            rec.costo_kg = base / rec.kg_secos if rec.kg_secos else 0.0

    @api.depends("kg_a_secadora", "kg_secos")
    def _compute_merma(self):
        for rec in self:
            if rec.kg_a_secadora:
                rec.merma_pct = 1.0 - (rec.kg_secos / rec.kg_a_secadora)
            else:
                rec.merma_pct = 0.0

    def action_open_close_wizard(self):
        self.ensure_one()
        if self.state == "cerrada":
            raise UserError("La cosecha ya está cerrada.")
        return {
            "type": "ir.actions.act_window",
            "name": "Cerrar cosecha (1425 → 1430)",
            "res_model": "paramo.cosecha.close",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_cosecha_id": self.id,
                "default_acumulado_1425": self.acumulado_1425,
                "default_kg_secos": self.kg_a_secadora,
            },
        }

    def action_view_move(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": self.account_move_id.id,
            "view_mode": "form",
        }

    def action_view_finca_move(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": self.move_finca_id.id,
            "view_mode": "form",
        }
