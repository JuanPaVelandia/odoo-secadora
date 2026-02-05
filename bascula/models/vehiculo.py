# -*- coding: utf-8 -*-

from odoo import models, fields, api


class SecadoraVehiculo(models.Model):
    _name = 'secadora.vehiculo'
    _description = 'Vehículos'
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
        result = []
        for record in self:
            name = record.placa
            if record.tipo_vehiculo:
                tipo = dict(self._fields['tipo_vehiculo'].selection).get(record.tipo_vehiculo)
                name = f"{record.placa} ({tipo})"
            result.append((record.id, name))
        return result
