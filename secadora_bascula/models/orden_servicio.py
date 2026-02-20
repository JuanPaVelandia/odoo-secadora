# -*- coding: utf-8 -*-

import logging
from odoo import models, fields

_logger = logging.getLogger(__name__)


class OrdenServicioStock(models.Model):
    _inherit = 'secadora.orden.servicio'

    picking_ids = fields.One2many(
        'stock.picking',
        'x_orden_servicio_id',
        string='Movimientos de Inventario',
        readonly=True,
    )

    picking_count = fields.Integer(
        string='Movimientos',
        compute='_compute_picking_count',
    )

    # Movimientos de transformación/merma (stock.move sin picking)
    transformacion_move_ids = fields.One2many(
        'stock.move',
        'x_orden_servicio_id',
        string='Movimientos de Transformacion',
        domain=[('x_tipo_movimiento_secadora', '!=', False)],
        readonly=True,
    )

    merma_move_ids = fields.One2many(
        'stock.move',
        'x_orden_servicio_id',
        string='Movimientos de Merma',
        domain=[('x_tipo_movimiento_secadora', '=', 'merma')],
        readonly=True,
    )

    merma_inventario_registrada = fields.Boolean(
        string='Merma Registrada en Inventario',
        default=False,
        readonly=True,
        copy=False,
    )

    def _compute_picking_count(self):
        for record in self:
            record.picking_count = len(record.picking_ids)

    def action_ver_pickings(self):
        """Abre los pickings vinculados a esta orden"""
        self.ensure_one()
        action = {
            'type': 'ir.actions.act_window',
            'name': f'Inventario - {self.name}',
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            'domain': [('x_orden_servicio_id', '=', self.id)],
            'context': {'default_x_orden_servicio_id': self.id},
        }
        if self.picking_count == 1:
            action['view_mode'] = 'form'
            action['res_id'] = self.picking_ids[0].id
        return action

    def action_ver_merma(self):
        """Abre los movimientos de merma de esta orden"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Merma - {self.name}',
            'res_model': 'stock.move',
            'view_mode': 'list,form',
            'domain': [
                ('x_orden_servicio_id', '=', self.id),
                ('x_tipo_movimiento_secadora', '=', 'merma'),
            ],
        }

    def action_ver_transformaciones(self):
        """Abre todos los movimientos de transformacion de esta orden"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Transformacion Inventario - {self.name}',
            'res_model': 'stock.move',
            'view_mode': 'list,form',
            'domain': [
                ('x_orden_servicio_id', '=', self.id),
                ('x_tipo_movimiento_secadora', '!=', False),
            ],
        }

    # ==================== OVERRIDES ====================

    def action_listo_liquidar(self):
        """Extiende para crear movimientos de transformación y merma"""
        res = super().action_listo_liquidar()
        for record in self:
            if record.state == 'listo_liquidar' and not record.merma_inventario_registrada:
                record._crear_movimientos_transformacion_merma()
        return res

    def action_volver_proceso(self):
        """Extiende para revertir movimientos de transformación"""
        for record in self:
            if record.merma_inventario_registrada:
                record._revertir_movimientos_transformacion()
        return super().action_volver_proceso()

    def action_cancelar(self):
        """Extiende para revertir movimientos de transformación al cancelar"""
        for record in self:
            if record.merma_inventario_registrada:
                record._revertir_movimientos_transformacion()
        return super().action_cancelar()

    # ==================== TRANSFORMACIÓN / MERMA ====================

    def _get_producto_arroz(self, nombre):
        """Busca un producto de arroz por nombre"""
        tmpl = self.env['product.template'].search([('name', '=', nombre)], limit=1)
        if tmpl:
            return tmpl.product_variant_id
        return False

    def _crear_movimientos_transformacion_merma(self):
        """Crea los 4 stock.moves de transformación para servicio/maquila.

        Move 1 (consumo):     Verde peso_salida  Secado En Proceso → Virtual/Production
        Move 2 (producción):  Seco  peso_salida  Virtual/Production → Secado En Proceso
        Move 3 (entrega):     Seco  peso_salida  Secado En Proceso → Clientes
        Move 4 (merma):       Verde merma        Secado En Proceso → Merma Secado
        """
        self.ensure_one()

        if self.merma_inventario_registrada:
            return

        producto_verde = self._get_producto_arroz('Arroz Paddy Verde')
        producto_seco = self._get_producto_arroz('Arroz Paddy Seco')

        if not producto_verde or not producto_seco:
            _logger.warning(
                'Orden %s: No se encontraron productos de arroz para transformacion',
                self.name
            )
            return

        peso_salida = self.peso_salida_real
        peso_entrada = self.peso_entrada
        merma = peso_entrada - peso_salida

        if peso_salida <= 0:
            _logger.warning('Orden %s: Peso de salida es 0, no se crean movimientos', self.name)
            return

        # Ubicaciones
        loc_secado = self.env.ref('secadora_bascula.stock_location_secado', raise_if_not_found=False)
        loc_production = self.env.ref('stock.stock_location_production', raise_if_not_found=False)
        loc_customers = self.env.ref('stock.stock_location_customers', raise_if_not_found=False)
        loc_merma = self.env.ref('secadora_bascula.stock_location_merma_secado', raise_if_not_found=False)

        if not all([loc_secado, loc_production, loc_customers, loc_merma]):
            _logger.warning('Orden %s: Ubicaciones faltantes para transformacion', self.name)
            return

        cliente_id = self.cliente_id.id

        move_vals_list = []

        # Move 1: Consumo Verde (Secado En Proceso → Production)
        move_vals_list.append({
            'name': f'Consumo Verde - {self.name}',
            'product_id': producto_verde.id,
            'product_uom_qty': peso_salida,
            'product_uom': producto_verde.uom_id.id,
            'location_id': loc_secado.id,
            'location_dest_id': loc_production.id,
            'x_orden_servicio_id': self.id,
            'x_tipo_movimiento_secadora': 'transformacion_consumo',
            'restrict_partner_id': cliente_id,
        })

        # Move 2: Producción Seco (Production → Secado En Proceso)
        move_vals_list.append({
            'name': f'Produccion Seco - {self.name}',
            'product_id': producto_seco.id,
            'product_uom_qty': peso_salida,
            'product_uom': producto_seco.uom_id.id,
            'location_id': loc_production.id,
            'location_dest_id': loc_secado.id,
            'x_orden_servicio_id': self.id,
            'x_tipo_movimiento_secadora': 'transformacion_produccion',
            'restrict_partner_id': cliente_id,
        })

        # Move 3: Entrega Seco al cliente (Secado En Proceso → Clientes)
        move_vals_list.append({
            'name': f'Entrega Seco - {self.name}',
            'product_id': producto_seco.id,
            'product_uom_qty': peso_salida,
            'product_uom': producto_seco.uom_id.id,
            'location_id': loc_secado.id,
            'location_dest_id': loc_customers.id,
            'x_orden_servicio_id': self.id,
            'x_tipo_movimiento_secadora': 'salida_servicio',
            'restrict_partner_id': cliente_id,
        })

        # Move 4: Merma (Secado En Proceso → Merma Secado) - solo si positiva
        if merma > 0:
            move_vals_list.append({
                'name': f'Merma Secado - {self.name}',
                'product_id': producto_verde.id,
                'product_uom_qty': merma,
                'product_uom': producto_verde.uom_id.id,
                'location_id': loc_secado.id,
                'location_dest_id': loc_merma.id,
                'x_orden_servicio_id': self.id,
                'x_tipo_movimiento_secadora': 'merma',
                'restrict_partner_id': cliente_id,
            })

        for vals in move_vals_list:
            move = self.env['stock.move'].create(vals)
            move._action_confirm()
            move.quantity = move.product_uom_qty
            move.picked = True
            move._action_done()

        self.merma_inventario_registrada = True

    def _revertir_movimientos_transformacion(self):
        """Revierte los movimientos de transformación creando moves inversos."""
        self.ensure_one()

        if not self.merma_inventario_registrada:
            return

        moves_a_revertir = self.env['stock.move'].search([
            ('x_orden_servicio_id', '=', self.id),
            ('x_tipo_movimiento_secadora', '!=', False),
            ('state', '=', 'done'),
        ])

        for move in moves_a_revertir:
            # Crear move reverso (intercambiar origen y destino)
            reverse_vals = {
                'name': f'Reversa: {move.name}',
                'product_id': move.product_id.id,
                'product_uom_qty': move.quantity,
                'product_uom': move.product_uom.id,
                'location_id': move.location_dest_id.id,
                'location_dest_id': move.location_id.id,
                'x_orden_servicio_id': self.id,
                'x_tipo_movimiento_secadora': move.x_tipo_movimiento_secadora,
                'restrict_partner_id': move.restrict_partner_id.id if move.restrict_partner_id else False,
            }
            reverse_move = self.env['stock.move'].create(reverse_vals)
            reverse_move._action_confirm()
            reverse_move.quantity = reverse_move.product_uom_qty
            reverse_move.picked = True
            reverse_move._action_done()

        self.merma_inventario_registrada = False
