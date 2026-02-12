# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError


class SecadoraPesajeStock(models.Model):
    _inherit = 'secadora.pesaje'

    picking_id = fields.Many2one(
        'stock.picking',
        string='Movimiento de Inventario',
        readonly=True,
        copy=False,
        help='Picking generado automaticamente al completar el pesaje'
    )

    picking_state = fields.Selection(
        related='picking_id.state',
        string='Estado Inventario',
        readonly=True,
    )

    def unlink(self):
        """Impedir borrar pesajes que tienen picking vinculado"""
        for record in self:
            if record.picking_id:
                raise UserError(
                    f'No se puede eliminar el pesaje {record.name} porque tiene '
                    f'un movimiento de inventario asociado ({record.picking_id.name}).\n\n'
                    'Cancele primero el movimiento de inventario antes de eliminar el pesaje.'
                )
        return super().unlink()

    def action_segunda_pesada(self):
        """Extiende la segunda pesada para crear picking si aplica"""
        res = super().action_segunda_pesada()

        for record in self:
            if record.state != 'completado':
                continue

            tipo = record.tipo_operacion_id
            if not tipo:
                continue

            if tipo.afecta_inventario and not tipo.es_servicio:
                record._crear_picking_inventario()
            elif tipo.es_servicio:
                record._crear_picking_servicio()

        return res

    def action_cancelar(self):
        """Extiende cancelacion para cancelar picking vinculado"""
        for record in self:
            if record.picking_id and record.picking_id.state not in ('done', 'cancel'):
                record.picking_id.action_cancel()
        return super().action_cancelar()

    def _get_picking_type(self, sequence_code):
        """Busca un picking type por sequence_code, lo crea si no existe"""
        picking_type = self.env['stock.picking.type'].search([
            ('sequence_code', '=', sequence_code),
        ], limit=1)
        if not picking_type:
            picking_type = self._create_picking_type(sequence_code)
        return picking_type

    def _create_picking_type(self, sequence_code):
        """Crea un picking type que no existe aun"""
        warehouse = self.env['stock.warehouse'].search([], limit=1)
        loc_stock = self.env.ref('stock.stock_location_stock', raise_if_not_found=False)
        loc_suppliers = self.env.ref('stock.stock_location_suppliers', raise_if_not_found=False)
        loc_customers = self.env.ref('stock.stock_location_customers', raise_if_not_found=False)
        loc_secado = self.env['stock.location'].search([('name', '=', 'Secado En Proceso')], limit=1)

        configs = {
            'REC-BAS': {
                'name': 'Recepcion Bascula',
                'code': 'incoming',
                'default_location_src_id': loc_suppliers.id if loc_suppliers else False,
                'default_location_dest_id': loc_stock.id if loc_stock else False,
            },
            'DES-BAS': {
                'name': 'Despacho Bascula',
                'code': 'outgoing',
                'default_location_src_id': loc_stock.id if loc_stock else False,
                'default_location_dest_id': loc_customers.id if loc_customers else False,
            },
            'ENT-SRV': {
                'name': 'Entrada Servicio',
                'code': 'incoming',
                'default_location_src_id': loc_suppliers.id if loc_suppliers else False,
                'default_location_dest_id': loc_secado.id if loc_secado else (loc_stock.id if loc_stock else False),
            },
            'SAL-SRV': {
                'name': 'Salida Servicio',
                'code': 'outgoing',
                'default_location_src_id': loc_secado.id if loc_secado else (loc_stock.id if loc_stock else False),
                'default_location_dest_id': loc_customers.id if loc_customers else False,
            },
        }

        if sequence_code not in configs:
            raise UserError(f'Tipo de operacion de inventario desconocido: {sequence_code}')

        vals = configs[sequence_code]
        vals['sequence_code'] = sequence_code
        vals['warehouse_id'] = warehouse.id if warehouse else False

        return self.env['stock.picking.type'].create(vals)

    def _crear_picking_inventario(self):
        """Crea picking para operaciones de COMPRA o VENTA"""
        self.ensure_one()

        if self.picking_id:
            return

        if not self.producto_id:
            raise UserError(
                'El producto es obligatorio para operaciones que afectan inventario.\n'
                'Por favor seleccione un producto antes de completar el pesaje.'
            )

        tipo = self.tipo_operacion_id

        if tipo.tipo_inventario == 'entrada':
            picking_type = self._get_picking_type('REC-BAS')
        else:
            picking_type = self._get_picking_type('DES-BAS')

        picking_vals = {
            'picking_type_id': picking_type.id,
            'partner_id': self.tercero_id.id,
            'origin': self.name,
            'x_numero_tiquete': self.name,
            'x_pesaje_id': self.id,
            'location_id': picking_type.default_location_src_id.id,
            'location_dest_id': picking_type.default_location_dest_id.id,
            'move_ids': [(0, 0, {
                'name': f'{self.producto_id.name} - {self.name}',
                'product_id': self.producto_id.id,
                'product_uom_qty': self.peso_neto,
                'product_uom': self.producto_id.uom_id.id,
                'location_id': picking_type.default_location_src_id.id,
                'location_dest_id': picking_type.default_location_dest_id.id,
            })],
        }

        if self.orden_servicio_id:
            picking_vals['x_orden_servicio_id'] = self.orden_servicio_id.id

        picking = self.env['stock.picking'].create(picking_vals)
        picking.action_confirm()

        self.picking_id = picking.id

    def _crear_picking_servicio(self):
        """Crea picking para operaciones de SERVICIO con owner_id = cliente"""
        self.ensure_one()

        if self.picking_id:
            return

        producto = self.producto_id
        if not producto:
            tmpl = self.env['product.template'].search([('name', '=', 'Arroz Paddy')], limit=1)
            if tmpl:
                producto = tmpl.product_variant_id
        if not producto:
            raise UserError(
                'No se encontro el producto Arroz Paddy.\n'
                'Por favor seleccione un producto o verifique que los datos del modulo esten instalados.'
            )

        if self.direccion == 'entrada':
            picking_type = self._get_picking_type('ENT-SRV')
        else:
            picking_type = self._get_picking_type('SAL-SRV')

        picking_vals = {
            'picking_type_id': picking_type.id,
            'partner_id': self.tercero_id.id,
            'owner_id': self.tercero_id.id,
            'origin': self.name,
            'x_numero_tiquete': self.name,
            'x_pesaje_id': self.id,
            'location_id': picking_type.default_location_src_id.id,
            'location_dest_id': picking_type.default_location_dest_id.id,
            'move_ids': [(0, 0, {
                'name': f'{producto.name} - {self.name}',
                'product_id': producto.id,
                'product_uom_qty': self.peso_neto,
                'product_uom': producto.uom_id.id,
                'location_id': picking_type.default_location_src_id.id,
                'location_dest_id': picking_type.default_location_dest_id.id,
            })],
        }

        if self.orden_servicio_id:
            picking_vals['x_orden_servicio_id'] = self.orden_servicio_id.id

        picking = self.env['stock.picking'].create(picking_vals)
        picking.action_confirm()

        self.picking_id = picking.id

    def action_ver_picking(self):
        """Abre el picking vinculado"""
        self.ensure_one()
        if not self.picking_id:
            raise UserError('Este pesaje no tiene un movimiento de inventario asociado.')
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'res_id': self.picking_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
