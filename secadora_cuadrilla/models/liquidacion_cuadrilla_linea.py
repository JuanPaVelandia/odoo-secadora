# -*- coding: utf-8 -*-

from odoo import models, fields, api


class LiquidacionCuadrillaLinea(models.Model):
    _name = 'secadora.cuadrilla.liquidacion.linea'
    _description = 'Línea de Liquidación de Cuadrilla'
    _order = 'liquidacion_id, id'
    _sql_constraints = [
        ('orden_linea_uniq', 'UNIQUE(orden_servicio_linea_id)',
         'Esta línea de servicio ya fue incluida en otra liquidación de cuadrilla.'),
    ]

    liquidacion_id = fields.Many2one(
        'secadora.cuadrilla.liquidacion',
        string='Liquidación',
        required=True,
        ondelete='cascade',
    )
    orden_servicio_id = fields.Many2one(
        'secadora.orden.servicio',
        string='Orden de Servicio',
    )
    orden_servicio_linea_id = fields.Many2one(
        'secadora.orden.servicio.linea',
        string='Línea de Servicio',
    )
    fecha = fields.Datetime(
        string='Fecha',
        related='orden_servicio_id.fecha_inicio',
        store=True,
    )
    cliente_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        related='orden_servicio_id.cliente_id',
        store=True,
    )
    producto_id = fields.Many2one(
        'product.product',
        string='Servicio',
    )
    base_peso = fields.Selection([
        ('peso_entrada', 'Peso de Entrada'),
        ('peso_salida', 'Peso de Salida'),
        ('peso_neto', 'Peso Neto'),
        ('bultos', 'Cantidad de Bultos'),
        ('fijo', 'Cantidad Fija'),
    ], string='Base de Peso')
    peso = fields.Float(string='Peso/Cantidad', digits=(12, 2))
    tarifa = fields.Float(string='Tarifa ($/kg)', digits=(12, 2))
    subtotal = fields.Float(
        string='Subtotal',
        compute='_compute_subtotal',
        store=True,
        digits=(12, 2),
    )

    @api.depends('peso', 'tarifa')
    def _compute_subtotal(self):
        for rec in self:
            rec.subtotal = rec.peso * rec.tarifa

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if rec.orden_servicio_linea_id:
                rec.orden_servicio_linea_id.cuadrilla_liquidacion_linea_id = rec.id
        return records

    def unlink(self):
        lineas_servicio = self.mapped('orden_servicio_linea_id')
        res = super().unlink()
        lineas_servicio.write({'cuadrilla_liquidacion_linea_id': False})
        return res
