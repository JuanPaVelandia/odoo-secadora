# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ResCityNeighborhood(models.Model):
    """
    Modelo para barrios/vecindarios de una ciudad
    Permite estandarizar y sugerir barrios al capturar direcciones
    """
    _name = 'res.city.neighborhood'
    _description = 'Barrio / Vecindario'
    _order = 'name'

    name = fields.Char(
        string='Nombre',
        required=True,
        index=True,
        help='Nombre del barrio o vecindario'
    )
    city_id = fields.Many2one(
        'res.city',
        string='Ciudad',
        required=True,
        index=True,
        ondelete='cascade',
        help='Ciudad a la que pertenece el barrio'
    )
    state_id = fields.Many2one(
        'res.country.state',
        string='Departamento',
        related='city_id.state_id',
        store=True,
        readonly=True
    )
    postal_code_id = fields.Many2one(
        'res.city.postal',
        string='Codigo Postal',
        domain="[('city_id', '=', city_id)]",
        help='Codigo postal del barrio (opcional)'
    )
    active = fields.Boolean(
        string='Activo',
        default=True
    )

    _name_city_unique = models.Constraint('unique(name, city_id)',
                                          'Ya existe un barrio con este nombre en la ciudad')

    @api.depends('name', 'city_id')
    def _compute_display_name(self):
        for record in self:
            if record.city_id:
                record.display_name = f"{record.name} ({record.city_id.name})"
            else:
                record.display_name = record.name or ''

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        """Buscar por nombre de barrio"""
        args = args or []
        domain = args[:]
        if name:
            domain = [('name', operator, name)] + domain
        records = self.search(domain, limit=limit)
        return [(record.id, record.display_name or record.name or '') for record in records]

    @api.model
    def get_or_create(self, name, city_id):
        """
        Obtiene un barrio existente o lo crea silenciosamente
        Args:
            name: Nombre del barrio
            city_id: ID de la ciudad
        Returns:
            Registro del barrio
        """
        if not name or not city_id:
            return False

        # Buscar existente (case insensitive)
        existing = self.search([
            ('name', '=ilike', name.strip()),
            ('city_id', '=', city_id)
        ], limit=1)

        if existing:
            return existing

        # Crear nuevo silenciosamente
        return self.create({
            'name': name.strip().upper(),
            'city_id': city_id,
        })

    @api.model
    def search_suggestions(self, name, city_id, limit=10):
        """
        Busca sugerencias de barrios basado en texto parcial
        Args:
            name: Texto a buscar
            city_id: ID de la ciudad (opcional)
        Returns:
            Lista de diccionarios con id, name y postal_code
        """
        domain = [('name', 'ilike', name)]
        if city_id:
            domain.append(('city_id', '=', city_id))

        neighborhoods = self.search(domain, limit=limit)
        return [{
            'id': n.id,
            'name': n.name,
            'postal_code': n.postal_code_id.postal_code if n.postal_code_id else ''
        } for n in neighborhoods]

    @api.model
    def extract_from_postal_codes(self, city_id=None):
        """
        Extrae barrios desde los códigos postales existentes
        y los crea como registros de res.city.neighborhood
        Args:
            city_id: ID de ciudad específica (opcional, si None procesa todas)
        Returns:
            Cantidad de barrios creados
        """
        PostalCode = self.env['res.city.postal']
        created_count = 0

        domain = []
        if city_id:
            domain.append(('city_id', '=', city_id))

        postal_codes = PostalCode.search(domain)

        for postal in postal_codes:
            # Extraer barrios del campo neighborhoods
            if postal.neighborhoods:
                neighborhoods = [n.strip() for n in postal.neighborhoods.split('-') if n.strip()]
                for neighborhood_name in neighborhoods:
                    # Solo crear si no existe
                    existing = self.search([
                        ('name', '=ilike', neighborhood_name),
                        ('city_id', '=', postal.city_id.id)
                    ], limit=1)

                    if not existing:
                        self.create({
                            'name': neighborhood_name.upper(),
                            'city_id': postal.city_id.id,
                            'postal_code_id': postal.id,
                        })
                        created_count += 1

            # Extraer veredas del campo villages
            if postal.villages:
                villages = [v.strip() for v in postal.villages.split('-') if v.strip()]
                for village_name in villages:
                    existing = self.search([
                        ('name', '=ilike', village_name),
                        ('city_id', '=', postal.city_id.id)
                    ], limit=1)

                    if not existing:
                        self.create({
                            'name': village_name.upper(),
                            'city_id': postal.city_id.id,
                            'postal_code_id': postal.id,
                        })
                        created_count += 1

        return created_count
