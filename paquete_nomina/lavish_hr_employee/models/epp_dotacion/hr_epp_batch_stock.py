# -*- coding: utf-8 -*-
"""
Extensión de hr.epp.batch para crear stock.move AGRUPADOS por producto
"""

from odoo import models, api, _
from odoo.exceptions import UserError
from collections import defaultdict
import logging

_logger = logging.getLogger(__name__)


class HrEppBatchStock(models.Model):
    """Extensión para manejar movimientos de stock agrupados"""
    _inherit = 'hr.epp.batch'

    def action_create_batch_stock_moves(self):
        """
        Crear movimientos de stock AGRUPADOS por producto

        En lugar de crear un stock.move por cada línea de cada solicitud,
        agrupa todos los productos iguales y crea UN SOLO move con cantidad total.

        Ejemplo:
        - Solicitud 1: 3 camisas talla M
        - Solicitud 2: 3 camisas talla M
        - Solicitud 3: 3 camisas talla L

        Crea:
        - stock.move: 6 camisas talla M (agrupadas)
        - stock.move: 3 camisas talla L
        """
        self.ensure_one()

        if not self.use_stock_location:
            raise UserError(_('El control de inventario no está activado para este lote'))

        if self.batch_type not in ('epp', 'dotacion'):
            raise UserError(_('Los movimientos de stock solo aplican para EPP y Dotación'))

        # Diccionario para agrupar: {(product_id, location_id): cantidad_total}
        moves_grouped = defaultdict(lambda: {
            'quantity': 0,
            'location_id': None,
            'product_id': None,
            'product_name': '',
            'uom_id': None,
            'request_ids': []
        })

        # Recorrer todas las solicitudes del lote
        for request in self.request_ids.filtered(lambda r: r.state == 'approved'):
            # Determinar bodega para esta solicitud
            location_id = self._get_request_location(request)

            if not location_id:
                _logger.warning(f"No location for request {request.name}, skipping stock moves")
                continue

            # Recorrer líneas de la solicitud
            for line in request.line_ids:
                if not line.product_id:
                    continue

                # Clave: producto + bodega
                key = (line.product_id.id, location_id.id)

                # Acumular cantidad
                moves_grouped[key]['quantity'] += line.quantity
                moves_grouped[key]['location_id'] = location_id
                moves_grouped[key]['product_id'] = line.product_id
                moves_grouped[key]['product_name'] = line.name
                moves_grouped[key]['uom_id'] = line.product_id.uom_id
                moves_grouped[key]['request_ids'].append(request.id)

        if not moves_grouped:
            raise UserError(_('No hay productos configurados para crear movimientos de stock'))

        # Ubicación destino (consumo/empleados)
        location_dest_id = self.env.ref('stock.stock_location_customers').id

        # Crear stock.move AGRUPADOS
        created_moves = []
        for (product_id, location_id), data in moves_grouped.items():
            move = self.env['stock.move'].create({
                'name': f"{self.name} - {data['product_name']}",
                'product_id': data['product_id'].id,
                'product_uom_qty': data['quantity'],
                'product_uom': data['uom_id'].id,
                'location_id': location_id,
                'location_dest_id': location_dest_id,
                'origin': self.name,
                'company_id': self.company_id.id,
                'state': 'draft',
            })

            # Confirmar y asignar
            move._action_confirm()
            move._action_assign()

            created_moves.append(move.id)

            # Asociar el move a las solicitudes que lo generaron
            for req_id in set(data['request_ids']):
                request = self.env['hr.epp.request'].browse(req_id)
                request.stock_move_ids = [(4, move.id)]
                request.state = 'picking'

            _logger.info(
                f"Created stock.move {move.name}: {data['quantity']} units from {data['location_id'].name}"
            )

        # Cambiar estado del lote
        self.state = 'in_progress'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Movimientos Creados'),
                'message': _('Se crearon %d movimientos de stock agrupados') % len(created_moves),
                'type': 'success',
                'sticky': False,
            }
        }

    def _get_request_location(self, request):
        """Determinar bodega para una solicitud (3 niveles)"""

        # Nivel 1: Bodega del empleado
        if request.employee_location_id and self.allow_employee_location:
            return request.employee_location_id

        # Nivel 2: Bodega del batch
        elif self.default_location_id:
            return self.default_location_id

        # Nivel 3: Bodega de configuración
        elif request.configuration_id and request.configuration_id.location_id:
            return request.configuration_id.location_id

        return False

    def action_view_stock_moves(self):
        """Ver todos los movimientos de stock del lote"""
        self.ensure_one()

        # Obtener todos los moves de todas las solicitudes
        all_moves = self.request_ids.mapped('stock_move_ids')

        return {
            'type': 'ir.actions.act_window',
            'name': _('Movimientos de Stock del Lote'),
            'res_model': 'stock.move',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', all_moves.ids)],
            'context': {'create': False}
        }

    def action_validate_stock_moves(self):
        """Validar (done) todos los movimientos de stock"""
        self.ensure_one()

        all_moves = self.request_ids.mapped('stock_move_ids')
        pending_moves = all_moves.filtered(lambda m: m.state != 'done')

        for move in pending_moves:
            if move.state == 'draft':
                move._action_confirm()
            if move.state in ('confirmed', 'assigned'):
                move._action_done()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Movimientos Validados'),
                'message': _('Se validaron %d movimientos de stock') % len(pending_moves),
                'type': 'success',
            }
        }
