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
    tipo_vehiculo = fields.Selection([
        ('camion', 'Camión'),
        ('tractomula', 'Tractomula'),
        ('turbo', 'Turbo'),
        ('camioneta', 'Camioneta'),
        ('otro', 'Otro'),
    ], string='Tipo de Vehículo', default='camion')
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

    _sql_constraints = [
        ('placa_unique', 'unique(placa)', 'La placa del vehículo debe ser única.')
    ]

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

    def name_get(self):
        """Muestra solo la placa del vehículo"""
        result = []
        for record in self:
            result.append((record.id, record.placa or 'Sin placa'))
        return result

    @api.model
    def _name_search(self, name='', args=None, operator='ilike', limit=100, name_get_uid=None):
        """Permite buscar por placa"""
        args = args or []
        if name:
            args = ['|', ('placa', operator, name)] + args
        return self._search(args, limit=limit, access_rights_uid=name_get_uid)
