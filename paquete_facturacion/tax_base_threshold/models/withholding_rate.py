# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class WithholdingRate(models.Model):
    """
    Tarifas de Retención por Año y Concepto

    Maneja:
    - Tarifas fijas (ej: Servicios 4%)
    - Tarifas diferenciadas (ej: Compras declarantes 2.5%, no declarantes 3.5%)
    - Bases mínimas en UVT o valor fijo
    """
    _name = 'withholding.rate'
    _description = 'Withholding Rate by Period'
    _order = 'concept_id, date_from desc'
    _rec_name = 'display_name'

    # Relación con concepto
    concept_id = fields.Many2one(
        'withholding.concept',
        string='Concept',
        required=True,
        ondelete='cascade'
    )
    concept_type = fields.Selection(
        related='concept_id.concept_type',
        store=True
    )
    calculation_type = fields.Selection(
        related='concept_id.calculation_type',
        store=True
    )

    # Período de vigencia
    date_from = fields.Date(
        string='Valid From',
        required=True
    )
    date_to = fields.Date(
        string='Valid To'
    )
    fiscal_year = fields.Char(
        string='Fiscal Year',
        compute='_compute_fiscal_year',
        store=True
    )

    # Tarifas
    rate_percent = fields.Float(
        string='Rate (%)',
        digits=(5, 2),
        help='Standard rate percentage'
    )
    rate_declarant = fields.Float(
        string='Rate Declarant (%)',
        digits=(5, 2),
        help='Rate for tax declarants (contribuyentes declarantes)'
    )
    rate_non_declarant = fields.Float(
        string='Rate Non-Declarant (%)',
        digits=(5, 2),
        help='Rate for non-declarants (no declarantes)'
    )

    # Base mínima
    min_base_uvt = fields.Float(
        string='Minimum Base (UVT)',
        digits=(10, 2),
        help='Minimum base in UVT units'
    )
    min_base_fixed = fields.Float(
        string='Minimum Base (COP)',
        digits='Product Price',
        help='Fixed minimum base in Colombian Pesos'
    )

    # Campos computados
    min_base_computed = fields.Float(
        string='Min Base (COP)',
        compute='_compute_min_base',
        digits='Product Price',
        help='Computed minimum base based on current UVT'
    )
    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name',
        store=True
    )

    # Estado
    active = fields.Boolean(
        string='Active',
        default=True
    )

    # Notas y referencia legal
    notes = fields.Text(
        string='Notes'
    )
    legal_reference = fields.Char(
        string='Legal Reference',
        help='Decree or article reference'
    )

    @api.depends('date_from')
    def _compute_fiscal_year(self):
        for record in self:
            record.fiscal_year = str(record.date_from.year) if record.date_from else ''

    @api.depends('concept_id', 'date_from', 'rate_percent', 'rate_declarant', 'min_base_uvt')
    def _compute_display_name(self):
        for record in self:
            parts = []
            if record.concept_id:
                parts.append(record.concept_id.code)
            if record.date_from:
                parts.append(str(record.date_from.year))
            if record.calculation_type == 'by_contributor':
                parts.append(f"D:{record.rate_declarant}% / ND:{record.rate_non_declarant}%")
            elif record.rate_percent:
                parts.append(f"{record.rate_percent}%")
            if record.min_base_uvt:
                parts.append(f"≥{record.min_base_uvt} UVT")

            record.display_name = ' - '.join(parts) if parts else _('New Rate')

    @api.depends('min_base_uvt', 'min_base_fixed', 'date_from', 'concept_id.base_type')
    def _compute_min_base(self):
        TaxParam = self.env['tax.general.parameter']
        for record in self:
            if record.concept_id.base_type == 'uvt' and record.min_base_uvt:
                uvt_value = TaxParam.get_uvt_value(
                    date_eval=record.date_from,
                    company_id=record.concept_id.company_id.id
                )
                record.min_base_computed = record.min_base_uvt * uvt_value
            else:
                record.min_base_computed = record.min_base_fixed

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for record in self:
            if record.date_to and record.date_from > record.date_to:
                raise ValidationError(_('End date must be after start date.'))

    @api.constrains('rate_percent', 'rate_declarant', 'rate_non_declarant')
    def _check_rates(self):
        for record in self:
            if record.calculation_type == 'by_contributor':
                if record.rate_declarant < 0 or record.rate_non_declarant < 0:
                    raise ValidationError(_('Rates cannot be negative.'))
            elif record.rate_percent < 0:
                raise ValidationError(_('Rate cannot be negative.'))


