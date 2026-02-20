# -*- coding: utf-8 -*-

from odoo import models, fields


class MovimientoArroz(models.Model):
    _name = 'secadora.movimiento.arroz'
    _description = 'Movimiento de Arroz'
    _order = 'fecha desc, id desc'

    posicion_id = fields.Many2one(
        'secadora.posicion.arroz',
        string='Posición',
        required=True,
        ondelete='cascade',
        index=True,
    )
    pesaje_id = fields.Many2one(
        'secadora.pesaje',
        string='Pesaje',
        related='posicion_id.pesaje_id',
        store=True,
        index=True,
    )
    sitio_origen_id = fields.Many2one(
        'secadora.sitio.muestra',
        string='Desde',
    )
    sitio_destino_id = fields.Many2one(
        'secadora.sitio.muestra',
        string='Hacia',
    )
    peso_kg = fields.Float(
        string='Peso (Kg)',
        digits=(12, 2),
    )
    fecha = fields.Datetime(
        string='Fecha',
        default=fields.Datetime.now,
        required=True,
    )
    usuario_id = fields.Many2one(
        'res.users',
        string='Usuario',
        default=lambda self: self.env.uid,
        required=True,
    )
    tipo = fields.Selection([
        ('creacion', 'Creación'),
        ('movimiento', 'Movimiento'),
        ('division', 'División'),
        ('retiro', 'Retiro'),
    ], string='Tipo', required=True)
    notas = fields.Text(string='Notas')
