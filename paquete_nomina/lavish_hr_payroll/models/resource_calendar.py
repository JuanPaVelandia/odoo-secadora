# -*- coding: utf-8 -*-
from odoo import models
from datetime import datetime, timedelta, time
from collections import defaultdict
from dateutil.relativedelta import relativedelta
from odoo.addons.hr_work_entry_contract.models.hr_work_intervals import WorkIntervals


class ResourceCalendar(models.Model):
    _inherit = 'resource.calendar'

    def _attendance_intervals_batch(self, start_dt, end_dt, resources=None, domain=None, tz=None, lunch=False):
        """
        Override para corregir el cálculo de horarios flexibles.

        El método original calcula por SEMANA (reinicia full_time_required_hours cada 7 días).
        Esta versión calcula por PERIODO COMPLETO, distribuyendo las horas totales del periodo
        de manera proporcional a los días.
        """
        result = super()._attendance_intervals_batch(start_dt, end_dt, resources, domain, tz, lunch)

        # Solo aplicar la corrección para calendarios flexibles
        if not self.flexible_hours:
            return result

        # Procesar solo recursos con calendarios flexibles
        if not resources:
            resources = self.env['resource.resource']
            resources_list = [resources]
        else:
            resources_list = list(resources) + [self.env['resource.resource']]

        for resource in resources_list:
            # Solo procesar recursos con horarios flexibles (no fully_flexible)
            if not resource or not resource.calendar_id.flexible_hours or resource._is_fully_flexible():
                continue

            # Obtener el timezone del recurso
            resource_tz = tz or resource.tz
            from pytz import timezone as pytz_timezone
            tz_obj = pytz_timezone(resource_tz) if isinstance(resource_tz, str) else resource_tz

            start_datetime = start_dt.astimezone(tz_obj)
            end_datetime = end_dt.astimezone(tz_obj)

            start_date = start_datetime.date()
            end_datetime_adjusted = end_datetime - relativedelta(seconds=1)
            end_date = end_datetime_adjusted.date()

            # Obtener configuración del calendario
            full_time_required_hours = resource.calendar_id.full_time_required_hours
            max_hours_per_day = resource.calendar_id.hours_per_day

            # CORRECCIÓN: Calcular horas totales para TODO EL PERIODO
            total_days = (end_date - start_date).days + 1

            # Calcular cuántas semanas completas hay en el periodo
            weeks_in_period = total_days / 7.0

            # Total de horas para el periodo completo (no por semana)
            total_period_hours = full_time_required_hours * weeks_in_period

            # Limitar al máximo de horas del periodo
            max_possible_hours = (end_dt - start_dt).total_seconds() / 3600
            total_period_hours = min(total_period_hours, max_possible_hours)

            # Crear intervalos distribuyendo las horas totales del periodo
            intervals = []
            remaining_hours = total_period_hours
            current_day = start_date

            while current_day <= end_date and remaining_hours > 0:
                # Asignar horas para este día
                allocate_hours = min(max_hours_per_day, remaining_hours)
                remaining_hours -= allocate_hours

                # Crear intervalo centrado a las 12:00 PM
                midpoint = tz_obj.localize(datetime.combine(current_day, time(12, 0)))
                start_time = midpoint - timedelta(hours=allocate_hours / 2)
                end_time = midpoint + timedelta(hours=allocate_hours / 2)

                # Crear dummy attendance con las horas asignadas
                dummy_attendance = self.env['resource.calendar.attendance'].new({
                    'duration_hours': allocate_hours,
                    'duration_days': 1,
                })

                intervals.append((start_time, end_time, dummy_attendance))
                current_day += timedelta(days=1)

            # Actualizar el resultado para este recurso
            result[resource.id] = WorkIntervals(intervals)

        return result
