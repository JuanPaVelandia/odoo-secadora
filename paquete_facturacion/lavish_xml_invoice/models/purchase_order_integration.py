# -*- coding: utf-8 -*-
"""
Purchase Order Matching para DIAN Document Processor
Permite asociar líneas de documentos DIAN con órdenes de compra existentes
"""

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_is_zero
from difflib import SequenceMatcher
import logging

_logger = logging.getLogger(__name__)


class DianDocumentProcessorLine(models.Model):
    """Extensión para agregar matching con Purchase Orders"""
    _inherit = 'dian.document.processor.line'

    # ========== CAMPOS DE MATCHING CON OC ==========
    purchase_order_id = fields.Many2one(
        'purchase.order',
        string='Orden de Compra',
        help='Orden de compra asociada a esta línea'
    )
    purchase_line_id = fields.Many2one(
        'purchase.order.line',
        string='Línea de OC',
        help='Línea específica de la orden de compra'
    )

    # Matching inteligente
    po_match_percentage = fields.Float(
        string='% Match OC',
        compute='_compute_po_match_percentage',
        store=False,
        help='Porcentaje de similitud con líneas de OC (0.0 a 1.0, donde 1.0 = 100%)'
    )
    po_match_reason = fields.Char(
        string='Razón Match OC',
        compute='_compute_po_match_percentage',
        help='Explica por qué se sugiere este match'
    )
    is_po_auto_matchable = fields.Boolean(
        string='Auto-asociable con OC',
        compute='_compute_is_po_auto_matchable',
        help='Indica si puede asociarse automáticamente según umbral'
    )
    po_match_threshold = fields.Float(
        string='Umbral Match OC',
        default=0.75,
        help='Umbral mínimo de similitud para match automático (0.75 = 75%)'
    )

    # Información de la línea de OC sugerida
    suggested_po_line_id = fields.Many2one(
        'purchase.order.line',
        string='Línea OC Sugerida',
        compute='_compute_suggested_po_line',
        help='Línea de OC sugerida automáticamente'
    )
    suggested_po_line_qty = fields.Float(
        string='Cant. OC Sugerida',
        compute='_compute_suggested_po_line_info',
        readonly=True
    )
    suggested_po_line_price = fields.Float(
        string='Precio OC Sugerida',
        compute='_compute_suggested_po_line_info',
        readonly=True
    )

    @api.depends('suggested_po_line_id')
    def _compute_suggested_po_line_info(self):
        for line in self:
            line.suggested_po_line_qty = line.suggested_po_line_id.product_qty or 0.0
            line.suggested_po_line_price = line.suggested_po_line_id.price_unit or 0.0

    # Validación de cantidades
    qty_to_invoice_po = fields.Float(
        string='Pendiente Facturar OC',
        compute='_compute_po_quantities',
        help='Cantidad pendiente de facturar en la OC'
    )
    qty_received_po = fields.Float(
        string='Cantidad Recibida OC',
        compute='_compute_po_quantities',
        help='Cantidad recibida en la OC'
    )

    # Estado de UdM
    uom_match_status = fields.Selection([
        ('match', 'Coincide'),
        ('convertible', 'Convertible'),
        ('mismatch', 'No Coincide'),
        ('unknown', 'Desconocido'),
    ], string='Estado UdM',
       compute='_compute_uom_match_status',
       help='Estado de coincidencia de unidades de medida')
    uom_warning = fields.Char(
        string='Advertencia UdM',
        compute='_compute_uom_match_status'
    )

    @api.depends('purchase_line_id', 'uom_id')
    def _compute_uom_match_status(self):
        """Verifica la compatibilidad de unidades de medida"""
        for line in self:
            if not line.purchase_line_id:
                line.uom_match_status = 'unknown'
                line.uom_warning = ''
                continue

            line_uom = line.uom_id
            po_uom = line.purchase_line_id.product_uom

            if not line_uom or not po_uom:
                line.uom_match_status = 'mismatch'
                line.uom_warning = _('Falta información de unidad de medida')
                continue

            # Verificar si son la misma UdM
            if line_uom == po_uom:
                line.uom_match_status = 'match'
                line.uom_warning = ''
            # Verificar si son convertibles (misma categoría)
            elif line_uom.category_id == po_uom.category_id:
                line.uom_match_status = 'convertible'
                line.uom_warning = _('UdMs diferentes pero convertibles: %s ↔ %s') % (
                    line_uom.name, po_uom.name
                )
            else:
                line.uom_match_status = 'mismatch'
                line.uom_warning = _('UdMs incompatibles: %s vs %s') % (
                    line_uom.name, po_uom.name
                )

    @api.depends('purchase_line_id')
    def _compute_po_quantities(self):
        """Calcula cantidades de la orden de compra"""
        for line in self:
            if line.purchase_line_id:
                pol = line.purchase_line_id
                line.qty_to_invoice_po = max(0, pol.product_qty - pol.qty_invoiced)
                line.qty_received_po = pol.qty_received or 0.0
            else:
                line.qty_to_invoice_po = 0.0
                line.qty_received_po = 0.0

    def _similarity_ratio(self, str1, str2):
        """Calcula el ratio de similitud entre dos strings (0.0 a 1.0)"""
        if not str1 or not str2:
            return 0.0
        s1 = ' '.join(str1.lower().split())
        s2 = ' '.join(str2.lower().split())
        return SequenceMatcher(None, s1, s2).ratio()

    @api.depends('product_id', 'product_code', 'product_name', 'quantity', 'price_unit', 'processor_id.supplier_id')
    def _compute_po_match_percentage(self):
        """Calcula el porcentaje de similitud con líneas de OC del proveedor"""
        for line in self:
            if not line.processor_id.supplier_id:
                line.po_match_percentage = 0.0
                line.po_match_reason = _('Sin proveedor definido')
                continue

            # Buscar líneas de OC del proveedor pendientes de facturar
            po_lines = line._find_candidate_po_lines()

            if not po_lines:
                line.po_match_percentage = 0.0
                line.po_match_reason = _('No hay OC pendientes del proveedor')
                continue

            # Calcular similitud con cada línea y tomar la mejor
            best_match = 0.0
            best_reason = []

            for po_line in po_lines:
                scores = []
                reasons = []

                # 1. Match por producto (peso: 40%)
                if line.product_id and po_line.product_id:
                    if line.product_id == po_line.product_id:
                        scores.append(0.40)
                        reasons.append(_('Mismo producto'))
                    else:
                        # Comparar por código
                        if line.product_code and po_line.product_id.default_code:
                            code_sim = self._similarity_ratio(
                                line.product_code,
                                po_line.product_id.default_code
                            )
                            if code_sim > 0:
                                scores.append(code_sim * 0.40)
                                if code_sim >= 0.8:
                                    reasons.append(_('Código similar (%.0f%%)') % (code_sim * 100))

                # 2. Match por descripción (peso: 20%)
                if line.product_name and po_line.name:
                    desc_sim = self._similarity_ratio(line.product_name, po_line.name)
                    if desc_sim > 0:
                        scores.append(desc_sim * 0.20)
                        if desc_sim >= 0.8:
                            reasons.append(_('Descripción similar'))

                # 3. Match por cantidad (peso: 15%)
                if line.quantity and po_line.product_qty:
                    qty_diff = abs(line.quantity - po_line.product_qty)
                    max_qty = max(line.quantity, po_line.product_qty)
                    qty_sim = max(0, 1 - (qty_diff / max_qty)) if max_qty > 0 else 0
                    if qty_sim > 0:
                        scores.append(qty_sim * 0.15)
                        if qty_sim >= 0.9:
                            reasons.append(_('Cantidad similar'))

                # 4. Match por precio (peso: 15%)
                if line.price_unit and po_line.price_unit:
                    price_diff = abs(line.price_unit - po_line.price_unit)
                    max_price = max(line.price_unit, po_line.price_unit)
                    price_sim = max(0, 1 - (price_diff / max_price)) if max_price > 0 else 0
                    if price_sim > 0:
                        scores.append(price_sim * 0.15)
                        if price_sim >= 0.9:
                            reasons.append(_('Precio similar'))

                # 5. Match por UdM (peso: 10%)
                if line.uom_id and po_line.product_uom:
                    if line.uom_id == po_line.product_uom:
                        scores.append(0.10)
                        reasons.append(_('UdM coincide'))
                    elif line.uom_id.category_id == po_line.product_uom.category_id:
                        scores.append(0.05)
                        reasons.append(_('UdM convertible'))

                match_score = sum(scores) if scores else 0.0

                if match_score > best_match:
                    best_match = match_score
                    best_reason = reasons

            line.po_match_percentage = best_match
            line.po_match_reason = ', '.join(best_reason) if best_reason else _('Sin coincidencias significativas')

    @api.depends('po_match_percentage', 'po_match_threshold')
    def _compute_is_po_auto_matchable(self):
        """Determina si puede auto-asociarse según umbral"""
        for line in self:
            line.is_po_auto_matchable = (
                line.po_match_percentage >= line.po_match_threshold and
                line.suggested_po_line_id and
                not line.purchase_line_id and
                line.uom_match_status != 'mismatch'
            )

    @api.depends('product_id', 'processor_id.supplier_id', 'po_match_percentage')
    def _compute_suggested_po_line(self):
        """Sugiere la mejor línea de OC para matching"""
        for line in self:
            if not line.processor_id.supplier_id or line.purchase_line_id:
                line.suggested_po_line_id = False
                continue

            # Buscar líneas candidatas
            po_lines = line._find_candidate_po_lines()

            if not po_lines:
                line.suggested_po_line_id = False
                continue

            # Calcular score para cada línea y tomar la mejor
            best_line = None
            best_score = 0.0

            for po_line in po_lines:
                score = line._calculate_match_score_with_po_line(po_line)
                if score > best_score:
                    best_score = score
                    best_line = po_line

            # Solo sugerir si supera un umbral mínimo
            if best_score >= 0.5:
                line.suggested_po_line_id = best_line
            else:
                line.suggested_po_line_id = False

    def _find_candidate_po_lines(self):
        """Busca líneas de OC candidatas para matching"""
        self.ensure_one()

        if not self.processor_id.supplier_id:
            return self.env['purchase.order.line']

        domain = [
            ('order_id.partner_id', '=', self.processor_id.supplier_id.id),
            ('order_id.state', 'in', ['purchase', 'done']),
            ('qty_to_invoice', '>', 0),  # Pendiente de facturar
        ]

        # Filtrar por producto si está identificado
        if self.product_id:
            domain.append(('product_id', '=', self.product_id.id))

        # Filtrar por referencia de OC si está en el documento
        if self.processor_id.order_reference:
            domain.append(('order_id.name', '=', self.processor_id.order_reference))

        return self.env['purchase.order.line'].search(domain, limit=50)

    def _calculate_match_score_with_po_line(self, po_line):
        """Calcula score de similitud con una línea específica de OC"""
        self.ensure_one()

        scores = []

        # Producto
        if self.product_id and po_line.product_id:
            if self.product_id == po_line.product_id:
                scores.append(0.40)
            else:
                if self.product_code and po_line.product_id.default_code:
                    code_sim = self._similarity_ratio(
                        self.product_code,
                        po_line.product_id.default_code
                    )
                    scores.append(code_sim * 0.40)

        # Descripción
        if self.product_name and po_line.name:
            desc_sim = self._similarity_ratio(self.product_name, po_line.name)
            scores.append(desc_sim * 0.20)

        # Cantidad
        if self.quantity and po_line.product_qty:
            qty_diff = abs(self.quantity - po_line.product_qty)
            max_qty = max(self.quantity, po_line.product_qty)
            qty_sim = max(0, 1 - (qty_diff / max_qty)) if max_qty > 0 else 0
            scores.append(qty_sim * 0.15)

        # Precio
        if self.price_unit and po_line.price_unit:
            price_diff = abs(self.price_unit - po_line.price_unit)
            max_price = max(self.price_unit, po_line.price_unit)
            price_sim = max(0, 1 - (price_diff / max_price)) if max_price > 0 else 0
            scores.append(price_sim * 0.15)

        # UdM
        if self.uom_id and po_line.product_uom:
            if self.uom_id == po_line.product_uom:
                scores.append(0.10)
            elif self.uom_id.category_id == po_line.product_uom.category_id:
                scores.append(0.05)

        return sum(scores) if scores else 0.0

    def action_associate_with_po_line(self):
        """Asocia manualmente con una línea de OC"""
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': _('Seleccionar Línea de Orden de Compra'),
            'res_model': 'dian.po.line.selection.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_dian_line_id': self.id,
                'default_supplier_id': self.processor_id.supplier_id.id,
            }
        }

    def action_auto_match_with_suggested(self):
        """Asocia automáticamente con la línea sugerida"""
        self.ensure_one()

        if not self.suggested_po_line_id:
            raise UserError(_('No hay línea de OC sugerida para esta línea'))

        if self.uom_match_status == 'mismatch':
            raise UserError(_('Las unidades de medida son incompatibles'))

        self.purchase_line_id = self.suggested_po_line_id
        self.purchase_order_id = self.suggested_po_line_id.order_id

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Éxito'),
                'message': _('Línea asociada con OC %s') % self.purchase_order_id.name,
                'type': 'success',
                'sticky': False,
            }
        }


