from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from datetime import date


class TaxGeneralParameter(models.Model):
    _name = 'tax.general.parameter'
    _description = 'General Tax Parameters (SMMLV, UVT)'
    _order = 'date_from desc'
    _rec_name = 'display_name'

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )
    parameter_type = fields.Selection([
        ('smmlv', 'SMMLV (Salario Mínimo Mensual Legal Vigente)'),
        ('uvt', 'UVT (Unidad de Valor Tributario)'),
    ], string='Parameter Type', required=True)

    date_from = fields.Date(
        string='Valid From',
        required=True,
        default=fields.Date.context_today
    )
    date_to = fields.Date(
        string='Valid To',
        required=False
    )
    value = fields.Float(
        string='Value',
        required=True,
        digits='Product Price',
        help='Value in company currency'
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        related='company_id.currency_id',
        readonly=True
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

    @api.depends('parameter_type', 'date_from', 'value', 'currency_id')
    def _compute_display_name(self):
        for record in self:
            param_name = dict(record._fields['parameter_type'].selection).get(record.parameter_type, '')
            record.display_name = f"{param_name} - {record.date_from} - {record.currency_id.symbol}{record.value:,.2f}"

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for record in self:
            if record.date_to and record.date_from > record.date_to:
                raise ValidationError(_('End date must be after start date.'))

            # Check for overlapping periods
            domain = [
                ('id', '!=', record.id),
                ('company_id', '=', record.company_id.id),
                ('parameter_type', '=', record.parameter_type),
                ('active', '=', True),
                '|',
                    '&',
                        ('date_from', '<=', record.date_from),
                        '|',
                            ('date_to', '>=', record.date_from),
                            ('date_to', '=', False),
                    '&',
                        ('date_from', '<=', record.date_to if record.date_to else date.max),
                        '|',
                            ('date_to', '>=', record.date_to if record.date_to else date.max),
                            ('date_to', '=', False),
            ]

            if record.search_count(domain) > 0:
                raise ValidationError(_(
                    'There is already a %(param)s parameter for this period. '
                    'Please check the dates.',
                    param=dict(record._fields['parameter_type'].selection).get(record.parameter_type, '')
                ))

    @api.model
    def get_parameter_value(self, parameter_type, date_eval=None, company_id=None):
        """Get the parameter value for a specific date and company"""
        if not date_eval:
            date_eval = fields.Date.context_today(self)
        if not company_id:
            company_id = self.env.company.id

        parameter = self.search([
            ('company_id', '=', company_id),
            ('parameter_type', '=', parameter_type),
            ('date_from', '<=', date_eval),
            '|',
                ('date_to', '>=', date_eval),
                ('date_to', '=', False),
            ('active', '=', True)
        ], limit=1)

        return parameter.value if parameter else 0.0

    @api.model
    def get_uvt_value(self, date_eval=None, company_id=None):
        """Shortcut to get UVT value"""
        return self.get_parameter_value('uvt', date_eval, company_id)

    @api.model
    def get_smmlv_value(self, date_eval=None, company_id=None):
        """Shortcut to get SMMLV value"""
        return self.get_parameter_value('smmlv', date_eval, company_id)