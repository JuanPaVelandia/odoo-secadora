# -*- coding: utf-8 -*-
"""
Matching de productos para documentos DIAN
Extiende DianDocumentProcessor con lógica de identificación de productos
"""

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from difflib import SequenceMatcher
import ast
import logging

_logger = logging.getLogger(__name__)


class DianDocumentProcessorProductMatching(models.Model):
    """Extensión de DianDocumentProcessor para matching de productos"""
    _inherit = 'dian.document.processor'

    # Campos de estadísticas
    products_matched_count = fields.Integer(
        'Productos Identificados',
        compute='_compute_product_stats',
        store=True
    )
    products_pending_count = fields.Integer(
        'Productos Pendientes',
        compute='_compute_product_stats',
        store=True
    )
    match_quality_percent = fields.Float(
        'Calidad Match %',
        compute='_compute_product_stats',
        store=True
    )

    @api.depends('line_ids.product_id', 'line_ids')
    def _compute_product_stats(self):
        """Calcula estadísticas de matching de productos"""
        for processor in self:
            total = len(processor.line_ids)
            matched = len(processor.line_ids.filtered('product_id'))
            processor.products_matched_count = matched
            processor.products_pending_count = total - matched
            processor.match_quality_percent = (matched / total * 100) if total > 0 else 0

    def action_predict_all_products(self):
        """Acción para predecir todos los productos pendientes"""
        self.ensure_one()
        chatter_msg = []
        matched = self._predict_products_full(chatter_msg)

        if matched > 0:
            self.message_post(
                body=_('Se identificaron %d producto(s) automaticamente') % matched,
                subject=_('Matching de Productos')
            )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Matching Completado'),
                'message': _('%d productos identificados, %d pendientes') % (
                    matched, self.products_pending_count
                ),
                'type': 'success' if self.products_pending_count == 0 else 'warning',
                'sticky': False,
            }
        }

    def _predict_products_full(self, chatter_msg):
        """Predicción completa de productos usando múltiples estrategias"""
        matched_count = 0

        for line in self.line_ids.filtered(lambda l: not l.product_id):
            product = self._find_product_multi_strategy(line, chatter_msg)

            if product:
                line.product_id = product
                matched_count += 1

                # Actualizar información de proveedor
                if self.update_product_codes:
                    self._update_supplier_product_info(product, line)

        return matched_count

    def _find_product_multi_strategy(self, line, chatter_msg):
        """Busca producto usando múltiples estrategias en orden de prioridad"""
        product = None

        # Estrategia 1: Código de barras EAN/GTIN
        if not product and line.product_ean:
            product = self._strategy_barcode(line, chatter_msg)

        # Estrategia 2: Código de proveedor
        if not product and line.product_code and self.supplier_id:
            product = self._strategy_supplier_code(line, chatter_msg)

        # Estrategia 3: Código interno
        if not product and line.product_code:
            product = self._strategy_internal_code(line, chatter_msg)

        # Estrategia 4: Nombre con similitud
        if not product and line.product_name:
            product = self._strategy_name_similarity(line, chatter_msg)

        # Estrategia 5: Código UNSPSC
        if not product and hasattr(line, 'unspsc_code') and line.unspsc_code:
            product = self._strategy_unspsc(line, chatter_msg)

        return product

    def _strategy_barcode(self, line, chatter_msg):
        """Estrategia 1: Buscar por código de barras"""
        product_dict = {
            'barcode': line.product_ean,
            'code': line.product_code or '',
        }

        product = self._match_product(
            product_dict,
            chatter_msg,
            seller=self.supplier_id or False,
            raise_exception=False
        )

        if product:
            _logger.info(f"Producto encontrado por barcode {line.product_ean}: {product.name}")

        return product

    def _strategy_supplier_code(self, line, chatter_msg):
        """Estrategia 2: Buscar por código de proveedor"""
        SupplierInfo = self.env['product.supplierinfo']

        # Búsqueda exacta
        supplierinfo = SupplierInfo.search([
            ('partner_id', '=', self.supplier_id.id),
            ('product_code', '=', line.product_code)
        ], limit=1)

        if supplierinfo:
            if supplierinfo.product_id:
                _logger.info(f"Producto encontrado por código proveedor {line.product_code}")
                return supplierinfo.product_id
            elif supplierinfo.product_tmpl_id:
                variants = supplierinfo.product_tmpl_id.product_variant_ids
                if len(variants) == 1:
                    return variants[0]

        # Búsqueda por nombre de producto en supplierinfo
        supplierinfo = SupplierInfo.search([
            ('partner_id', '=', self.supplier_id.id),
            ('product_name', 'ilike', line.product_code)
        ], limit=1)

        if supplierinfo and supplierinfo.product_id:
            return supplierinfo.product_id

        return None

    def _strategy_internal_code(self, line, chatter_msg):
        """Estrategia 3: Buscar por código interno"""
        product_dict = {'code': line.product_code}

        product = self._match_product(
            product_dict,
            chatter_msg,
            seller=False,
            raise_exception=False
        )

        if product:
            _logger.info(f"Producto encontrado por código interno {line.product_code}")

        return product

    def _strategy_name_similarity(self, line, chatter_msg, threshold=0.7):
        """Estrategia 4: Buscar por similitud de nombre"""
        if not line.product_name:
            return None

        search_name = line.product_name.lower().strip()

        # Buscar productos candidatos
        products = self.env['product.product'].search([
            '|', '|',
            ('name', 'ilike', search_name[:15]),
            ('default_code', 'ilike', search_name[:15]),
            ('product_tmpl_id.name', 'ilike', search_name[:15])
        ], limit=30)

        if not products:
            return None

        best_match = None
        best_score = 0.0

        for product in products:
            # Calcular similitud
            score = SequenceMatcher(
                None,
                search_name,
                product.name.lower()
            ).ratio()

            # Bonus si el código coincide parcialmente
            if line.product_code and product.default_code:
                if line.product_code in product.default_code:
                    score += 0.1

            if score > best_score and score >= threshold:
                best_score = score
                best_match = product

        if best_match:
            _logger.info(
                f"Producto encontrado por similitud ({best_score:.2f}): "
                f"{line.product_name} -> {best_match.name}"
            )

        return best_match

    def _strategy_unspsc(self, line, chatter_msg):
        """Estrategia 5: Buscar por código UNSPSC"""
        if not hasattr(line, 'unspsc_code') or not line.unspsc_code:
            return None

        unspsc = self.env['product.unspsc.code'].search([
            ('code', '=', line.unspsc_code),
            ('applies_to', '=', 'product')
        ], limit=1)

        if unspsc:
            product = self.env['product.product'].search([
                ('unspsc_code_id', '=', unspsc.id)
            ], limit=1)

            if product:
                _logger.info(f"Producto encontrado por UNSPSC {line.unspsc_code}")
                return product

        return None

    def _update_supplier_product_info(self, product, line):
        """Actualiza información del proveedor para el producto"""
        if not self.supplier_id:
            return

        SupplierInfo = self.env['product.supplierinfo']

        # Buscar info existente
        existing = SupplierInfo.search([
            ('partner_id', '=', self.supplier_id.id),
            ('product_id', '=', product.id)
        ], limit=1)

        vals = {
            'product_code': line.product_code,
            'product_name': line.product_name,
            'price': line.price_unit,
        }

        if self.document_currency_id:
            vals['currency_id'] = self.document_currency_id.id

        if existing:
            existing.write(vals)
            _logger.info(f"Actualizada info proveedor para {product.name}")
        else:
            vals.update({
                'partner_id': self.supplier_id.id,
                'product_id': product.id,
                'product_tmpl_id': product.product_tmpl_id.id,
            })
            SupplierInfo.create(vals)
            _logger.info(f"Creada info proveedor para {product.name}")

    def action_create_missing_products(self):
        """Crea productos para líneas sin identificar"""
        self.ensure_one()
        created = 0

        for line in self.line_ids.filtered(lambda l: not l.product_id):
            product = self._create_product_from_line(line)
            if product:
                line.product_id = product
                created += 1

        if created > 0:
            self.message_post(
                body=_('Se crearon %d producto(s) nuevos') % created,
                subject=_('Productos Creados')
            )

        return True

    def _create_product_from_line(self, line):
        """Crea un producto desde una línea DIAN"""
        Product = self.env['product.product']

        vals = {
            'name': line.product_name or _('Producto sin nombre'),
            'default_code': line.product_code,
            'barcode': line.product_ean if line.product_ean_type == 'gtin' else False,
            'type': 'consu',
            'purchase_ok': True,
            'sale_ok': True,
            'list_price': line.price_unit,
            'standard_price': line.price_unit,
        }

        # Agregar UoM si existe
        if line.uom_id:
            vals['uom_id'] = line.uom_id.id
            vals['uom_po_id'] = line.uom_id.id

        product = Product.create(vals)

        # Crear información de proveedor
        if self.supplier_id:
            self.env['product.supplierinfo'].create({
                'partner_id': self.supplier_id.id,
                'product_id': product.id,
                'product_tmpl_id': product.product_tmpl_id.id,
                'product_code': line.product_code,
                'product_name': line.product_name,
                'price': line.price_unit,
                'currency_id': self.document_currency_id.id if self.document_currency_id else False,
            })

        _logger.info(f"Producto creado desde DIAN: {product.name} [{product.default_code}]")

        return product


class DianDocumentProcessorLineMatching(models.Model):
    """Extensión de líneas para matching de productos"""
    _inherit = 'dian.document.processor.line'

    def action_find_product_wizard(self):
        """Abre wizard para buscar producto manualmente"""
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': _('Buscar Producto'),
            'res_model': 'dian.document.product.search.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_line_id': self.id,
                'default_search_term': self.product_name or self.product_code,
            }
        }

    def action_create_product(self):
        """Crea producto desde esta línea"""
        self.ensure_one()

        if self.product_id:
            raise UserError(_("Esta línea ya tiene un producto asociado"))

        product = self.processor_id._create_product_from_line(self)
        if product:
            self.product_id = product

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Producto Creado'),
                'message': product.display_name,
                'type': 'success',
                'sticky': False,
            }
        }
