from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class TaxBaseThreshold(models.Model):
    _name = 'tax.base.threshold'
    _description = 'Tax Base Threshold'
    _order = 'tax_id, date_from desc'
    _rec_name = 'display_name'

    tax_id = fields.Many2one(
        'account.tax',
        string='Tax',
        required=True,
        ondelete='cascade',
        domain=[('needs_base_threshold', '=', True)]
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='tax_id.company_id',
        store=True,
        readonly=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        related='company_id.currency_id',
        readonly=True
    )

    date_from = fields.Date(
        string='Valid From',
        required=True,
        default=fields.Date.context_today
    )
    date_to = fields.Date(
        string='Valid To',
        required=False
    )

    # Base thresholds
    base_amount = fields.Float(
        string='Minimum Base Amount',
        digits='Product Price',
        required=True,
        help='Minimum base amount in company currency to apply this tax'
    )
    base_uvt = fields.Float(
        string='Minimum Base in UVT',
        digits=(16, 2),
        help='Minimum base amount in UVT units to apply this tax'
    )

    # Computed fields
    base_amount_from_uvt = fields.Float(
        string='Base Amount (from UVT)',
        compute='_compute_base_amount_from_uvt',
        digits='Product Price',
        help='Base amount calculated from UVT value'
    )
    uvt_value = fields.Float(
        string='Current UVT Value',
        compute='_compute_uvt_value',
        digits='Product Price'
    )
    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name',
        store=True
    )
    active = fields.Boolean(
        string='Active',
        default=True
    )

    @api.depends('date_from')
    def _compute_uvt_value(self):
        TaxParam = self.env['tax.general.parameter']
        for record in self:
            record.uvt_value = TaxParam.get_uvt_value(
                date_eval=record.date_from,
                company_id=record.company_id.id
            )

    @api.depends('base_uvt', 'uvt_value')
    def _compute_base_amount_from_uvt(self):
        for record in self:
            record.base_amount_from_uvt = record.base_uvt * record.uvt_value

    @api.depends('tax_id', 'date_from', 'base_amount', 'base_uvt')
    def _compute_display_name(self):
        for record in self:
            name_parts = [record.tax_id.name]
            name_parts.append(str(record.date_from))

            if record.base_uvt:
                name_parts.append(f"{record.base_uvt:.2f} UVT")
            elif record.base_amount:
                name_parts.append(f"{record.currency_id.symbol}{record.base_amount:,.2f}")

            record.display_name = ' - '.join(name_parts)

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for record in self:
            if record.date_to and record.date_from > record.date_to:
                raise ValidationError(_('End date must be after start date.'))

            # Check for overlapping periods for the same tax
            domain = [
                ('id', '!=', record.id),
                ('tax_id', '=', record.tax_id.id),
                ('active', '=', True),
                '|',
                    '&',
                        ('date_from', '<=', record.date_from),
                        '|',
                            ('date_to', '>=', record.date_from),
                            ('date_to', '=', False),
                    '&',
                        ('date_from', '<=', record.date_to if record.date_to else '2099-12-31'),
                        '|',
                            ('date_to', '>=', record.date_to if record.date_to else '2099-12-31'),
                            ('date_to', '=', False),
            ]

            if record.search_count(domain) > 0:
                raise ValidationError(_(
                    'There is already a threshold configuration for tax "%(tax)s" in this period. '
                    'Please check the dates.',
                    tax=record.tax_id.name
                ))

    @api.constrains('base_amount', 'base_uvt')
    def _check_base_values(self):
        for record in self:
            if record.base_amount < 0 or record.base_uvt < 0:
                raise ValidationError(_('Base amounts must be positive values.'))
            if not record.base_amount and not record.base_uvt:
                raise ValidationError(_('You must specify either a base amount or a base in UVT.'))

    def get_threshold_for_date(self, date_eval):
        """Get the threshold configuration for a specific date"""
        self.ensure_one()
        if self.date_from <= date_eval and (not self.date_to or self.date_to >= date_eval):
            return self
        return False

    @api.model
    def get_tax_threshold(self, tax_id, date_eval):
        """Get the active threshold for a tax on a specific date"""
        threshold = self.search([
            ('tax_id', '=', tax_id),
            ('date_from', '<=', date_eval),
            '|',
                ('date_to', '>=', date_eval),
                ('date_to', '=', False),
            ('active', '=', True)
        ], limit=1)
        return threshold

    def get_minimum_base(self, date_eval=None):
        """Calculate the minimum base amount considering UVT if applicable"""
        self.ensure_one()
        if not date_eval:
            date_eval = fields.Date.context_today(self)

        if self.base_uvt:
            # Calculate base from UVT
            uvt_value = self.env['tax.general.parameter'].get_uvt_value(
                date_eval=date_eval,
                company_id=self.company_id.id
            )
            return self.base_uvt * uvt_value
        else:
            return self.base_amount