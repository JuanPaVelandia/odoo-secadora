# -*- coding: utf-8 -*-

import logging
from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


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

    def write(self, vals):
        # Detectar corrección de peso sobre pesajes cuyo inventario ya se
        # validó (picking done). Se captura el peso neto ANTES del cambio para
        # calcular la diferencia y ajustar el stock.
        # NOTA: peso_neto se calcula aquí como bruto - tara directamente, NO se
        # lee el campo computado, porque su compute devuelve 0 si bruto o tara
        # es 0 (usa 'and'), lo que falsearía la diferencia al poner uno en cero.
        afecta_peso = {'peso_bruto', 'peso_tara'} & set(vals)
        pesos_previos = {}
        if afecta_peso:
            for record in self:
                if record.picking_id and record.picking_id.state == 'done':
                    pesos_previos[record.id] = record.peso_bruto - record.peso_tara

        res = super().write(vals)

        for record in self:
            if record.id not in pesos_previos:
                continue
            neto_viejo = pesos_previos[record.id]
            neto_nuevo = record.peso_bruto - record.peso_tara
            diferencia = neto_nuevo - neto_viejo
            if abs(diferencia) < 0.01:
                continue
            record._ajustar_inventario_por_correccion(neto_viejo, neto_nuevo, diferencia)

        return res

    def _ajustar_inventario_por_correccion(self, neto_viejo, neto_nuevo, diferencia):
        """Crea un stock.move SUELTO (sin picking) y validado por la DIFERENCIA
        de peso cuando se corrige un pesaje cuyo picking ya estaba validado.

        Deja intacto el movimiento original y el picking done; el ajuste es un
        movimiento independiente (mismo patrón que _crear_transformacion_venta).

        diferencia > 0: mismo sentido que el original (entró/salió más).
        diferencia < 0: sentido inverso (se corrigió a la baja).
        """
        self.ensure_one()

        # Guarda: el peso corregido debe ser físicamente válido.
        if neto_nuevo <= 0:
            raise UserError(
                f'El peso neto corregido del pesaje {self.name} es {neto_nuevo:.0f} kg. '
                'No se puede ajustar el inventario con un peso menor o igual a cero.'
            )

        picking = self.picking_id

        # Caso NO soportado: ventas de Seco generan movimientos de transformación
        # Verde→Seco (consumo + producción + merma) que dependen del peso. Ajustar
        # solo el move principal dejaría la transformación descuadrada. Se bloquea
        # y se pide corrección manual.
        transformacion = self.env['stock.move'].search_count([
            ('x_pesaje_id', '=', self.id),
            ('x_tipo_movimiento_secadora', 'in',
             ('transformacion_consumo', 'transformacion_produccion', 'merma')),
        ])
        if transformacion:
            raise UserError(
                f'El pesaje {self.name} generó movimientos de transformación '
                'Verde→Seco. El ajuste automático de inventario no soporta este '
                'caso: revierta y regenere el movimiento de inventario manualmente '
                'desde Inventario.'
            )

        # Move principal del picking. Debe existir exactamente uno con el producto
        # del pesaje; si el producto está vacío o hay ambigüedad, no adivinar.
        moves_producto = picking.move_ids.filtered(
            lambda m: m.product_id == self.producto_id
        ) if self.producto_id else picking.move_ids
        if len(moves_producto) != 1:
            raise UserError(
                f'No se pudo identificar el movimiento de inventario a ajustar '
                f'para el pesaje {self.name} (se encontraron {len(moves_producto)}). '
                'Corrija el inventario manualmente.'
            )
        move_orig = moves_producto

        qty = abs(diferencia)
        if diferencia > 0:
            loc_src, loc_dest = move_orig.location_id, move_orig.location_dest_id
        else:
            loc_src, loc_dest = move_orig.location_dest_id, move_orig.location_id

        # Owner del arroz (consignación de cliente). restrict_partner_id se debe
        # setear ANTES de _action_confirm para que el override
        # _update_reserved_quantity (stock_picking.py) filtre la reserva por dueño.
        owner = move_orig.restrict_partner_id or move_orig.move_line_ids[:1].owner_id

        move = self.env['stock.move'].create({
            'name': f'Ajuste peso {self.name} ({diferencia:+.0f} kg)',
            'product_id': move_orig.product_id.id,
            'product_uom_qty': qty,
            'product_uom': move_orig.product_uom.id,
            'location_id': loc_src.id,
            'location_dest_id': loc_dest.id,
            'x_pesaje_id': self.id,
            'restrict_partner_id': owner.id if owner else False,
        })
        if self.orden_servicio_id:
            move.x_orden_servicio_id = self.orden_servicio_id.id
        move._action_confirm()
        move._action_assign()
        # Si el ajuste SACA de una ubicación interna, exigir que haya stock
        # reservable: forzar la cantidad sin disponibilidad crearía un quant
        # negativo silencioso. Desde ubicaciones externas (proveedor/cliente/
        # producción) no hay restricción de stock y se procede como el resto
        # del módulo.
        if loc_src.usage == 'internal' and move.state != 'assigned':
            reservado = move.quantity
            move._action_cancel()
            raise UserError(
                f'No hay stock suficiente para ajustar el pesaje {self.name}: '
                f'se requieren {qty:.0f} kg en {loc_src.display_name} y solo hay '
                f'{reservado:.0f} kg reservables. Corrija el inventario manualmente.'
            )
        move.quantity = qty
        if owner:
            for ml in move.move_line_ids:
                ml.owner_id = owner.id
        move.picked = True
        move._action_done()
        self.message_post(
            body=f'Ajuste de inventario por corrección de peso: '
                 f'{neto_viejo:.0f} kg → {neto_nuevo:.0f} kg '
                 f'(diferencia {diferencia:+.0f} kg). Movimiento de ajuste: {move.name}.'
        )

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
        """Extiende cancelacion para cancelar picking vinculado.

        Primero llama a super() (que bloquea la cancelación de pesajes
        completados). Solo si el pesaje quedó cancelado se cancela el picking
        asociado, evitando dejar un picking cancelado con el pesaje intacto.
        """
        res = super().action_cancelar()
        for record in self:
            if (record.state == 'cancelado' and record.picking_id
                    and record.picking_id.state not in ('done', 'cancel')):
                record.picking_id.action_cancel()
        return res

    def action_borrador(self):
        """Impide volver a borrador si el inventario ya se movió.

        Un pesaje con picking validado (done) movió stock; volver a borrador y
        re-completarlo dejaría el inventario descuadrado. Se bloquea igual que
        el unlink.
        """
        for record in self:
            if record.picking_id and record.picking_id.state == 'done':
                raise UserError(
                    f'No se puede volver a borrador el pesaje {record.name}: su '
                    f'movimiento de inventario ({record.picking_id.name}) ya está '
                    f'validado. Cancele o revierta primero el movimiento.'
                )
        return super().action_borrador()

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

    def _get_producto_servicio(self, nombre):
        """Busca un producto por nombre para servicios"""
        tmpl = self.env['product.template'].search([('name', '=', nombre)], limit=1)
        if tmpl:
            return tmpl.product_variant_id
        return False

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
        self._validar_picking(picking)

        self.picking_id = picking.id

        # Para VENTA de Seco, crear movimientos de transformación Verde→Seco
        if tipo.tipo_inventario == 'salida':
            self._crear_transformacion_venta()

    def _crear_picking_servicio(self):
        """Crea picking para operaciones de SERVICIO con owner_id = cliente.
        - ENTRADA: siempre crea picking ENT-SRV
        - SALIDA modalidad bultos: crea picking SAL-SRV desde líneas de despacho
        - SALIDA granel/silobolsa: crea picking SAL-SRV desde peso neto
        """
        self.ensure_one()

        if self.picking_id:
            return

        if self.direccion == 'salida':
            if self.orden_servicio_id and self.orden_servicio_id.modalidad_salida == 'bultos':
                return self._crear_picking_salida_bultos()
            return self._crear_picking_salida_servicio()

        # Solo entrada de servicio
        producto = self.producto_id or self._get_producto_servicio('Arroz Paddy Verde')
        picking_type = self._get_picking_type('ENT-SRV')

        if not producto:
            raise UserError(
                'No se encontro el producto de arroz.\n'
                'Por favor seleccione un producto o verifique que los datos del modulo esten instalados.'
            )

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
        self._validar_picking(picking)

        self.picking_id = picking.id

    def _crear_picking_salida_servicio(self):
        """Crea picking SAL-SRV para salida de servicio (granel/silobolsa)."""
        self.ensure_one()

        producto = self.producto_id or self._get_producto_servicio('Arroz Paddy Seco')
        picking_type = self._get_picking_type('SAL-SRV')

        if not producto:
            raise UserError(
                'No se encontro el producto de arroz.\n'
                'Por favor seleccione un producto o verifique que los datos del modulo esten instalados.'
            )

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
        self._validar_picking(picking)

        self.picking_id = picking.id

    def _crear_picking_salida_bultos(self):
        """Crea picking SAL-SRV para salida de servicio con modalidad bultos.

        Usa las líneas de despacho (despacho_bultos_ids) para crear los
        movimientos de inventario, en vez del peso neto del pesaje.
        """
        self.ensure_one()

        if not self.despacho_bultos_ids:
            return

        picking_type = self._get_picking_type('SAL-SRV')
        producto = self.producto_id or self._get_producto_servicio('Arroz Paddy Seco')

        if not producto:
            raise UserError(
                'No se encontro el producto de arroz.\n'
                'Por favor seleccione un producto o verifique que los datos del modulo esten instalados.'
            )

        peso_total_bultos = sum(self.despacho_bultos_ids.mapped('peso_subtotal'))

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
                'name': f'{producto.name} - {self.name} (bultos)',
                'product_id': producto.id,
                'product_uom_qty': peso_total_bultos,
                'product_uom': producto.uom_id.id,
                'location_id': picking_type.default_location_src_id.id,
                'location_dest_id': picking_type.default_location_dest_id.id,
            })],
        }

        if self.orden_servicio_id:
            picking_vals['x_orden_servicio_id'] = self.orden_servicio_id.id

        picking = self.env['stock.picking'].create(picking_vals)
        picking.action_confirm()
        self._validar_picking(picking)

        self.picking_id = picking.id

    def _validar_picking(self, picking):
        """Valida el picking automáticamente asignando las cantidades hechas"""
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
        picking.button_validate()

    def _crear_transformacion_venta(self):
        """Crea movimientos de transformación Verde→Seco para operaciones propias (VENTA).

        Solo se dispara si el producto vendido es 'Arroz Paddy Seco'.
        Usa el factor de conversión configurable para calcular cuánto Verde se consumió.

        Genera 3 stock.moves:
          1. Consumo: Verde X kg  WH/Stock → Virtual/Production
          2. Producción: Seco Y kg  Virtual/Production → WH/Stock
          3. Merma: Verde (X-Y) kg  WH/Stock → Merma Secado
        """
        self.ensure_one()

        producto_seco = self._get_producto_servicio('Arroz Paddy Seco')
        if not producto_seco or self.producto_id != producto_seco:
            return

        producto_verde = self._get_producto_servicio('Arroz Paddy Verde')
        if not producto_verde:
            _logger.warning('Pesaje %s: No se encontro producto Arroz Paddy Verde para transformacion', self.name)
            return

        # Obtener factor de conversión
        factor = float(self.env['ir.config_parameter'].sudo().get_param(
            'bascula.factor_conversion_verde_seco', '1.18'
        ))

        peso_seco = self.peso_neto
        peso_verde_consumido = peso_seco * factor
        merma = peso_verde_consumido - peso_seco

        # Ubicaciones
        loc_stock = self.env.ref('stock.stock_location_stock', raise_if_not_found=False)
        loc_production = self.env['stock.location']._get_produccion_secadora(self.company_id)
        loc_merma = self.env.ref('secadora_bascula.stock_location_merma_secado', raise_if_not_found=False)

        if not loc_stock or not loc_production or not loc_merma:
            raise UserError(
                'No se pudo crear la transformación Verde→Seco: faltan ubicaciones de '
                'inventario (Stock, Producción o Merma Secado). Verifique la configuración '
                'del módulo antes de completar el pesaje.'
            )

        # Verificar disponibilidad de Verde en Stock (advertencia, no bloquear)
        quant_verde = self.env['stock.quant'].search([
            ('product_id', '=', producto_verde.id),
            ('location_id', '=', loc_stock.id),
            ('owner_id', '=', False),
        ])
        verde_disponible = sum(quant_verde.mapped('quantity'))
        if verde_disponible < peso_verde_consumido:
            _logger.warning(
                'Pesaje %s: Stock insuficiente de Verde. Disponible: %.2f kg, Requerido: %.2f kg. '
                'Se procedera de todas formas.',
                self.name, verde_disponible, peso_verde_consumido
            )

        uom_kg = producto_verde.uom_id

        move_vals = []

        # Move 1: Consumo Verde (Stock → Production)
        move_vals.append({
            'name': f'Consumo Verde - {self.name}',
            'product_id': producto_verde.id,
            'product_uom_qty': peso_verde_consumido,
            'product_uom': uom_kg.id,
            'location_id': loc_stock.id,
            'location_dest_id': loc_production.id,
            'x_pesaje_id': self.id,
            'x_tipo_movimiento_secadora': 'transformacion_consumo',
        })

        # Move 2: Producción Seco (Production → Stock)
        move_vals.append({
            'name': f'Produccion Seco - {self.name}',
            'product_id': producto_seco.id,
            'product_uom_qty': peso_seco,
            'product_uom': producto_seco.uom_id.id,
            'location_id': loc_production.id,
            'location_dest_id': loc_stock.id,
            'x_pesaje_id': self.id,
            'x_tipo_movimiento_secadora': 'transformacion_produccion',
        })

        # Move 3: Merma (Stock → Merma Secado) - solo si hay merma positiva
        if merma > 0:
            move_vals.append({
                'name': f'Merma Secado - {self.name}',
                'product_id': producto_verde.id,
                'product_uom_qty': merma,
                'product_uom': uom_kg.id,
                'location_id': loc_stock.id,
                'location_dest_id': loc_merma.id,
                'x_pesaje_id': self.id,
                'x_tipo_movimiento_secadora': 'merma',
            })

        orden_id = self.orden_servicio_id.id if self.orden_servicio_id else False

        for vals in move_vals:
            if orden_id:
                vals['x_orden_servicio_id'] = orden_id
            move = self.env['stock.move'].create(vals)
            move._action_confirm()
            move.quantity = move.product_uom_qty
            move.picked = True
            # Los movimientos que CONSUMEN Verde desde el stock propio
            # (consumo y merma, origen = WH/Stock) deben tomar solo arroz
            # propio (owner vacío), nunca el arroz de clientes en consignación.
            if move.location_id.id == loc_stock.id:
                for ml in move.move_line_ids:
                    ml.owner_id = False
            move._action_done()

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
