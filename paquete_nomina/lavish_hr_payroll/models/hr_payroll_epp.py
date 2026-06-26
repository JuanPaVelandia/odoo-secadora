# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from dateutil.relativedelta import relativedelta


class HrPayslipEPP(models.Model):
    """Integración de EPP/Dotación con nómina"""
    _inherit = 'hr.payslip'

    # Campos relacionados con EPP
    needs_epp_request = fields.Boolean('Necesita Solicitud EPP', compute='_compute_epp_status', store=False)
    epp_pending_requests = fields.Integer('Solicitudes EPP Pendientes', compute='_compute_epp_status', store=False)
    last_epp_delivery_date = fields.Date('Última Entrega EPP', related='employee_id.last_dotacion_date', readonly=True)
    has_valid_medical = fields.Boolean('Certificado Médico Vigente', related='employee_id.has_valid_medical', readonly=True)

    @api.depends('employee_id', 'date_from')
    def _compute_epp_status(self):
        """Calcular si el empleado necesita solicitar EPP/Dotación"""
        for payslip in self:
            if not payslip.employee_id:
                payslip.needs_epp_request = False
                payslip.epp_pending_requests = 0
                continue

            employee = payslip.employee_id

            # Verificar solicitudes pendientes
            pending_requests = self.env['hr.epp.request'].search_count([
                ('employee_id', '=', employee.id),
                ('state', 'in', ['draft', 'requested', 'approved', 'picking'])
            ])
            payslip.epp_pending_requests = pending_requests

            # Verificar si necesita nueva dotación (cada 3 meses por ejemplo)
            needs_request = False
            if employee.last_dotacion_date:
                # Calcular si han pasado 3 meses desde la última entrega
                three_months_ago = fields.Date.today() - relativedelta(months=3)
                needs_request = employee.last_dotacion_date <= three_months_ago
            else:
                # Si nunca ha recibido dotación, necesita una
                needs_request = True

            payslip.needs_epp_request = needs_request and pending_requests == 0

    def action_create_epp_request(self):
        """Crear solicitud de EPP/Dotación desde la nómina"""
        self.ensure_one()

        # Buscar configuración activa para el empleado
        config = self.env['hr.epp.configuration'].search([
            ('active', '=', True),
            ('type', '=', 'dotacion'),
            '|',
            ('department_ids', '=', False),
            ('department_ids', 'in', [self.employee_id.department_id.id] if self.employee_id.department_id else []),
            '|',
            ('job_ids', '=', False),
            ('job_ids', 'in', [self.employee_id.job_id.id] if self.employee_id.job_id else [])
        ], limit=1)

        if not config:
            # Crear configuración por defecto si no existe
            config = self.env['hr.epp.configuration'].create_default_configuration()

        # Crear solicitud
        request = self.env['hr.epp.request'].create({
            'employee_id': self.employee_id.id,
            'configuration_id': config.id,
            'type': 'dotacion',
            'state': 'draft',
            'request_date': fields.Date.today(),
        })

        # Agregar items del kit con tallas del empleado
        for line in config.kit_line_ids:
            size = False
            product_id = line.product_id.id if line.product_id else False

            if line.item_type == 'shirt':
                size = self.employee_id.shirt_size or 'M'
                if self.employee_id.default_shirt_product_id:
                    product_id = self.employee_id.default_shirt_product_id.id
            elif line.item_type == 'pants':
                size = self.employee_id.pants_size or '32'
                if self.employee_id.default_pants_product_id:
                    product_id = self.employee_id.default_pants_product_id.id
            elif line.item_type == 'shoes':
                size = self.employee_id.shoe_size or '40'
                if self.employee_id.default_shoes_product_id:
                    product_id = self.employee_id.default_shoes_product_id.id

            self.env['hr.epp.request.line'].create({
                'request_id': request.id,
                'item_type': line.item_type,
                'product_id': product_id,
                'name': line.name,
                'quantity': line.quantity,
                'size': size,
            })

        # Abrir la solicitud creada
        return {
            'type': 'ir.actions.act_window',
            'name': _('Solicitud EPP/Dotación'),
            'res_model': 'hr.epp.request',
            'res_id': request.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_epp_requests(self):
        """Ver solicitudes de EPP del empleado"""
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': _('Solicitudes EPP/Dotación'),
            'res_model': 'hr.epp.request',
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.employee_id.id)],
            'context': {'default_employee_id': self.employee_id.id},
        }


class HrPayslipRun(models.Model):
    """Integración de EPP en lotes de nómina"""
    _inherit = 'hr.payslip.run'

    employees_need_epp = fields.Integer('Empleados que Necesitan EPP', compute='_compute_epp_summary')
    employees_pending_epp = fields.Integer('Solicitudes EPP Pendientes', compute='_compute_epp_summary')

    @api.depends('slip_ids', 'slip_ids.employee_id')
    def _compute_epp_summary(self):
        """Calcular resumen de EPP para el lote"""
        for payslip_run in self:
            if not payslip_run.slip_ids:
                payslip_run.employees_need_epp = 0
                payslip_run.employees_pending_epp = 0
                continue

            employees = payslip_run.slip_ids.mapped('employee_id')

            # Contar empleados que necesitan solicitar EPP
            need_epp = 0
            for emp in employees:
                if emp.last_dotacion_date:
                    three_months_ago = fields.Date.today() - relativedelta(months=3)
                    if emp.last_dotacion_date <= three_months_ago:
                        need_epp += 1
                else:
                    need_epp += 1

            # Contar solicitudes pendientes
            pending_requests = self.env['hr.epp.request'].search_count([
                ('employee_id', 'in', employees.ids),
                ('state', 'in', ['draft', 'requested', 'approved', 'picking'])
            ])

            payslip_run.employees_need_epp = need_epp
            payslip_run.employees_pending_epp = pending_requests

    def action_generate_epp_requests(self):
        """Generar solicitudes de EPP para todos los empleados del lote que lo necesiten"""
        self.ensure_one()

        created_requests = []
        for slip in self.slip_ids:
            if slip.needs_epp_request:
                # Crear solicitud para este empleado
                request = slip.action_create_epp_request()
                if request and 'res_id' in request:
                    created_requests.append(request['res_id'])

        if created_requests:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Solicitudes EPP Creadas'),
                'res_model': 'hr.epp.request',
                'view_mode': 'list,form',
                'domain': [('id', 'in', created_requests)],
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sin solicitudes'),
                    'message': _('No hay empleados que necesiten solicitar EPP en este momento'),
                    'type': 'info',
                    'sticky': False,
                }
            }
