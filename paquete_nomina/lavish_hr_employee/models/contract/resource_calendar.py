# -*- coding: utf-8 -*-
"""
Extension de resource.calendar - Horarios de trabajo con horas diurnas/nocturnas.
"""
from odoo import models, fields, api, _
from datetime import timedelta

class ResourceCalendar(models.Model):
    _inherit = 'resource.calendar'

    type_working_schedule = fields.Selection([
        ('employees', 'Empleados'),
        ('tasks', 'Tareas Proyectos'),
        ('other', 'Otro')
    ], string='Tipo Horario')
    consider_holidays = fields.Boolean(string='Tener en Cuenta Festivos')

    @api.model
    def get_working_hours_payroll(self, schedule, date_from, date_to):
        DSDF = '%Y-%m-%d'
        res = []
        date_from = date_from -timedelta(hours=5)
        nb_of_days = (date_to - date_from).days + 1
        
        for day in range(nb_of_days):
            dateinit = date_from + timedelta(days=day)
            hour_from = 0.0 if day > 0 else float(dateinit.hour) + float(dateinit.minute) / 60.0
            hour_to = 24 if day + 1 != nb_of_days else float(date_to.hour) + float(date_to.minute) / 60.0

            day_of_week = dateinit.weekday()
            working_hours = 0
            
            for reg in schedule.attendance_ids:
                if int(reg.dayofweek) == day_of_week:
                    from_hour = max(hour_from, reg.hour_from)
                    to_hour = min(hour_to, reg.hour_to)
                    working_hours += max(0, to_hour - from_hour)

            working_days = working_hours / schedule.hours_per_day if schedule.hours_per_day else 0
            date = dateinit.strftime(DSDF)
            res.append({
                'date': date, 
                'hours': working_hours,
                'days': working_days, 
                'week_day': str(day_of_week)
            })

        return res



class ResourceCalendarAttendance(models.Model):
    _inherit = 'resource.calendar.attendance'

    daytime_hours = fields.Float(string='Horas Diurnas',compute='_get_jornada_hours',store=True)
    night_hours = fields.Float(string='Horas Nocturnas',compute='_get_jornada_hours',store=True)

    @api.depends('hour_from','hour_to')
    def _get_jornada_hours(self):
        for record in self:
            hour_from = record.hour_from if record.hour_from else 0
            hour_to = record.hour_to if record.hour_to else 0
            #Calcular horas diurnas y nocturnas
            daytime_hours_initial = float(self.env['ir.config_parameter'].sudo().get_param('lavish_planning.daytime_hours_initial')) or False
            daytime_hours_finally = float(self.env['ir.config_parameter'].sudo().get_param('lavish_planning.daytime_hours_finally')) or False
            night_hours_initial = float(self.env['ir.config_parameter'].sudo().get_param('lavish_planning.night_hours_initial')) or False
            night_hours_finally = float(self.env['ir.config_parameter'].sudo().get_param('lavish_planning.night_hours_finally')) or False
            if daytime_hours_initial and daytime_hours_finally and night_hours_initial and night_hours_finally:
                if hour_from >= daytime_hours_initial and hour_to <= daytime_hours_finally:
                    record.night_hours = 0
                    record.daytime_hours = hour_to - hour_from + 24 if hour_to < hour_from else hour_to - hour_from
                elif (hour_from >= night_hours_initial and hour_to <= 24) or (hour_from >= 0 and hour_to <= night_hours_finally):
                    record.night_hours = hour_to - hour_from + 24 if hour_to < hour_from else hour_to - hour_from
                    record.daytime_hours = 0
                elif hour_from >= daytime_hours_initial and hour_from <= daytime_hours_finally and hour_to >= daytime_hours_finally:
                    record.night_hours = hour_to - daytime_hours_finally + 24 if hour_to < daytime_hours_finally else hour_to - daytime_hours_finally
                    record.daytime_hours = daytime_hours_finally - hour_from + 24 if daytime_hours_finally < hour_from else daytime_hours_finally - hour_from
                elif (hour_from <= daytime_hours_initial and hour_to >= daytime_hours_finally and hour_to <= daytime_hours_finally)\
                        or (hour_from <= daytime_hours_initial and hour_to >= daytime_hours_initial and hour_to <= daytime_hours_finally):
                    record.night_hours = daytime_hours_initial - hour_from + 24 if daytime_hours_initial < hour_from else daytime_hours_initial - hour_from
                    record.daytime_hours = hour_to - daytime_hours_initial + 24 if hour_to < daytime_hours_initial else hour_to - daytime_hours_initial
                elif hour_from <= daytime_hours_initial and hour_to >= daytime_hours_finally:
                    record.night_hours = daytime_hours_initial - hour_from + 24 if daytime_hours_initial < hour_from else daytime_hours_initial - hour_from
                    record.daytime_hours = daytime_hours_finally - daytime_hours_initial + 24 if daytime_hours_finally < daytime_hours_initial else daytime_hours_finally - daytime_hours_initial
                    record.night_hours += hour_to - daytime_hours_finally + 24 if hour_to < daytime_hours_finally else hour_to - daytime_hours_finally
                else:
                    record.night_hours = 0
                    record.daytime_hours = 0
            else:
                record.night_hours = 0
                record.daytime_hours = 0
