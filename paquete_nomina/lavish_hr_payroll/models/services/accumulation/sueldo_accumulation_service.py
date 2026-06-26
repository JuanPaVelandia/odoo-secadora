# -*- coding: utf-8 -*-
"""
Servicio de Acumulación de Sueldos (Promedios)
Maneja cálculo de promedios de sueldo para prestaciones y liquidaciones
"""

import logging
from typing import Dict, List, Optional
from datetime import date
from dateutil.relativedelta import relativedelta

_logger = logging.getLogger(__name__)

class SueldoAccumulationService:
    """
    Servicio para acumulación y promedios de sueldos.
    
    Proporciona métodos para calcular:
    - Promedio de sueldo (últimos N meses)
    - Promedio de IBC/IBD (últimos N meses)
    - Promedio de devengos (últimos N meses)
    - Salario base histórico
    """
    
    def __init__(self, env, batch_ctx=None):
        """
        Args:
            env: Odoo environment
            batch_ctx: PayrollBatchContext opcional
        """
        self.env = env
        self.batch_ctx = batch_ctx

    def _normalize_states(self, states):
        if states is None:
            return ['done', 'paid']
        if isinstance(states, str):
            return [states]
        return list(states) if states else ['done', 'paid']

    def _get_rule_id(self, rule_code):
        if not rule_code:
            return None
        return self.env['hr.salary.rule'].search([('code', '=', rule_code)], limit=1).id

    def _get_category_ids(self, category_codes):
        if not category_codes:
            return []
        return self.env['hr.salary.rule.category'].search([
            ('code', 'in', category_codes)
        ]).ids

    def _build_line_domain(
        self,
        contract_id,
        date_from,
        date_to,
        company_id=None,
        states=None,
        rule_id=None,
        category_ids=None,
    ):
        domain = [
            ('contract_id', '=', contract_id),
            ('state_slip', 'in', self._normalize_states(states)),
        ]
        date_domain = []
        if date_from and date_to:
            date_domain = [
                ('date_from', '>=', date_from),
                ('date_from', '<=', date_to),
            ]
        elif date_from:
            date_domain = [('date_from', '>=', date_from)]
        elif date_to:
            date_domain = [('date_from', '<=', date_to)]
        if date_domain:
            domain += date_domain
        if company_id:
            domain.append(('company_id', '=', company_id))
        if rule_id:
            domain.append(('salary_rule_id', '=', rule_id))
        if category_ids:
            domain.append(('category_id', 'in', category_ids))
        return domain
    
    def get_average_salary(
        self,
        contract_id: int,
        end_date: date,
        months: int = 12,
        company_id: Optional[int] = None,
        rule_code: str = 'BASIC'
    ) -> float:
        """
        Calcula promedio de sueldo de los últimos N meses.
        
        Args:
            contract_id: ID del contrato
            end_date: Fecha de corte (hasta esta fecha)
            months: Número de meses a considerar (default: 12)
            company_id: ID de compañía (opcional)
            rule_code: Código de regla a promediar (default: 'BASIC')
        
        Returns:
            float: Promedio de sueldo
        """
        if not contract_id:
            return 0.0
        
        date_start = end_date - relativedelta(months=months)
        rule_id = self._get_rule_id(rule_code)
        if not rule_id:
            return 0.0

        domain = self._build_line_domain(
            contract_id=contract_id,
            date_from=date_start,
            date_to=end_date,
            company_id=company_id,
            rule_id=rule_id,
        )

        grouped = self.env['hr.payslip.line']._read_group(
            domain,
            groupby=[],
            aggregates=['total:avg'],
        )
        avg_salary = float(grouped[0][0] or 0.0) if grouped else 0.0

        _logger.info(
            f"Promedio de sueldo ({rule_code}): ${avg_salary:,.2f}, "
            f"últimos {months} meses hasta {end_date}, contrato {contract_id}"
        )
        
        return avg_salary
    
    def get_average_ibc(
        self,
        contract_id: int,
        end_date: date,
        months: int = 12,
        company_id: Optional[int] = None
    ) -> float:
        """
        Calcula promedio de IBC (Ingreso Base de Cotización) de los últimos N meses.
        
        Args:
            contract_id: ID del contrato
            end_date: Fecha de corte
            months: Número de meses a considerar (default: 12)
            company_id: ID de compañía (opcional)
        
        Returns:
            float: Promedio de IBC
        """
        return self.get_average_salary(
            contract_id=contract_id,
            end_date=end_date,
            months=months,
            company_id=company_id,
            rule_code='IBD'  # IBD es el IBC en el sistema
        )
    
    def get_average_earnings(
        self,
        contract_id: int,
        end_date: date,
        months: int = 12,
        company_id: Optional[int] = None,
        category_codes: Optional[List[str]] = None
    ) -> float:
        """
        Calcula promedio de devengos de los últimos N meses.
        
        Args:
            contract_id: ID del contrato
            end_date: Fecha de corte
            months: Número de meses a considerar (default: 12)
            company_id: ID de compañía (opcional)
            category_codes: Códigos de categorías a incluir (default: ['BASIC', 'o_SALARY', 'COMP'])
        
        Returns:
            float: Promedio de devengos
        """
        if not contract_id:
            return 0.0
        
        if category_codes is None:
            category_codes = ['BASIC', 'o_SALARY', 'COMP']
        
        date_start = end_date - relativedelta(months=months)
        category_ids = self._get_category_ids(category_codes)
        if not category_ids:
            return 0.0

        domain = self._build_line_domain(
            contract_id=contract_id,
            date_from=date_start,
            date_to=end_date,
            company_id=company_id,
            category_ids=category_ids,
        )

        grouped = self.env['hr.payslip.line']._read_group(
            domain,
            groupby=[],
            aggregates=['total:avg'],
        )
        avg_earnings = float(grouped[0][0] or 0.0) if grouped else 0.0

        _logger.info(
            f"Promedio de devengos: ${avg_earnings:,.2f}, "
            f"últimos {months} meses hasta {end_date}, contrato {contract_id}"
        )
        
        return avg_earnings
    
    def get_salary_history(
        self,
        contract_id: int,
        date_from: date,
        date_to: date,
        company_id: Optional[int] = None,
        rule_code: str = 'BASIC'
    ) -> List[Dict]:
        """
        Obtiene historial de sueldo por período.
        
        Args:
            contract_id: ID del contrato
            date_from: Fecha inicial
            date_to: Fecha final
            company_id: ID de compañía (opcional)
            rule_code: Código de regla (default: 'BASIC')
        
        Returns:
            list: [
                {
                    'date_from': date,
                    'date_to': date,
                    'total': float,
                    'payslip_id': int
                },
                ...
            ]
        """
        if not contract_id:
            return []
        
        rule_id = self._get_rule_id(rule_code)
        if not rule_id:
            return []

        domain = self._build_line_domain(
            contract_id=contract_id,
            date_from=date_from,
            date_to=date_to,
            company_id=company_id,
            rule_id=rule_id,
        )

        grouped = self.env['hr.payslip.line']._read_group(
            domain,
            groupby=['slip_id'],
            aggregates=['total:sum'],
        )

        slip_ids = [slip_rec.id for slip_rec, _total in grouped if slip_rec]
        slips = {s.id: s for s in self.env['hr.payslip'].browse(slip_ids)}

        history = []
        for slip_rec, total_sum in grouped:
            if not slip_rec:
                continue
            slip_id = slip_rec.id
            slip = slips.get(slip_id)
            history.append({
                'date_from': slip.date_from if slip else None,
                'date_to': slip.date_to if slip else None,
                'total': float(total_sum or 0.0),
                'payslip_id': slip_id,
            })

        history.sort(key=lambda x: x['date_from'] or date.min)
        return history
    
    def calculate_prorated_salary(
        self,
        contract_id: int,
        date_from: date,
        date_to: date,
        base_salary: float,
        days_worked: int,
        days_no_pay: int = 0,
        company_id: Optional[int] = None
    ) -> Dict:
        """
        Calcula salario prorrateado considerando días trabajados y ausencias.
        
        Args:
            contract_id: ID del contrato
            date_from: Fecha inicial
            date_to: Fecha final
            base_salary: Salario base del contrato
            days_worked: Días trabajados
            days_no_pay: Días sin pago (ausencias no remuneradas)
            company_id: ID de compañía (opcional)
        
        Returns:
            dict: {
                'total_salary': float,
                'worked_days': int,
                'salary_per_day': float,
                'base_salary': float,
                'days_no_pay': int,
                'adjustments': list
            }
        """
        if days_worked == 0:
            return {
                'total_salary': 0.0,
                'worked_days': 0,
                'salary_per_day': 0.0,
                'base_salary': base_salary,
                'days_no_pay': days_no_pay,
                'adjustments': []
            }
        
        # Calcular salario diario
        salary_per_day = base_salary / 30.0  # Método comercial 360
        
        # Calcular salario total
        total_salary = salary_per_day * days_worked
        
        # Ajustes por ausencias no pagadas
        adjustments = []
        if days_no_pay > 0:
            adjustment_amount = -salary_per_day * days_no_pay
            adjustments.append({
                'type': 'leave_no_pay',
                'days': days_no_pay,
                'amount': adjustment_amount
            })
            total_salary += adjustment_amount
        
        return {
            'total_salary': total_salary,
            'worked_days': days_worked,
            'salary_per_day': salary_per_day,
            'base_salary': base_salary,
            'days_no_pay': days_no_pay,
            'adjustments': adjustments
        }