class DianDocumentProcessor(models.Model):
    """Extensión para agregar funcionalidad de matching con OC"""
    _inherit = 'dian.document.processor'

    # Campos de matching
    purchase_order_ids = fields.Many2many(
        'purchase.order',
        string='Órdenes de Compra',
        compute='_compute_purchase_orders',
        help='Órdenes de compra asociadas a las líneas'
    )
    purchase_order_count = fields.Integer(
        string='# OC',
        compute='_compute_purchase_orders'
    )
    has_po_matches = fields.Boolean(
        string='Tiene Matches con OC',
        compute='_compute_has_po_matches'
    )
    po_match_progress = fields.Float(
        string='Progreso Matching (%)',
        compute='_compute_po_match_progress',
        help='Porcentaje de líneas asociadas con OC'
    )

    @api.depends('line_ids.purchase_order_id')
    def _compute_purchase_orders(self):
        """Calcula las órdenes de compra asociadas"""
        for processor in self:
            orders = processor.line_ids.mapped('purchase_order_id')
            processor.purchase_order_ids = orders
            processor.purchase_order_count = len(orders)

    @api.depends('line_ids.purchase_line_id')
    def _compute_has_po_matches(self):
        """Determina si hay líneas asociadas"""
        for processor in self:
            processor.has_po_matches = any(processor.line_ids.mapped('purchase_line_id'))

    @api.depends('line_ids.purchase_line_id', 'line_ids')
    def _compute_po_match_progress(self):
        """Calcula el progreso del matching"""
        for processor in self:
            total_lines = len(processor.line_ids)
            if total_lines == 0:
                processor.po_match_progress = 0.0
            else:
                matched_lines = len(processor.line_ids.filtered('purchase_line_id'))
                processor.po_match_progress = (matched_lines / total_lines) * 100

    def action_auto_match_all_po_lines(self):
        """Asocia automáticamente todas las líneas que cumplan el umbral"""
        self.ensure_one()

        matchable_lines = self.line_ids.filtered('is_po_auto_matchable')

        if not matchable_lines:
            raise UserError(_(
                'No hay líneas que cumplan el umbral mínimo de similitud para matching automático'
            ))

        matched_count = 0
        warnings = []

        for line in matchable_lines:
            if not line.purchase_line_id and line.suggested_po_line_id:
                # Advertencia si las UdM son convertibles
                if line.uom_match_status == 'convertible':
                    warnings.append(_('Línea %s: %s') % (line.sequence, line.uom_warning))

                line.purchase_line_id = line.suggested_po_line_id
                line.purchase_order_id = line.suggested_po_line_id.order_id
                matched_count += 1

        message = _('%d líneas fueron asociadas automáticamente con OC.') % matched_count
        if warnings:
            message += '\n\n' + _('Advertencias:') + '\n' + '\n'.join(warnings)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Matching Automático Completado'),
                'message': message,
                'type': 'warning' if warnings else 'success',
                'sticky': bool(warnings),
            }
        }

    def action_view_purchase_orders(self):
        """Abre las órdenes de compra asociadas"""
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': _('Órdenes de Compra'),
            'res_model': 'purchase.order',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.purchase_order_ids.ids)],
        }

    def action_open_po_matching_wizard(self):
        """Abre wizard para matching con OC"""
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': _('Asociar con Órdenes de Compra'),
            'res_model': 'dian.po.matching.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_processor_id': self.id,
            }
        }


