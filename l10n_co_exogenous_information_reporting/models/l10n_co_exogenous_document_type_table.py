# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class L10ncoExogenousDocumentTypeTable(models.Model):
    _name = "l10n_co.exogenous_document_type_table"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "Plantilla para la creación de las tablas a usar por formato"
    _check_company_auto = True


    @api.constrains('name')
    def _check_unique_name(self):
        for record in self:
            if self.search_count([('name', '=', record.name)]) > 1:
                raise ValidationError(_("El nombre debe ser único"))

    name = fields.Char(string='Nombre', tracking=True)
    active = fields.Boolean(string='Activo', default=True, tracking=True)
    company_id = fields.Many2one(
        comodel_name='res.company', string='Compañía', default=lambda self: self.env.company.id)

    applies_to_colaboracion = fields.Boolean(
        string='Aplica a contrato de participación',
        default=False, tracking=True,
        help='Marca si esta tabla agrupa tipos de documento aplicables a contratos de colaboración.')
    version = fields.Char(string='Versión', tracking=True)
    appendix = fields.Char(string='Anexo', tracking=True)