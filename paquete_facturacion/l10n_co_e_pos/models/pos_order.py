# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PosOrder(models.Model):
    _inherit = "pos.order"

    l10n_co_edi_nc_type = fields.Selection(
        [
            ("1", "Devolución parcial de los bienes y/o no aceptación parcial del servicio"),
            ("2", "Anulación de la factura electrónica"),
            ("3", "Rebaja total aplicada"),
            ("4", "Descuento parcial o total"),
            ("5", "Rescisión: nulidad por falta de requisitos"),
            ("6", "Otros"),
        ],
        string="Tipo de Nota Crédito",
        help="Concepto de corrección para notas crédito según DIAN",
        copy=False,
    )

    @api.model
    def _order_fields(self, ui_order):
        """Persist extra fields coming from the POS UI JSON payload.

        Without this mapping, the UI can set/export the value but it won't be
        written on `pos.order`, causing backend validations (invoice/refund) to
        fail.
        """
        res = super()._order_fields(ui_order)
        res["l10n_co_edi_nc_type"] = ui_order.get("l10n_co_edi_nc_type") or False
        return res

    # Campos DIAN para caché (se llenan después de crear la factura)
    # MEJORA: Campos ampliados para evitar consultas a account.move
    dian_number = fields.Char(string="Número DIAN", readonly=True, copy=False, index=True)
    dian_cufe = fields.Char(string="CUFE", readonly=True, copy=False, index=True)
    dian_co_qr_data = fields.Char(string="QR Data", readonly=True, copy=False)
    dian_ei_is_valid = fields.Boolean(string="EI Válido", readonly=True, copy=False)
    dian_state_dian_document = fields.Char(string="Estado Documento DIAN", readonly=True, copy=False)

    # Datos de resolución DIAN
    dian_resolution_number = fields.Char(string="Número Resolución DIAN", readonly=True, copy=False)
    dian_resolution_date = fields.Date(string="Fecha Resolución DIAN", readonly=True, copy=False)
    dian_resolution_date_to = fields.Date(string="Fecha Fin Resolución", readonly=True, copy=False)
    dian_resolution_number_to = fields.Char(string="Número Hasta", readonly=True, copy=False)
    dian_resolution_number_from = fields.Char(string="Número Desde", readonly=True, copy=False)

    # Fechas y referencias
    dian_invoice_date = fields.Date(string="Fecha Factura DIAN", readonly=True, copy=False, index=True)
    dian_invoice_date_xml = fields.Char(string="Fecha XML", readonly=True, copy=False)
    dian_invoice_date_due = fields.Date(string="Fecha Vencimiento", readonly=True, copy=False)
    dian_invoice_origin = fields.Char(string="Origen Factura", readonly=True, copy=False)
    dian_ref = fields.Char(string="Prefijo DIAN", readonly=True, copy=False)

    # Datos de la compañía
    dian_formated_nit = fields.Char(string="NIT Formateado", readonly=True, copy=False)
    dian_company_idname = fields.Char(string="Nombre Compañía", readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        """Sanitizar valores vacíos para campos Date antes de crear"""
        for vals in vals_list:
            # Convertir cadenas vacías a False para campos Date
            date_fields = [
                'dian_resolution_date',
                'dian_resolution_date_to',
                'dian_invoice_date',
                'dian_invoice_date_due',
            ]
            for field in date_fields:
                if vals.get(field) == '':
                    vals[field] = False
        return super().create(vals_list)

    def _export_for_ui(self, order):
        res = super()._export_for_ui(order)

        # Datos básicos
        res.update({
            "pos_number": order.name,
            "l10n_co_edi_nc_type": order.l10n_co_edi_nc_type,
        })

        # MEJORA: Usar datos cacheados primero, luego account_move como fallback
        # Esto asegura que los datos persistan en reimpresiones
        res.update({
            # Datos principales
            "dian_number": order.dian_number or (order.account_move.name if order.account_move else False),
            "dian_cufe": order.dian_cufe or (order.account_move.cufe if order.account_move else False),
            "dian_co_qr_data": (order.dian_co_qr_data if order.dian_co_qr_data and order.dian_co_qr_data.startswith('data:') else None) or (order.account_move._get_qr_image_data_uri() if order.account_move else False),
            "dian_ei_is_valid": order.dian_ei_is_valid or (order.account_move.journal_id.sequence_id.use_dian_control if order.account_move else False),
            "dian_state_dian_document": order.dian_state_dian_document or (order.account_move.state_dian_document if order.account_move else False),

            # Resolución DIAN
            "dian_resolution_number": order.dian_resolution_number or (order.account_move.resolution_number if order.account_move else False),
            "dian_resolution_date": order.dian_resolution_date or (order.account_move.resolution_date if order.account_move else False),
            "dian_resolution_date_to": order.dian_resolution_date_to or (order.account_move.resolution_date_to if order.account_move else False),
            "dian_resolution_number_to": order.dian_resolution_number_to or (order.account_move.resolution_number_to if order.account_move else False),
            "dian_resolution_number_from": order.dian_resolution_number_from or (order.account_move.resolution_number_from if order.account_move else False),

            # Fechas y referencias
            "dian_invoice_date": order.dian_invoice_date or (order.account_move.invoice_date if order.account_move else False),
            "dian_invoice_date_xml": order.dian_invoice_date_xml or (order.account_move.fecha_xml if order.account_move else False),
            "dian_invoice_date_due": order.dian_invoice_date_due or (order.account_move.invoice_date_due if order.account_move else False),
            "dian_invoice_origin": order.dian_invoice_origin or (order.account_move.invoice_origin if order.account_move else False),
            "dian_ref": order.dian_ref or (order.account_move.ref if order.account_move else False),

            # Datos de la compañía
            "dian_formatedNit": order.dian_formated_nit or (order.account_move.company_id.partner_id.vat if order.account_move else False),
            "dian_company_idname": order.dian_company_idname or (order.account_move.company_id.partner_id.name if order.account_move else False),
        })

        return res

    def get_invoice(self):
        import logging
        _logger = logging.getLogger(__name__)

        self.ensure_one()
        _logger.info(f"=== DEBUG get_invoice() para order {self.id} ===")
        _logger.info(f"Order name: {self.name}")
        _logger.info(f"Account move exists: {bool(self.account_move)}")

        if self.account_move:
            _logger.info(f"Account move ID: {self.account_move.id}")
            _logger.info(f"Account move name: {self.account_move.name}")
            _logger.info(f"Invoice date: {self.account_move.invoice_date}")
            _logger.info(f"CUFE: {self.account_move.cufe}")
            _logger.info(f"Resolution number: {self.account_move.resolution_number}")

            vals = {
                "number": self.account_move.name,
                "cufe": self.account_move.cufe,
                "co_qr_data": self.account_move.diancode_id.qr_data if self.account_move.diancode_id else False,
                "ei_is_valid": self.account_move.journal_id.sequence_id.use_dian_control
                or False,
                "state_dian_document": self.account_move.state_dian_document,
                "resolution_number": self.account_move.resolution_number,
                "resolution_date": self.account_move.resolution_date,
                "resolution_date_to": self.account_move.resolution_date_to,
                "resolution_number_to": self.account_move.resolution_number_to,
                "resolution_number_from": self.account_move.resolution_number_from,
                "invoice_date": self.account_move.invoice_date,
                "invoice_date_xml": self.account_move.fecha_xml,
                "invoice_date_due": self.account_move.invoice_date_due,
                "invoice_origin": self.account_move.invoice_origin,
                "ref": self.account_move.ref,
                "formatedNit": self.account_move.company_id.partner_id.vat,
                "company_idname": self.account_move.company_id.partner_id.name,
                "pos_number": self.name,
            }
            _logger.info(f"Retornando vals con number: {vals.get('number')}, invoice_date: {vals.get('invoice_date')}")
        else:
            _logger.warning(f"Account move NO existe para order {self.id}")
            vals = {
                "pos_number": self.name,
            }
        return vals

    def action_pos_order_invoice(self):
        # EXTENDS 'point_of_sale'
        # Validación: Orden original debe estar facturada (patrón Perú)
        if self.company_id.country_code == 'CO' and self.refunded_order_id:
            if not self.refunded_order_id.account_move:
                raise UserError(_(
                    "No puede facturar esta nota crédito porque la orden original "
                    "aún no ha sido facturada.\n\n"
                    "Orden original: %s\n\n"
                    "Por favor, facture primero la orden original antes de crear la nota crédito."
                ) % self.refunded_order_id.name)

        return super().action_pos_order_invoice()

    def _prepare_invoice_vals(self):
        """
        Mapear tipo de NC a conceptos DIAN

        MEJORA: Validar tipo NC obligatorio para refunds
        """
        vals = super(PosOrder, self)._prepare_invoice_vals()
        vals['journal_id'] = self.session_id.config_id.electronic_invoice_journal_id.id
        vals['currency_id'] = self.currency_id.id

        # Validación: Tipo NC obligatorio para refunds
        if vals.get('move_type') == 'out_refund':
            # Fallback: si el POS no envió el concepto, usar "6" (Otros) para no bloquear la operación.
            # Esto mantiene compatibilidad mientras se corrige el flujo del popup en frontend.
            nc_type = self.l10n_co_edi_nc_type or "6"
            # El módulo `l10n_co_e_invoice` usa `concepto_credit_note` en account.move.
            # Guardamos el código (string) para que el EDI lo tome al generar el XML.
            vals["concepto_credit_note"] = nc_type

        return vals

    def _generate_pos_order_invoice(self):
        # Registrar órdenes sin factura para procesar DIAN después
        orders_to_dian = self.filtered(lambda o: not o.account_move and o.partner_id)

        # Delegar toda la lógica estándar (pagos, reconciliación, PDF) al super()
        result = super()._generate_pos_order_invoice()

        # Lógica DIAN post-facturación
        for order in orders_to_dian:
            new_move = order.account_move
            if not new_move:
                continue

            # Enviar a DIAN si aún no está exitoso
            if new_move.state_dian_document != 'exitoso':
                try:
                    new_move.sudo().with_company(order.company_id).with_context(
                        skip_invoice_sync=True
                    ).dian_send_invoice()
                except Exception as e:
                    _logger.warning("Error enviando a DIAN orden %s: %s", order.name, e)

            # Cachear campos DIAN en la orden para evitar consultas en reimpresión
            dian_vals = {
                "dian_number": new_move.name,
                "dian_cufe": new_move.cufe if hasattr(new_move, 'cufe') else False,
                "dian_co_qr_data": new_move._get_qr_image_data_uri() if hasattr(new_move, '_get_qr_image_data_uri') else False,
                "dian_ei_is_valid": new_move.journal_id.sequence_id.use_dian_control if new_move.journal_id and new_move.journal_id.sequence_id else False,
                "dian_state_dian_document": new_move.state_dian_document if hasattr(new_move, 'state_dian_document') else False,
                "dian_resolution_number": new_move.resolution_number if hasattr(new_move, 'resolution_number') else False,
                "dian_resolution_date": new_move.resolution_date if hasattr(new_move, 'resolution_date') else False,
                "dian_resolution_date_to": new_move.resolution_date_to if hasattr(new_move, 'resolution_date_to') else False,
                "dian_resolution_number_to": new_move.resolution_number_to if hasattr(new_move, 'resolution_number_to') else False,
                "dian_resolution_number_from": new_move.resolution_number_from if hasattr(new_move, 'resolution_number_from') else False,
                "dian_invoice_date": new_move.invoice_date,
                "dian_invoice_date_xml": new_move.fecha_xml if hasattr(new_move, 'fecha_xml') else False,
                "dian_invoice_date_due": new_move.invoice_date_due if new_move.invoice_date_due else False,
                "dian_invoice_origin": new_move.invoice_origin if new_move.invoice_origin else False,
                "dian_ref": new_move.ref if new_move.ref else False,
                "dian_formated_nit": new_move.company_id.partner_id.vat if new_move.company_id and new_move.company_id.partner_id else False,
                "dian_company_idname": new_move.company_id.partner_id.name if new_move.company_id and new_move.company_id.partner_id else False,
            }
            order.write(dian_vals)

        return result

    # -------------------------------------------------------------------------
    # BUSINESS METHODS (Smart Buttons)
    # -------------------------------------------------------------------------

    def action_view_dian_invoice(self):
        """Abre la factura DIAN asociada"""
        self.ensure_one()
        if not self.account_move:
            return {}

        return {
            'name': _('Factura DIAN'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.account_move.id,
            'target': 'current',
        }

    def action_view_refund_origin(self):
        """Abre la orden original del refund"""
        self.ensure_one()
        if not self.refunded_order_id:
            return {}

        return {
            'name': _('Orden Original'),
            'type': 'ir.actions.act_window',
            'res_model': 'pos.order',
            'view_mode': 'form',
            'res_id': self.refunded_order_id.id,
            'target': 'current',
        }


class PosOrderLineCustom(models.Model):
    _inherit = "pos.order.line"

    # Campos de precio con y sin impuestos
    price_unit_incl = fields.Monetary(
        string="Precio Unit. (c/IVA)",
        compute="_compute_price_unit_with_taxes",
        currency_field="currency_id",
        help="Precio unitario con impuestos incluidos"
    )

    price_unit_excl = fields.Monetary(
        string="Precio Unit. (s/IVA)",
        compute="_compute_price_unit_with_taxes",
        currency_field="currency_id",
        help="Precio unitario sin impuestos"
    )

    @api.depends('price_unit', 'tax_ids', 'tax_ids_after_fiscal_position')
    def _compute_price_unit_with_taxes(self):
        """Calcula precio unitario con y sin impuestos"""
        for line in self:
            # Usar tax_ids_after_fiscal_position si existe, sino tax_ids
            taxes = line.tax_ids_after_fiscal_position or line.tax_ids
            if taxes:
                tax_result = taxes._filter_taxes_by_company(
                    self.env.company
                ).compute_all(
                    line.price_unit,
                    product=line.product_id,
                    partner=self.env['res.partner']
                )
                line.price_unit_incl = tax_result['total_included']
                line.price_unit_excl = tax_result['total_excluded']
            else:
                line.price_unit_incl = line.price_unit
                line.price_unit_excl = line.price_unit

    def _export_for_ui(self, orderline):
        res = super()._export_for_ui(orderline)
        res.update(
            {
                "default_code": orderline.product_id.default_code,
                "uom_name": orderline.product_uom_id.name if orderline.product_uom_id else "",
            }
        )
        return res


class ResPartnerPosCoExtend(models.Model):
    _inherit = "res.partner"

    @api.model
    def _load_pos_data_fields(self, config):
        res = super()._load_pos_data_fields(config)
        if config.company_id.country_code == "CO":
            extra = [
                "first_name",
                "l10n_latam_identification_type_id",
                "second_name",
                "first_lastname",
                "second_lastname",
                "is_company",
                "city_id",
                "country_code",
                "category_id",
                "fiscal_responsability_ids",
                "tribute_id",
            ]
            for f in extra:
                if f not in res:
                    res.append(f)
        return res


class PosPaymentMethodCoExtend(models.Model):
    _inherit = "pos.payment.method"

    @api.model
    def _load_pos_data_fields(self, config):
        res = super()._load_pos_data_fields(config)
        if "method_payment_id" not in res:
            res.append("method_payment_id")
        return res


class AccountMove(models.Model):
    _inherit = "account.move"

    pos_order_ids = fields.One2many("pos.order", "account_move")
    pos_payment_ids = fields.One2many("pos.payment", "account_move_id")
    pos_refunded_invoice_ids = fields.Many2many(
        "account.move",
        "refunded_invoices",
        "refund_account_move",
        "original_account_move",
    )
    pos_session_id = fields.Many2one(
        "pos.session", string="POS Session", compute="_compute_pos_session"
    )

    def _compute_pos_order_count(self):
        for move in self:
            move.pos_order_count = len(move.pos_order_ids)

    def _compute_pos_payment_count(self):
        for move in self:
            move.pos_payment_count = len(move.pos_payment_ids)

    def _compute_pos_refunded_invoice_count(self):
        for move in self:
            # Buscar lineas de orden POS que reembolsan las ordenes de esta factura
            # Usamos refunded_orderline_id en pos.order.line que SI esta almacenado
            original_order_line_ids = move.pos_order_ids.mapped('lines').ids
            refund_lines = self.env['pos.order.line'].search([
                ('refunded_orderline_id', 'in', original_order_line_ids)
            ])
            refund_orders = refund_lines.mapped('order_id')
            move.pos_refunded_invoice_count = len(refund_orders)

    def _compute_pos_session(self):
        for move in self:
            pos_order = move.pos_order_ids and move.pos_order_ids[0] or False
            move.pos_session_id = pos_order and pos_order.session_id or False

    def _get_pos_payment_methods_display(self):
        """Retorna métodos de pago POS (nombres) para usar en reportes."""
        self.ensure_one()
        payments = self.pos_payment_ids
        if not payments and self.invoice_origin:
            pos_order = self.env['pos.order'].search([('name', '=', self.invoice_origin)], limit=1)
            if pos_order:
                payments = pos_order.payment_ids
        names = []
        for p in payments:
            pm = p.payment_method_id
            dian = pm.method_payment_id if pm else False
            if dian and dian.name:
                names.append(dian.name)
            elif pm and pm.name:
                names.append(pm.name)
        return ", ".join(names)

    def _compute_pos_payment_methods_display(self):
        for move in self:
            move.pos_payment_methods_display = move._get_pos_payment_methods_display()

    pos_order_count = fields.Integer(
        string="POS Orders", compute="_compute_pos_order_count"
    )
    pos_payment_count = fields.Integer(
        string="POS Payments", compute="_compute_pos_payment_count"
    )
    pos_refunded_invoice_count = fields.Integer(
        string="Refunded Invoices", compute="_compute_pos_refunded_invoice_count"
    )
    pos_payment_methods_display = fields.Char(
        string="POS Payment Methods",
        compute="_compute_pos_payment_methods_display",
    )

    def action_view_pos_orders(self):
        self.ensure_one()
        return {
            "name": "POS Orders",
            "type": "ir.actions.act_window",
            "view_mode": "list,form",
            "res_model": "pos.order",
            "domain": [("id", "in", self.pos_order_ids.ids)],
            "context": {"create": False},
        }

    def action_view_pos_payments(self):
        self.ensure_one()
        return {
            "name": "POS Payments",
            "type": "ir.actions.act_window",
            "view_mode": "list,form",
            "res_model": "pos.payment",
            "domain": [("id", "in", self.pos_payment_ids.ids)],
            "context": {"create": False},
        }

    def action_view_refunded_invoices(self):
        self.ensure_one()
        # Buscar lineas de orden POS que reembolsan las ordenes de esta factura
        # Usamos refunded_orderline_id en pos.order.line que SI esta almacenado
        original_order_line_ids = self.pos_order_ids.mapped('lines').ids
        refund_lines = self.env['pos.order.line'].search([
            ('refunded_orderline_id', 'in', original_order_line_ids)
        ])
        refund_orders = refund_lines.mapped('order_id')
        # Obtener las facturas relacionadas con estas ordenes de reembolso
        refund_invoice_ids = refund_orders.mapped('account_move').ids
        return {
            "name": "Refunded Invoices",
            "type": "ir.actions.act_window",
            "view_mode": "list,form",
            "res_model": "account.move",
            "domain": [("id", "in", refund_invoice_ids)],
            "context": {"create": False},
        }

    def action_view_pos_session(self):
        self.ensure_one()
        if self.pos_session_id:
            return {
                "name": "POS Session",
                "type": "ir.actions.act_window",
                "view_mode": "form",
                "res_model": "pos.session",
                "res_id": self.pos_session_id.id,
                "target": "current",
                "context": {"create": False},
            }
        return {}
