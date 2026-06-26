from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import formatLang


class TreasuryInternalTransfer(models.Model):
    _name = "treasury.internal.transfer"
    _description = "Transferencia Interna de Tesorería"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    name: str = fields.Char(
        string="Número",
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: _("Nuevo"),
    )
    state: str = fields.Selection(
        selection=[
            ("draft", "Borrador"),
            ("confirmed", "Confirmada"),
            ("received", "Recibida"),
            ("cancelled", "Cancelada"),
        ],
        string="Estado",
        default="draft",
        required=True,
        tracking=True,
        copy=False,
    )

    date = fields.Date(
        string="Fecha",
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    amount = fields.Monetary(string="Monto", required=True, tracking=True)
    currency_id = fields.Many2one(
        "res.currency",
        string="Moneda",
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
    )

    source_journal_id = fields.Many2one(
        "account.journal",
        string="Diario origen",
        required=True,
        tracking=True,
        check_company=True,
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
        help="Diario (banco o caja) desde el que sale el dinero.",
    )
    destination_journal_id = fields.Many2one(
        "account.journal",
        string="Diario destino",
        required=True,
        tracking=True,
        check_company=True,
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
        help="Diario (banco o caja) al que entra el dinero.",
    )

    reason: str = fields.Text(string="Motivo / Concepto", required=True, tracking=True)
    bank_reference: str = fields.Char(
        string="Referencia bancaria",
        help="Número de comprobante o referencia del movimiento (opcional).",
    )

    sender_user_id = fields.Many2one(
        "res.users",
        string="Responsable que envía",
        required=True,
        tracking=True,
        default=lambda self: self.env.user,
    )
    receiver_user_id = fields.Many2one(
        "res.users",
        string="Responsable que recibe",
        required=True,
        tracking=True,
        help="Persona que confirmará la recepción del dinero.",
    )

    received_user_id = fields.Many2one(
        "res.users",
        string="Recepción confirmada por",
        readonly=True,
        copy=False,
        tracking=True,
    )
    received_date = fields.Datetime(
        string="Fecha de recepción", readonly=True, copy=False
    )

    outbound_payment_id = fields.Many2one(
        "account.payment", string="Pago de salida", readonly=True, copy=False
    )
    inbound_payment_id = fields.Many2one(
        "account.payment", string="Cobro de entrada", readonly=True, copy=False
    )
    payment_count = fields.Integer(
        string="Pagos generados", compute="_compute_payment_count"
    )

    transfer_account_id = fields.Many2one(
        related="company_id.transfer_account_id",
        string="Cuenta de transferencia interna",
        readonly=True,
    )

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends("outbound_payment_id", "inbound_payment_id")
    def _compute_payment_count(self):
        for rec in self:
            rec.payment_count = len(rec.outbound_payment_id | rec.inbound_payment_id)

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------
    @api.constrains("amount")
    def _check_amount(self):
        for rec in self:
            if rec.amount <= 0:
                raise ValidationError(_("El monto debe ser mayor a cero."))

    @api.constrains("source_journal_id", "destination_journal_id")
    def _check_journals(self):
        for rec in self:
            if rec.source_journal_id and rec.source_journal_id == rec.destination_journal_id:
                raise ValidationError(
                    _("El diario origen y el diario destino deben ser diferentes.")
                )

    @api.constrains("source_journal_id", "destination_journal_id", "currency_id")
    def _check_currency(self):
        for rec in self:
            for journal in (rec.source_journal_id, rec.destination_journal_id):
                if not journal:
                    continue
                journal_currency = journal.currency_id or rec.company_id.currency_id
                if journal_currency != rec.currency_id:
                    raise ValidationError(
                        _(
                            "El diario «%(journal)s» opera en %(jcur)s, distinta a la "
                            "moneda de la transferencia (%(tcur)s). Las transferencias "
                            "deben hacerse en la misma moneda.",
                            journal=journal.name,
                            jcur=journal_currency.name,
                            tcur=rec.currency_id.name,
                        )
                    )

    # ------------------------------------------------------------------
    # Create (secuencia)
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("Nuevo")) == _("Nuevo"):
                vals["name"] = (
                    self.env["ir.sequence"].next_by_code("treasury.internal.transfer")
                    or _("Nuevo")
                )
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _prepare_payment_vals(self, payment_type, journal):
        """Valores para crear el account.payment.

        El partner_type se elige a propósito (outbound→customer, inbound→supplier)
        para NO disparar las secuencias de negocio (RC/CE) del módulo de tesorería:
        una transferencia interna no es un cobro de cliente ni un pago a proveedor.
        La contrapartida real (cuenta puente) se fuerza en action_confirm.
        """
        self.ensure_one()
        partner_type = "customer" if payment_type == "outbound" else "supplier"
        memo = "%s - %s" % (self.name, self.reason or "")
        if self.bank_reference:
            memo = "%s [%s]" % (memo, self.bank_reference)
        return {
            "payment_type": payment_type,
            "partner_type": partner_type,
            "journal_id": journal.id,
            "amount": self.amount,
            "date": self.date,
            "currency_id": self.currency_id.id,
            "company_id": self.company_id.id,
            "memo": memo[:2000],
        }

    def _get_transfer_account_lines(self, payments):
        transfer_account = self.company_id.transfer_account_id
        return payments.move_id.line_ids.filtered(
            lambda line: line.account_id == transfer_account
        )

    def _amount_label(self):
        self.ensure_one()
        return formatLang(self.env, self.amount, currency_obj=self.currency_id)

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def action_confirm(self):
        Payment = self.env["account.payment"]
        for rec in self:
            if rec.state != "draft":
                raise UserError(
                    _("Solo se pueden confirmar transferencias en estado Borrador.")
                )
            transfer_account = rec.company_id.transfer_account_id
            if not transfer_account:
                raise UserError(
                    _(
                        "No hay una Cuenta de transferencia interna configurada para la "
                        "empresa. Defínela en Contabilidad → Configuración → Ajustes "
                        "(sección de cuentas predeterminadas) para poder confirmar "
                        "transferencias."
                    )
                )

            out_pay = Payment.create(
                rec._prepare_payment_vals("outbound", rec.source_journal_id)
            )
            in_pay = Payment.create(
                rec._prepare_payment_vals("inbound", rec.destination_journal_id)
            )

            # Pareo nativo de transferencia interna (botón "Transferencia Destino").
            out_pay.paired_internal_transfer_payment_id = in_pay
            in_pay.paired_internal_transfer_payment_id = out_pay

            # Forzar la cuenta puente como contrapartida. Debe ser el ÚLTIMO write
            # antes de contabilizar para que el compute de destino no lo sobrescriba.
            out_pay.destination_account_id = transfer_account
            in_pay.destination_account_id = transfer_account

            payments = out_pay | in_pay
            payments.action_post()

            # Conciliar la cuenta puente: salida (débito) contra entrada (crédito).
            lines = rec._get_transfer_account_lines(payments).filtered(
                lambda line: not line.reconciled
            )
            if len(lines) > 1:
                lines.reconcile()

            rec.write(
                {
                    "outbound_payment_id": out_pay.id,
                    "inbound_payment_id": in_pay.id,
                    "state": "confirmed",
                }
            )
            rec.message_post(body=rec._build_confirm_html())

            # Avisar al responsable destino para que confirme la recepción.
            if rec.receiver_user_id:
                rec.activity_schedule(
                    "mail.mail_activity_data_todo",
                    user_id=rec.receiver_user_id.id,
                    summary=_("Confirmar recepción de transferencia %s") % rec.name,
                    note=_(
                        "Confirma que recibiste %(amount)s en el diario %(journal)s."
                    )
                    % {
                        "amount": rec._amount_label(),
                        "journal": rec.destination_journal_id.display_name,
                    },
                )
        return True

    def action_confirm_receipt(self):
        for rec in self:
            if rec.state != "confirmed":
                raise UserError(
                    _(
                        "Solo se puede confirmar la recepción de una transferencia "
                        "en estado Confirmada."
                    )
                )
            is_manager = self.env.user.has_group(
                "custom_account_treasury.group_treasury_manager"
            )
            if self.env.user != rec.receiver_user_id and not is_manager:
                raise UserError(
                    _(
                        "Solo el responsable que recibe (%s) o un Responsable de "
                        "Tesorería puede confirmar la recepción."
                    )
                    % rec.receiver_user_id.display_name
                )
            rec.write(
                {
                    "state": "received",
                    "received_user_id": self.env.user.id,
                    "received_date": fields.Datetime.now(),
                }
            )
            if rec.receiver_user_id:
                rec.activity_feedback(
                    ["mail.mail_activity_data_todo"],
                    user_id=rec.receiver_user_id.id,
                )
            rec.message_post(
                body=_("Recepción del dinero confirmada por %s.")
                % self.env.user.display_name
            )
        return True

    def action_cancel(self):
        for rec in self:
            if rec.state == "cancelled":
                continue
            payments = rec.outbound_payment_id | rec.inbound_payment_id
            if payments:
                lines = rec._get_transfer_account_lines(payments).filtered(
                    lambda line: line.reconciled
                )
                if lines:
                    lines.remove_move_reconcile()
                payments.action_draft()
                payments.action_cancel()
            rec.write({"state": "cancelled"})
            rec.message_post(
                body=_("Transferencia cancelada por %s.") % self.env.user.display_name
            )
        return True

    def action_draft(self):
        for rec in self:
            if rec.state != "cancelled":
                raise UserError(
                    _("Solo se puede regresar a Borrador una transferencia cancelada.")
                )
            rec.state = "draft"
        return True

    def action_view_payments(self):
        self.ensure_one()
        payments = self.outbound_payment_id | self.inbound_payment_id
        return {
            "name": _("Pagos de la transferencia"),
            "type": "ir.actions.act_window",
            "res_model": "account.payment",
            "domain": [("id", "in", payments.ids)],
            "view_mode": "list,form",
            "target": "current",
        }

    # ------------------------------------------------------------------
    # HTML para chatter
    # ------------------------------------------------------------------
    def _build_confirm_html(self):
        self.ensure_one()
        return Markup(
            "<p>Transferencia interna <b>%(name)s</b> confirmada y contabilizada.</p>"
            "<ul>"
            "<li>Monto: <b>%(amount)s</b></li>"
            "<li>Origen: <b>%(src)s</b> → Destino: <b>%(dst)s</b></li>"
            "<li>Pago de salida: %(out)s</li>"
            "<li>Cobro de entrada: %(in)s</li>"
            "</ul>"
        ) % {
            "name": self.name,
            "amount": self._amount_label(),
            "src": self.source_journal_id.display_name,
            "dst": self.destination_journal_id.display_name,
            "out": self.outbound_payment_id.display_name or "-",
            "in": self.inbound_payment_id.display_name or "-",
        }
