# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class AccountTax(models.Model):
    _inherit = 'account.tax'

    # === CAMPOS ORIGINALES (mantener compatibilidad) ===
    needs_base_threshold = fields.Boolean(
        string='Requires Minimum Base',
        default=False,
        help='If checked, this tax will only apply when the base amount exceeds the configured threshold'
    )
    base_threshold_ids = fields.One2many(
        'tax.base.threshold',
        'tax_id',
        string='Base Thresholds (Legacy)',
        help='Configure minimum base amounts for different periods'
    )
    current_threshold_id = fields.Many2one(
        'tax.base.threshold',
        string='Current Threshold',
        compute='_compute_current_threshold',
        help='Active threshold for today'
    )

    # === NUEVOS CAMPOS PARA SISTEMA COLOMBIANO ===
    withholding_concept_id = fields.Many2one(
        'withholding.concept',
        string='Withholding Concept',
        help='Link to Colombian withholding concept for automatic rate/base calculation'
    )
    use_withholding_concept = fields.Boolean(
        string='Use Withholding Concept',
        default=False,
        help='If checked, use the withholding concept configuration for calculation'
    )
    contributor_type = fields.Selection([
        ('declarant', 'Declarant (Declarante)'),
        ('non_declarant', 'Non-Declarant (No Declarante)'),
        ('auto', 'Auto-detect from Partner'),
    ], string='Contributor Type', default='auto',
        help='Type of contributor for rate determination')

    # Campos informativos del concepto
    concept_rate_info = fields.Char(
        string='Current Rate Info',
        compute='_compute_concept_rate_info'
    )

    @api.depends('base_threshold_ids', 'base_threshold_ids.date_from', 'base_threshold_ids.date_to')
    def _compute_current_threshold(self):
        today = fields.Date.context_today(self)
        for tax in self:
            tax.current_threshold_id = tax.base_threshold_ids.filtered(
                lambda t: t.active and t.date_from <= today and (not t.date_to or t.date_to >= today)
            )[:1]

    @api.depends('withholding_concept_id', 'contributor_type')
    def _compute_concept_rate_info(self):
        today = fields.Date.context_today(self)
        for tax in self:
            if tax.withholding_concept_id:
                rate_info = tax.withholding_concept_id.get_current_rate(
                    date_eval=today,
                    contributor_type=tax.contributor_type if tax.contributor_type != 'auto' else 'declarant'
                )
                tax.concept_rate_info = _(
                    'Rate: %(rate).2f%% | Min Base: %(uvt).2f UVT ($%(amount)s)',
                    rate=rate_info['rate_percent'],
                    uvt=rate_info['min_base_uvt'],
                    amount=f"{rate_info['min_base_amount']:,.0f}"
                )
            else:
                tax.concept_rate_info = ''

    @api.onchange('withholding_concept_id')
    def _onchange_withholding_concept(self):
        """Auto-configure tax based on selected concept"""
        if self.withholding_concept_id:
            self.use_withholding_concept = True
            self.needs_base_threshold = self.withholding_concept_id.requires_minimum_base

    def _get_evaluation_date(self, record=None):
        """
        Get the evaluation date for tax computation from various sources
        """
        # Priority 1: Try to get from the record itself
        if record:
            if hasattr(record, 'move_id') and record.move_id:
                if hasattr(record.move_id, 'invoice_date') and record.move_id.invoice_date:
                    return record.move_id.invoice_date
                if hasattr(record.move_id, 'date') and record.move_id.date:
                    return record.move_id.date

            if hasattr(record, 'invoice_date') and record.invoice_date:
                return record.invoice_date
            if hasattr(record, 'date') and record.date:
                return record.date

            if hasattr(record, 'date_order') and record.date_order:
                return record.date_order.date() if hasattr(record.date_order, 'date') else record.date_order

            if hasattr(record, 'order_id') and record.order_id:
                if hasattr(record.order_id, 'date_order') and record.order_id.date_order:
                    return record.order_id.date_order.date() if hasattr(record.order_id.date_order, 'date') else record.order_id.date_order

        # Priority 2: Try to get from context
        date_eval = (
            self._context.get('invoice_date') or
            self._context.get('order_date') or
            self._context.get('date')
        )

        if date_eval:
            return date_eval

        # Priority 3: Use today's date as fallback
        return fields.Date.context_today(self)

    def _get_contributor_type(self, partner=None):
        """
        Determine contributor type from partner or tax configuration
        """
        self.ensure_one()

        if self.contributor_type != 'auto':
            return self.contributor_type

        if partner:
            # Check partner's fiscal position or custom field
            if hasattr(partner, 'is_tax_declarant'):
                return 'declarant' if partner.is_tax_declarant else 'non_declarant'
            # Check if it's a company (usually declarant)
            if partner.is_company:
                return 'declarant'
            # Check for VAT (NIT) - if has NIT, likely declarant
            if partner.vat:
                return 'declarant'

        return 'declarant'  # Default

    def _check_base_threshold_new(self, base_amount, date_eval=None, partner=None, record=None):
        """
        Check if the base amount meets the minimum threshold using new concept system

        Returns: dict with applies (bool), rate (float), reason (str)
        """
        self.ensure_one()

        if not self.use_withholding_concept or not self.withholding_concept_id:
            # Fall back to legacy behavior
            return self._check_base_threshold_legacy(base_amount, date_eval, record)

        if not date_eval:
            date_eval = self._get_evaluation_date(record)

        contributor_type = self._get_contributor_type(partner)
        concept = self.withholding_concept_id

        # Determine document type from context
        document_type = self._context.get('document_type', 'sale')

        # Determine which base to use based on concept configuration
        total_document_base = None
        base_to_evaluate = base_amount

        if concept.base_evaluation == 'document':
            # Use total document base from context
            total_document_base = self._context.get('total_document_base', base_amount)
            base_to_evaluate = total_document_base
        elif concept.base_evaluation == 'document_by_tax':
            # Use total base for this specific tax from context
            document_bases = self._context.get('document_base_by_tax', {})
            total_document_base = document_bases.get(self.id, base_amount)
            base_to_evaluate = total_document_base

        # Calculate using concept
        result = self.withholding_concept_id.calculate_withholding(
            base_amount=base_amount,  # Original line base for actual calculation
            date_eval=date_eval,
            contributor_type=contributor_type,
            document_type=document_type,
            total_document_base=total_document_base  # For threshold evaluation
        )

        return result

    def _check_base_threshold_legacy(self, base_amount, date_eval=None, record=None):
        """
        Legacy threshold check (backward compatibility)
        """
        self.ensure_one()

        if not self.needs_base_threshold:
            return {'applies': True, 'rate': self.amount, 'reason': ''}

        if not date_eval:
            date_eval = self._get_evaluation_date(record)

        threshold = self.env['tax.base.threshold'].get_tax_threshold(self.id, date_eval)

        if not threshold:
            _logger.warning(f'No threshold defined for tax {self.name} on date {date_eval}')
            return {'applies': True, 'rate': self.amount, 'reason': ''}

        minimum_base = threshold.get_minimum_base(date_eval)
        base_amount_abs = abs(base_amount)

        if base_amount_abs < minimum_base:
            return {
                'applies': False,
                'rate': 0,
                'reason': _(
                    'Base %(base)s < Threshold %(min)s',
                    base=f"${base_amount_abs:,.0f}",
                    min=f"${minimum_base:,.0f}"
                )
            }

        return {'applies': True, 'rate': self.amount, 'reason': ''}

    def _check_base_threshold(self, base_amount, date_eval=None, record=None):
        """
        Check if the base amount meets the minimum threshold requirement
        Wrapper that calls new or legacy method
        """
        self.ensure_one()

        if self.use_withholding_concept and self.withholding_concept_id:
            result = self._check_base_threshold_new(base_amount, date_eval, record=record)
            return result.get('applies', True)
        else:
            result = self._check_base_threshold_legacy(base_amount, date_eval, record)
            return result.get('applies', True)

    def compute_all(self, price_unit, currency=None, quantity=1.0, product=None, partner=None,
                    is_refund=False, handle_price_include=True, include_caba_tags=False,
                    rounding_method=None):
        """
        Override compute_all to check base thresholds before applying taxes
        """
        record = self._context.get('base_line_record')
        date_eval = self._get_evaluation_date(record)

        if not currency:
            company = self[0].company_id if self else self.env.company
            currency = company.currency_id

        # Calculate base amount in company currency
        base_amount = price_unit * quantity
        if currency != self.env.company.currency_id:
            base_amount = currency._convert(
                base_amount,
                self.env.company.currency_id,
                self.env.company,
                date_eval
            )

        # Filter taxes based on threshold
        taxes_to_apply = self.env['account.tax']
        for tax in self:
            if tax.use_withholding_concept and tax.withholding_concept_id:
                result = tax._check_base_threshold_new(base_amount, date_eval, partner, record)
                if result.get('applies', True):
                    taxes_to_apply |= tax
            elif tax._check_base_threshold(base_amount, date_eval, record):
                taxes_to_apply |= tax

        # If some taxes were filtered out, recompute
        if len(taxes_to_apply) < len(self):
            if not taxes_to_apply:
                return {
                    'total_excluded': price_unit * quantity,
                    'total_included': price_unit * quantity,
                    'total_void': 0.0,
                    'base_tags': [],
                    'taxes': [],
                }
            else:
                return super(AccountTax, taxes_to_apply).compute_all(
                    price_unit=price_unit,
                    currency=currency,
                    quantity=quantity,
                    product=product,
                    partner=partner,
                    is_refund=is_refund,
                    handle_price_include=handle_price_include,
                    include_caba_tags=include_caba_tags,
                    rounding_method=rounding_method
                )

        return super().compute_all(
            price_unit=price_unit,
            currency=currency,
            quantity=quantity,
            product=product,
            partner=partner,
            is_refund=is_refund,
            handle_price_include=handle_price_include,
            include_caba_tags=include_caba_tags,
            rounding_method=rounding_method
        )

    def _compute_amount(self, base_amount, price_unit, quantity, product, partner, fixed_multiplicator=1):
        """
        Override to check threshold before computing tax amount
        """
        record = self._context.get('base_line_record')
        date_eval = self._get_evaluation_date(record)

        if self.use_withholding_concept and self.withholding_concept_id:
            result = self._check_base_threshold_new(base_amount, date_eval, partner, record)
            if not result.get('applies', True):
                return 0.0

            # For progressive taxes, use the calculated amount
            if self.withholding_concept_id.calculation_type == 'progressive':
                return result.get('withholding_amount', 0.0) * (-1 if self.amount < 0 else 1)

        elif not self._check_base_threshold(base_amount, date_eval, record):
            return 0.0

        return super()._compute_amount(
            base_amount=base_amount,
            price_unit=price_unit,
            quantity=quantity,
            product=product,
            partner=partner,
            fixed_multiplicator=fixed_multiplicator
        )

    @api.model
    def _add_tax_details_in_base_line(self, base_line, company, rounding_method=None):
        """
        Override to filter out withholding taxes that don't meet minimum base threshold.
        This is where Odoo 18 calculates taxes for invoices.
        """
        # Get the original tax_ids before filtering
        original_taxes = base_line.get('tax_ids', self.env['account.tax'])

        if not original_taxes:
            return super()._add_tax_details_in_base_line(base_line, company, rounding_method)

        # Calculate the base amount for threshold comparison
        price_unit_after_discount = base_line['price_unit'] * (1 - (base_line['discount'] / 100.0))
        base_amount = price_unit_after_discount * base_line['quantity']

        # Get evaluation date from context or base_line
        date_eval = (
            self._context.get('invoice_date') or
            self._context.get('date') or
            base_line.get('date') or
            fields.Date.context_today(self)
        )

        # Get partner from context or base_line
        partner = base_line.get('partner_id') or self._context.get('partner_id')
        if isinstance(partner, int):
            partner = self.env['res.partner'].browse(partner)

        # Filter taxes: keep those that pass threshold check or don't use withholding concept
        taxes_to_keep = self.env['account.tax']
        taxes_filtered_out = []

        for tax in original_taxes:
            if tax.use_withholding_concept and tax.withholding_concept_id:
                # Check if this tax should apply based on minimum base threshold
                result = tax._check_base_threshold_new(
                    base_amount=base_amount,
                    date_eval=date_eval,
                    partner=partner,
                    record=None
                )
                if result.get('applies', True):
                    taxes_to_keep |= tax
                else:
                    taxes_filtered_out.append({
                        'tax': tax.name,
                        'reason': result.get('reason', 'Base below threshold')
                    })
                    _logger.info(
                        f"Tax '{tax.name}' filtered out: {result.get('reason', 'Base below threshold')} "
                        f"(base=${base_amount:,.0f})"
                    )
            else:
                # Non-withholding taxes always apply
                taxes_to_keep |= tax

        # Update base_line with filtered taxes
        base_line['tax_ids'] = taxes_to_keep

        # Call parent method with filtered taxes
        result = super()._add_tax_details_in_base_line(base_line, company, rounding_method)

        # Restore original taxes (in case something else needs them)
        base_line['tax_ids'] = original_taxes

        return result
