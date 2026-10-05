# -*- coding: utf-8 -*-

from odoo import api, models, fields


class RegistroBultosStock(models.Model):
    _inherit = 'secadora.registro.bultos'

    stock_move_id = fields.Many2one(
        'stock.move',
        string='Movimiento de Inventario',
        readonly=True,
        copy=False,
        help='Movimiento que consume empaques del inventario'
    )

    # El consumo sigue al registro desde que se crea: los registros no se
    # confirman en la práctica (el tablero los deja en borrador), así que
    # amarrarlo a la confirmación dejaba el inventario sin descontar.

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sincronizar_consumo_empaque()
        return records

    def write(self, vals):
        res = super().write(vals)
        if {'cantidad', 'producto_empaque_id', 'proveedor_empaque', 'fecha',
                'trasladado_de_id', 'orden_id'} & vals.keys():
            self._sincronizar_consumo_empaque()
        return res

    def unlink(self):
        movimientos = self.sudo().stock_move_id
        res = super().unlink()
        movimientos._empaque_anular()
        return res

    def action_confirmar(self):
        self._sincronizar_consumo_empaque()
        return super().action_confirmar()

    def _empaques_a_consumir(self):
        """Empaques que este registro saca del inventario de la secadora.

        Los que trae el cliente no cuentan, y los bultos que llegan por
        traslado ya se descontaron en el registro del que salieron."""
        self.ensure_one()
        if (self.proveedor_empaque != 'secadora' or self.trasladado_de_id
                or not self.producto_empaque_id.es_empaque):
            return 0
        return self.cantidad

    def _sincronizar_consumo_empaque(self):
        Move = self.env['stock.move']
        for record in self:
            cantidad = record._empaques_a_consumir()
            if not cantidad and not record.stock_move_id:
                continue
            move = Move._empaque_sincronizar(
                record.stock_move_id, record.producto_empaque_id, cantidad, 'consumo', False,
                record.fecha,
                ' - '.join(filter(None, [record.orden_id.name, record.sudo().cliente_id.name])))
            if move != record.stock_move_id:
                record.sudo().stock_move_id = move
