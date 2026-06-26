# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
import logging

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # Campo informativo para mostrar qué impuestos fueron filtrados por base
    withholding_info = fields.Text(
        string='Withholding Info',
        compute='_compute_withholding_info',
        help='Information about applied/skipped withholding taxes'
    )

    def _prepare_tax_context(self):
        """Prepare context for tax computation with additional parameters"""
        self.ensure_one()
        return {
            'invoice_date': self.date_order.date() if self.date_order else fields.Date.context_today(self),
            'order_date': self.date_order.date() if self.date_order else fields.Date.context_today(self),
            'partner_id': self.partner_id.id,
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
            'document_type': 'sale',
        }

    def _get_document_base_by_tax(self):
        """
        Calculate total base amount per tax for document-level evaluation

        Returns:
            dict: {tax_id: total_base_amount}
        """
        self.ensure_one()
        tax_bases = {}
        for line in self.order_line:
            line_base = line.price_subtotal
            for tax in line.tax_ids:
                if tax.id not in tax_bases:
                    tax_bases[tax.id] = 0.0
                tax_bases[tax.id] += line_base
        return tax_bases

    def _get_total_document_base(self):
        """Get total untaxed amount for document-level evaluation"""
        self.ensure_one()
        return self.amount_untaxed

    @api.depends('order_line.tax_ids', 'order_line.price_subtotal')
    def _compute_withholding_info(self):
        """Compute information about withholding tax application"""
        for order in self:
            info_lines = []
            date_eval = order.date_order.date() if order.date_order else fields.Date.context_today(order)
            document_base = order._get_total_document_base()
            tax_bases = order._get_document_base_by_tax()

            # Get all unique taxes with withholding concepts
            taxes_with_concepts = order.order_line.mapped('tax_ids').filtered(
                lambda t: t.use_withholding_concept and t.withholding_concept_id
            )

            for tax in taxes_with_concepts:
                concept = tax.withholding_concept_id

                # Skip if concept doesn't apply on sales
                if not concept.apply_on_sale:
                    info_lines.append(f"⚠ {concept.display_name}: No aplica en ventas")
                    continue

                # Determine which base to use
                if concept.base_evaluation == 'document':
                    base_to_check = document_base
                    base_label = "Total Documento"
                elif concept.base_evaluation == 'document_by_tax':
                    base_to_check = tax_bases.get(tax.id, 0)
                    base_label = "Total por Impuesto"
                else:
                    # Per line - will be calculated per line
                    continue

                # Check if tax applies
                contributor_type = tax._get_contributor_type(order.partner_id)
                should_apply = concept.should_apply_tax(
                    base_amount=base_to_check,
                    date_eval=date_eval,
                    contributor_type=contributor_type,
                    document_type='sale',
                    total_document_base=base_to_check
                )

                if should_apply['applies']:
                    info_lines.append(
                        f"✓ {concept.display_name}: Aplica ({base_label}: ${base_to_check:,.0f})"
                    )
                else:
                    info_lines.append(
                        f"✗ {concept.display_name}: {should_apply['reason']}"
                    )

            order.withholding_info = '\n'.join(info_lines) if info_lines else ''

    @api.depends('order_line.tax_ids', 'order_line.price_unit', 'amount_total', 'amount_untaxed', 'currency_id', 'date_order')
    def _compute_tax_totals(self):
        """Override to pass order date context for tax computation"""
        for order in self:
            # Prepare context with document-level bases
            ctx = order._prepare_tax_context()
            ctx['total_document_base'] = order._get_total_document_base()
            ctx['document_base_by_tax'] = order._get_document_base_by_tax()
            order = order.with_context(**ctx)
        return super()._compute_tax_totals()


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    # Campo informativo para mostrar el estado de retención por línea
    withholding_status = fields.Char(
        string='Withholding Status',
        compute='_compute_withholding_status',
        help='Status of withholding tax for this line'
    )

    @api.depends('tax_ids', 'price_subtotal', 'order_id.partner_id')
    def _compute_withholding_status(self):
        """Compute withholding status for each line"""
        for line in self:
            statuses = []
            date_eval = line.order_id.date_order.date() if line.order_id.date_order else fields.Date.context_today(line)

            # Get document-level bases
            document_base = line.order_id._get_total_document_base() if line.order_id else 0
            tax_bases = line.order_id._get_document_base_by_tax() if line.order_id else {}

            for tax in line.tax_ids.filtered(lambda t: t.use_withholding_concept and t.withholding_concept_id):
                concept = tax.withholding_concept_id

                # Skip if doesn't apply on sales
                if not concept.apply_on_sale:
                    continue

                # Determine base to evaluate
                if concept.base_evaluation == 'document':
                    base_to_check = document_base
                elif concept.base_evaluation == 'document_by_tax':
                    base_to_check = tax_bases.get(tax.id, 0)
                else:
                    base_to_check = line.price_subtotal

                contributor_type = tax._get_contributor_type(line.order_id.partner_id)
                should_apply = concept.should_apply_tax(
                    base_amount=base_to_check,
                    date_eval=date_eval,
                    contributor_type=contributor_type,
                    document_type='sale',
                    total_document_base=base_to_check if concept.base_evaluation != 'line' else None
                )

                if should_apply['applies']:
                    statuses.append(f"✓ {concept.code}")
                else:
                    statuses.append(f"✗ {concept.code}")

            line.withholding_status = ' | '.join(statuses) if statuses else ''

    def _prepare_line_tax_context(self):
        """Prepare context for line-level tax computation"""
        self.ensure_one()
        order = self.order_id
        return {
            'invoice_date': order.date_order.date() if order.date_order else fields.Date.context_today(self),
            'order_date': order.date_order.date() if order.date_order else fields.Date.context_today(self),
            'partner_id': order.partner_id.id if order.partner_id else False,
            'company_id': order.company_id.id if order.company_id else self.env.company.id,
            'currency_id': order.currency_id.id if order.currency_id else self.env.company.currency_id.id,
            'document_type': 'sale',
            'total_document_base': order._get_total_document_base() if order else 0,
            'document_base_by_tax': order._get_document_base_by_tax() if order else {},
            'base_line_record': self,
        }

