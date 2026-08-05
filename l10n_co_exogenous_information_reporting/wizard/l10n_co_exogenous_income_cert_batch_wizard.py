# -*- coding: utf-8 -*-
"""Wizard para generar Certificados de Ingresos y Retenciones en lote.

Crea una solicitud (l10n_co.exogenous_income_cert_request) por cada empleado
seleccionado, ejecuta action_generate y opcionalmente envía por correo.
"""
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class IncomeCertBatchWizard(models.TransientModel):
    _name = 'l10n_co.exogenous_income_cert_batch_wizard'
    _description = 'Generación en lote de Certificados de Ingresos'

    header_id = fields.Many2one(
        'l10n_co.exogenous_income_cert_config',
        string='Configuración del certificado',
        required=True,
        domain="[('active', '=', True)]",
        help='Plantilla y reglas de cálculo a usar para todos los certificados.',
    )
    year = fields.Integer(string='Año gravable', required=True)
    date_from = fields.Date(string='Fecha desde', required=True)
    date_to = fields.Date(string='Fecha hasta', required=True)

    output_format = fields.Selection([
        ('pdf', 'PDF'),
        ('excel', 'Excel'),
    ], string='Formato', default='pdf', required=True)

    send_by_email = fields.Boolean(
        string='Enviar por correo',
        default=False,
        help='Envía el certificado al correo del empleado al generarlo.',
    )

    employee_selection = fields.Selection([
        ('payslips', 'Empleados con nóminas en el período'),
        ('selected', 'Empleados seleccionados'),
        ('company', 'Todos los empleados de la compañía'),
    ], string='Selección de empleados', default='payslips', required=True)

    employee_ids = fields.Many2many(
        'hr.employee',
        string='Empleados',
        help='Lista de empleados a procesar (cuando "Selección" = Empleados seleccionados).',
    )
    company_id = fields.Many2one(
        'res.company', string='Compañía',
        default=lambda self: self.env.company, required=True,
    )

    skip_existing = fields.Boolean(
        string='Omitir empleados con certificado ya generado',
        default=True,
        help='No vuelve a generar si ya existe una solicitud en estado "done" '
             'para el mismo empleado/año.',
    )

    @api.onchange('header_id')
    def _onchange_header_id(self):
        if self.header_id:
            self.year = self.header_id.year
            self.date_from = fields.Date.from_string(f'{self.header_id.year}-01-01')
            self.date_to = fields.Date.from_string(f'{self.header_id.year}-12-31')

    def _get_target_employees(self):
        """Devuelve el recordset de empleados a procesar según employee_selection."""
        self.ensure_one()
        Employee = self.env['hr.employee']
        if self.employee_selection == 'selected':
            if not self.employee_ids:
                raise UserError(_('Debe seleccionar al menos un empleado.'))
            return self.employee_ids
        if self.employee_selection == 'company':
            return Employee.search(Employee._check_company_domain(self.company_id))
        # payslips: empleados con nóminas done/paid en el período
        Payslip = self.env['hr.payslip']
        slips = Payslip.search([
            *Payslip._check_company_domain(self.company_id),
            ('state', 'in', ['done', 'paid']),
            ('date_from', '<=', self.date_to),
            ('date_to', '>=', self.date_from),
        ])
        return slips.mapped('employee_id')

    def _existing_done_employee_ids(self):
        """IDs de empleados que ya tienen una solicitud generada para el año."""
        Request = self.env['l10n_co.exogenous_income_cert_request']
        existing = Request.search([
            *Request._check_company_domain(self.company_id),
            ('year', '=', self.year),
            ('state', '=', 'done'),
        ])
        return set(existing.mapped('employee_id').ids)

    def action_generate_batch(self):
        """Crea una request por empleado y ejecuta action_generate (+ envío opcional)."""
        self.ensure_one()
        employees = self._get_target_employees()
        if not employees:
            raise UserError(_('No se encontraron empleados para procesar.'))

        skip_ids = self._existing_done_employee_ids() if self.skip_existing else set()

        Request = self.env['l10n_co.exogenous_income_cert_request']
        ok_ids, error_msgs, skipped = [], [], 0

        for emp in employees:
            if emp.id in skip_ids:
                skipped += 1
                continue
            try:
                req = Request.create({
                    'employee_id': emp.id,
                    'header_id': self.header_id.id,
                    'year': self.year,
                    'date_from': self.date_from,
                    'date_to': self.date_to,
                    'output_format': self.output_format,
                    'send_by_email': self.send_by_email,
                    'state': 'requested',
                })
                req.action_generate()
                if self.send_by_email and req.state == 'done':
                    try:
                        req.action_send_email()
                    except Exception as e:
                        error_msgs.append(_('Email %s: %s') % (emp.name, e))
                ok_ids.append(req.id)
            except Exception as e:
                error_msgs.append(_('Empleado %s: %s') % (emp.name, e))
                self.env.cr.rollback()

        # Confirmar lo bueno (rollback ya solo afectó las fallidas)
        self.env.cr.commit()

        # Mensaje de resultado
        msg_parts = [_('Generados: %s') % len(ok_ids)]
        if skipped:
            msg_parts.append(_('Omitidos: %s') % skipped)
        if error_msgs:
            msg_parts.append(_('Errores: %s') % len(error_msgs))

        # Devolver la lista de solicitudes generadas
        return {
            'name': _('Certificados generados (%s)') % len(ok_ids),
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_co.exogenous_income_cert_request',
            'view_mode': 'list,form',
            'domain': [('id', 'in', ok_ids)],
            'context': {
                'batch_summary': ' | '.join(msg_parts),
                'batch_errors': error_msgs[:50],
            },
        }
