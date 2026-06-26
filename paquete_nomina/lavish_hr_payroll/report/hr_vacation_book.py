# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta, date
from dateutil.relativedelta import relativedelta
import base64
import io
import xlsxwriter


class HrVacationBook(models.TransientModel):
    _name = "hr.vacation.book"
    _description = "Libro de Vacaciones"

    name = fields.Char('Nombre', compute='_compute_name', store=True)
    company_id = fields.Many2one('res.company', string='Compañía',
                                  default=lambda self: self.env.company, required=True)
    date_cut = fields.Date('Fecha de Corte', required=True, default=fields.Date.context_today)

    employee_ids = fields.Many2many('hr.employee', string='Empleados',
                                     help='Dejar vacío para incluir todos los empleados')
    department_ids = fields.Many2many('hr.department', string='Departamentos')
    contract_state = fields.Selection([
        ('all', 'Todos'),
        ('draft', 'Borrador'),
        ('open', 'En Proceso'),
        ('close', 'Cerrado'),
        ('cancel', 'Cancelado')
    ], string='Estado del Contrato', default='open', required=True)

    include_zero_balance = fields.Boolean('Incluir Saldo Cero', default=False,
                                           help='Incluir empleados sin días pendientes')
    group_by_department = fields.Boolean('Agrupar por Departamento', default=False)
    show_detail = fields.Boolean('Mostrar Detalle de Vacaciones', default=True)

    excel_file = fields.Binary('Archivo Excel', readonly=True)
    excel_file_name = fields.Char('Nombre Excel')

    line_ids = fields.One2many('hr.vacation.book.line', 'wizard_id', string='Detalle')

    total_employees = fields.Integer('Total Empleados', compute='_compute_totals')
    total_days_earned = fields.Float('Total Días Causados', compute='_compute_totals')
    total_days_taken = fields.Float('Total Días Tomados', compute='_compute_totals')
    total_days_pending = fields.Float('Total Días Pendientes', compute='_compute_totals')
    total_value = fields.Monetary('Valor Total Provisión', compute='_compute_totals',
                                   currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id')

    @api.depends('date_cut', 'company_id')
    def _compute_name(self):
        for rec in self:
            if rec.date_cut:
                rec.name = f"Libro Vacaciones - {rec.date_cut.strftime('%d/%m/%Y')}"
            else:
                rec.name = "Libro Vacaciones"

    @api.depends('line_ids')
    def _compute_totals(self):
        for rec in self:
            rec.total_employees = len(rec.line_ids)
            rec.total_days_earned = sum(rec.line_ids.mapped('days_earned'))
            rec.total_days_taken = sum(rec.line_ids.mapped('days_taken'))
            rec.total_days_pending = sum(rec.line_ids.mapped('days_pending'))
            rec.total_value = sum(rec.line_ids.mapped('provision_value'))

    def _dias360(self, start_date, end_date):
        """Calcula días según el método 360/30"""
        if not start_date or not end_date or start_date > end_date:
            return 0
        if isinstance(start_date, datetime):
            start_date = start_date.date()
        if isinstance(end_date, datetime):
            end_date = end_date.date()
        year_360 = (end_date.year - start_date.year) * 360
        month_360 = (end_date.month - start_date.month) * 30
        day_diff = min(end_date.day, 30) - min(start_date.day, 30)
        return max(0, year_360 + month_360 + day_diff)

    def _get_contracts_domain(self):
        """Construye el dominio para buscar contratos"""
        domain = [('company_id', '=', self.company_id.id)]

        if self.employee_ids:
            domain.append(('employee_id', 'in', self.employee_ids.ids))

        if self.department_ids:
            domain.append(('employee_id.department_id', 'in', self.department_ids.ids))

        if self.contract_state and self.contract_state != 'all':
            domain.append(('state', '=', self.contract_state))

        return domain

    def _get_employee_vacation_data(self, contract):
        """Obtiene los datos de vacaciones para un contrato"""
        employee = contract.employee_id
        date_cut = self.date_cut

        date_start = contract.date_start
        days_worked = self._dias360(date_start, date_cut)

        absences = self.env['hr.leave'].search([
            ('employee_id', '=', employee.id),
            ('date_from', '>=', date_start),
            ('date_to', '<=', date_cut),
            ('state', '=', 'validate'),
            ('holiday_status_id.unpaid_absences', '=', True)
        ])
        total_absences = sum(self._dias360(leave.date_from.date() if isinstance(leave.date_from, datetime) else leave.date_from,
                                            leave.date_to.date() if isinstance(leave.date_to, datetime) else leave.date_to)
                             for leave in absences)

        effective_days = days_worked - total_absences
        days_earned = (effective_days * 15) / 360

        vacations = self.env['hr.vacation'].search([
            ('employee_id', '=', employee.id),
            ('contract_id', '=', contract.id),
            ('departure_date', '<=', date_cut)
        ])

        days_business = sum(v.business_units or 0 for v in vacations)
        days_holidays = sum(v.holiday_units or 0 for v in vacations)
        days_money = sum(v.units_of_money or 0 for v in vacations)
        days_taken = days_business + days_holidays + days_money

        value_business = sum(v.value_business_days or 0 for v in vacations)
        value_holidays = sum(v.holiday_value or 0 for v in vacations)
        value_money = sum(v.money_value or 0 for v in vacations)
        value_taken = value_business + value_holidays + value_money

        days_pending = days_earned - days_taken

        salary = contract.wage or 0
        daily_salary = salary / 30 if salary else 0
        provision_value = days_pending * daily_salary

        last_vacation = vacations.sorted('departure_date', reverse=True)[:1]
        last_vacation_date = last_vacation.departure_date if last_vacation else False

        details = []

        for vacation in vacations:
            leave = vacation.leave_id
            payslip = vacation.payslip

            if vacation.units_of_money and vacation.units_of_money > 0:
                vac_type = 'money'
                days_total = vacation.units_of_money or 0
                value = vacation.money_value or 0
            else:
                vac_type = 'time'
                days_total = (vacation.business_units or 0) + (vacation.holiday_units or 0)
                value = (vacation.value_business_days or 0) + (vacation.holiday_value or 0)

            salary_rule = False
            salary_rule_code = ''
            salary_rule_name = ''
            if payslip:
                vac_lines = payslip.line_ids.filtered(
                    lambda l: l.leave_id.id == leave.id if leave and l.leave_id else False
                )
                if not vac_lines:
                    vac_lines = payslip.line_ids.filtered(
                        lambda l: l.code in ('VACDISFRUTADAS', 'VACREMUNERADAS', 'VACATIONS_MONEY', 'VACDINERO')
                    )
                if vac_lines:
                    salary_rule = vac_lines[0].salary_rule_id
                    salary_rule_code = salary_rule.code if salary_rule else ''
                    salary_rule_name = salary_rule.name if salary_rule else ''

            details.append({
                'leave_id': leave.id if leave else False,
                'vacation_id': vacation.id,
                'payslip_id': payslip.id if payslip else False,
                'leave_code': leave.name if leave else '',
                'leave_name': leave.holiday_status_id.name if leave and leave.holiday_status_id else (vacation.description or 'Vacaciones'),
                'leave_type_id': leave.holiday_status_id.id if leave and leave.holiday_status_id else False,
                'leave_type_name': leave.holiday_status_id.name if leave and leave.holiday_status_id else 'Vacaciones',
                'salary_rule_id': salary_rule.id if salary_rule else False,
                'salary_rule_code': salary_rule_code,
                'salary_rule_name': salary_rule_name,
                'payslip_number': payslip.number if payslip else '',
                'date_from': vacation.departure_date,
                'date_to': vacation.return_date,
                'days_business': vacation.business_units or 0,
                'days_holidays': vacation.holiday_units or 0,
                'days_money': vacation.units_of_money or 0,
                'days_total': days_total,
                'value': value,
                'vacation_type': vac_type,
            })

        for absence in absences:
            absence_days = self._dias360(
                absence.date_from.date() if isinstance(absence.date_from, datetime) else absence.date_from,
                absence.date_to.date() if isinstance(absence.date_to, datetime) else absence.date_to
            )

            payslip = self.env['hr.payslip'].search([
                ('employee_id', '=', employee.id),
                ('date_from', '<=', absence.date_to),
                ('date_to', '>=', absence.date_from),
                ('state', 'in', ['done', 'paid'])
            ], limit=1, order='date_from desc')

            salary_rule = False
            salary_rule_code = ''
            salary_rule_name = ''
            if payslip:
                abs_lines = payslip.line_ids.filtered(lambda l: l.leave_id.id == absence.id)
                if abs_lines:
                    salary_rule = abs_lines[0].salary_rule_id
                    salary_rule_code = salary_rule.code if salary_rule else ''
                    salary_rule_name = salary_rule.name if salary_rule else ''

            details.append({
                'leave_id': absence.id,
                'vacation_id': False,
                'payslip_id': payslip.id if payslip else False,
                'leave_code': absence.name or '',
                'leave_name': absence.holiday_status_id.name if absence.holiday_status_id else 'Ausencia',
                'leave_type_id': absence.holiday_status_id.id if absence.holiday_status_id else False,
                'leave_type_name': absence.holiday_status_id.name if absence.holiday_status_id else 'Ausencia No Remunerada',
                'salary_rule_id': salary_rule.id if salary_rule else False,
                'salary_rule_code': salary_rule_code,
                'salary_rule_name': salary_rule_name,
                'payslip_number': payslip.number if payslip else '',
                'date_from': absence.date_from.date() if isinstance(absence.date_from, datetime) else absence.date_from,
                'date_to': absence.date_to.date() if isinstance(absence.date_to, datetime) else absence.date_to,
                'days_business': 0,
                'days_holidays': 0,
                'days_money': 0,
                'days_total': absence_days,
                'value': 0,
                'vacation_type': 'absence',
            })

        return {
            'employee_id': employee.id,
            'contract_id': contract.id,
            'department_id': employee.department_id.id if employee.department_id else False,
            'identification': employee.identification_id or '',
            'employee_name': employee.name,
            'department_name': employee.department_id.name if employee.department_id else '',
            'job_name': contract.job_id.name if contract.job_id else '',
            'date_start': date_start,
            'contract_state': contract.state,
            'days_worked': days_worked,
            'days_absences': total_absences,
            'days_earned': round(days_earned, 2),
            'days_business': days_business,
            'days_holidays': days_holidays,
            'days_money': days_money,
            'days_taken': days_taken,
            'days_pending': round(days_pending, 2),
            'value_business': value_business,
            'value_holidays': value_holidays,
            'value_money': value_money,
            'value_taken': value_taken,
            'salary': salary,
            'provision_value': round(provision_value, 2),
            'last_vacation_date': last_vacation_date,
            'details': details,
        }

    def action_generate(self):
        """Genera el libro de vacaciones"""
        self.ensure_one()

        self.line_ids.unlink()

        domain = self._get_contracts_domain()
        contracts = self.env['hr.contract'].search(domain, order='employee_id')

        if not contracts:
            raise UserError(_('No se encontraron contratos con los filtros seleccionados.'))

        for contract in contracts:
            data = self._get_employee_vacation_data(contract)

            if not self.include_zero_balance and data['days_pending'] <= 0:
                continue

            line = self.env['hr.vacation.book.line'].create({
                'wizard_id': self.id,
                'employee_id': data['employee_id'],
                'contract_id': data['contract_id'],
                'department_id': data['department_id'],
                'identification': data['identification'],
                'date_start': data['date_start'],
                'contract_state': data['contract_state'],
                'days_worked': data['days_worked'],
                'days_absences': data['days_absences'],
                'days_earned': data['days_earned'],
                'days_business': data['days_business'],
                'days_holidays': data['days_holidays'],
                'days_money': data['days_money'],
                'days_taken': data['days_taken'],
                'days_pending': data['days_pending'],
                'value_business': data['value_business'],
                'value_holidays': data['value_holidays'],
                'value_money': data['value_money'],
                'value_taken': data['value_taken'],
                'salary': data['salary'],
                'provision_value': data['provision_value'],
                'last_vacation_date': data['last_vacation_date'],
            })

            if data.get('details'):
                for detail in data['details']:
                    self.env['hr.vacation.book.detail'].create({
                        'line_id': line.id,
                        'leave_id': detail.get('leave_id'),
                        'vacation_id': detail.get('vacation_id'),
                        'payslip_id': detail.get('payslip_id'),
                        'leave_code': detail.get('leave_code', ''),
                        'leave_name': detail.get('leave_name', ''),
                        'leave_type_id': detail.get('leave_type_id'),
                        'leave_type_name': detail.get('leave_type_name', ''),
                        'salary_rule_id': detail.get('salary_rule_id'),
                        'salary_rule_code': detail.get('salary_rule_code', ''),
                        'salary_rule_name': detail.get('salary_rule_name', ''),
                        'payslip_number': detail.get('payslip_number', ''),
                        'date_from': detail.get('date_from'),
                        'date_to': detail.get('date_to'),
                        'days_business': detail.get('days_business', 0),
                        'days_holidays': detail.get('days_holidays', 0),
                        'days_money': detail.get('days_money', 0),
                        'days_total': detail.get('days_total', 0),
                        'value': detail.get('value', 0),
                        'vacation_type': detail.get('vacation_type'),
                    })

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_generate_excel(self):
        """Genera el reporte en Excel"""
        self.ensure_one()

        if not self.line_ids:
            self.action_generate()

        if not self.line_ids:
            raise UserError(_('No hay datos para generar el reporte.'))

        stream = io.BytesIO()
        workbook = xlsxwriter.Workbook(stream, {'in_memory': True})

        formats = self._get_excel_formats(workbook)

        sheet = workbook.add_worksheet('Libro de Vacaciones')
        self._write_excel_header(sheet, formats)
        row = self._write_excel_data(sheet, formats)
        self._write_excel_totals(sheet, row, formats)

        self._set_column_widths(sheet)

        if self.show_detail:
            self._write_excel_detail_sheet(workbook, formats)

        workbook.close()

        filename = f'Libro_Vacaciones_{self.date_cut.strftime("%Y%m%d")}.xlsx'
        self.write({
            'excel_file': base64.b64encode(stream.getvalue()),
            'excel_file_name': filename,
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/?model={self._name}&id={self.id}'
                   f'&filename_field=excel_file_name&field=excel_file&download=true'
                   f'&filename={filename}',
            'target': 'self',
        }

    def _get_excel_formats(self, workbook):
        """Define los formatos para Excel"""
        return {
            'title': workbook.add_format({
                'bold': True, 'font_size': 16, 'font_color': '#1F497D',
                'align': 'center', 'valign': 'vcenter'
            }),
            'subtitle': workbook.add_format({
                'bold': True, 'font_size': 12, 'font_color': '#1F497D',
                'align': 'left', 'valign': 'vcenter'
            }),
            'header': workbook.add_format({
                'bold': True, 'font_size': 10, 'font_color': 'white',
                'bg_color': '#1F497D', 'align': 'center', 'valign': 'vcenter',
                'border': 1, 'text_wrap': True
            }),
            'text': workbook.add_format({
                'font_size': 9, 'align': 'left', 'valign': 'vcenter', 'border': 1
            }),
            'text_center': workbook.add_format({
                'font_size': 9, 'align': 'center', 'valign': 'vcenter', 'border': 1
            }),
            'number': workbook.add_format({
                'font_size': 9, 'num_format': '#,##0.00', 'align': 'right',
                'valign': 'vcenter', 'border': 1
            }),
            'money': workbook.add_format({
                'font_size': 9, 'num_format': '$#,##0.00', 'align': 'right',
                'valign': 'vcenter', 'border': 1
            }),
            'date': workbook.add_format({
                'font_size': 9, 'num_format': 'dd/mm/yyyy', 'align': 'center',
                'valign': 'vcenter', 'border': 1
            }),
            'total_label': workbook.add_format({
                'bold': True, 'font_size': 10, 'font_color': 'white',
                'bg_color': '#1F497D', 'align': 'right', 'valign': 'vcenter', 'border': 1
            }),
            'total_number': workbook.add_format({
                'bold': True, 'font_size': 10, 'num_format': '#,##0.00',
                'bg_color': '#D9E1F2', 'align': 'right', 'valign': 'vcenter', 'border': 1
            }),
            'total_money': workbook.add_format({
                'bold': True, 'font_size': 10, 'num_format': '$#,##0.00',
                'bg_color': '#D9E1F2', 'align': 'right', 'valign': 'vcenter', 'border': 1
            }),
            'warning': workbook.add_format({
                'font_size': 9, 'num_format': '#,##0.00', 'align': 'right',
                'valign': 'vcenter', 'border': 1, 'bg_color': '#FFC7CE', 'font_color': '#9C0006'
            }),
        }

    def _write_excel_header(self, sheet, formats):
        """Escribe el encabezado del reporte"""
        sheet.merge_range('A1:P1', self.company_id.name, formats['title'])
        sheet.merge_range('A2:P2', 'LIBRO DE VACACIONES', formats['title'])
        sheet.merge_range('A3:P3', f'Fecha de Corte: {self.date_cut.strftime("%d/%m/%Y")}', formats['subtitle'])
        sheet.write('A4', f'Generado por: {self.env.user.name}', formats['subtitle'])
        sheet.write('H4', f'Fecha: {fields.Datetime.now().strftime("%d/%m/%Y %H:%M")}', formats['subtitle'])

        sheet.write('A6', f'Total Empleados: {self.total_employees}', formats['subtitle'])
        sheet.write('D6', f'Días Causados: {self.total_days_earned:.2f}', formats['subtitle'])
        sheet.write('G6', f'Días Tomados: {self.total_days_taken:.2f}', formats['subtitle'])
        sheet.write('J6', f'Días Pendientes: {self.total_days_pending:.2f}', formats['subtitle'])
        sheet.write('M6', f'Provisión Total: ${self.total_value:,.2f}', formats['subtitle'])

    def _write_excel_data(self, sheet, formats):
        """Escribe los datos del reporte"""
        headers = [
            'Identificación', 'Empleado', 'Departamento', 'Cargo', 'Fecha Ingreso',
            'Estado', 'Días Trabajados', 'Inasistencias', 'Días Causados',
            'Días Hábiles', 'Días Festivos', 'Días Dinero', 'Total Tomados',
            'Días Pendientes', 'Salario', 'Provisión'
        ]

        row = 8
        for col, header in enumerate(headers):
            sheet.write(row, col, header, formats['header'])

        row += 1
        lines = self.line_ids.sorted(lambda l: (l.department_id.name or '', l.employee_id.name))

        current_dept = None
        for line in lines:
            if self.group_by_department and line.department_id != current_dept:
                if current_dept is not None:
                    row = self._write_department_subtotal(sheet, row, current_dept, formats)
                current_dept = line.department_id

            sheet.write(row, 0, line.identification or '', formats['text'])
            sheet.write(row, 1, line.employee_id.name, formats['text'])
            sheet.write(row, 2, line.department_id.name or '', formats['text'])
            sheet.write(row, 3, line.contract_id.job_id.name if line.contract_id.job_id else '', formats['text'])
            sheet.write(row, 4, line.date_start, formats['date'])
            sheet.write(row, 5, dict(line._fields['contract_state'].selection).get(line.contract_state, ''), formats['text_center'])
            sheet.write(row, 6, line.days_worked, formats['number'])
            sheet.write(row, 7, line.days_absences, formats['number'])
            sheet.write(row, 8, line.days_earned, formats['number'])
            sheet.write(row, 9, line.days_business, formats['number'])
            sheet.write(row, 10, line.days_holidays, formats['number'])
            sheet.write(row, 11, line.days_money, formats['number'])
            sheet.write(row, 12, line.days_taken, formats['number'])

            pending_format = formats['warning'] if line.days_pending > 30 else formats['number']
            sheet.write(row, 13, line.days_pending, pending_format)

            sheet.write(row, 14, line.salary, formats['money'])
            sheet.write(row, 15, line.provision_value, formats['money'])

            row += 1

        if self.group_by_department and current_dept is not None:
            row = self._write_department_subtotal(sheet, row, current_dept, formats)

        return row

    def _write_department_subtotal(self, sheet, row, department, formats):
        """Escribe subtotal por departamento"""
        dept_lines = self.line_ids.filtered(lambda l: l.department_id == department)

        sheet.merge_range(row, 0, row, 7, f'Subtotal {department.name or "Sin Departamento"}', formats['total_label'])
        sheet.write(row, 8, sum(dept_lines.mapped('days_earned')), formats['total_number'])
        sheet.write(row, 9, sum(dept_lines.mapped('days_business')), formats['total_number'])
        sheet.write(row, 10, sum(dept_lines.mapped('days_holidays')), formats['total_number'])
        sheet.write(row, 11, sum(dept_lines.mapped('days_money')), formats['total_number'])
        sheet.write(row, 12, sum(dept_lines.mapped('days_taken')), formats['total_number'])
        sheet.write(row, 13, sum(dept_lines.mapped('days_pending')), formats['total_number'])
        sheet.write(row, 14, '', formats['total_number'])
        sheet.write(row, 15, sum(dept_lines.mapped('provision_value')), formats['total_money'])

        return row + 2

    def _write_excel_totals(self, sheet, row, formats):
        """Escribe los totales del reporte"""
        row += 1
        sheet.merge_range(row, 0, row, 7, 'TOTALES GENERALES', formats['total_label'])
        sheet.write(row, 8, self.total_days_earned, formats['total_number'])
        sheet.write(row, 9, sum(self.line_ids.mapped('days_business')), formats['total_number'])
        sheet.write(row, 10, sum(self.line_ids.mapped('days_holidays')), formats['total_number'])
        sheet.write(row, 11, sum(self.line_ids.mapped('days_money')), formats['total_number'])
        sheet.write(row, 12, self.total_days_taken, formats['total_number'])
        sheet.write(row, 13, self.total_days_pending, formats['total_number'])
        sheet.write(row, 14, '', formats['total_number'])
        sheet.write(row, 15, self.total_value, formats['total_money'])

    def _set_column_widths(self, sheet):
        """Configura los anchos de columna"""
        widths = [12, 30, 20, 20, 12, 10, 12, 12, 12, 12, 12, 12, 12, 12, 15, 15]
        for col, width in enumerate(widths):
            sheet.set_column(col, col, width)

    def _write_excel_detail_sheet(self, workbook, formats):
        """Escribe la hoja de detalle de ausencias por empleado"""
        formats['employee_header'] = workbook.add_format({
            'bold': True, 'font_size': 11, 'font_color': 'white',
            'bg_color': '#1F497D', 'align': 'left', 'valign': 'vcenter', 'border': 1
        })
        formats['subtotal'] = workbook.add_format({
            'bold': True, 'font_size': 9, 'bg_color': '#D9E1F2',
            'align': 'right', 'valign': 'vcenter', 'border': 1
        })
        formats['type_time'] = workbook.add_format({
            'font_size': 9, 'bg_color': '#17a2b8', 'font_color': 'white',
            'align': 'center', 'valign': 'vcenter', 'border': 1
        })
        formats['type_money'] = workbook.add_format({
            'font_size': 9, 'bg_color': '#28a745', 'font_color': 'white',
            'align': 'center', 'valign': 'vcenter', 'border': 1
        })
        formats['type_absence'] = workbook.add_format({
            'font_size': 9, 'bg_color': '#ffc107', 'font_color': '#333',
            'align': 'center', 'valign': 'vcenter', 'border': 1
        })

        sheet = workbook.add_worksheet('Detalle por Empleado')

        detail_widths = [15, 35, 12, 15, 25, 20, 10, 12, 12, 10, 15]
        for col, width in enumerate(detail_widths):
            sheet.set_column(col, col, width)

        sheet.merge_range('A1:K1', f'{self.company_id.name} - DETALLE DE VACACIONES Y AUSENCIAS', formats['title'])
        sheet.merge_range('A2:K2', f'Fecha de Corte: {self.date_cut.strftime("%d/%m/%Y")}', formats['subtitle'])

        row = 4

        detail_headers = [
            'Identificación', 'Empleado', 'Nómina', 'Código Ausencia',
            'Tipo Ausencia', 'Regla Salarial', 'Tipo', 'Desde', 'Hasta', 'Días', 'Valor'
        ]

        for line in self.line_ids.sorted(lambda l: (l.department_id.name or '', l.employee_id.name)):
            if not line.detail_ids:
                continue

            employee_info = f"{line.employee_id.name} - {line.identification or 'S/I'} | Dpto: {line.department_id.name or 'N/A'} | Salario: ${line.salary:,.0f}"
            sheet.merge_range(row, 0, row, 10, employee_info, formats['employee_header'])
            row += 1

            for col, header in enumerate(detail_headers):
                sheet.write(row, col, header, formats['header'])
            row += 1

            total_days = 0
            total_value = 0

            for detail in line.detail_ids.sorted('date_from'):
                sheet.write(row, 0, line.identification or '', formats['text'])
                sheet.write(row, 1, line.employee_id.name, formats['text'])
                sheet.write(row, 2, detail.payslip_number or '-', formats['text'])
                sheet.write(row, 3, detail.leave_code or '-', formats['text'])
                sheet.write(row, 4, detail.leave_type_name or detail.leave_name or '-', formats['text'])

                rule_text = f"[{detail.salary_rule_code}] {detail.salary_rule_name}" if detail.salary_rule_code else '-'
                sheet.write(row, 5, rule_text, formats['text'])

                type_format = formats['type_time']
                type_text = 'TIEMPO'
                if detail.vacation_type == 'money':
                    type_format = formats['type_money']
                    type_text = 'DINERO'
                elif detail.vacation_type == 'absence':
                    type_format = formats['type_absence']
                    type_text = 'AUSENCIA'
                sheet.write(row, 6, type_text, type_format)

                sheet.write(row, 7, detail.date_from, formats['date'])
                sheet.write(row, 8, detail.date_to, formats['date'])
                sheet.write(row, 9, detail.days_total, formats['number'])
                sheet.write(row, 10, detail.value, formats['money'])

                total_days += detail.days_total
                total_value += detail.value
                row += 1

            sheet.merge_range(row, 0, row, 8, f'Subtotal {line.employee_id.name}:', formats['subtotal'])
            sheet.write(row, 9, total_days, formats['total_number'])
            sheet.write(row, 10, total_value, formats['total_money'])
            row += 2

        all_details = self.env['hr.vacation.book.detail'].search([
            ('line_id', 'in', self.line_ids.ids)
        ])
        grand_total_days = sum(all_details.mapped('days_total'))
        grand_total_value = sum(all_details.mapped('value'))

        sheet.merge_range(row, 0, row, 8, 'TOTAL GENERAL:', formats['total_label'])
        sheet.write(row, 9, grand_total_days, formats['total_number'])
        sheet.write(row, 10, grand_total_value, formats['total_money'])

    def action_generate_pdf(self):
        """Genera el reporte en PDF"""
        self.ensure_one()

        if not self.line_ids:
            self.action_generate()

        if not self.line_ids:
            raise UserError(_('No hay datos para generar el reporte.'))

        return self.env.ref('lavish_hr_payroll.action_report_vacation_book').report_action(self)

    def get_lines_by_department(self):
        """Retorna las líneas agrupadas por departamento para el PDF"""
        result = {}
        for line in self.line_ids.sorted(lambda l: (l.department_id.name or 'ZZZ', l.employee_id.name)):
            dept_name = line.department_id.name or 'Sin Departamento'
            if dept_name not in result:
                result[dept_name] = {
                    'lines': [],
                    'total_earned': 0,
                    'total_taken': 0,
                    'total_pending': 0,
                    'total_provision': 0,
                }
            result[dept_name]['lines'].append(line)
            result[dept_name]['total_earned'] += line.days_earned
            result[dept_name]['total_taken'] += line.days_taken
            result[dept_name]['total_pending'] += line.days_pending
            result[dept_name]['total_provision'] += line.provision_value
        return result


class HrVacationBookLine(models.TransientModel):
    _name = "hr.vacation.book.line"
    _description = "Línea de Libro de Vacaciones"
    _order = "department_id, employee_id"

    wizard_id = fields.Many2one('hr.vacation.book', string='Wizard', ondelete='cascade')
    employee_id = fields.Many2one('hr.employee', string='Empleado')
    contract_id = fields.Many2one('hr.contract', string='Contrato')
    department_id = fields.Many2one('hr.department', string='Departamento')
    identification = fields.Char('Identificación')
    date_start = fields.Date('Fecha Ingreso')
    contract_state = fields.Selection([
        ('draft', 'Borrador'),
        ('open', 'En Proceso'),
        ('close', 'Cerrado'),
        ('cancel', 'Cancelado')
    ], string='Estado Contrato')

    days_worked = fields.Float('Días Trabajados')
    days_absences = fields.Float('Inasistencias')
    days_earned = fields.Float('Días Causados')
    days_business = fields.Float('Días Hábiles')
    days_holidays = fields.Float('Días Festivos')
    days_money = fields.Float('Días Dinero')
    days_taken = fields.Float('Días Tomados')
    days_pending = fields.Float('Días Pendientes')

    value_business = fields.Monetary('Valor Días Hábiles', currency_field='currency_id')
    value_holidays = fields.Monetary('Valor Días Festivos', currency_field='currency_id')
    value_money = fields.Monetary('Valor Días Dinero', currency_field='currency_id')
    value_taken = fields.Monetary('Valor Total Tomado', currency_field='currency_id')
    salary = fields.Monetary('Salario', currency_field='currency_id')
    provision_value = fields.Monetary('Valor Provisión', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', related='wizard_id.currency_id')

    last_vacation_date = fields.Date('Última Vacación')

    detail_ids = fields.One2many('hr.vacation.book.detail', 'line_id', string='Detalle de Ausencias')


class HrVacationBookDetail(models.TransientModel):
    """Detalle de cada ausencia/vacación para el libro de vacaciones."""
    _name = "hr.vacation.book.detail"
    _description = "Detalle de Ausencia en Libro de Vacaciones"
    _order = "date_from"

    line_id = fields.Many2one('hr.vacation.book.line', string='Línea', ondelete='cascade')
    employee_id = fields.Many2one('hr.employee', related='line_id.employee_id', store=True)

    leave_id = fields.Many2one('hr.leave', string='Ausencia')
    vacation_id = fields.Many2one('hr.vacation', string='Registro Vacación')
    payslip_id = fields.Many2one('hr.payslip', string='Nómina')

    leave_code = fields.Char('Código Ausencia')
    leave_name = fields.Char('Nombre Ausencia')
    leave_type_id = fields.Many2one('hr.leave.type', string='Tipo de Ausencia')
    leave_type_name = fields.Char('Tipo Ausencia')
    salary_rule_id = fields.Many2one('hr.salary.rule', string='Regla Salarial')
    salary_rule_code = fields.Char('Código Regla')
    salary_rule_name = fields.Char('Nombre Regla')
    payslip_number = fields.Char('Número Nómina')

    date_from = fields.Date('Fecha Desde')
    date_to = fields.Date('Fecha Hasta')

    days_business = fields.Float('Días Hábiles')
    days_holidays = fields.Float('Días Festivos')
    days_money = fields.Float('Días Dinero')
    days_total = fields.Float('Total Días')
    value = fields.Monetary('Valor', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', related='line_id.currency_id')

    vacation_type = fields.Selection([
        ('time', 'En Tiempo'),
        ('money', 'En Dinero'),
        ('absence', 'Ausencia No Remunerada')
    ], string='Tipo')
