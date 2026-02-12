# -*- coding: utf-8 -*-

from odoo import models, fields
from odoo.exceptions import UserError


class RegistroBultosStock(models.Model):
    _inherit = 'secadora.registro.bultos'

    stock_move_id = fields.Many2one(
        'stock.move',
        string='Movimiento de Inventario',
        readonly=True,
        copy=False,
        help='Movimiento que consume empaques del inventario'
    )

    def action_confirmar(self):
        """Extiende confirmacion para consumir empaques del inventario"""
        for record in self:
            if record.state != 'borrador':
                continue

            if record.proveedor_empaque == 'secadora' and record.producto_empaque_id:
                record._crear_movimiento_consumo_empaque()

        return super().action_confirmar()

    def _crear_movimiento_consumo_empaque(self):
        """Consume empaques del inventario cuando los provee la secadora"""
        self.ensure_one()

        if self.stock_move_id:
            return

        location_stock = self.env.ref('stock.stock_location_stock', raise_if_not_found=False)
        location_production = self.env.ref('stock.location_production', raise_if_not_found=False)

        if not location_stock or not location_production:
            raise UserError('No se encontraron las ubicaciones de inventario necesarias.')

        move = self.env['stock.move'].create({
            'name': f'Consumo empaques - {self.orden_id.name}',
            'product_id': self.producto_empaque_id.id,
            'product_uom_qty': self.cantidad,
            'product_uom': self.producto_empaque_id.uom_id.id,
            'location_id': location_stock.id,
            'location_dest_id': location_production.id,
            'origin': self.orden_id.name,
        })

        move._action_confirm()
        move._action_assign()
        move._action_done()

        self.stock_move_id = move.id
