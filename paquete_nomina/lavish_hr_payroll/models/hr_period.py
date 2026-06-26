from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import datetime, timedelta
import calendar
from typing import Optional
from .hr_slip import TYPE_PERIOD, TYPE_BIWEEKLY
from dateutil.relativedelta import relativedelta

class HrPeriod(models.Model):
    _name = 'hr.period'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Periodo de nomina'
    _order = 'date_start,name'

    name = fields.Char(string='Nombre', readonly=True)
    active = fields.Boolean(string='Activo', default=True)
    date_start = fields.Date(string='Fecha de Inicio', readonly=True)
    date_end = fields.Date(string='Fecha de Fin', readonly=True)
    type_period = fields.Selection(string='Tipo de periodo', selection=TYPE_PERIOD, readonly=True)
    type_biweekly = fields.Selection(string='Tipo de quincena', selection=TYPE_BIWEEKLY, readonly=True)
    company_id = fields.Many2one(comodel_name='res.company', string='Compania', default=lambda self: self.env.company, readonly=True)
    closed = fields.Boolean(string='Cerrado', default=False)
    unlock_reason = fields.Text(string='Motivo de Desbloqueo', readonly=True)
    year = fields.Integer(string='Ano', compute='_compute_year', store=True)
    year_month = fields.Char(string='Ano-Mes', compute='_compute_year_month', store=True)
    all_payslips_computed = fields.Boolean(string='Nominas Calculadas', default=False)
    all_payslips_paid = fields.Boolean(string='Nominas Pagadas', default=False)
    display_name = fields.Char(compute='_compute_display_name')

    _date_period_company_uniq = models.Constraint('unique(date_start, date_end, type_period, type_biweekly, company_id)', 'No puede existir un periodo duplicado para la misma compania')

    @api.depends('date_start')
    def _compute_year(self):
        for record in self:
            record.year = record.date_start.year if record.date_start else False

    @api.depends('date_start')
    def _compute_year_month(self):
        for record in self:
            if record.date_start:
                record.year_month = f"{record.date_start.year}{record.date_start.month:02d}"
            else:
                record.year_month = False

    @api.depends('name', 'type_period', 'type_biweekly')
    def _compute_display_name(self):
        for record in self:
            name = record.name or ''
            if record.type_period:
                type_text = dict(TYPE_PERIOD).get(record.type_period, '')
                name = f"{name} ({type_text})"
                if record.type_period == 'bi-monthly' and record.type_biweekly:
                    biweekly_text = dict(TYPE_BIWEEKLY).get(record.type_biweekly, '')
                    name = f"{name} - {biweekly_text}"
            record.display_name = name

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'allow_create' in vals and vals['allow_create']:
                vals.pop('allow_create')
            else:
                raise UserError(_('Ningun usuario tiene permitido crear periodos manualmente. Vaya al creador de periodos.'))
        return super(HrPeriod, self).create(vals_list)

    def write(self, vals):
        allowed_fields = {'active', 'closed', 'unlock_reason', 'all_payslips_computed', 'all_payslips_paid'}
        if not set(vals.keys()).issubset(allowed_fields):
            raise UserError(_('Solo se puede modificar el estado activo, cerrado y otros campos de estado del periodo.'))
        return super(HrPeriod, self).write(vals)

    def get_period(self, date_from, date_to, type_period, company_id=None):
        domain = [
            ('type_period', '=', type_period),
            ('active', '=', True)
        ]
        if company_id:
            domain.append(('company_id', '=', company_id))
        else:
            domain.append(('company_id', '=', self.env.company.id))
        domain.extend([
            ('date_start', '<=', date_to),
            ('date_end', '>=', date_from)
        ])

        return self.search(domain, limit=1)

    def between(self, date):
        if not date:
            return False
        return self.date_start <= date <= self.date_end

    def _get_schedule_days(self, type_period):
        dias_dif = 0
        if type_period == 'weekly':
            dias_dif = 7
        elif type_period == 'bi-monthly':
            dias_dif = 15
        elif type_period == 'monthly':
            dias_dif = 30
        elif type_period == 'dualmonth':
            dias_dif = 60
        elif type_period == 'quarterly':
            dias_dif = 90
        elif type_period == 'semi-annually':
            dias_dif = 180
        elif type_period == 'annually':
            dias_dif = 360

        return dias_dif

    def get_previous_periods(self, count=1):
        self.ensure_one()
        return self.search([
            ('type_period', '=', self.type_period),
            ('type_biweekly', '=', self.type_biweekly),
            ('company_id', '=', self.company_id.id),
            ('date_end', '<', self.date_start),
            ('active', '=', True)
        ], order='date_end desc', limit=count)

    def get_next_periods(self, count=1):
        self.ensure_one()
        return self.search([
            ('type_period', '=', self.type_period),
            ('type_biweekly', '=', self.type_biweekly),
            ('company_id', '=', self.company_id.id),
            ('date_start', '>', self.date_end),
            ('active', '=', True)
        ], order='date_start asc', limit=count)

    def close_period(self):
        self.ensure_one()
        payslips = self.env['hr.payslip'].search([
            ('period_id', '=', self.id),
            ('state', 'not in', ['done', 'cancel'])
        ])

        if payslips:
            raise UserError(_("No se puede cerrar el periodo porque existen nominas en proceso. Finalice todas las nominas antes de cerrar el periodo."))

        self.closed = True
        return True

    def unlock_period(self, reason):
        self.ensure_one()
        if not reason:
            raise UserError(_("Debe proporcionar un motivo para desbloquear el periodo."))

        self.write({
            'closed': False,
            'unlock_reason': reason,
        })

        self.env['mail.message'].create({
            'model': self._name,
            'res_id': self.id,
            'message_type': 'notification',
            'body': _("Periodo desbloqueado. Motivo: %s") % reason,
        })

        return True

    @api.model
    def create_periods_for_year(self, year, schedule_pays=None, company_id=None):
        if schedule_pays is None:
            schedule_pays = ['monthly', 'bi-monthly']

        if company_id is None:
            company_id = self.env.company.id

        created_periods = []

        for schedule_pay in schedule_pays:
            if schedule_pay == 'weekly':
                start_date = datetime(year, 1, 1)
                while start_date.weekday() != 0:
                    start_date += timedelta(days=1)

                for week in range(52):
                    end_date = start_date + timedelta(days=6)
                    period_name = f"Semana {week+1}/{year}"

                    period_vals = {
                        'name': period_name,
                        'date_start': start_date,
                        'date_end': end_date,
                        'type_period': 'weekly',
                        'company_id': company_id,
                        'allow_create': True
                    }

                    period_id = self.create(period_vals)
                    created_periods.append(period_id.id)

                    start_date = end_date + timedelta(days=1)

            elif schedule_pay == 'bi-monthly':
                for month in range(1, 13):
                    start_date = datetime(year, month, 1)
                    end_date = datetime(year, month, 15)
                    period_name = f"1-15/{month}/{year}"

                    period_vals = {
                        'name': period_name,
                        'date_start': start_date,
                        'date_end': end_date,
                        'type_period': 'bi-monthly',
                        'type_biweekly': 'first',
                        'company_id': company_id,
                        'allow_create': True
                    }

                    period_id = self.create(period_vals)
                    created_periods.append(period_id.id)

                    start_date = datetime(year, month, 16)
                    last_day = calendar.monthrange(year, month)[1]
                    end_date = datetime(year, month, last_day)
                    period_name = f"16-{last_day}/{month}/{year}"

                    period_vals = {
                        'name': period_name,
                        'date_start': start_date,
                        'date_end': end_date,
                        'type_period': 'bi-monthly',
                        'type_biweekly': 'second',
                        'company_id': company_id,
                        'allow_create': True
                    }

                    period_id = self.create(period_vals)
                    created_periods.append(period_id.id)

            elif schedule_pay == 'monthly':
                for month in range(1, 13):
                    start_date = datetime(year, month, 1)
                    last_day = calendar.monthrange(year, month)[1]
                    end_date = datetime(year, month, last_day)

                    month_name = start_date.strftime('%B').capitalize()
                    period_name = f"{month_name} {year}"

                    period_vals = {
                        'name': period_name,
                        'date_start': start_date,
                        'date_end': end_date,
                        'type_period': 'monthly',
                        'company_id': company_id,
                        'allow_create': True
                    }

                    period_id = self.create(period_vals)
                    created_periods.append(period_id.id)

            elif schedule_pay == 'dualmonth':
                for i in range(6):
                    month = i * 2 + 1
                    start_date = datetime(year, month, 1)

                    if month == 11:
                        end_date = datetime(year, month + 1, 30)
                    else:
                        next_month = month + 1 if month < 12 else 1
                        next_month_year = year if month < 12 else year + 1
                        end_date = datetime(next_month_year, next_month, 30)

                    period_name = f"{month}-{month+1}/{year}"

                    period_vals = {
                        'name': period_name,
                        'date_start': start_date,
                        'date_end': end_date,
                        'type_period': 'dualmonth',
                        'company_id': company_id,
                        'allow_create': True
                    }

                    period_id = self.create(period_vals)
                    created_periods.append(period_id.id)

            elif schedule_pay == 'quarterly':
                for quarter in range(4):
                    month = quarter * 3 + 1
                    start_date = datetime(year, month, 1)

                    end_month = month + 2
                    end_date = datetime(year, end_month, 30)

                    period_name = f"Q{quarter+1}/{year}"

                    period_vals = {
                        'name': period_name,
                        'date_start': start_date,
                        'date_end': end_date,
                        'type_period': 'quarterly',
                        'company_id': company_id,
                        'allow_create': True
                    }

                    period_id = self.create(period_vals)
                    created_periods.append(period_id.id)

            elif schedule_pay == 'semi-annually':
                start_date = datetime(year, 1, 1)
                end_date = datetime(year, 6, 30)
                period_name = f"S1/{year}"

                period_vals = {
                    'name': period_name,
                    'date_start': start_date,
                    'date_end': end_date,
                    'type_period': 'semi-annually',
                    'company_id': company_id,
                    'allow_create': True
                }

                period_id = self.create(period_vals)
                created_periods.append(period_id.id)

                start_date = datetime(year, 7, 1)
                end_date = datetime(year, 12, 30)
                period_name = f"S2/{year}"

                period_vals = {
                    'name': period_name,
                    'date_start': start_date,
                    'date_end': end_date,
                    'type_period': 'semi-annually',
                    'company_id': company_id,
                    'allow_create': True
                }

                period_id = self.create(period_vals)
                created_periods.append(period_id.id)

            elif schedule_pay == 'annually':
                start_date = datetime(year, 1, 1)
                end_date = datetime(year, 12, 30)
                period_name = f"Ano {year}"

                period_vals = {
                    'name': period_name,
                    'date_start': start_date,
                    'date_end': end_date,
                    'type_period': 'annually',
                    'company_id': company_id,
                    'allow_create': True
                }

                period_id = self.create(period_vals)
                created_periods.append(period_id.id)

        return created_periods

    @api.model
    def _cron_check_payslips_status(self):
        active_periods = self.search([
            ('active', '=', True),
            ('closed', '=', False),
            ('date_end', '<', fields.Date.today())
        ])

        for period in active_periods:
            payslips = self.env['hr.payslip'].search([
                ('period_id', '=', period.id),
                ('state', 'not in', ['cancel'])
            ])

            if not payslips:
                continue

            all_computed = all(p.state != 'draft' for p in payslips)
            all_paid = all(p.state == 'validated' for p in payslips)

            period.write({
                'all_payslips_computed': all_computed,
                'all_payslips_paid': all_paid
            })

            if all_paid:
                self.env['mail.activity'].create({
                    'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id,
                    'note': _("Todas las nominas de este periodo estan pagadas. Se recomienda cerrar el periodo."),
                    'user_id': self.env.user.id,
                    'res_id': period.id,
                    'res_model_id': self.env['ir.model'].search(
                        [('model', '=', 'hr.period')], limit=1).id,
                })

class ResourceCalendar(models.Model):
    _inherit = "resource.calendar"

    def get_holidays(self, year, add_offset=False):
        self.ensure_one()
        leave_obj = self.env['resource.calendar.leaves']
        holidays = []
        tz_offset = 0
        if add_offset:
            tz_offset = fields.Datetime.context_timestamp(
                self, fields.Datetime.from_string(fields.Datetime.now())).\
                utcoffset().total_seconds()
        start_dt = fields.Datetime.from_string(fields.Datetime.now()).\
            replace(year=year, month=1, day=1, hour=0, minute=0, second=0) + \
            relativedelta(seconds=tz_offset)
        end_dt = start_dt + relativedelta(years=1) - relativedelta(seconds=1)
        leaves_domain = [
            ('calendar_id', '=', self.id),
            ('resource_id', '=', False),
            ('date_from', '>=', fields.Datetime.to_string(start_dt)),
            ('date_to', '<=', fields.Datetime.to_string(end_dt))
        ]
        for leave in leave_obj.search(leaves_domain):
            date_from = fields.Datetime.from_string(leave.date_from)
            holidays.append((date_from.date(), leave.name))
        return holidays