class DianPOLineSelectionWizard(models.TransientModel):
    """Wizard para seleccionar línea de OC manualmente"""
    _name = 'dian.po.line.selection.wizard'
    _description = 'Seleccionar Línea de Orden de Compra'

    dian_line_id = fields.Many2one(
        'dian.document.processor.line',
        string='Línea DIAN',
        required=True,
        readonly=True
    )
    supplier_id = fields.Many2one(
        'res.partner',
        string='Proveedor',
        readonly=True
    )

    # Información de la línea DIAN
    product_name = fields.Char(related='dian_line_id.product_name', readonly=True)
    quantity = fields.Float(related='dian_line_id.quantity', readonly=True)
    price_unit = fields.Float(related='dian_line_id.price_unit', readonly=True)

    # Búsqueda de OC
    purchase_order_id = fields.Many2one(
        'purchase.order',
        string='Orden de Compra',
        domain="[('partner_id', '=', supplier_id), ('state', 'in', ['purchase', 'done'])]"
    )

    po_line_ids = fields.Many2many(
        'purchase.order.line',
        string='Líneas Disponibles',
        compute='_compute_po_lines'
    )

    selected_po_line_id = fields.Many2one(
        'purchase.order.line',
        string='Línea Seleccionada',
        domain="[('id', 'in', po_line_ids)]"
    )

    # Información de la línea seleccionada
    selected_line_qty = fields.Float(
        string='Cantidad OC',
        related='selected_po_line_id.product_qty',
        readonly=True
    )
    selected_line_price = fields.Float(
        string='Precio OC',
        related='selected_po_line_id.price_unit',
        readonly=True
    )
    match_score = fields.Float(
        string='Score de Similitud',
        compute='_compute_match_score'
    )

    @api.depends('purchase_order_id')
    def _compute_po_lines(self):
        """Obtiene las líneas de la OC seleccionada"""
        for wizard in self:
            if wizard.purchase_order_id:
                wizard.po_line_ids = wizard.purchase_order_id.order_line.filtered(
                    lambda l: l.qty_to_invoice > 0
                )
            else:
                wizard.po_line_ids = False

    @api.depends('selected_po_line_id', 'dian_line_id')
    def _compute_match_score(self):
        """Calcula el score de similitud con la línea seleccionada"""
        for wizard in self:
            if wizard.selected_po_line_id and wizard.dian_line_id:
                wizard.match_score = wizard.dian_line_id._calculate_match_score_with_po_line(
                    wizard.selected_po_line_id
                )
            else:
                wizard.match_score = 0.0

    def action_confirm(self):
        """Confirma la asociación"""
        self.ensure_one()

        if not self.selected_po_line_id:
            raise UserError(_('Debe seleccionar una línea de OC'))

        # Validar UdM
        if self.dian_line_id.uom_id and self.selected_po_line_id.product_uom:
            if (self.dian_line_id.uom_id.category_id !=
                self.selected_po_line_id.product_uom.category_id):
                raise UserError(_(
                    'Las unidades de medida son incompatibles:\n'
                    'DIAN: %s\nOC: %s'
                ) % (self.dian_line_id.uom_id.name,
                     self.selected_po_line_id.product_uom.name))

        # Asociar
        self.dian_line_id.write({
            'purchase_line_id': self.selected_po_line_id.id,
            'purchase_order_id': self.selected_po_line_id.order_id.id,
        })

        return {'type': 'ir.actions.act_window_close'}


