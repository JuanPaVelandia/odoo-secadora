# -*- coding: utf-8 -*-
"""
Sincronización con Órdenes de Compra para documentos DIAN
Actualiza líneas de OC pendientes cuando se identifican productos
"""

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools import float_compare
import logging

_logger = logging.getLogger(__name__)


class DianDocumentProcessorPOSync(models.Model):
    """Extensión para sincronización con órdenes de compra"""
    _inherit = 'dian.document.processor'

    # Campos de relación con OC
    po_sync_enabled = fields.Boolean(
        'Sincronizar con OC',
        default=True,
        help='Actualizar automáticamente líneas de OC cuando se identifican productos'
    )
    po_lines_updated_count = fields.Integer(
        'Líneas OC Actualizadas',
        compute='_compute_po_sync_stats'
    )

    def _compute_po_sync_stats(self):
        """Calcula estadísticas de sincronización con OC"""
        for processor in self:
            updated = len(processor.line_ids.filtered('purchase_line_id'))
            processor.po_lines_updated_count = updated

    def action_sync_purchase_orders(self):
        """Sincroniza todos los productos identificados con OC pendientes"""
        self.ensure_one()

        if not self.supplier_id:
            raise UserError(_('Debe definir un proveedor para sincronizar con OC'))

        updated_count = 0
        chatter_msg = []

        for line in self.line_ids.filtered(lambda l: l.product_id):
            updated = self._sync_po_line(line.product_id, line, chatter_msg)
            if updated:
                updated_count += updated

        if updated_count > 0:
            self.message_post(
                body=_('Se actualizaron %d línea(s) de órdenes de compra') % updated_count,
                subject=_('Sincronización OC')
            )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Sincronización Completada'),
                'message': _('%d líneas de OC actualizadas') % updated_count,
                'type': 'success',
                'sticky': False,
            }
        }

    def _sync_po_line(self, product, dian_line, chatter_msg):
        """Sincroniza una línea DIAN con líneas de OC pendientes"""
        if not self.po_sync_enabled:
            return 0

        updated_count = 0

        # Buscar líneas de OC sin producto que coincidan
        po_lines = self._find_matching_po_lines(product, dian_line)

        for po_line in po_lines:
            self._update_po_line(po_line, product, dian_line)
            updated_count += 1

            msg = _(
                'Línea de OC %(po)s actualizada: %(product)s'
            ) % {
                'po': po_line.order_id.name,
                'product': product.display_name,
            }
            chatter_msg.append(msg)
            _logger.info(msg)

        return updated_count

    def _find_matching_po_lines(self, product, dian_line):
        """Encuentra líneas de OC que coinciden con el producto/código"""
        POLine = self.env['purchase.order.line']

        domain = [
            ('product_id', '=', False),
            ('order_id.partner_id', '=', self.supplier_id.id),
            ('order_id.state', 'in', ['draft', 'sent', 'to approve']),
        ]

        # Agregar condiciones de coincidencia
        match_conditions = []

        if dian_line.product_code:
            match_conditions.append(('name', 'ilike', dian_line.product_code))

        if dian_line.product_name:
            match_conditions.append(('name', 'ilike', dian_line.product_name[:30]))

        if not match_conditions:
            return POLine.browse()

        # Construir domain con OR
        if len(match_conditions) > 1:
            domain.append('|')
        domain.extend(match_conditions)

        return POLine.search(domain)

    def _update_po_line(self, po_line, product, dian_line):
        """Actualiza una línea de OC con el producto identificado"""
        vals = {
            'product_id': product.id,
        }

        # Actualizar precio si las monedas coinciden
        if self.document_currency_id == po_line.order_id.currency_id:
            vals['price_unit'] = dian_line.price_unit

        # Actualizar UoM si coincide con la del producto
        if dian_line.uom_id and dian_line.uom_id.category_id == product.uom_id.category_id:
            vals['product_uom'] = dian_line.uom_id.id

        po_line.write(vals)

        # Mensaje en la OC
        po_line.order_id.message_post(
            body=_(
                'Línea actualizada desde documento DIAN %(doc)s:<br/>'
                '- Producto: %(product)s<br/>'
                '- Precio: %(price)s'
            ) % {
                'doc': self.document_number,
                'product': product.display_name,
                'price': dian_line.price_unit,
            }
        )


class DianPurchaseOrderComparison(models.Model):
    """Comparación de documento DIAN con órdenes de compra"""
    _inherit = 'dian.document.processor'

    def action_compare_with_po(self):
        """Abre wizard para comparar con una OC específica"""
        self.ensure_one()

        if not self.supplier_id:
            raise UserError(_('Debe definir un proveedor primero'))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Comparar con Orden de Compra'),
            'res_model': 'dian.compare.po.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_processor_id': self.id,
                'default_supplier_id': self.supplier_id.id,
            }
        }

    def _compare_with_purchase_order(self, purchase_order, chatter_msg):
        """Compara líneas del documento con una OC usando compare_lines"""
        # Preparar líneas existentes (OC)
        existing_lines = []
        for po_line in purchase_order.order_line:
            existing_lines.append({
                'product': po_line.product_id,
                'name': po_line.name,
                'qty': po_line.product_qty,
                'price_unit': po_line.price_unit,
                'uom': po_line.product_uom,
                'line': po_line,
            })

        # Preparar líneas importadas (DIAN)
        import_lines = []
        for dian_line in self.line_ids:
            import_lines.append({
                'product': {
                    'barcode': dian_line.product_ean or '',
                    'code': dian_line.product_code or '',
                },
                'qty': dian_line.quantity,
                'price_unit': dian_line.price_unit,
                'uom': {'unece_code': dian_line.uom_code} if dian_line.uom_code else {},
            })

        # Usar compare_lines del módulo base
        result = self.compare_lines(
            existing_lines,
            import_lines,
            chatter_msg,
            seller=self.supplier_id
        )

        return result


