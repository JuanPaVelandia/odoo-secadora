# -*- coding: utf-8 -*-
"""
Wizard para generar nóminas electrónicas por empleados.
"""
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HrPayslipEdiByEmployees(models.TransientModel):
    _name = 'hr.payslip.edi.employees'
    _description = 'Generar Nóminas Electrónicas por Empleados'

    date_from = fields.Date(
        string='Fecha Desde',
        required=True,
        default=lambda self: date.today().replace(day=1)
    )
    date_to = fields.Date(
        string='Fecha Hasta',
        required=True,
        default=lambda self: (date.today() + relativedelta(months=1, day=1, days=-1))
    )
    employee_ids = fields.Many2many(
        comodel_name='hr.employee',
        relation='hr_payslip_edi_employees_rel',
        column1='wizard_id',
        column2='employee_id',
        string='Empleados',
        default=lambda self: self._default_employees()
    )

    @api.model
    def _default_employees(self):
        """Carga empleados con nómina confirmada en el período por defecto."""
        date_from = date.today().replace(day=1)
        date_to = date.today() + relativedelta(months=1, day=1, days=-1)

        # Verificar si hay lote origen en el EDI run activo
        run_id = self.env.context.get('active_id')
        source_batch = False
        if run_id:
            edi_run = self.env['hr.payslip.edi.run'].browse(run_id)
            if edi_run.exists() and edi_run.payslip_run_source_id:
                source_batch = edi_run.payslip_run_source_id
                # Usar fechas del lote origen
                date_from = source_batch.date_start
                date_to = source_batch.date_end

        return self._get_employees_with_payslips_static(date_from, date_to, source_batch)

    @api.model
    def _get_employees_with_payslips_static(self, date_from, date_to, source_batch=False):
        """Obtiene empleados con nóminas confirmadas (versión estática para default)."""
        if source_batch:
            # Buscar nóminas del lote origen (incluye verify para consolidaciones)
            payslips = self.env['hr.payslip'].search([
                ('payslip_run_id', '=', source_batch.id),
                ('state', 'in', ['verify', 'done', 'paid']),
            ])
        else:
            # Buscar nóminas confirmadas en el período
            payslips = self.env['hr.payslip'].search([
                ('date_from', '>=', date_from),
                ('date_to', '<=', date_to),
                ('state', 'in', ['done', 'paid']),
            ])

        if not payslips:
            return self.env['hr.employee']

        employee_ids = payslips.mapped('employee_id').ids

        # Excluir empleados que ya tienen EDI
        existing_edi = self.env['hr.payslip.edi'].search([
            ('employee_id', 'in', employee_ids),
            ('date_from', '=', date_from),
            ('date_to', '=', date_to),
            ('state', '!=', 'cancel'),
        ])
        existing_employee_ids = existing_edi.mapped('employee_id').ids

        return self.env['hr.employee'].browse(
            [eid for eid in employee_ids if eid not in existing_employee_ids]
        )

    @api.onchange('date_from', 'date_to')
    def _onchange_dates(self):
        """Recarga empleados cuando cambian las fechas."""
        if self.date_from and self.date_to:
            employees = self._get_employees_with_payslips()
            self.employee_ids = [(6, 0, employees.ids)]

    def _get_source_batch(self):
        """Obtiene el lote origen del EDI run activo, si existe."""
        run_id = self.env.context.get('active_id')
        if run_id:
            edi_run = self.env['hr.payslip.edi.run'].browse(run_id)
            if edi_run.exists() and edi_run.payslip_run_source_id:
                return edi_run.payslip_run_source_id
        return False

    def _get_employees_with_payslips(self):
        """Obtiene empleados con nóminas confirmadas en el período que no tienen EDI generado."""
        if not self.date_from or not self.date_to:
            return self.env['hr.employee']

        source_batch = self._get_source_batch()

        if source_batch:
            # Buscar nóminas del lote origen (incluye verify para consolidaciones)
            payslips = self.env['hr.payslip'].search([
                ('payslip_run_id', '=', source_batch.id),
                ('state', 'in', ['verify', 'done', 'paid']),
            ])
        else:
            # Buscar nóminas confirmadas (done/paid) en el período
            payslips = self.env['hr.payslip'].search([
                ('date_from', '>=', self.date_from),
                ('date_to', '<=', self.date_to),
                ('state', 'in', ['done', 'paid']),
            ])

        if not payslips:
            return self.env['hr.employee']

        # Obtener empleados de esas nóminas
        employee_ids = payslips.mapped('employee_id').ids

        # Excluir empleados que ya tienen nómina electrónica en el período
        existing_edi = self.env['hr.payslip.edi'].search([
            ('employee_id', 'in', employee_ids),
            ('date_from', '=', self.date_from),
            ('date_to', '=', self.date_to),
            ('state', '!=', 'cancel'),
        ])
        existing_employee_ids = existing_edi.mapped('employee_id').ids

        # Retornar empleados que tienen nómina pero no EDI
        return self.env['hr.employee'].browse(
            [eid for eid in employee_ids if eid not in existing_employee_ids]
        )

    def compute_edi_payslips(self):
        """Genera nóminas electrónicas para los empleados seleccionados."""
        self.ensure_one()

        if not self.employee_ids:
            raise UserError(_('Debe seleccionar al menos un empleado.'))

        PayslipEdi = self.env['hr.payslip.edi']
        run_id = self.env.context.get('active_id')

        payslip_run = self.env['hr.payslip.edi.run'].browse(run_id) if run_id else False

        created_slips = PayslipEdi
        skipped_employees = []
        source_batch = self._get_source_batch()

        for employee in self.employee_ids:
            # Verificar si ya existe una nómina electrónica para este período
            existing = PayslipEdi.search([
                ('employee_id', '=', employee.id),
                ('date_from', '=', self.date_from),
                ('date_to', '=', self.date_to),
                ('state', '!=', 'cancel'),
            ], limit=1)

            if existing:
                skipped_employees.append(f"{employee.name} (ya existe EDI)")
                continue

            # Buscar nómina del empleado
            if source_batch:
                # Buscar en el lote origen (incluye verify para consolidaciones)
                payslip = self.env['hr.payslip'].search([
                    ('employee_id', '=', employee.id),
                    ('payslip_run_id', '=', source_batch.id),
                    ('state', 'in', ['verify', 'done', 'paid']),
                ], limit=1)
            else:
                # Buscar nómina confirmada en el período
                payslip = self.env['hr.payslip'].search([
                    ('employee_id', '=', employee.id),
                    ('date_from', '>=', self.date_from),
                    ('date_to', '<=', self.date_to),
                    ('state', 'in', ['done', 'paid']),
                ], limit=1)

            if not payslip:
                skipped_employees.append(f"{employee.name} (sin nómina confirmada)")
                continue

            # Usar versión de contrato y estructura de la nómina existente
            version = payslip.version_id
            struct = payslip.struct_id

            if not version:
                skipped_employees.append(f"{employee.name} (sin versión de contrato)")
                continue

            vals = {
                'employee_id': employee.id,
                'version_id': version.id,
                'struct_id': struct.id if struct else version.struct_id.id,
                'date_from': self.date_from,
                'date_to': self.date_to,
                'name': 'Nómina Electrónica - %s - %s' % (employee.name, self.date_from.strftime('%B %Y')),
            }

            if payslip_run:
                vals['payslip_run_id'] = payslip_run.id
                vals['fecha_vencimiento'] = payslip_run.fecha_vencimiento
                if payslip_run.provision_mode:
                    vals['provision_mode'] = payslip_run.provision_mode
                if payslip_run.use_external_accumulated:
                    vals['use_external_accumulated'] = True

            slip = PayslipEdi.create(vals)
            slip._onchange_employee()
            created_slips += slip

        if payslip_run and created_slips:
            payslip_run.write({'state': 'verify'})

        if not created_slips:
            msg = _('No se crearon nóminas electrónicas.')
            if skipped_employees:
                msg += '\n\nEmpleados omitidos:\n- ' + '\n- '.join(skipped_employees)
            raise UserError(msg)

        return {
            'type': 'ir.actions.act_window',
            'name': _('Nóminas Electrónicas Generadas (%d)') % len(created_slips),
            'res_model': 'hr.payslip.edi',
            'view_mode': 'list,form',
            'domain': [('id', 'in', created_slips.ids)],
        }
