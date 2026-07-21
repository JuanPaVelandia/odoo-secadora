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
    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        related='posicion_id.company_id',
        store=True,
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
        ('combinacion', 'Combinación'),
        ('despacho', 'Despacho'),
    ], string='Tipo', required=True,
       help='Tipo de movimiento: Creación (ingreso), Movimiento (cambio de sitio), '
            'División (separación de posición), Retiro (salida de planta), '
            'Combinación (unión de posiciones), Despacho (envío a cliente)')
    notas = fields.Text(string='Notas')
