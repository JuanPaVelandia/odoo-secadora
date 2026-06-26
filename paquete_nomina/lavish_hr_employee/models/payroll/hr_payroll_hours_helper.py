# -*- coding: utf-8 -*-
from odoo import models, fields, api


class HrPayrollHoursHelper(models.AbstractModel):
    """
    Mixin para obtener las horas laborales aplicables según el periodo de la nómina.

    Este helper centraliza la lógica de obtención de horas laborales considerando
    la reducción gradual establecida en la Ley 2101 de 2021.
    """
    _name = 'hr.payroll.hours.helper'
    _description = 'Helper para Horas Laborales en Nómina'

    @api.model
    def get_working_hours_for_period(self, date_start, date_end, company_id=None):
        """
        Obtiene las horas laborales aplicables para un periodo de nómina.

        Maneja periodos que cruzan cambios de jornada (ej: 01/07 - 31/07/2024)
        calculando proporcionalmente las horas de cada sub-periodo.

        Args:
            date_start: Fecha inicio del periodo de nómina
            date_end: Fecha fin del periodo de nómina
            company_id: ID de la compañía (usa la actual si no se especifica)

        Returns:
            dict: {
                'hours_to_pay': float,  # Horas mensuales ponderadas del periodo
                'max_hours_per_week': float,  # Horas semanales ponderadas
                'periods': tree,  # Lista de sub-periodos aplicados
                'is_split': bool,  # True si el periodo cruza un cambio de jornada
            }
        """
        if not company_id:
            company_id = self.env.company.id

        # Buscar todas las configuraciones que aplican al periodo
        configs = self.env['hr.company.working.hours'].search([
            ('company_id', '=', company_id),
            ('effective_date', '<=', date_end),
        ], order='effective_date asc')

        if not configs:
            # Fallback: usar horas según Ley 2101 sin configuración
            return self._get_default_hours_for_date(date_end)

        # Identificar sub-periodos dentro del rango de nómina
        period_details = []
        total_days = (date_end - date_start).days + 1

        for i, config in enumerate(configs):
            # Determinar inicio y fin del sub-periodo
            period_start = max(date_start, config.effective_date)

            # Fin del sub-periodo: antes del siguiente config o date_end
            if i + 1 < len(configs):
                next_config = configs[i + 1]
                period_end = min(date_end, next_config.effective_date - fields.timedelta(days=1))
            else:
                period_end = date_end

            # Solo incluir si el periodo es válido
            if period_start <= date_end and period_end >= date_start:
                days_in_period = (period_end - period_start).days + 1
                weight = days_in_period / total_days

                period_details.append({
                    'start': period_start,
                    'end': period_end,
                    'days': days_in_period,
                    'weight': weight,
                    'hours_to_pay': config.hours_to_pay,
                    'max_hours_per_week': config.max_hours_per_week,
                    'config_id': config.id,
                })

        # Calcular horas ponderadas
        if not period_details:
            return self._get_default_hours_for_date(date_end)

        weighted_hours_to_pay = sum(p['hours_to_pay'] * p['weight'] for p in period_details)
        weighted_max_hours_week = sum(p['max_hours_per_week'] * p['weight'] for p in period_details)

        return {
            'hours_to_pay': weighted_hours_to_pay,
            'max_hours_per_week': weighted_max_hours_week,
            'periods': period_details,
            'is_split': len(period_details) > 1,
        }

    @api.model
    def get_working_hours_for_date(self, date_reference, company_id=None):
        """
        Obtiene las horas laborales aplicables para una fecha específica.

        Args:
            date_reference: Fecha de referencia
            company_id: ID de la compañía (usa la actual si no se especifica)

        Returns:
            dict: {
                'hours_to_pay': float,
                'max_hours_per_week': float,
                'config_id': int or False,
            }
        """
        if not company_id:
            company_id = self.env.company.id

        # Buscar la configuración vigente para la fecha
        config = self.env['hr.company.working.hours'].search([
            ('company_id', '=', company_id),
            ('effective_date', '<=', date_reference),
        ], order='effective_date desc', limit=1)

        if config:
            # Verificar que no haya un siguiente config antes de la fecha
            next_config = self.env['hr.company.working.hours'].search([
                ('company_id', '=', company_id),
                ('effective_date', '>', config.effective_date),
                ('effective_date', '<=', date_reference),
            ], limit=1)

            if not next_config:
                return {
                    'hours_to_pay': config.hours_to_pay,
                    'max_hours_per_week': config.max_hours_per_week,
                    'config_id': config.id,
                }

        # Fallback: calcular según Ley 2101 sin configuración
        return self._get_default_hours_for_date(date_reference)

    @api.model
    def _get_default_hours_for_date(self, date_reference):
        """
        Calcula horas según Ley 2101 de 2021 sin configuración en BD.

        Método de fallback cuando no hay hr.company.working.hours configurado.
        """
        year = date_reference.year
        month = date_reference.month
        day = date_reference.day

        # Antes de 2023: 48h/semana = 240h/mes
        if year < 2023:
            return {'hours_to_pay': 240.0, 'max_hours_per_week': 48.0, 'config_id': False}

        # 2023: 48h hasta jul 14, 47h desde jul 15
        if year == 2023:
            if month < 7 or (month == 7 and day < 15):
                return {'hours_to_pay': 240.0, 'max_hours_per_week': 48.0, 'config_id': False}
            else:
                return {'hours_to_pay': 235.0, 'max_hours_per_week': 47.0, 'config_id': False}

        # 2024: 47h hasta jul 14, 46h desde jul 15
        if year == 2024:
            if month < 7 or (month == 7 and day < 15):
                return {'hours_to_pay': 235.0, 'max_hours_per_week': 47.0, 'config_id': False}
            else:
                return {'hours_to_pay': 230.0, 'max_hours_per_week': 46.0, 'config_id': False}

        # 2025: 46h hasta jul 14, 44h desde jul 15
        if year == 2025:
            if month < 7 or (month == 7 and day < 15):
                return {'hours_to_pay': 230.0, 'max_hours_per_week': 46.0, 'config_id': False}
            else:
                return {'hours_to_pay': 220.0, 'max_hours_per_week': 44.0, 'config_id': False}

        # 2026: 44h hasta jul 14, 42h desde jul 15
        if year == 2026:
            if month < 7 or (month == 7 and day < 15):
                return {'hours_to_pay': 220.0, 'max_hours_per_week': 44.0, 'config_id': False}
            else:
                return {'hours_to_pay': 210.0, 'max_hours_per_week': 42.0, 'config_id': False}

        # 2027 en adelante: 42h/semana = 210h/mes
        return {'hours_to_pay': 210.0, 'max_hours_per_week': 42.0, 'config_id': False}