class DianPOMatchingWizard(models.TransientModel):
    """Wizard para matching masivo con OC"""
    _name = 'dian.po.matching.wizard'
    _description = 'Matching con Órdenes de Compra'

    processor_id = fields.Many2one(
        'dian.document.processor',
        string='Procesador',
        required=True,
        readonly=True
    )

    supplier_id = fields.Many2one(
        related='processor_id.supplier_id',
        readonly=True
    )

    # Opciones de matching
    auto_match_threshold = fields.Float(
        string='Umbral de Match',
        default=0.75,
        help='Umbral mínimo de similitud (0.75 = 75%)'
    )

    only_exact_matches = fields.Boolean(
        string='Solo matches exactos',
        default=False,
        help='Solo asociar productos exactamente iguales'
    )

    # Filtros de OC
    purchase_order_id = fields.Many2one(
        'purchase.order',
        string='Filtrar por OC',
        domain="[('partner_id', '=', supplier_id), ('state', 'in', ['purchase', 'done'])]"
    )

    # Estadísticas
    total_lines = fields.Integer(
        string='Total Líneas',
        compute='_compute_stats'
    )
    matchable_lines = fields.Integer(
        string='Líneas Auto-asociables',
        compute='_compute_stats'
    )
    already_matched = fields.Integer(
        string='Ya Asociadas',
        compute='_compute_stats'
    )

    @api.depends('processor_id.line_ids')
    def _compute_stats(self):
        """Calcula estadísticas de matching"""
        for wizard in self:
            wizard.total_lines = len(wizard.processor_id.line_ids)
            wizard.already_matched = len(
                wizard.processor_id.line_ids.filtered('purchase_line_id')
            )
            wizard.matchable_lines = len(
                wizard.processor_id.line_ids.filtered('is_po_auto_matchable')
            )

    def action_preview_matches(self):
        """Vista previa de matches sugeridos"""
        self.ensure_one()

        # Aplicar umbral temporalmente
        self.processor_id.line_ids.write({'po_match_threshold': self.auto_match_threshold})

        # Mostrar líneas auto-asociables
        matchable_lines = self.processor_id.line_ids.filtered('is_po_auto_matchable')

        return {
            'type': 'ir.actions.act_window',
            'name': _('Vista Previa de Matches'),
            'res_model': 'dian.document.processor.line',
            'view_mode': 'list',
            'domain': [('id', 'in', matchable_lines.ids)],
            'target': 'new',
        }

    def action_execute_matching(self):
        """Ejecuta el matching automático"""
        self.ensure_one()

        # Aplicar configuración
        self.processor_id.line_ids.write({'po_match_threshold': self.auto_match_threshold})

        # Ejecutar matching
        return self.processor_id.action_auto_match_all_po_lines()


