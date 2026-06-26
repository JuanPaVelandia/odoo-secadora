# -*- coding: utf-8 -*-
"""
Wizard para Generar Solicitudes/Exámenes Masivos

Este wizard solo FILTRA empleados y genera registros.
No guarda datos, es transient.
"""

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from dateutil.relativedelta import relativedelta
import logging

_logger = logging.getLogger(__name__)


class WizardEppBatchGenerate(models.TransientModel):
    """
    Wizard para FILTRAR empleados y generar solicitudes/exámenes

    Este wizard NO guarda datos, solo filtra y crea registros en:
    - hr.epp.request (si es EPP/Dotación)
    - hr.medical.certificate (si es examen médico)
    """
    _name = 'wizard.epp.batch.generate'
    _description = 'Wizard Generar Solicitudes/Exámenes'

    # ========================================================================
    # LOTE ORIGEN
    # ========================================================================

    batch_id = fields.Many2one(
        'hr.epp.batch',
        string='Lote',
        required=True,
        ondelete='cascade'
    )

    batch_type = fields.Selection(
        related='batch_id.batch_type',
        readonly=True
    )

    company_id = fields.Many2one(
        related='batch_id.company_id',
        readonly=True
    )

    # ========================================================================
    # FILTROS PARA SELECCIÓN DE EMPLEADOS
    # ========================================================================

    selection_mode = fields.Selection([
        ('all', 'Todos los Empleados'),
        ('department', 'Por Departamento'),
        ('job', 'Por Puesto de Trabajo'),
        ('manual', 'Selección Manual'),
        ('filters', 'Filtros Combinados'),
    ], string='Modo de Selección',
       default='all',
       required=True)

    department_ids = fields.Many2many(
        'hr.department',
        'wizard_epp_batch_department_rel',
        'wizard_id',
        'department_id',
        string='Departamentos',
        domain="[('company_id', '=', company_id)]"
    )

    job_ids = fields.Many2many(
        'hr.job',
        'wizard_epp_batch_job_rel',
        'wizard_id',
        'job_id',
        string='Puestos de Trabajo',
        domain="[('company_id', '=', company_id)]"
    )

    employee_type = fields.Selection([
        ('employee', 'Empleado'),
        ('contractor', 'Contratista'),
        ('intern', 'Aprendiz'),
    ], string='Tipo de Empleado')

    employee_ids = fields.Many2many(
        'hr.employee',
        'wizard_epp_batch_employee_rel',
        'wizard_id',
        'employee_id',
        string='Empleados Seleccionados',
        domain="[('company_id', '=', company_id), ('active', '=', True)]"
    )

    # ========================================================================
    # CONFIGURACIÓN PARA GENERACIÓN
    # ========================================================================

    config_id = fields.Many2one(
        'hr.epp.configuration',
        string='Configuración a Aplicar',
        help='Configuración de EPP/Dotación a usar (opcional)'
    )

    medical_exam_type = fields.Selection([
        ('ingress', 'Examen de Ingreso'),
        ('periodic', 'Examen Periódico'),
        ('retirement', 'Examen de Retiro'),
        ('post_incapacity', 'Post Incapacidad'),
        ('height_work', 'Trabajo en Alturas'),
        ('confined_spaces', 'Espacios Confinados'),
        ('psychosensory', 'Psicosensométrico'),
        ('occupational', 'Ocupacional'),
    ], string='Tipo de Examen')

    medical_provider_id = fields.Many2one(
        'hr.medical.provider',
        string='Proveedor Médico'
    )

    certificate_validity_months = fields.Integer(
        string='Vigencia (meses)',
        default=12
    )

    # ========================================================================
    # PREVIEW DE EMPLEADOS
    # ========================================================================

    employee_count = fields.Integer(
        string='Empleados Encontrados',
        compute='_compute_employee_preview'
    )

    employee_preview_ids = fields.Many2many(
        'hr.employee',
        'wizard_epp_batch_preview_rel',
        'wizard_id',
        'employee_id',
        string='Preview Empleados',
        compute='_compute_employee_preview'
    )

    @api.depends('selection_mode', 'department_ids', 'job_ids', 'employee_type', 'employee_ids')
    def _compute_employee_preview(self):
        for wizard in self:
            employees = wizard._get_filtered_employees()
            wizard.employee_preview_ids = employees
            wizard.employee_count = len(employees)

    # ========================================================================
    # MÉTODOS
    # ========================================================================

    def _get_filtered_employees(self):
        """Obtiene empleados según los filtros aplicados"""
        self.ensure_one()

        domain = [
            ('company_id', '=', self.company_id.id),
            ('active', '=', True)
        ]

        if self.selection_mode == 'all':
            pass

        elif self.selection_mode == 'department':
            if self.department_ids:
                domain.append(('department_id', 'in', self.department_ids.ids))

        elif self.selection_mode == 'job':
            if self.job_ids:
                domain.append(('job_id', 'in', self.job_ids.ids))

        elif self.selection_mode == 'manual':
            if self.employee_ids:
                domain.append(('id', 'in', self.employee_ids.ids))

        elif self.selection_mode == 'filters':
            if self.department_ids:
                domain.append(('department_id', 'in', self.department_ids.ids))
            if self.job_ids:
                domain.append(('job_id', 'in', self.job_ids.ids))
            if self.employee_type:
                domain.append(('employee_type', '=', self.employee_type))

        return self.env['hr.employee'].search(domain)

    def action_generate(self):
        """Generar solicitudes/certificados para los empleados filtrados"""
        self.ensure_one()

        employees = self._get_filtered_employees()

        if not employees:
            raise UserError(_('No se encontraron empleados con los filtros aplicados'))

        generated_count = 0

        if self.batch_type in ('epp', 'dotacion'):
            generated_count = self._generate_epp_requests(employees)
        else:
            generated_count = self._generate_medical_certificates(employees)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Generación Exitosa'),
                'message': _('Se generaron %d solicitudes/certificados') % generated_count,
                'type': 'success',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.act_window_close'
                }
            }
        }

    def _generate_epp_requests(self, employees):
        """Generar solicitudes de EPP/Dotación"""
        self.ensure_one()
        generated = 0

        for employee in employees:
            # Verificar si ya existe
            existing = self.env['hr.epp.request'].search([
                ('employee_id', '=', employee.id),
                ('batch_id', '=', self.batch_id.id)
            ], limit=1)

            if existing:
                continue

            # Crear solicitud
            request = self.env['hr.epp.request'].create({
                'employee_id': employee.id,
                'type': self.batch_type,
                'batch_id': self.batch_id.id,
                'configuration_id': self.config_id.id if self.config_id else False,
                'state': 'draft',
            })

            # Agregar items del kit
            if self.config_id:
                for kit_line in self.config_id.kit_line_ids:
                    size = self._get_employee_size(employee, kit_line.item_type)

                    self.env['hr.epp.request.line'].create({
                        'request_id': request.id,
                        'item_type': kit_line.item_type,
                        'product_id': kit_line.product_id.id if kit_line.product_id else False,
                        'name': kit_line.name,
                        'quantity': kit_line.quantity,
                        'size': size,
                    })

            generated += 1

        return generated

    def _generate_medical_certificates(self, employees):
        """Generar certificados médicos"""
        self.ensure_one()
        generated = 0

        expiry_date = fields.Date.today() + relativedelta(
            months=self.certificate_validity_months
        )

        for employee in employees:
            # Verificar si ya existe
            existing = self.env['hr.medical.certificate'].search([
                ('employee_id', '=', employee.id),
                ('batch_id', '=', self.batch_id.id)
            ], limit=1)

            if existing:
                continue

            # Crear certificado
            self.env['hr.medical.certificate'].create({
                'employee_id': employee.id,
                'batch_id': self.batch_id.id,
                'provider_id': self.medical_provider_id.id if self.medical_provider_id else False,
                'certificate_type': self.medical_exam_type or 'occupational',
                'issue_date': fields.Date.today(),
                'expiry_date': expiry_date,
            })

            generated += 1

        return generated

    def _get_employee_size(self, employee, item_type):
        """Obtiene la talla del empleado según el tipo de item"""
        if item_type == 'shirt':
            return employee.shirt_size or 'M'
        elif item_type == 'pants':
            return employee.pants_size or '32'
        elif item_type in ('shoes', 'boots'):
            return employee.shoe_size or '40'
        return False
