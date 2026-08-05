# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class L10ncoExogenousDocumentType(models.Model):
    _name = "l10n_co.exogenous_document_type"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "Plantilla para la creación de tablas de detalle de tipos de documento requeridos para formatos de información exógena"
    _check_company_auto = True

    @api.constrains('name', 'code', 'type_document_id')
    def _check_unique_name(self):
        for record in self:
            if self.search_count([('name', '=', record.name), ('code', '=', record.code), ('type_document_id', '=', record.type_document_id.id)]) > 1:
                raise ValidationError(_("El nombre, código y tipo de documento deben ser únicos"))

    name = fields.Char(string='Nombre', tracking=True)
    type_document_id = fields.Many2one(comodel_name='l10n_latam.identification.type', string='Tipo de documento', tracking=True)
    active = fields.Boolean(string='Activo', default=True, tracking=True)
    code = fields.Char(string='Código', tracking=True, size=2)
    document_type_table_ids = fields.Many2many(comodel_name="l10n_co.exogenous_document_type_table", relation="l10n_co_exogenous_document_type_table_rel", column1="document_type_id", column2="document_type_table_id", string='Tablas')

    company_id = fields.Many2one(
        comodel_name='res.company', string='Compañía', default=lambda self: self.env.company.id)

    applies_to_colaboracion = fields.Boolean(
        string='Aplica a contrato de participación',
        default=False, tracking=True,
        help='Marca si este tipo de documento aplica a contratos de colaboración / cuentas en participación. '
             'Cuando está activo, el dropdown del partícipe (tdopa) en formatos 5247-5252 lo muestra.')
    version = fields.Char(
        string='Versión',
        tracking=True,
        help='Versión del documento DIAN, p.ej. "v3", "v3.3.0".')
    appendix = fields.Char(
        string='Anexo',
        tracking=True,
        help='Referencia al anexo de la resolución DIAN.')