class DianDocumentProcessorPOCreation(models.Model):
    """Extensión para creación y búsqueda de OC"""
    _inherit = 'dian.document.processor'

    # Búsqueda por valor
    suggested_po_by_amount_ids = fields.Many2many(
        'purchase.order',
        string='OC Sugeridas por Monto',
        compute='_compute_suggested_po_by_amount',
        help='Órdenes de compra con monto similar'
    )

    has_suggested_po_by_amount = fields.Boolean(
        string='Tiene OC Sugeridas',
        compute='_compute_suggested_po_by_amount'
    )

    @api.depends('supplier_id', 'amount_total', 'document_currency_id', 'line_ids.product_id', 'line_ids.quantity')
    def _compute_suggested_po_by_amount(self):
        """Busca órdenes de compra con monto y cantidad similar"""
        for processor in self:
            if not processor.supplier_id or not processor.amount_total:
                processor.suggested_po_by_amount_ids = False
                processor.has_suggested_po_by_amount = False
                continue

            # Tolerancia del 5% en el monto y cantidad
            tolerance = 0.05
            min_amount = processor.amount_total * (1 - tolerance)
            max_amount = processor.amount_total * (1 + tolerance)

            # Contar productos y cantidad total en el documento DIAN
            doc_product_count = len(processor.line_ids.filtered(lambda l: l.product_id))
            doc_total_qty = sum(processor.line_ids.mapped('quantity'))

            # Buscar OCs del proveedor con monto similar
            domain = [
                ('partner_id', '=', processor.supplier_id.id),
                ('state', 'in', ['purchase', 'done']),
                ('amount_total', '>=', min_amount),
                ('amount_total', '<=', max_amount),
            ]

            # Filtrar por moneda si es posible
            if processor.document_currency_id:
                domain.append(('currency_id', '=', processor.document_currency_id.id))

            # Buscar todas las OCs que cumplan con los criterios de monto
            all_orders = self.env['purchase.order'].search(domain, limit=100)

            # Filtrar órdenes con lógica coherente por valor Y cantidad
            def is_order_eligible(po):
                # 1. Filtrar órdenes completamente procesadas
                if po.invoice_status == 'invoiced':
                    # Verificar si todas las líneas están completamente recibidas
                    if all(line.qty_received >= line.product_qty for line in po.order_line):
                        return False  # Completamente facturada Y recibida = excluir

                # 2. Verificar similitud de cantidad de productos
                po_product_count = len(po.order_line)
                if doc_product_count > 0:
                    # Tolerancia en cantidad de líneas
                    if abs(po_product_count - doc_product_count) > max(2, doc_product_count * 0.2):
                        return False  # Muy diferente cantidad de líneas

                # 3. Verificar similitud de cantidad total
                if doc_total_qty > 0:
                    po_total_qty = sum(po.order_line.mapped('product_qty'))
                    min_qty = doc_total_qty * (1 - tolerance)
                    max_qty = doc_total_qty * (1 + tolerance)
                    if not (min_qty <= po_total_qty <= max_qty):
                        return False  # Cantidad total muy diferente

                # 4. Bonus: Verificar coincidencia de productos si hay matches
                if doc_product_count > 0:
                    doc_products = set(processor.line_ids.filtered(lambda l: l.product_id).mapped('product_id.id'))
                    po_products = set(po.order_line.mapped('product_id.id'))
                    common_products = doc_products & po_products
                    # Si hay menos del 30% de productos en común, menos relevante
                    if len(common_products) < len(doc_products) * 0.3:
                        # No excluir, pero será menos relevante en el score
                        pass

                return True

            suggested_orders = all_orders.filtered(is_order_eligible)

            processor.suggested_po_by_amount_ids = suggested_orders[:20]  # Limitar a 20
            processor.has_suggested_po_by_amount = bool(suggested_orders)

    def action_create_purchase_order(self):
        """Crea una orden de compra desde el documento DIAN"""
        self.ensure_one()

        if not self.supplier_id:
            raise UserError(_('Debe definir un proveedor antes de crear la orden de compra'))

        if not self.line_ids:
            raise UserError(_('El documento no tiene líneas para crear la orden de compra'))

        # Verificar que los productos estén identificados
        lines_without_product = self.line_ids.filtered(lambda l: not l.product_id)
        if lines_without_product:
            raise UserError(_(
                '%d líneas no tienen producto identificado. '
                'Debe identificar todos los productos antes de crear la OC.'
            ) % len(lines_without_product))

        # Crear orden de compra
        po_vals = self._prepare_purchase_order_vals()
        purchase_order = self.env['purchase.order'].create(po_vals)

        # Crear líneas
        for line in self.line_ids:
            line_vals = self._prepare_purchase_order_line_vals(line, purchase_order)
            self.env['purchase.order.line'].create(line_vals)

        # Asociar líneas automáticamente
        for line in self.line_ids:
            # Buscar la línea creada
            po_line = purchase_order.order_line.filtered(
                lambda l: l.product_id == line.product_id and
                abs(l.product_qty - line.quantity) < 0.01
            )[:1]

            if po_line:
                line.write({
                    'purchase_order_id': purchase_order.id,
                    'purchase_line_id': po_line.id,
                })

        # Mensaje de éxito
        self.message_post(
            body=_('Orden de compra %s creada automáticamente desde documento DIAN') % purchase_order.name,
            subject=_('OC Creada')
        )

        return {
            'type': 'ir.actions.act_window',
            'name': _('Orden de Compra Creada'),
            'res_model': 'purchase.order',
            'res_id': purchase_order.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _prepare_purchase_order_vals(self):
        """Prepara valores para crear la orden de compra"""
        self.ensure_one()

        vals = {
            'partner_id': self.supplier_id.id,
            'currency_id': self.document_currency_id.id or self.currency_id.id,
            'date_order': self.issue_date or fields.Date.today(),
            'origin': _('DIAN: %s') % (self.document_number or self.cufe or 'Sin número'),
        }

        # Agregar referencia si existe
        if self.order_reference:
            vals['partner_ref'] = self.order_reference

        # Agregar fecha de entrega si existe
        if self.due_date:
            vals['date_planned'] = self.due_date

        # Agregar notas
        notes = []
        if self.document_number:
            notes.append(_('Documento DIAN: %s') % self.document_number)
        if self.cufe:
            notes.append(_('CUFE: %s') % self.cufe)
        if self.notes:
            notes.append(self.notes)

        if notes:
            vals['notes'] = '\n'.join(notes)

        return vals

    def _prepare_purchase_order_line_vals(self, dian_line, purchase_order):
        """Prepara valores para crear línea de orden de compra"""
        self.ensure_one()

        if not dian_line.product_id:
            raise UserError(_('La línea debe tener un producto identificado'))

        vals = {
            'order_id': purchase_order.id,
            'product_id': dian_line.product_id.id,
            'name': dian_line.product_name or dian_line.product_id.name,
            'product_qty': dian_line.quantity,
            'product_uom': dian_line.uom_id.id if dian_line.uom_id else dian_line.product_id.uom_po_id.id,
            'price_unit': dian_line.price_unit,
            'date_planned': self.due_date or fields.Date.today(),
        }

        # Agregar impuestos - PRIORIZAR impuestos extraídos del XML
        if dian_line.tax_ids:
            # Usar impuestos extraídos del XML (recomendado)
            _logger.info(f"Usando impuestos del XML para línea {dian_line.sequence}: {dian_line.tax_ids.mapped('name')}")
            vals['taxes_id'] = [(6, 0, dian_line.tax_ids.ids)]
        elif dian_line.product_id:
            # Si no hay impuestos del XML, usar impuestos del producto (fallback)
            taxes = dian_line.product_id.supplier_taxes_id
            # Filtrar por compañía actual si es necesario
            if taxes:
                # Usar la compañía del entorno o filtrar si hay múltiples compañías
                company_taxes = taxes.filtered(
                    lambda t: not t.company_id or t.company_id == self.env.company
                )
                if company_taxes:
                    _logger.info(f"Usando impuestos del producto (fallback) para línea {dian_line.sequence}: {company_taxes.mapped('name')}")
                    vals['taxes_id'] = [(6, 0, company_taxes.ids)]
                else:
                    # Si no hay taxes filtrados, usar todos
                    vals['taxes_id'] = [(6, 0, taxes.ids)]
        else:
            _logger.warning(f"No se encontraron impuestos para línea {dian_line.sequence}")

        return vals

    def action_view_suggested_po_by_amount(self):
        """Muestra wizard con órdenes sugeridas por monto"""
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': _('Órdenes de Compra Sugeridas por Monto'),
            'res_model': 'dian.po.suggestion.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_processor_id': self.id,
            }
        }


