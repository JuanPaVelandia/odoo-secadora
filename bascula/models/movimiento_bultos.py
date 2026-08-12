# -*- coding: utf-8 -*-

from odoo import models, fields


class MovimientoBultos(models.Model):
    """Libro de movimientos de bultos entre bodegas.

    El saldo vive en `secadora.registro.bultos` (empacados menos despachados);
    esto es el historial de cómo llegó a ser ese saldo. Se escribe solo, nunca
    a mano: cada ingreso, salida o traslado deja su línea.

    Mismo diseño que `secadora.movimiento.arroz` del tablero, que resuelve el
    problema equivalente para el arroz a granel.
    """

    _name = 'secadora.movimiento.bultos'
    _description = 'Movimiento de Bultos'
    _order = 'fecha desc, id desc'

    registro_bultos_id = fields.Many2one(
        'secadora.registro.bultos',
        string='Bultos',
        required=True,
        ondelete='cascade',
        index=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        related='registro_bultos_id.company_id',
        store=True,
        index=True,
    )
    cliente_id = fields.Many2one(
        'res.partner',
        string='Dueño / Agricultor',
        related='registro_bultos_id.cliente_id',
        store=True,
    )
    variedad_id = fields.Many2one(
        'secadora.variedad.arroz',
        string='Variedad',
        related='registro_bultos_id.variedad_id',
        store=True,
    )

    tipo = fields.Selection([
        ('ingreso', 'Ingreso a bodega'),
        ('salida_flete', 'Salida en flete'),
        ('traslado', 'Traslado entre bodegas'),
        ('ajuste', 'Ajuste de inventario'),
    ], string='Tipo', required=True, index=True)

    bodega_origen_id = fields.Many2one(
        'secadora.lugar',
        string='Desde',
        domain=[('tipo', '=', 'bodega')],
        help='Vacío cuando los bultos entran por primera vez.',
    )
    bodega_destino_id = fields.Many2one(
        'secadora.lugar',
        string='Hacia',
        domain=[('tipo', '=', 'bodega')],
        help='Vacío cuando los bultos salen definitivamente.',
    )

    cantidad = fields.Integer(string='Bultos', required=True)
    fecha = fields.Datetime(
        string='Fecha',
        required=True,
        default=fields.Datetime.now,
        index=True,
    )
    usuario_id = fields.Many2one(
        'res.users',
        string='Registrado por',
        default=lambda self: self.env.user,
    )
    # El enlace al flete lo agrega `secadora_transporte`: es ese módulo el que
    # depende de este, no al revés.
    notas = fields.Text(string='Notas')
