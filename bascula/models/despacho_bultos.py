# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import ValidationError


class DespachoBultos(models.Model):
    _name = 'secadora.despacho.bultos'
    _description = 'Línea de Despacho de Bultos'

    pesaje_id = fields.Many2one(
        'secadora.pesaje',
        string='Pesaje de Salida',
        ondelete='set null',
        index=True,
        help='Pesaje de salida asociado (vacío si fue despacho desde tablero)',
    )

    registro_bultos_id = fields.Many2one(
        'secadora.registro.bultos',
        string='Registro de Bultos',
        required=True,
        ondelete='restrict',
        help='Registro de bultos empacados del cual se despacha',
    )

    cantidad = fields.Integer(
        string='Bultos a Despachar',
        required=True,
        help='Cantidad de bultos que se despachan de este registro',
    )

    confirmado = fields.Boolean(
        string='Confirmado',
        default=False,
        help='Se marca True al completar la 2ª pesada del pesaje de salida',
    )

    # Campos related para mostrar info en la vista
    orden_id = fields.Many2one(
        related='registro_bultos_id.orden_id',
        string='Orden de Servicio',
    )
    cantidad_disponible = fields.Integer(
        string='Disponibles',
        compute='_compute_cantidad_disponible',
        help='Bultos disponibles para despachar de este registro',
    )
    producto_id = fields.Many2one(
        related='registro_bultos_id.producto_id',
        string='Producto',
    )
    producto_empaque_id = fields.Many2one(
        related='registro_bultos_id.producto_empaque_id',
        string='Empaque',
    )
    peso_promedio = fields.Float(
        related='registro_bultos_id.peso_promedio',
        string='Peso Prom.',
    )
    fecha_empaque = fields.Date(
        related='registro_bultos_id.fecha',
        string='Fecha Empaque',
    )

    peso_subtotal = fields.Float(
        string='Peso Subtotal (kg)',
        compute='_compute_peso_subtotal',
        store=True,
        digits=(12, 2),
    )

    @api.depends('cantidad', 'peso_promedio')
    def _compute_peso_subtotal(self):
        for record in self:
            record.peso_subtotal = record.cantidad * record.peso_promedio

    @api.depends('registro_bultos_id', 'registro_bultos_id.cantidad',
                 'registro_bultos_id.cantidad_despachada')
    def _compute_cantidad_disponible(self):
        for record in self:
            if record.registro_bultos_id:
                record.cantidad_disponible = (
                    record.registro_bultos_id.cantidad
                    - record.registro_bultos_id.cantidad_despachada
                )
            else:
                record.cantidad_disponible = 0

    @api.constrains('cantidad', 'registro_bultos_id')
    def _check_cantidad(self):
        # Agrupar por registro para validar una sola vez por registro
        registros = {}
        for record in self:
            if record.cantidad <= 0:
                raise ValidationError('La cantidad a despachar debe ser mayor a 0.')
            if record.registro_bultos_id:
                reg = record.registro_bultos_id
                if reg.id not in registros:
                    registros[reg.id] = {'registro': reg, 'cantidad_batch': 0}
                registros[reg.id]['cantidad_batch'] += record.cantidad

        for data in registros.values():
            reg = data['registro']
            cantidad_batch = data['cantidad_batch']
            # Cantidad ya confirmada en despachos anteriores (excluir el batch actual)
            ya_despachado = sum(
                d.cantidad for d in reg.despacho_ids
                if d.confirmado and d.id not in self.ids
            )
            total = ya_despachado + cantidad_batch
            if total > reg.cantidad:
                raise ValidationError(
                    f'No se pueden despachar más bultos de los empacados.\n'
                    f'Registro: {reg.name}\n'
                    f'Empacados: {reg.cantidad}\n'
                    f'Ya despachados (confirmados): {ya_despachado}\n'
                    f'Intentando despachar: {cantidad_batch}'
                )