class DianPOSuggestionWizard(models.TransientModel):
    """Wizard para mostrar sugerencias de OC por monto"""
    _name = 'dian.po.suggestion.wizard'
    _description = 'Sugerencias de Órdenes de Compra por Monto'

    processor_id = fields.Many2one(
        'dian.document.processor',
        string='Procesador DIAN',
        required=True,
        readonly=True
    )

    supplier_id = fields.Many2one(
        related='processor_id.supplier_id',
        readonly=True
    )

    document_amount = fields.Monetary(
        string='Monto Documento',
        related='processor_id.amount_total',
        currency_field='currency_id',
        readonly=True
    )

    currency_id = fields.Many2one(
        related='processor_id.document_currency_id',
        readonly=True
    )

    suggestion_ids = fields.One2many(
        'dian.po.suggestion.line',
        'wizard_id',
        string='Órdenes Sugeridas',
        compute='_compute_suggestions'
    )

    tolerance_percentage = fields.Float(
        string='Tolerancia %',
        default=5.0,
        help='Porcentaje de tolerancia en el monto (5% = ±5%)'
    )

    has_suggestions = fields.Boolean(
        string='Tiene Sugerencias',
        compute='_compute_suggestions'
    )

    @api.depends('processor_id', 'tolerance_percentage')
    def _compute_suggestions(self):
        """Calcula las órdenes sugeridas"""
        for wizard in self:
            # Limpiar líneas existentes
            wizard.suggestion_ids = [(5, 0, 0)]

            if not wizard.processor_id.supplier_id or not wizard.processor_id.amount_total:
                wizard.has_suggestions = False
                continue

            # Calcular rango de búsqueda
            tolerance = wizard.tolerance_percentage / 100.0
            min_amount = wizard.processor_id.amount_total * (1 - tolerance)
            max_amount = wizard.processor_id.amount_total * (1 + tolerance)

            # Buscar órdenes
            domain = [
                ('partner_id', '=', wizard.processor_id.supplier_id.id),
                ('state', 'in', ['purchase', 'done']),
                ('amount_total', '>=', min_amount),
                ('amount_total', '<=', max_amount),
            ]

            if wizard.processor_id.document_currency_id:
                domain.append(('currency_id', '=', wizard.processor_id.document_currency_id.id))

            orders = self.env['purchase.order'].search(domain, limit=50, order='date_order desc')

            # Filtrar órdenes completamente procesadas
            eligible_orders = orders.filtered(
                lambda po: (
                    po.invoice_status != 'invoiced' or
                    any(line.qty_received < line.product_qty for line in po.order_line)
                )
            )

            # Datos del documento DIAN para comparación
            doc_total_qty = sum(wizard.processor_id.line_ids.mapped('quantity'))
            doc_product_ids = set(wizard.processor_id.line_ids.filtered(lambda l: l.product_id).mapped('product_id.id'))

            # Crear líneas de sugerencias
            lines = []
            for order in eligible_orders:
                # 1. Similitud por MONTO
                diff = order.amount_total - wizard.processor_id.amount_total
                diff_pct = (diff / wizard.processor_id.amount_total) if wizard.processor_id.amount_total else 0
                amount_similarity = max(0.0, 1.0 - abs(diff_pct))

                # 2. Similitud por CANTIDAD (peso 30%)
                po_total_qty = sum(order.order_line.mapped('product_qty'))
                if doc_total_qty > 0 and po_total_qty > 0:
                    qty_diff = abs(po_total_qty - doc_total_qty) / doc_total_qty
                    qty_similarity = max(0.0, 1.0 - qty_diff)
                else:
                    qty_similarity = 0.5  # Neutro si no hay datos

                # 3. Similitud por PRODUCTOS (peso 20%)
                po_product_ids = set(order.order_line.mapped('product_id.id'))
                if doc_product_ids and po_product_ids:
                    common_products = doc_product_ids & po_product_ids
                    product_similarity = len(common_products) / len(doc_product_ids)
                else:
                    product_similarity = 0.5  # Neutro si no hay datos

                # Score final ponderado: 50% monto + 30% cantidad + 20% productos
                similarity = (
                    amount_similarity * 0.50 +
                    qty_similarity * 0.30 +
                    product_similarity * 0.20
                )

                lines.append((0, 0, {
                    'purchase_order_id': order.id,
                    'amount_difference': diff,
                    'difference_percentage': diff_pct,  # Base 0-1 para widget percentage
                    'similarity_score': similarity,  # Base 0-1 para widget percentage
                }))

            wizard.suggestion_ids = lines
            wizard.has_suggestions = bool(lines)

    def action_refresh_suggestions(self):
        """Refresca las sugerencias con la nueva tolerancia"""
        self._compute_suggestions()
        return {'type': 'ir.actions.do_nothing'}


