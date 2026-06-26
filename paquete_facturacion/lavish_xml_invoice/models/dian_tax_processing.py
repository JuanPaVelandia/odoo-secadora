# -*- coding: utf-8 -*-
import logging
from odoo import models, _

_logger = logging.getLogger(__name__)


class DianTaxProcessingMixin(models.AbstractModel):
    """Mixin para procesamiento de impuestos y retenciones DIAN"""
    _name = 'dian.tax.processing.mixin'
    _description = 'Mixin de Procesamiento de Impuestos DIAN'

    def _find_or_suggest_odoo_tax(self, tax_code, tax_name, tax_percentage, is_purchase=True):
        """Encuentra impuesto usando business.document.import con fallback a búsqueda manual"""
        Tax = self.env['account.tax']
        company = self.env.company
        chatter_msg = []

        dian_to_unece = {
            '01': 'VAT',
            '02': 'VAT',
            '03': 'VAT',
            '04': 'VAT',
            '05': 'VAT',
            '06': 'VAT',
            '07': 'VAT',
        }

        withholding_codes = ['05', '06', '07']
        is_withholding = tax_code in withholding_codes
        type_tax_use = 'purchase' if is_purchase else 'sale'

        tax_dict = {
            'amount_type': 'percent',
            'amount': -abs(tax_percentage) if is_withholding else tax_percentage,
        }
        if tax_code in dian_to_unece:
            tax_dict['unece_type_code'] = dian_to_unece[tax_code]

        matching_tax = self._match_tax(
            tax_dict,
            chatter_msg,
            type_tax_use=type_tax_use,
            raise_exception=False
        )

        if matching_tax:
            _logger.info(f"Impuesto via _match_tax: {matching_tax.name} ({matching_tax.amount}%)")
            return matching_tax

        domain = [
            ('company_id', '=', company.id),
            ('type_tax_use', '=', type_tax_use),
            ('amount_type', '=', 'percent'),
            ('amount', '=', -abs(tax_percentage) if is_withholding else tax_percentage),
        ]
        matching_tax = Tax.search(domain, limit=1)

        if matching_tax:
            _logger.info(f"Impuesto manual: {matching_tax.name} ({matching_tax.amount}%)")
            return matching_tax

        if tax_name:
            similar_tax = Tax.search([
                ('company_id', '=', company.id),
                ('type_tax_use', '=', type_tax_use),
                ('name', 'ilike', tax_name[:20])
            ], limit=1)
            if similar_tax:
                _logger.warning(f"Impuesto similar: {similar_tax.name}")
                return similar_tax

        if tax_code == '01':
            generic_iva = Tax.search([
                ('company_id', '=', company.id),
                ('type_tax_use', '=', type_tax_use),
                ('name', 'ilike', 'IVA'),
                ('amount', '=', tax_percentage)
            ], limit=1)
            if generic_iva:
                return generic_iva

        _logger.warning(f"No se encontró impuesto para {tax_code} - {tax_name} ({tax_percentage}%)")
        return False

    def _process_tax_totals(self, tax_totals):
        """Procesa resumen de impuestos"""
        if not isinstance(tax_totals, list):
            tax_totals = [tax_totals] if tax_totals else []

        total_tax = 0
        total_withholding = 0

        for tax_total in tax_totals:
            subtotals = tax_total.get('cac:TaxSubtotal', [])
            if not isinstance(subtotals, list):
                subtotals = [subtotals] if subtotals else []

            for subtotal in subtotals:
                category = subtotal.get('cac:TaxCategory', {})
                scheme = category.get('cac:TaxScheme', {})

                tax_code = self._get_value(scheme.get('cbc:ID', {})) or 'ZZ'
                tax_name = self._get_value(scheme.get('cbc:Name', {}))
                tax_base = float(self._get_value(subtotal.get('cbc:TaxableAmount', {})) or 0)
                tax_amt = float(self._get_value(subtotal.get('cbc:TaxAmount', {})) or 0)
                tax_pct = float(self._get_value(category.get('cbc:Percent', {})) or 0)

                odoo_tax = self._find_or_suggest_odoo_tax(
                    tax_code=tax_code,
                    tax_name=tax_name,
                    tax_percentage=tax_pct,
                    is_purchase=True
                )

                tax_field = self.env['dian.document.processor.tax']._fields.get('tax_code')
                valid_codes = []
                if tax_field and tax_field.selection:
                    if callable(tax_field.selection):
                        valid_codes = [s[0] for s in tax_field.selection(self.env['dian.document.processor.tax'])]
                    else:
                        valid_codes = [s[0] for s in tax_field.selection]

                vals = {
                    'tax_code': tax_code if tax_code in valid_codes else 'ZZ',
                    'tax_name': tax_name,
                    'tax_base': tax_base,
                    'tax_amount': tax_amt,
                    'tax_percentage': tax_pct,
                    'tax_id': odoo_tax.id if odoo_tax else False,
                }

                self.tax_summary_ids = [(0, 0, vals)]

                withholding_codes = ['05', '06', '07']
                if vals['tax_code'] in withholding_codes:
                    total_withholding += tax_amt
                else:
                    total_tax += tax_amt

        self.amount_tax = total_tax
        self.amount_withholding = total_withholding

    def _process_withholding_tax_totals(self, withholding_totals):
        """Procesa retenciones del documento"""
        if not withholding_totals:
            return

        if not isinstance(withholding_totals, list):
            withholding_totals = [withholding_totals]

        total_withholding = self.amount_withholding or 0

        for wh_total in withholding_totals:
            wh_amount = float(self._get_value(wh_total.get('cbc:TaxAmount', {})) or 0)

            subtotals = wh_total.get('cac:TaxSubtotal', [])
            if not isinstance(subtotals, list):
                subtotals = [subtotals] if subtotals else []

            for subtotal in subtotals:
                category = subtotal.get('cac:TaxCategory', {})
                scheme = category.get('cac:TaxScheme', {})

                tax_code = self._get_value(scheme.get('cbc:ID', {})) or 'ZZ'
                tax_name = self._get_value(scheme.get('cbc:Name', {}))
                tax_base = float(self._get_value(subtotal.get('cbc:TaxableAmount', {})) or 0)
                tax_amt = float(self._get_value(subtotal.get('cbc:TaxAmount', {})) or 0)
                tax_pct = float(self._get_value(category.get('cbc:Percent', {})) or 0)

                odoo_tax = self._find_or_suggest_odoo_tax(
                    tax_code=tax_code,
                    tax_name=tax_name,
                    tax_percentage=tax_pct,
                    is_purchase=True
                )

                tax_field = self.env['dian.document.processor.tax']._fields.get('tax_code')
                valid_codes = []
                if tax_field and tax_field.selection:
                    if callable(tax_field.selection):
                        valid_codes = [s[0] for s in tax_field.selection(self.env['dian.document.processor.tax'])]
                    else:
                        valid_codes = [s[0] for s in tax_field.selection]

                if tax_code not in valid_codes:
                    retention_map = {
                        'ReteIVA': '05',
                        'ReteFuente': '06',
                        'ReteICA': '07',
                        'Reteiva': '05',
                        'Retefuente': '06',
                        'Reteica': '07',
                    }
                    tax_code = retention_map.get(tax_code, 'ZZ')

                final_tax_code = tax_code if tax_code in valid_codes else 'ZZ'
                vals = {
                    'tax_code': final_tax_code,
                    'tax_name': tax_name or f'Retención {tax_code}',
                    'tax_base': tax_base,
                    'tax_amount': tax_amt,
                    'tax_percentage': tax_pct,
                    'tax_id': odoo_tax.id if odoo_tax else False,
                }

                self.tax_summary_ids = [(0, 0, vals)]
                total_withholding += tax_amt

                _logger.info(f"Retención: {tax_code} - {tax_name} - Base: {tax_base} - Monto: {tax_amt}")

        self.amount_withholding = total_withholding

    def _auto_match_taxes(self):
        """Intenta encontrar impuestos Odoo para todas las líneas de impuestos"""
        for tax_line in self.tax_summary_ids:
            if not tax_line.tax_id:
                odoo_tax = self._find_or_suggest_odoo_tax(
                    tax_code=tax_line.tax_code,
                    tax_name=tax_line.tax_name,
                    tax_percentage=tax_line.tax_percentage,
                    is_purchase=self._is_purchase()
                )
                if odoo_tax:
                    tax_line.tax_id = odoo_tax.id
