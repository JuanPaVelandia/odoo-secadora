# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class ResCityPostal(models.Model):
    _name = 'res.city.postal'
    _description = 'Codigos Postales Colombia'
    _order = 'postal_code'

    postal_code = fields.Char(
        string='Codigo Postal',
        required=True,
        index=True,
        size=6,
        help='Codigo postal de 6 digitos'
    )
    postal_zone = fields.Char(
        string='Zona Postal',
        size=4,
        help='Zona postal de 4 digitos'
    )
    city_id = fields.Many2one(
        'res.city',
        string='Ciudad/Municipio',
        required=True,
        index=True,
        ondelete='cascade'
    )
    state_id = fields.Many2one(
        'res.country.state',
        string='Departamento',
        related='city_id.state_id',
        store=True
    )
    country_id = fields.Many2one(
        'res.country',
        string='Pais',
        related='city_id.country_id',
        store=True
    )
    zone_type = fields.Selection(
        [('urban', 'Urbano'), ('rural', 'Rural')],
        string='Tipo de Zona',
        default='urban'
    )
    neighborhoods = fields.Text(
        string='Barrios',
        help='Barrios contenidos en este codigo postal'
    )
    villages = fields.Text(
        string='Veredas',
        help='Veredas contenidas en este codigo postal'
    )
    active = fields.Boolean(default=True)

    _postal_code_uniq = models.Constraint('unique(postal_code)', 'El codigo postal debe ser unico')

    def _get_first_location(self):
        """Obtiene el primer barrio o vereda del codigo postal"""
        self.ensure_one()
        # Primero intentar con barrios (urbano)
        if self.neighborhoods:
            parts = [p.strip() for p in self.neighborhoods.split('-') if p.strip()]
            if parts:
                return parts[0]
        # Luego con veredas (rural)
        if self.villages:
            parts = [p.strip() for p in self.villages.split('-') if p.strip()]
            if parts:
                return parts[0]
        return ''

    def _get_zone_label(self):
        """Obtiene la etiqueta del tipo de zona"""
        self.ensure_one()
        return 'Urbano' if self.zone_type == 'urban' else 'Rural'

    @api.depends('postal_code', 'city_id', 'state_id', 'neighborhoods', 'villages', 'zone_type')
    def _compute_display_name(self):
        for record in self:
            if record.postal_code and record.city_id:
                first_loc = record._get_first_location()
                zone_label = record._get_zone_label()
                state_name = record.state_id.name if record.state_id else ''
                city_state = f"{record.city_id.name}, {state_name}" if state_name else record.city_id.name
                if first_loc:
                    record.display_name = f"[{record.postal_code}] {first_loc} - {city_state} ({zone_label})"
                else:
                    record.display_name = f"[{record.postal_code}] {city_state} ({zone_label})"
            else:
                record.display_name = record.postal_code or ''

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        """Busqueda por codigo postal, ciudad, departamento, barrio o vereda"""
        if not args:
            args = []
        domain = args[:]
        if name:
            domain = ['|', '|', '|', '|',
                ('postal_code', operator, name),
                ('city_id.name', operator, name),
                ('state_id.name', operator, name),
                ('neighborhoods', operator, name),
                ('villages', operator, name)
            ] + domain
        records = self.search(domain, limit=limit)
        return [(record.id, record.display_name) for record in records]

    @api.model
    def get_postal_code_for_city(self, city_id, zone_type=None):
        """Obtener codigos postales de una ciudad"""
        domain = [('city_id', '=', city_id)]
        if zone_type:
            domain.append(('zone_type', '=', zone_type))
        return self.search(domain)


class Cities(models.Model):
    _inherit = "res.city"
    _description = 'Ciudades por departamento'

    name = fields.Char(translate=True)
    code = fields.Char(string='Codigo DANE', size=10)
    code_zip = fields.Char(string='Codigo Postal Principal', size=10)
    postal_code_ids = fields.One2many(
        'res.city.postal',
        'city_id',
        string='Codigos Postales'
    )
    postal_code_count = fields.Integer(
        string='Cantidad Codigos Postales',
        compute='_compute_postal_code_count'
    )

    @api.depends('postal_code_ids')
    def _compute_postal_code_count(self):
        for city in self:
            city.postal_code_count = len(city.postal_code_ids)


class ResCountryState(models.Model):
    _inherit = 'res.country.state'

    code_dian = fields.Char(string='Codigo DIAN del Departamento')