class DianPOSuggestionLine(models.TransientModel):
    """Línea de sugerencia de OC"""
    _name = 'dian.po.suggestion.line'
    _description = 'Línea de Sugerencia de OC'
    _order = 'similarity_score desc, id'

    wizard_id = fields.Many2one(
        'dian.po.suggestion.wizard',
        required=True,
        ondelete='cascade'
    )

    purchase_order_id = fields.Many2one(
        'purchase.order',
        string='Orden de Compra',
        required=True
    )

    # Información de la OC
    po_name = fields.Char(
        string='Número',
        related='purchase_order_id.name',
        readonly=True
    )

    po_date = fields.Datetime(
        string='Fecha',
        related='purchase_order_id.date_order',
        readonly=True
    )

    po_amount = fields.Monetary(
        string='Monto OC',
        related='purchase_order_id.amount_total',
        currency_field='currency_id',
        readonly=True
    )

    po_state = fields.Selection(
        related='purchase_order_id.state',
        readonly=True
    )

    po_partner_ref = fields.Char(
        string='Ref. Proveedor',
        related='purchase_order_id.partner_ref',
        readonly=True
    )

    po_line_ids = fields.One2many(
        related='purchase_order_id.order_line',
        string='Líneas de OC',
        readonly=True
    )

    po_line_count = fields.Integer(
        string='# Líneas',
        compute='_compute_po_line_count'
    )

    po_date_planned = fields.Datetime(
        string='Fecha Entrega',
        related='purchase_order_id.date_planned',
        readonly=True
    )

    po_invoice_status = fields.Selection(
        related='purchase_order_id.invoice_status',
        string='Estado Facturación',
        readonly=True
    )

    po_qty_to_receive = fields.Float(
        string='Pendiente Recibir',
        compute='_compute_po_pending_qty'
    )

    po_qty_to_invoice = fields.Float(
        string='Pendiente Facturar',
        compute='_compute_po_pending_qty'
    )

    currency_id = fields.Many2one(
        related='wizard_id.currency_id',
        readonly=True
    )

    @api.depends('purchase_order_id.order_line')
    def _compute_po_line_count(self):
        """Cuenta las líneas de la OC"""
        for line in self:
            line.po_line_count = len(line.purchase_order_id.order_line)

    @api.depends('purchase_order_id.order_line.qty_received', 'purchase_order_id.order_line.qty_invoiced')
    def _compute_po_pending_qty(self):
        """Calcula cantidades pendientes de recibir y facturar"""
        for line in self:
            po_lines = line.purchase_order_id.order_line
            line.po_qty_to_receive = sum(
                l.product_qty - l.qty_received for l in po_lines
            )
            line.po_qty_to_invoice = sum(
                l.product_qty - l.qty_invoiced for l in po_lines
            )

    # Análisis de similitud
    amount_difference = fields.Monetary(
        string='Diferencia',
        currency_field='currency_id',
        help='Diferencia con el monto del documento DIAN'
    )

    difference_percentage = fields.Float(
        string='Diferencia %',
        help='Porcentaje de diferencia con respecto al documento'
    )

    similarity_score = fields.Float(
        string='Similitud',
        help='Score de similitud (100 = idéntico, 0 = muy diferente)'
    )

    # Visualización
    similarity_class = fields.Char(
        string='Clase CSS',
        compute='_compute_similarity_class'
    )

    @api.depends('similarity_score')
    def _compute_similarity_class(self):
        """Determina la clase CSS según la similitud (escala 0-1)"""
        for line in self:
            if line.similarity_score >= 0.95:  # 95%
                line.similarity_class = 'text-success'
            elif line.similarity_score >= 0.90:  # 90%
                line.similarity_class = 'text-info'
            elif line.similarity_score >= 0.80:  # 80%
                line.similarity_class = 'text-warning'
            else:
                line.similarity_class = 'text-muted'

    def action_match_with_order(self):
        """Asocia el documento DIAN con esta orden de compra"""
        self.ensure_one()

        processor = self.wizard_id.processor_id

        # Intentar match automático de líneas
        matched_count = 0
        for dian_line in processor.line_ids:
            if dian_line.purchase_line_id:
                continue  # Ya está asociada

            if not dian_line.product_id:
                continue  # Sin producto identificado

            # Buscar línea en la OC
            po_line = self.purchase_order_id.order_line.filtered(
                lambda l: l.product_id == dian_line.product_id and
                l.qty_to_invoice > 0
            )[:1]

            if po_line:
                dian_line.write({
                    'purchase_order_id': self.purchase_order_id.id,
                    'purchase_line_id': po_line.id,
                })
                matched_count += 1

        # Mensaje
        if matched_count > 0:
            message = _('%d líneas asociadas con OC %s') % (matched_count, self.purchase_order_id.name)
        else:
            message = _('OC %s seleccionada. Asocie las líneas manualmente.') % self.purchase_order_id.name

        processor.message_post(
            body=message,
            subject=_('OC Asociada')
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Éxito'),
                'message': message,
                'type': 'success',
                'sticky': False,
            }
        }
