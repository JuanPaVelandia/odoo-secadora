# -*- coding: utf-8 -*-
"""
Mixin para importación de documentos DIAN
Extiende business.document.import con métodos específicos para Colombia
"""

from odoo import api, models, _
from odoo.exceptions import UserError
from odoo.fields import Domain as expression
from odoo.tools import float_compare
import logging

_logger = logging.getLogger(__name__)


class DianDocumentImportMixin(models.AbstractModel):
    """Mixin abstracto con métodos de matching específicos para DIAN Colombia"""
    _name = 'dian.document.import.mixin'
    _description = 'Mixin para importación de documentos DIAN'

    # Mapeo de códigos de impuestos DIAN a UNECE
    DIAN_TO_UNECE_TAX = {
        '01': 'VAT',      # IVA
        '02': 'VAT',      # IC - Impuesto al Consumo
        '03': 'VAT',      # ICA
        '04': 'VAT',      # INC
        '05': 'VAT',      # ReteIVA
        '06': 'VAT',      # ReteFuente
        '07': 'VAT',      # ReteICA
        '08': 'VAT',      # ReteCREE
    }

    # Códigos de retención DIAN
    WITHHOLDING_CODES = ['05', '06', '07', '08']

    # Mapeo de códigos UoM DIAN a UNECE
    DIAN_TO_UNECE_UOM = {
        '94': 'C62',   # Unidad
        'NIU': 'C62',  # Unidad
        'BX': 'C62',   # Caja -> Unidad
        'KGM': 'KGM',  # Kilogramo
        'LTR': 'LTR',  # Litro
        'MTR': 'MTR',  # Metro
        'MTK': 'MTK',  # Metro cuadrado
        'MTQ': 'MTQ',  # Metro cúbico
    }

    @api.model
    def _dian_match_partner_by_nit(self, nit, chatter_msg, partner_type='supplier'):
        """Busca partner por NIT colombiano"""
        if not nit:
            return None

        nit_clean = nit.replace(' ', '').replace('-', '').upper()

        # Formatos posibles de NIT
        nit_formats = [
            nit_clean,
            f'CO{nit_clean}',
            nit_clean.lstrip('CO'),
        ]

        domain = self._match_company_domain()
        order = 'supplier_rank desc' if partner_type == 'supplier' else 'customer_rank desc'

        for nit_format in nit_formats:
            partner = self.env['res.partner'].search(
                expression.AND([domain, [('vat', '=', nit_format)]]),
                limit=1,
                order=order
            )
            if partner:
                return partner

        # Búsqueda parcial
        partner = self.env['res.partner'].search(
            expression.AND([domain, [('vat', 'ilike', nit_clean[-9:])]]),
            limit=1,
            order=order
        )

        return partner or None

    @api.model
    def _dian_match_product_by_supplier(self, supplier, code, chatter_msg):
        """Busca producto por código de proveedor DIAN"""
        if not supplier or not code:
            return None

        # Buscar en product.supplierinfo
        supplierinfo = self.env['product.supplierinfo'].search([
            ('partner_id', '=', supplier.id),
            ('product_code', '=', code)
        ], limit=1)

        if supplierinfo:
            if supplierinfo.product_id:
                return supplierinfo.product_id
            elif supplierinfo.product_tmpl_id:
                variants = supplierinfo.product_tmpl_id.product_variant_ids
                if len(variants) == 1:
                    return variants[0]

        # Búsqueda alternativa por nombre
        supplierinfo = self.env['product.supplierinfo'].search([
            ('partner_id', '=', supplier.id),
            ('product_name', 'ilike', code)
        ], limit=1)

        if supplierinfo and supplierinfo.product_id:
            return supplierinfo.product_id

        return None

    @api.model
    def _dian_match_product_by_barcode(self, barcode, chatter_msg):
        """Busca producto por código de barras EAN/GTIN"""
        if not barcode:
            return None

        domain = self._match_company_domain()

        # Buscar por barcode directo
        product = self.env['product.product'].search(
            expression.AND([domain, [('barcode', '=', barcode)]]),
            limit=1
        )
        if product:
            return product

        # Buscar en packaging
        product = self.env['product.product'].search(
            expression.AND([domain, [('packaging_ids.barcode', '=', barcode)]]),
            limit=1
        )

        return product or None

    @api.model
    def _dian_match_product_by_code(self, code, chatter_msg):
        """Busca producto por código interno"""
        if not code:
            return None

        domain = self._match_company_domain()

        product = self.env['product.product'].search(
            expression.AND([domain, [('default_code', '=', code)]]),
            limit=1
        )

        return product or None

    @api.model
    def _dian_match_tax(self, tax_code, tax_percentage, chatter_msg, is_purchase=True):
        """Busca impuesto DIAN en Odoo"""
        Tax = self.env['account.tax']
        company = self.env.company

        is_withholding = tax_code in self.WITHHOLDING_CODES
        type_tax_use = 'purchase' if is_purchase else 'sale'

        # Preparar monto del impuesto
        amount = -abs(tax_percentage) if is_withholding else tax_percentage

        # Preparar diccionario para _match_tax de base_business_document_import
        tax_dict = {
            'amount_type': 'percent',
            'amount': amount,
        }

        if tax_code in self.DIAN_TO_UNECE_TAX:
            tax_dict['unece_type_code'] = self.DIAN_TO_UNECE_TAX[tax_code]

        # Intentar match con método base
        if hasattr(self, '_match_tax'):
            tax = self._match_tax(
                tax_dict,
                chatter_msg,
                type_tax_use=type_tax_use,
                raise_exception=False
            )
            if tax:
                return tax

        # Fallback: búsqueda directa
        domain = [
            ('company_id', '=', company.id),
            ('type_tax_use', '=', type_tax_use),
            ('amount_type', '=', 'percent'),
            ('amount', '=', amount),
        ]

        tax = Tax.search(domain, limit=1)
        if tax:
            return tax

        # Búsqueda por nombre
        tax_names = {
            '01': 'IVA',
            '04': 'INC',
            '05': 'ReteIVA',
            '06': 'ReteFuente',
            '07': 'ReteICA',
        }

        if tax_code in tax_names:
            tax = Tax.search([
                ('company_id', '=', company.id),
                ('type_tax_use', '=', type_tax_use),
                ('name', 'ilike', tax_names[tax_code]),
                ('amount', '=', amount)
            ], limit=1)

        return tax or None

    @api.model
    def _dian_match_uom(self, uom_code, chatter_msg, product=None):
        """Busca UoM por código DIAN/UNECE"""
        if not uom_code:
            if product:
                return product.uom_id
            return self.env.ref('uom.product_uom_unit', raise_if_not_found=False)

        # Convertir código DIAN a UNECE si es necesario
        unece_code = self.DIAN_TO_UNECE_UOM.get(uom_code, uom_code)

        # Buscar por código UNECE
        uom = self.env['uom.uom'].search([
            ('unece_code', '=', unece_code)
        ], limit=1)

        if uom:
            return uom

        # Buscar por código UNSPSC
        unspsc = self.env['product.unspsc.code'].search([
            ('code', '=', uom_code),
            ('applies_to', '=', 'uom'),
            ('active', '=', True)
        ], limit=1)

        if unspsc:
            uom = self.env['uom.uom'].search([
                ('unspsc_code_id', '=', unspsc.id)
            ], limit=1)
            if uom:
                return uom

        # Default
        if product:
            return product.uom_id
        return self.env.ref('uom.product_uom_unit', raise_if_not_found=False)

    @api.model
    def _dian_match_currency(self, currency_code, chatter_msg):
        """Busca moneda por código ISO"""
        if not currency_code:
            return self.env.company.currency_id

        currency = self.env['res.currency'].search([
            ('name', '=', currency_code.upper())
        ], limit=1)

        if currency:
            return currency

        # Mapeo de códigos alternativos
        currency_map = {
            'COP': 'COP',
            'USD': 'USD',
            'EUR': 'EUR',
            'PESO': 'COP',
            'DOLAR': 'USD',
        }

        mapped_code = currency_map.get(currency_code.upper(), currency_code)
        currency = self.env['res.currency'].search([
            ('name', '=', mapped_code)
        ], limit=1)

        return currency or self.env.company.currency_id

    @api.model
    def _dian_create_supplier_info(self, product, supplier, vals):
        """Crea o actualiza información de proveedor"""
        if not product or not supplier:
            return None

        SupplierInfo = self.env['product.supplierinfo']

        existing = SupplierInfo.search([
            ('partner_id', '=', supplier.id),
            ('product_id', '=', product.id)
        ], limit=1)

        if existing:
            existing.write(vals)
            return existing
        else:
            vals.update({
                'partner_id': supplier.id,
                'product_id': product.id,
                'product_tmpl_id': product.product_tmpl_id.id,
            })
            return SupplierInfo.create(vals)

    @api.model
    def _dian_log_match_result(self, entity_type, match_result, source_data):
        """Registra resultado de matching para debugging"""
        if match_result:
            _logger.info(
                f"DIAN Match {entity_type}: Encontrado {match_result.display_name} "
                f"desde {source_data}"
            )
        else:
            _logger.warning(
                f"DIAN Match {entity_type}: No encontrado para {source_data}"
            )
