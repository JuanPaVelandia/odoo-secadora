# -*- coding: utf-8 -*-
"""
Servicio de Acumulación de Ausencias
Maneja acumulación de ausencias por línea, nómina y período usando SQL objects
"""

import logging
from collections import defaultdict
from typing import Dict, List, Optional
from datetime import date
from psycopg2 import sql

_logger = logging.getLogger(__name__)


class AusenciaAccumulationService:
    """
    Servicio para acumulación de ausencias usando SQL objects.
    
    Proporciona métodos para obtener:
    - Ausencias por línea (hr.leave.line)
    - Ausencias por nómina (agrupadas por payslip)
    - Ausencias acumuladas (por período y tipo)
    """
    
    def __init__(self, env, batch_ctx=None):
        """
        Args:
            env: Odoo environment
            batch_ctx: PayrollBatchContext opcional para procesamiento batch
        """
        self.env = env
        self.batch_ctx = batch_ctx
        self._cr = env.cr

    def _normalize_states(self, states, default_states=None):
        if default_states is None:
            default_states = ['paid', 'validate', 'validated']
        if states is None:
            return list(default_states)
        if isinstance(states, str):
            return [states]
        return list(states) if states else list(default_states)

    def _get_leave_type_ids(self, leave_type_codes):
        if not leave_type_codes:
            return []
        return self.env['hr.leave.type'].search([('code', 'in', leave_type_codes)]).ids

    def _build_leave_line_domain(
        self,
        contract_id,
        date_from,
        date_to,
        employee_id=None,
        leave_type_codes=None,
        exclude_payslip_id=None,
        states=None,
    ):
        domain = [
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('state', 'in', self._normalize_states(states)),
        ]
        if contract_id:
            domain.append(('leave_id.contract_id', '=', contract_id))
        if employee_id:
            domain.append(('leave_id.employee_id', '=', employee_id))
        if exclude_payslip_id:
            domain.append(('payslip_id', '!=', exclude_payslip_id))

        leave_type_ids = self._get_leave_type_ids(leave_type_codes)
        if leave_type_codes:
            if not leave_type_ids:
                return [], []
            domain.append(('leave_id.holiday_status_id', 'in', leave_type_ids))

        return domain, leave_type_ids

    def _get_leave_lines_grouped(self, domain, include_line_ids=True):
        if not domain:
            return {}

        LeaveLine = self.env['hr.leave.line']
        grouped = LeaveLine._read_group(
            domain,
            groupby=['leave_id'],
            aggregates=[
                '__count',
                'amount:sum',
                'days_holiday:sum',
                'holiday_amount:sum',
                'days_holiday_31:sum',
                'holiday_31_amount:sum',
            ],
        )

        leave_ids = {leave_rec.id for leave_rec, *_ in grouped if leave_rec}
        if not leave_ids:
            return {}

        leave_map = {
            leave.id: leave
            for leave in self.env['hr.leave'].browse(leave_ids)
        }

        totals_by_code = defaultdict(
            lambda: {
                'days': 0,
                'amount': 0.0,
                'holiday_days': 0.0,
                'holiday_amount': 0.0,
                'holiday_31_days': 0.0,
                'holiday_31_amount': 0.0,
            }
        )

        for leave_rec, count, amount, days_holiday, holiday_amount, days_holiday_31, holiday_31_amount in grouped:
            if not leave_rec:
                continue
            leave = leave_map.get(leave_rec.id)
            if not leave or not leave.holiday_status_id:
                continue
            code = leave.holiday_status_id.code or ''
            if not code:
                continue

            data = totals_by_code[code]
            data['days'] += count or 0
            data['amount'] += amount or 0.0
            data['holiday_days'] += days_holiday or 0.0
            data['holiday_amount'] += holiday_amount or 0.0
            data['holiday_31_days'] += days_holiday_31 or 0.0
            data['holiday_31_amount'] += holiday_31_amount or 0.0

        line_ids_by_code = defaultdict(list)
        if include_line_ids:
            line_rows = LeaveLine.search_read(domain, ['id', 'leave_id'])
            for row in line_rows:
                leave_ref = row.get('leave_id')
                if not leave_ref:
                    continue
                leave = leave_map.get(leave_ref[0])
                if not leave or not leave.holiday_status_id:
                    continue
                code = leave.holiday_status_id.code or ''
                if not code:
                    continue
                line_ids_by_code[code].append(row['id'])

        accumulated = {}
        for code, data in totals_by_code.items():
            accumulated[code] = {
                'days': int(data['days']),
                'amount': float(data['amount']),
                'holiday_days': int(data['holiday_days']),
                'holiday_amount': float(data['holiday_amount']),
                'holiday_31_days': int(data['holiday_31_days']),
                'holiday_31_amount': float(data['holiday_31_amount']),
                'line_ids': line_ids_by_code.get(code, []) if include_line_ids else [],
            }

        return accumulated
    
    def get_leave_lines_accumulated(
        self,
        contract_id: int,
        date_from: date,
        date_to: date,
        employee_id: Optional[int] = None,
        leave_type_codes: Optional[List[str]] = None,
        exclude_payslip_id: Optional[int] = None,
        states: Optional[List[str]] = None
    ) -> Dict[str, Dict]:
        """
        Obtiene ausencias acumuladas por tipo usando SQL objects.
        
        Retorna días, montos e IDs de líneas agrupados por tipo de ausencia.
        
        Args:
            contract_id: ID del contrato
            date_from: Fecha inicial
            date_to: Fecha final
            employee_id: ID del empleado (opcional)
            leave_type_codes: Códigos de tipos de ausencia a filtrar (opcional)
            exclude_payslip_id: ID de nómina a excluir (opcional)
            states: Estados de líneas de ausencia (default: ['paid', 'validate', 'validated'])
        
        Returns:
            dict: {
                'leave_type_code': {
                    'days': int,
                    'amount': float,
                    'line_ids': [int, ...]
                }
            }
        """
        if not contract_id:
            _logger.warning("Contrato no definido para consultar ausencias")
            return {}
        
        domain, _leave_type_ids = self._build_leave_line_domain(
            contract_id=contract_id,
            date_from=date_from,
            date_to=date_to,
            employee_id=employee_id,
            leave_type_codes=leave_type_codes,
            exclude_payslip_id=exclude_payslip_id,
            states=states,
        )

        accumulated = self._get_leave_lines_grouped(domain, include_line_ids=True)
        
        _logger.info(
            f"Ausencias acumuladas: {len(accumulated)} tipos, "
            f"período {date_from} - {date_to}, contrato {contract_id}"
        )
        
        return accumulated
    
    def get_leave_lines_by_payslip(
        self,
        payslip_id: int
    ) -> Dict[str, Dict]:
        """
        Obtiene ausencias agrupadas por tipo para una nómina específica.
        
        Args:
            payslip_id: ID de la nómina
        
        Returns:
            dict: {
                'leave_type_code': {
                    'days': int,
                    'amount': float,
                    'line_ids': [int, ...]
                }
            }
        """
        payslip = self.env['hr.payslip'].browse(payslip_id)
        if not payslip.exists():
            return {}
        
        accumulated = self._get_leave_lines_grouped(
            [('payslip_id', '=', payslip_id)],
            include_line_ids=True
        )
        
        return accumulated
    
    def get_leave_days_no_pay(
        self,
        contract_id: int,
        date_from: date,
        date_to: date,
        employee_id: Optional[int] = None,
        exclude_payslip_id: Optional[int] = None
    ) -> int:
        """
        Obtiene cantidad de días de ausencias no remuneradas.
        
        Args:
            contract_id: ID del contrato
            date_from: Fecha inicial
            date_to: Fecha final
            employee_id: ID del empleado (opcional)
            exclude_payslip_id: ID de nómina a excluir (opcional)
        
        Returns:
            int: Cantidad de días sin pago
        """
        if not contract_id:
            return 0
        
        domain, _leave_type_ids = self._build_leave_line_domain(
            contract_id=contract_id,
            date_from=date_from,
            date_to=date_to,
            employee_id=employee_id,
            exclude_payslip_id=exclude_payslip_id,
        )

        if not domain:
            return 0

        unpaid_type_ids = self.env['hr.leave.type'].search([
            ('unpaid_absences', '=', True)
        ]).ids
        if not unpaid_type_ids:
            return 0

        domain.append(('leave_id.holiday_status_id', 'in', unpaid_type_ids))

        days_no_pay = self.env['hr.leave.line'].search_count(domain)
        
        _logger.info(
            f"Días sin pago: {days_no_pay} días, "
            f"período {date_from} - {date_to}, contrato {contract_id}"
        )
        
        return days_no_pay
    
    def get_salary_in_leave(
        self,
        contract_id: int,
        date_from: date,
        date_to: date,
        employee_id: Optional[int] = None
    ) -> float:
        """
        Obtiene el salario que se debió pagar durante incapacidades o vacaciones.
        
        Args:
            contract_id: ID del contrato
            date_from: Fecha inicial
            date_to: Fecha final
            employee_id: ID del empleado (opcional)
        
        Returns:
            float: Monto total que se debió pagar en ausencias
        """
        if not contract_id:
            return 0.0
        
        # Query con DISTINCT ON y subquery
        query = sql.SQL("""
            SELECT COALESCE(SUM(TMP.value_day), 0) AS total_salary
            FROM (
                SELECT DISTINCT ON(HLL.date)
                    HLL.date,
                    WUH.wage / 30 AS value_day
                FROM hr_leave_line AS HLL
                INNER JOIN hr_leave AS HL ON HL.id = HLL.leave_id
                INNER JOIN hr_leave_type AS HLT ON HLT.id = HL.holiday_status_id
                INNER JOIN hr_contract_change_wage AS WUH ON WUH.contract_id = HL.contract_id
                WHERE HL.contract_id = %(contract_id)s
                AND HLL.state IN ('done', 'validated')
                AND HLL.date BETWEEN %(date_from)s AND %(date_to)s
                AND HLT.code IN ('INC', 'INC_ARL', 'VAC', 'LIC_PAG')
                AND HLL.date - WUH.date_start >= 0
                AND EXTRACT(DAY FROM HLL.date) < 31
                ORDER BY HLL.date, HLL.date - WUH.date_start
            ) AS TMP
        """)
        
        params = {
            'contract_id': contract_id,
            'date_from': date_from,
            'date_to': date_to
        }
        
        self._cr.execute(query, params)
        result = self._cr.fetchone()
        
        salary_in_leave = float(result[0]) if result and result[0] else 0.0
        
        _logger.info(
            f"Salario en ausencias: ${salary_in_leave:,.2f}, "
            f"período {date_from} - {date_to}, contrato {contract_id}"
        )
        
        return salary_in_leave
