# -*- coding: utf-8 -*-

from odoo import models, fields, api


class HrMedicalCertificateType(models.Model):
    """Modelo jerárquico para tipos de certificados médicos"""
    _name = 'hr.medical.certificate.type'
    _description = 'Tipo de Certificado Médico'
    _parent_name = 'parent_id'
    _parent_store = True
    _order = 'sequence, complete_name'
    _rec_name = 'complete_name'

    name = fields.Char('Nombre', required=True, translate=True)
    complete_name = fields.Char(
        'Nombre Completo',
        compute='_compute_complete_name',
        recursive=True,
        store=True
    )
    code = fields.Char('Código', required=True, index=True)
    description = fields.Text('Descripción')
    sequence = fields.Integer('Secuencia', default=10)

    # Jerarquía
    parent_id = fields.Many2one(
        'hr.medical.certificate.type',
        string='Tipo Padre',
        index=True,
        ondelete='cascade',
        domain="[('parent_id', '=', False)]"
    )
    parent_path = fields.Char(index=True, unaccent=False)
    child_ids = fields.One2many(
        'hr.medical.certificate.type',
        'parent_id',
        string='Subtipos'
    )

    # Configuración
    validity_months = fields.Integer(
        'Vigencia (meses)',
        default=12,
        help="Vigencia por defecto en meses para este tipo de certificado"
    )
    requires_height_certification = fields.Boolean(
        'Requiere Certificación Alturas',
        help="Indica si este tipo de examen incluye certificación de trabajo en alturas"
    )
    is_mandatory = fields.Boolean(
        'Obligatorio',
        help="Indica si este tipo de certificado es obligatorio para los empleados"
    )
    renewal_alert_days = fields.Integer(
        'Días de Alerta',
        default=30,
        help="Días antes del vencimiento para enviar alertas"
    )

    # Campos computados
    is_category = fields.Boolean(
        'Es Categoría',
        compute='_compute_is_category',
        store=True,
        help="True si es una categoría padre (no tiene parent_id)"
    )

    active = fields.Boolean('Activo', default=True)

    _code_uniq = models.Constraint('unique(code)', 'El código debe ser único!')

    @api.depends('name', 'parent_id.complete_name')
    def _compute_complete_name(self):
        for record in self:
            if record.parent_id:
                record.complete_name = f"{record.parent_id.complete_name} / {record.name}"
            else:
                record.complete_name = record.name

    @api.depends('parent_id')
    def _compute_is_category(self):
        for record in self:
            record.is_category = not record.parent_id

