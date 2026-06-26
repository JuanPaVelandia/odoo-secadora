# -*- coding: utf-8 -*-
"""
Servicio de Cálculo de Período
==============================

Gestiona la asignación y validación de períodos para nóminas.
Incluye:
- Asignación automática de período según fechas
- Validación de nóminas sin período
- Creación de períodos faltantes
"""

import logging

_logger = logging.getLogger(__name__)


class PeriodCalculationService:
    """
    Servicio para gestionar períodos de nómina.
    Extrae la lógica de período de hr.payslip.
    """

    def __init__(self, payslip):
        """
        Args:
            payslip: hr.payslip record
        """
        self.payslip = payslip
        self.env = payslip.env
        self.date_from = payslip.date_from
        self.date_to = payslip.date_to
        self.company_id = payslip.company_id.id

    def get_periodo_string(self):
        """
        Obtiene el string del período (YYYYMM).

        Returns:
            str: Período en formato YYYYMM o vacío
        """
        if self.date_to:
            return self.date_to.strftime("%Y%m")
        return ''

    def get_period_type(self):
        """
        Determina el tipo de período según la duración.

        Returns:
            str: 'monthly' o 'bi-monthly'
        """
        days_diff = (self.date_to - self.date_from).days + 1
        return 'monthly' if days_diff > 15 else 'bi-monthly'

    def get_or_create_period(self):
        """
        Obtiene o crea el período correspondiente a la nómina.

        Returns:
            hr.period record o False
        """
        period_type = self.get_period_type()
        Period = self.env['hr.period']

        period = Period.get_period(
            self.date_from,
            self.date_to,
            period_type,
            self.company_id
        )

        if not period:
            # Crear períodos del año si no existen
            year = self.date_from.year
            self._ensure_periods_exist(year, period_type)
            period = Period.get_period(
                self.date_from,
                self.date_to,
                period_type,
                self.company_id
            )

        return period

    def _ensure_periods_exist(self, year, period_type):
        """
        Asegura que existan los períodos para el año.

        Args:
            year: Año a verificar
            period_type: Tipo de período ('monthly', 'bi-monthly')
        """
        Period = self.env['hr.period']

        existing_periods = Period.search([
            ('year', '=', year),
            ('type_period', '=', period_type),
            ('company_id', '=', self.company_id)
        ], limit=1)

        if not existing_periods:
            self.env.cr.commit()
            Period.create_periods_for_year(
                year,
                schedule_pays=[period_type],
                company_id=self.company_id
            )
            self.env.cr.commit()

    def assign_period(self):
        """
        Asigna el período a la nómina actual.

        Returns:
            bool: True si se asignó correctamente
        """
        period = self.get_or_create_period()
        if period:
            self.payslip.period_id = period.id
            return True
        return False

    @classmethod
    def check_payslips_without_period(cls, env):
        """
        Busca nóminas en estados avanzados sin período asignado.

        Args:
            env: Odoo environment

        Returns:
            recordset: Nóminas sin período
        """
        payslips_without_period = env['hr.payslip'].search([
            ('state', 'in', ['verify', 'done', 'paid']),
            ('period_id', '=', False),
        ])

        if payslips_without_period:
            message = f"Se encontraron {len(payslips_without_period)} nóminas en estados avanzados sin período asignado."

            if len(payslips_without_period) <= 10:
                slip_details = []
                for slip in payslips_without_period:
                    details = f"- {slip.name} ({slip.employee_id.name}), Estado: {slip.state}, Fechas: {slip.date_from} - {slip.date_to}"
                    slip_details.append(details)

                message += "\n\nDetalles:\n" + "\n".join(slip_details)

            admin_user = env.ref('base.user_admin')
            model_id = env['ir.model'].search([('model', '=', 'hr.payslip')], limit=1).id

            env['mail.activity'].create({
                'activity_type_id': env.ref('mail.mail_activity_data_todo').id,
                'note': message,
                'user_id': admin_user.id,
                'res_model_id': model_id,
                'res_id': payslips_without_period[0].id if payslips_without_period else False,
                'summary': "Nóminas sin período asignado",
            })

        return payslips_without_period

    @classmethod
    def assign_periods_to_draft_payslips(cls, env, company_id=None):
        """
        Asigna períodos a todas las nóminas sin período.

        Args:
            env: Odoo environment
            company_id: ID de compañía (opcional)

        Returns:
            int: Cantidad de nóminas actualizadas
        """
        domain = [('period_id', '=', False)]
        if company_id:
            domain.append(('company_id', '=', company_id))

        draft_slips = env['hr.payslip'].search(domain)

        if not draft_slips:
            return 0

        # Obtener años únicos
        years_to_check = set(slip.date_from.year for slip in draft_slips)
        company = company_id or env.company.id

        # Crear períodos faltantes
        for year in years_to_check:
            for period_type in ['monthly', 'bi-monthly']:
                existing_periods = env['hr.period'].search([
                    ('year', '=', year),
                    ('type_period', '=', period_type),
                    ('company_id', '=', company)
                ], limit=1)

                if not existing_periods:
                    env.cr.commit()
                    env['hr.period'].create_periods_for_year(
                        year,
                        schedule_pays=[period_type],
                        company_id=company
                    )
                    env.cr.commit()

        # Asignar períodos en lotes
        updated_count = 0
        batch_size = 100
        Period = env['hr.period']

        for i in range(0, len(draft_slips), batch_size):
            batch = draft_slips[i:i + batch_size]

            for slip in batch:
                days_diff = (slip.date_to - slip.date_from).days + 1
                period_type = 'monthly' if days_diff > 15 else 'bi-monthly'

                period = Period.get_period(
                    slip.date_from,
                    slip.date_to,
                    period_type,
                    slip.company_id.id
                )

                if period:
                    slip.write({"period_id": period.id})
                    updated_count += 1

            env.cr.commit()

        return updated_count