class WithholdingBracket(models.Model):
    """
    Rangos Progresivos para Retención (Ej: Tabla Art. 383 E.T.)

    Cada rango define:
    - Desde UVT / Hasta UVT
    - Tarifa marginal %
    - Fórmula: (Base - resta_uvt) * tarifa% + mas_uvt
    """
    _name = 'withholding.bracket'
    _description = 'Progressive Withholding Bracket'
    _order = 'concept_id, date_from desc, from_uvt'
    _rec_name = 'display_name'

    # Relación con concepto
    concept_id = fields.Many2one(
        'withholding.concept',
        string='Concept',
        required=True,
        ondelete='cascade',
        domain=[('calculation_type', '=', 'progressive')]
    )

    # Período de vigencia
    date_from = fields.Date(
        string='Valid From',
        required=True
    )
    date_to = fields.Date(
        string='Valid To'
    )

    # Definición del rango
    bracket_number = fields.Integer(
        string='Bracket #',
        required=True,
        help='Bracket number (1, 2, 3, ...)'
    )
    from_uvt = fields.Float(
        string='From (UVT)',
        digits=(10, 2),
        required=True,
        help='Lower limit in UVT (exclusive, >)'
    )
    to_uvt = fields.Float(
        string='To (UVT)',
        digits=(10, 2),
        help='Upper limit in UVT (inclusive, <=). Leave 0 for infinite.'
    )

    # Fórmula de cálculo
    rate_percent = fields.Float(
        string='Marginal Rate (%)',
        digits=(5, 2),
        required=True,
        help='Marginal tax rate for this bracket'
    )
    subtract_uvt = fields.Float(
        string='Subtract (UVT)',
        digits=(10, 2),
        help='UVT to subtract from base before applying rate'
    )
    plus_uvt = fields.Float(
        string='Plus (UVT)',
        digits=(10, 2),
        help='Fixed UVT to add after applying rate'
    )

    # Campos computados
    from_amount = fields.Float(
        string='From (COP)',
        compute='_compute_amounts',
        digits='Product Price'
    )
    to_amount = fields.Float(
        string='To (COP)',
        compute='_compute_amounts',
        digits='Product Price'
    )
    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name',
        store=True
    )

    # Estado
    active = fields.Boolean(
        string='Active',
        default=True
    )

    @api.depends('bracket_number', 'from_uvt', 'to_uvt', 'rate_percent')
    def _compute_display_name(self):
        for record in self:
            to_str = f"{record.to_uvt:.0f}" if record.to_uvt else "∞"
            record.display_name = f"Rango {record.bracket_number}: >{record.from_uvt:.0f} - {to_str} UVT @ {record.rate_percent}%"

    @api.depends('from_uvt', 'to_uvt', 'date_from', 'concept_id')
    def _compute_amounts(self):
        TaxParam = self.env['tax.general.parameter']
        for record in self:
            uvt_value = TaxParam.get_uvt_value(
                date_eval=record.date_from,
                company_id=record.concept_id.company_id.id if record.concept_id else self.env.company.id
            )
            record.from_amount = record.from_uvt * uvt_value
            record.to_amount = record.to_uvt * uvt_value if record.to_uvt else 0

    @api.constrains('from_uvt', 'to_uvt')
    def _check_uvt_range(self):
        for record in self:
            if record.to_uvt and record.from_uvt >= record.to_uvt:
                raise ValidationError(_('Upper limit must be greater than lower limit.'))

    @api.constrains('bracket_number')
    def _check_bracket_number(self):
        for record in self:
            if record.bracket_number < 1:
                raise ValidationError(_('Bracket number must be at least 1.'))