class DianComparePOWizard(models.TransientModel):
    """Wizard para comparar documento DIAN con OC"""
    _name = 'dian.compare.po.wizard'
    _description = 'Comparar DIAN con Orden de Compra'

    processor_id = fields.Many2one(
        'dian.document.processor',
        required=True,
        readonly=True
    )
    supplier_id = fields.Many2one(
        'res.partner',
        readonly=True
    )
    purchase_order_id = fields.Many2one(
        'purchase.order',
        string='Orden de Compra',
        domain="[('partner_id', '=', supplier_id), ('state', 'in', ['purchase', 'done'])]",
        required=True
    )

    # Resultados
    comparison_html = fields.Html('Resultado', compute='_compute_comparison')
    lines_to_add = fields.Integer('Agregar', compute='_compute_comparison')
    lines_to_update = fields.Integer('Actualizar', compute='_compute_comparison')
    lines_to_remove = fields.Integer('Eliminar', compute='_compute_comparison')
    can_apply = fields.Boolean('Puede Aplicar', compute='_compute_comparison')

    @api.depends('purchase_order_id', 'processor_id')
    def _compute_comparison(self):
        """Ejecuta comparación y genera resultados"""
        for wizard in self:
            if not wizard.purchase_order_id or not wizard.processor_id:
                wizard.comparison_html = ''
                wizard.lines_to_add = 0
                wizard.lines_to_update = 0
                wizard.lines_to_remove = 0
                wizard.can_apply = False
                continue

            chatter_msg = []
            result = wizard.processor_id._compare_with_purchase_order(
                wizard.purchase_order_id,
                chatter_msg
            )

            if result:
                wizard.lines_to_add = len(result.get('to_add', []))
                wizard.lines_to_update = len(result.get('to_update', {}))
                wizard.lines_to_remove = len(result.get('to_remove') or [])
                wizard.can_apply = wizard.lines_to_update > 0
                wizard.comparison_html = wizard._format_comparison(result)
            else:
                wizard.comparison_html = '<p class="text-warning">No se pudo comparar</p>'
                wizard.lines_to_add = 0
                wizard.lines_to_update = 0
                wizard.lines_to_remove = 0
                wizard.can_apply = False

    def _format_comparison(self, result):
        """Formatea resultado de comparación como HTML"""
        html = ['<div class="o_comparison_result">']

        # Líneas a agregar
        to_add = result.get('to_add', [])
        if to_add:
            html.append('<h5>Lineas Nuevas:</h5><ul class="text-success">')
            for item in to_add:
                product = item.get('product')
                name = product.display_name if product else 'Sin identificar'
                qty = item.get('import_line', {}).get('qty', 0)
                html.append(f'<li>{name} (Cant: {qty})</li>')
            html.append('</ul>')

        # Líneas a actualizar
        to_update = result.get('to_update', {})
        if to_update:
            html.append('<h5>Lineas a Actualizar:</h5><ul class="text-info">')
            for line, updates in to_update.items():
                changes = []
                if 'qty' in updates:
                    changes.append(f'Cant: {updates["qty"][0]}→{updates["qty"][1]}')
                if 'price_unit' in updates:
                    changes.append(f'Precio: {updates["price_unit"][0]}→{updates["price_unit"][1]}')
                html.append(f'<li>{line.name}: {", ".join(changes)}</li>')
            html.append('</ul>')

        # Líneas a eliminar
        to_remove = result.get('to_remove')
        if to_remove:
            html.append('<h5>Lineas Sobrantes:</h5><ul class="text-danger">')
            for line in to_remove:
                html.append(f'<li>{line.name}</li>')
            html.append('</ul>')

        if not to_add and not to_update and not to_remove:
            html.append('<p class="text-success"><strong>Las lineas coinciden</strong></p>')

        html.append('</div>')
        return ''.join(html)

    def action_apply_updates(self):
        """Aplica las actualizaciones a la OC"""
        self.ensure_one()

        chatter_msg = []
        result = self.processor_id._compare_with_purchase_order(
            self.purchase_order_id,
            chatter_msg
        )

        if not result:
            raise UserError(_('No se pudo realizar la comparacion'))

        updated = 0
        for line, updates in result.get('to_update', {}).items():
            vals = {}
            if 'qty' in updates:
                vals['product_qty'] = updates['qty'][1]
            if 'price_unit' in updates:
                vals['price_unit'] = updates['price_unit'][1]
            if vals:
                line.write(vals)
                updated += 1

        self.purchase_order_id.message_post(
            body=_(
                'Orden actualizada desde documento DIAN %(doc)s<br/>'
                '%(count)d linea(s) modificada(s)'
            ) % {
                'doc': self.processor_id.document_number,
                'count': updated,
            }
        )

        return {'type': 'ir.actions.act_window_close'}
