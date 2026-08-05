# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class L10nCoExogenousDistrict(models.Model):
    _name = "l10n_co.exogenous_district"
    _description = "Distrito/Municipio para información exógena distrital (ICA)"
    _check_company_auto = True
    _rec_name = 'name'
    _order = 'name'

    name = fields.Char(
        string='Ciudad / Municipio',
        required=True)
    code = fields.Char(
        string='Código DANE',
        required=True,
        size=8,
        help='Código DANE del municipio')
    department = fields.Char(
        string='Departamento')
    department_code = fields.Char(
        string='Código departamento',
        size=2)
    active = fields.Boolean(
        string='Activo',
        default=True)

    # --- Configuración de archivo plano ---
    delimiter = fields.Selection(
        selection=[
            ('pipe', 'Pipe ( | )'),
            ('semicolon', 'Punto y coma ( ; )'),
            ('comma', 'Coma ( , )'),
            ('tab', 'Tabulación'),
        ],
        string='Delimitador',
        default='pipe',
        required=True,
        help='Delimitador del archivo plano')
    file_extension = fields.Selection(
        selection=[
            ('txt', 'Texto (.txt)'),
            ('csv', 'CSV (.csv)'),
            ('xlsx', 'Excel (.xlsx)'),
        ],
        string='Extensión archivo',
        default='txt',
        required=True)
    include_header = fields.Boolean(
        string='Incluir encabezado',
        default=True,
        help='Incluir fila de encabezado con nombres de columna')
    text_encoding = fields.Selection(
        selection=[
            ('utf-8', 'UTF-8'),
            ('iso-8859-1', 'ISO-8859-1 (Latin-1)'),
            ('windows-1252', 'Windows-1252'),
        ],
        string='Codificación',
        default='utf-8',
        required=True)
    sanitize_text = fields.Boolean(
        string='Sanitizar texto',
        default=True,
        help='Eliminar acentos, caracteres especiales y estandarizar direcciones')
    max_field_length = fields.Integer(
        string='Longitud máxima campo',
        default=0,
        help='Longitud máxima por campo (0 = sin límite)')

    document_type_table_id = fields.Many2one('l10n_co.exogenous_document_type_table',
        string='Tabla de tipos de documento',
        help='Tabla de tipos de documento específica del municipio',
        check_company=True)

    notes = fields.Text(
        string='Notas',
        help='Observaciones sobre el formato del municipio')
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compañía',
        default=lambda self: self.env.company.id)

    _code_uniq = models.Constraint(
        'UNIQUE(code, company_id)',
        'El código DANE debe ser único por compañía.')

    @api.depends('name', 'code')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f'[{rec.code}] {rec.name}' if rec.code else rec.name

    def _get_delimiter_char(self):
        """Retorna el caracter delimitador real."""
        self.ensure_one()
        mapping = {
            'pipe': '|',
            'semicolon': ';',
            'comma': ',',
            'tab': '\t',
        }
        return mapping.get(self.delimiter, '|')
