from odoo import api, fields, models
from odoo.exceptions import UserError


class ParamoCosechaClose(models.TransientModel):
    """Cierre de cosecha: 1425 → 1430, nace el costo/kg y se incorpora la merma.

    Mecánica (v0.2 — validada en Odoo 19; compatible 18):
      1. Lote = Cosecha (trazabilidad que sobrevive el silo).
      2. Recepción del paddy con price_unit = acumulado ÷ kg_secos → el costo/kg y la
         merma quedan resueltos en la propia capa de valoración (AVCO correcto).
      3. Asiento de contrapartida en la compañía destino:
         - Odoo 19 (sin stock.valuation.layer): la recepción no postea GL (el modelo de
           valoración ajusta la cuenta de inventario en el cierre), así que se postea
           directamente D 1430 / C (1425 mono | CxP intercompañía).
         - Odoo <=18 (con SVL): la recepción ya posteó D 1430 / C cuenta puente (stock
           input), así que la contrapartida es D cuenta puente / C (1425 | CxP).

    Camino intercompañía (finca ≠ secadora), transferencia AL COSTO:
       - En la SECADORA:  D 1430 / C CxP intercompañía
       - En la FINCA:     D CxC intercompañía / C 1425  (CON analítica Punto Operativo +
                          Cosecha → relieva también el saldo analítico)
       Las cuentas puente CxC(finca)/CxP(secadora) se netean en consolidación: cero margen.

    En ambos casos el Punto Operativo NO se propaga a 1430: la finca se pierde a
    propósito; sobreviven el costo/kg y el lote-Cosecha.
    """

    _name = "paramo.cosecha.close"
    _description = "Cerrar cosecha (1425 → 1430)"

    cosecha_id = fields.Many2one("paramo.cosecha", required=True)
    company_id = fields.Many2one(related="cosecha_id.company_id")
    currency_id = fields.Many2one(related="cosecha_id.currency_id")
    is_intercompany = fields.Boolean(related="cosecha_id.is_intercompany")
    acumulado_1425 = fields.Monetary(string="Acumulado 1425", readonly=True)
    kg_secos = fields.Float(
        string="Kg secos (tras merma)", required=True, digits="Product Unit of Measure"
    )
    costo_kg = fields.Monetary(string="Costo por kg (resultante)", compute="_compute_costo_kg")

    @api.depends("acumulado_1425", "kg_secos")
    def _compute_costo_kg(self):
        for w in self:
            w.costo_kg = w.acumulado_1425 / w.kg_secos if w.kg_secos else 0.0

    # ------------------------------------------------------------------ acción
    def action_confirm(self):
        self.ensure_one()
        cosecha = self.cosecha_id
        if not cosecha.product_paddy_id:
            raise UserError("Defina el producto arroz seco (paddy) en la cosecha.")
        if not cosecha.account_biologico_id:
            raise UserError("Defina la cuenta de activo biológico (1425) en la cosecha.")
        if self.kg_secos <= 0:
            raise UserError("Los kg secos deben ser mayores a cero.")

        inter = cosecha.is_intercompany
        if inter:
            if not (cosecha.account_cxc_intercia_id and cosecha.account_cxp_intercia_id):
                raise UserError(
                    "Intercompañía: defina las cuentas puente CxC (finca) y CxP (secadora)."
                )
            dest_company = cosecha.company_destino_id
            if dest_company not in self.env.user.company_ids:
                raise UserError(
                    "El usuario no tiene acceso a la compañía secadora '%s'. "
                    "Añádala a sus compañías permitidas." % dest_company.display_name
                )
            credit_account = cosecha.account_cxp_intercia_id
        else:
            dest_company = cosecha.company_id
            credit_account = cosecha.account_biologico_id

        lot = (
            self.env["stock.lot"]
            .with_company(dest_company)
            .create(
                {
                    "name": cosecha.campaign,
                    "product_id": cosecha.product_paddy_id.id,
                    "company_id": dest_company.id,
                }
            )
        )
        picking = self._create_receipt(cosecha, lot, dest_company)
        move_secadora = self._create_counterpart_move(
            cosecha, dest_company, credit_account
        )

        vals = {
            "kg_secos": self.kg_secos,
            "acumulado_cierre": self.acumulado_1425,
            "lot_id": lot.id,
            "picking_id": picking.id,
            "account_move_id": move_secadora.id,
            "state": "cerrada",
        }
        if inter:
            vals["move_finca_id"] = self._create_finca_relief(cosecha).id
        cosecha.write(vals)

        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": move_secadora.id,
            "view_mode": "form",
        }

    # ------------------------------------------------------------- helpers
    def _create_receipt(self, cosecha, lot, company):
        warehouse = (
            self.env["stock.warehouse"]
            .with_company(company)
            .search([("company_id", "=", company.id)], limit=1)
        )
        if not warehouse:
            raise UserError("No hay bodega configurada para la compañía '%s'." % company.display_name)
        picking_type = warehouse.in_type_id
        src = self.env.ref("stock.stock_location_suppliers")
        dest = picking_type.default_location_dest_id or warehouse.lot_stock_id
        product = cosecha.product_paddy_id

        move_vals = {
            "product_id": product.id,
            "product_uom_qty": self.kg_secos,
            "product_uom": product.uom_id.id,
            # Odoo <=18: el costo/kg entra por price_unit en la capa de valoración.
            # (En 19 price_unit ya no participa en la valoración; ver value_manual abajo.)
            "price_unit": self.costo_kg,
            "location_id": src.id,
            "location_dest_id": dest.id,
        }
        # Odoo <=18: stock.move llevaba 'name' obligatorio (eliminado en 19)
        if "name" in self.env["stock.move"]._fields:
            move_vals["name"] = product.display_name

        picking = (
            self.env["stock.picking"]
            .with_company(company)
            .create(
                {
                    "picking_type_id": picking_type.id,
                    "location_id": src.id,
                    "location_dest_id": dest.id,
                    "company_id": company.id,
                    "origin": cosecha.name,
                    "move_ids": [(0, 0, move_vals)],
                }
            )
        )
        picking.action_confirm()
        for move in picking.move_ids:
            move.move_line_ids.unlink()
            self.env["stock.move.line"].create(
                {
                    "move_id": move.id,
                    "product_id": move.product_id.id,
                    "quantity": self.kg_secos,
                    "lot_id": lot.id,
                    "location_id": move.location_id.id,
                    "location_dest_id": move.location_dest_id.id,
                    "picking_id": picking.id,
                }
            )
        picking.button_validate()

        # Odoo 19: la valoración ya no lee price_unit (cadena: valor manual → factura →
        # producción → cotización → std price). Se fija el valor total del movimiento
        # vía value_manual, que crea un product.value con prioridad máxima — el mismo
        # mecanismo del botón "Ajustar valoración" de la UI.
        if "stock.valuation.layer" not in self.env.registry:
            for move in picking.move_ids:
                move = move.with_company(company)
                move.value_manual = self.acumulado_1425
                move._set_value()  # refresca move.value y recalcula el costo promedio
        return picking

    def _create_counterpart_move(self, cosecha, company, credit_account):
        """D (1430 | cuenta puente) / C (1425 | CxP) en la compañía destino, por el
        acumulado completo del cultivo.
        """
        journal = self.env["account.journal"].search(
            [("type", "=", "general"), ("company_id", "=", company.id)], limit=1
        )
        if not journal:
            raise UserError(
                "No hay diario general en '%s' para el asiento de cosecha." % company.display_name
            )

        paddy = cosecha.product_paddy_id.with_company(company)
        accounts = paddy.product_tmpl_id.get_product_accounts()
        if "stock.valuation.layer" in self.env.registry:
            # Odoo <=18: la recepción acreditó la cuenta puente (stock input)
            debit_account = accounts.get("stock_input") or accounts["stock_valuation"]
        else:
            # Odoo 19: la recepción no postea GL → débito directo a valoración (1430)
            debit_account = accounts["stock_valuation"]
        if not debit_account:
            raise UserError("El producto paddy no tiene cuenta de valoración configurada.")

        amount = self.acumulado_1425
        move = (
            self.env["account.move"]
            .with_company(company)
            .create(
                {
                    "move_type": "entry",
                    "company_id": company.id,
                    "journal_id": journal.id,
                    "ref": "Cosecha %s · %s kg secos" % (cosecha.campaign, self.kg_secos),
                    "line_ids": [
                        (
                            0,
                            0,
                            {
                                "account_id": debit_account.id,
                                "name": "Paddy cosecha %s" % cosecha.campaign,
                                "debit": amount,
                                "credit": 0.0,
                            },
                        ),
                        (
                            0,
                            0,
                            {
                                "account_id": credit_account.id,
                                "name": "Costo cultivo %s" % cosecha.campaign,
                                "debit": 0.0,
                                "credit": amount,
                            },
                        ),
                    ],
                }
            )
        )
        move.action_post()
        return move

    def _create_finca_relief(self, cosecha):
        """Asiento en la FINCA: D CxC intercompañía / C 1425, con analítica Punto
        Operativo + Cosecha en la línea de 1425 para relevar también el saldo analítico.
        """
        finca = cosecha.company_id
        journal = self.env["account.journal"].search(
            [("type", "=", "general"), ("company_id", "=", finca.id)], limit=1
        )
        if not journal:
            raise UserError("No hay diario general en la finca '%s'." % finca.display_name)

        po_acc = cosecha.punto_operativo_id.analytic_account_id
        cosecha_acc = cosecha.analytic_cosecha_id
        distribution = False
        if po_acc and cosecha_acc:
            distribution = {"%s,%s" % (po_acc.id, cosecha_acc.id): 100.0}
        elif po_acc:
            distribution = {str(po_acc.id): 100.0}

        amount = self.acumulado_1425
        move = (
            self.env["account.move"]
            .with_company(finca)
            .create(
                {
                    "move_type": "entry",
                    "company_id": finca.id,
                    "journal_id": journal.id,
                    "ref": "Relieve cosecha %s → %s"
                    % (cosecha.campaign, cosecha.company_destino_id.display_name),
                    "line_ids": [
                        (
                            0,
                            0,
                            {
                                "account_id": cosecha.account_cxc_intercia_id.id,
                                "name": "CxC paddy %s" % cosecha.campaign,
                                "debit": amount,
                                "credit": 0.0,
                            },
                        ),
                        (
                            0,
                            0,
                            {
                                "account_id": cosecha.account_biologico_id.id,
                                "name": "Relieve activo biológico %s" % cosecha.campaign,
                                "debit": 0.0,
                                "credit": amount,
                                "analytic_distribution": distribution,
                            },
                        ),
                    ],
                }
            )
        )
        move.action_post()
        return move
