# -*- coding: utf-8 -*-

from odoo import models, fields, api


class SecadoraTransportadora(models.Model):
    _name = 'secadora.transportadora'
    _description = 'Empresas Transportadoras'
    _order = 'name'

    name = fields.Char(
        string='Nombre',
        required=True,
        index=True
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Contacto',
        help='Contacto asociado a la transportadora. Permite halar el NIT y '
             'los datos de contacto desde Contactos y asociarla a contabilidad.',
    )
    nit = fields.Char(
        string='NIT',
        compute='_compute_datos_contacto',
        store=True,
        readonly=False,
    )
    telefono = fields.Char(
        string='Teléfono',
        compute='_compute_datos_contacto',
        store=True,
        readonly=False,
    )
    direccion = fields.Text(
        string='Dirección',
        compute='_compute_datos_contacto',
        store=True,
        readonly=False,
    )
    contacto = fields.Char(string='Contacto (texto)')
    active = fields.Boolean(
        string='Activo',
        default=True
    )
    vehiculo_ids = fields.One2many(
        'secadora.vehiculo',
        'transportadora_id',
        string='Vehículos'
    )

    @api.depends('partner_id')
    def _compute_datos_contacto(self):
        """Halar NIT, teléfono y dirección del contacto asociado.

        Los campos quedan editables (readonly=False): si no hay contacto o el
        contacto no tiene el dato, se conserva el valor escrito manualmente.
        """
        for rec in self:
            partner = rec.partner_id
            if partner:
                if partner.vat:
                    rec.nit = partner.vat
                telefono = partner.phone or getattr(partner, 'mobile', False)
                if telefono:
                    rec.telefono = telefono
                direccion = partner._display_address() if hasattr(partner, '_display_address') else False
                if direccion:
                    rec.direccion = direccion
            # Si no hay partner, se conservan los valores actuales (no se pisan).

    def _aplicar_etiqueta_transportadora(self):
        """Marcar el contacto asociado con la etiqueta nativa 'Transportadora'."""
        categoria = self.env.ref('bascula.partner_category_transportadora', raise_if_not_found=False)
        if not categoria:
            return
        for rec in self:
            if rec.partner_id and categoria not in rec.partner_id.category_id:
                rec.partner_id.category_id = [fields.Command.link(categoria.id)]

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._aplicar_etiqueta_transportadora()
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'partner_id' in vals:
            self._aplicar_etiqueta_transportadora()
        return res
