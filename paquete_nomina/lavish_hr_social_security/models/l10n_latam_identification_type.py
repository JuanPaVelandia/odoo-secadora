from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class L10nLatamIdentificationType(models.Model):
    _inherit = 'l10n_latam.identification.type'

    dian_code = fields.Char(
        string='DIAN Code',
        help='DIAN identification type code'
    )

    # _sql_constraints = [
    #     ('dian_code_unique', 'unique(dian_code)', 'DIAN Code must be unique!'),
    # ]

    # @api.model
    # def create(self, vals_list):
    #     """Override create to handle import scenarios"""
    #     if isinstance(vals_list, dict):
    #         vals_list = [vals_list]

    #     for vals in vals_list:
    #         # Validate DIAN code if provided
    #         if vals.get('dian_code'):
    #             existing = self.search([('dian_code', '=', vals['dian_code'])])
    #             if existing:
    #                 raise ValidationError(_('DIAN Code %s already exists!') % vals['dian_code'])

    #     return super().create(vals_list)

    # @api.model
    # def _load_records_create(self, vals_list):
    #     """Override to handle bulk import operations"""
    #     return super()._load_records_create(vals_list)