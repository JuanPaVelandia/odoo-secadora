# -*- coding: utf-8 -*-

from odoo import models, fields, api


class SecadoraVehiculo(models.Model):
    _name = 'secadora.vehiculo'
    _description = 'Vehículos'
    _rec_name = 'placa'
    _order = 'placa'

    placa = fields.Char(
        string='Placa',
        required=True,
        index=True,
        help='Placa del vehículo'
    )
    tipo_vehiculo_id = fields.Many2one(
        'secadora.tipo.vehiculo',
        string='Tipo de Vehículo',
        required=True,
    )
    capacidad_kg = fields.Float(
        string='Capacidad (Kg)',
        help='Capacidad de carga en kilogramos'
    )
    tara_promedio = fields.Float(
        string='Tara Promedio (Kg)',
        help='Peso del vehículo vacío'
    )
    conductor_habitual_id = fields.Many2one(
        'secadora.conductor',
        string='Conductor Habitual'
    )
    transportadora_id = fields.Many2one(
        'secadora.transportadora',
        string='Transportadora'
    )
    active = fields.Boolean(
        string='Activo',
        default=True
    )
    notes = fields.Text(string='Notas')

    _placa_unique = models.Constraint(
        'unique(placa)', 'La placa del vehículo debe ser única.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'placa' in vals and vals['placa']:
                vals['placa'] = vals['placa'].upper()
        return super().create(vals_list)

    def write(self, vals):
        if 'placa' in vals and vals['placa']:
            vals['placa'] = vals['placa'].upper()
        return super().write(vals)

    @api.depends('placa')
    def _compute_display_name(self):
        """Muestra solo la placa del vehículo (Odoo 18 usa display_name)."""
        for record in self:
            record.display_name = record.placa or 'Sin placa'

    @api.model
    def _name_search(self, name='', domain=None, operator='ilike', limit=None, order=None):
        """Permite buscar por placa (firma de Odoo 18)."""
        domain = list(domain or [])
        if name:
            domain = ['|', ('placa', operator, name)] + domain
        return self._search(domain, limit=limit, order=order)
