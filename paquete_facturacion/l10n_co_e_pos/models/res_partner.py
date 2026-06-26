from odoo import models, fields, api


class Partner(models.Model):
    _inherit = "res.partner"

    # Campos de Firma Electrónica
    signature_image = fields.Binary(
        string='Firma Digital',
        help='Firma digital del cliente capturada en el POS',
        copy=False
    )
    signature_date = fields.Datetime(
        string='Fecha de Firma',
        help='Fecha y hora en que el cliente firmó',
        readonly=True,
        copy=False
    )
    terms_accepted = fields.Boolean(
        string='Términos Aceptados',
        help='El cliente aceptó los términos y condiciones',
        default=False,
        copy=False
    )
    privacy_policy_accepted = fields.Boolean(
        string='Política de Datos Aceptada',
        help='El cliente aceptó la política de tratamiento de datos personales (HABEAS DATA)',
        default=False,
        copy=False
    )

    def _sync_vat_fields(self, vals):
        if "vat_co" not in self._fields:
            return
        vat = vals.get("vat")
        vat_co = vals.get("vat_co")

        def _clean_vat_base(value):
            if not value:
                return value
            if "-" in value:
                value = value.split("-", 1)[0]
            return "".join(ch for ch in value if ch.isdigit())

        if vat_co:
            vals["vat_co"] = _clean_vat_base(vat_co)

        if vat and not vat_co:
            vals["vat_co"] = _clean_vat_base(vat)
        elif vat_co and not vat:
            vals["vat"] = _clean_vat_base(vat_co)

    @api.model
    def create_from_ui(self, partner):
        self._sync_vat_fields(partner)
        if partner.get("country_id"):
            partner["country_id"] = int(partner.get("country_id"))
        if partner.get("vat"):
            if not partner.get("fiscal_responsability_ids"):
                partner["fiscal_responsability_ids"] = [(6, 0, [7])]
        if partner.get("state_id"):
            partner["state_id"] = int(partner.get("state_id"))

        # Capturar firma si viene desde el POS
        if partner.get("signature_image"):
            partner["signature_date"] = fields.Datetime.now()
            if partner.get("terms_accepted"):
                partner["terms_accepted"] = True
            if partner.get("privacy_policy_accepted"):
                partner["privacy_policy_accepted"] = True

        return super().create_from_ui(partner)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._sync_vat_fields(vals)
        return super().create(vals_list)

    def write(self, vals):
        self._sync_vat_fields(vals)
        return super().write(vals)
