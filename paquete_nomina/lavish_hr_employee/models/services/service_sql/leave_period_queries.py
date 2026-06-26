# -*- coding: utf-8 -*-
"""
Consultas de Ausencias por Periodo
==================================

Builder especializado para consultas de ausencias agrupadas por periodo.
"""
from typing import Dict, Any, Tuple
from datetime import date
from .field_sets import VALID_LEAVE_LINE_STATES


class LeavePeriodQueryBuilder:
    """
    Builder para consultas de ausencias por periodo.

    A diferencia de PeriodQueryBuilder (para lineas de nomina),
    este builder trabaja con hr_leave_line.

    Uso:
        builder = LeavePeriodQueryBuilder()
        query, params = (builder
            .for_contract(contract_id)
            .in_period(date_from, date_to)
            .for_calculation_type('ibd')
            .build()
        )
    """

    def __init__(self):
        self._contract_id = None
        self._date_from = None
        self._date_to = None
        self._leave_states = VALID_LEAVE_LINE_STATES
        self._calculation_type = 'ibd'

    def for_contract(self, contract_id: int) -> 'LeavePeriodQueryBuilder':
        """Filtrar por contrato."""
        self._contract_id = contract_id
        return self

    def in_period(self, date_from: date, date_to: date) -> 'LeavePeriodQueryBuilder':
        """Definir periodo de consulta."""
        self._date_from = date_from
        self._date_to = date_to
        return self

    def with_leave_states(self, states: Tuple[str, ...]) -> 'LeavePeriodQueryBuilder':
        """Estados de lineas de ausencia a incluir."""
        self._leave_states = states
        return self

    def for_calculation_type(self, calc_type: str) -> 'LeavePeriodQueryBuilder':
        """Tipo de calculo: 'ibd', 'retenciones', 'prestaciones'."""
        self._calculation_type = calc_type
        return self

    def _get_extra_select(self) -> str:
        """Campos SELECT adicionales segun tipo de calculo."""
        if self._calculation_type == 'ibd':
            return """,
                CASE
                    WHEN HLT.unpaid_absences THEN 'no_salary'
                    ELSE 'salary'
                END AS data_type"""
        elif self._calculation_type == 'retenciones':
            return """,
                CASE
                    WHEN HLT.unpaid_absences THEN 'dev_no_salarial'
                    ELSE 'devengos'
                END AS data_type"""
        elif self._calculation_type == 'prestaciones':
            return """,
                NULL AS base_field,
                CASE
                    WHEN HLT.unpaid_absences THEN 'variable'
                    ELSE 'basic'
                END AS data_type"""
        else:
            return ", NULL AS data_type"

    def build(self) -> Tuple[str, Dict[str, Any]]:
        """Construir query y parametros."""
        if not self._contract_id:
            raise ValueError("contract_id requerido. Usa .for_contract()")
        if not self._date_from or not self._date_to:
            raise ValueError("Periodo requerido. Usa .in_period()")

        extra_select = self._get_extra_select()
        base_field_select = ', base_field' if self._calculation_type == 'prestaciones' else ''

        query = f"""
        WITH
        leaves_by_period AS (
            SELECT
                hl.id AS leave_id,
                hl.contract_id,
                hl.date_from,
                hl.date_to,
                TO_CHAR(hl.date_from, 'YYYY-MM') AS period_key,
                EXTRACT(YEAR FROM hl.date_from) AS year,
                EXTRACT(MONTH FROM hl.date_from) AS month
            FROM hr_leave hl
            WHERE hl.contract_id = %(contract_id)s
              AND hl.state = 'validate'
              AND hl.date_from <= %(date_to)s
              AND hl.date_to >= %(date_from)s
        )
        SELECT
            hll.id AS line_id,
            NULL::int AS payslip_id,
            NULL::varchar AS payslip_number,
            hll.date AS date_from,
            hll.date AS date_to,
            HLT.code AS rule_code_full,
            COALESCE(HLT.name->>'es_CO', HLT.name->>'en_US', HLT.code) AS rule_name,
            CASE
                WHEN HLT.unpaid_absences THEN 'DED'
                ELSE 'DEV_SALARIAL'
            END AS category_code,
            COALESCE(HLT.name->>'es_CO', HLT.name->>'en_US', HLT.code) AS category_name,
            COALESCE(hll.amount, 0) AS total,
            COALESCE(hll.amount, 0) AS amount,
            COALESCE(hll.days_payslip, 0) AS quantity,
            lbp.period_key,
            lbp.year,
            lbp.month,
            'leave' AS source_type
            {extra_select}
            {base_field_select}
        FROM hr_leave_line hll
        INNER JOIN leaves_by_period lbp ON lbp.leave_id = hll.leave_id
        INNER JOIN hr_leave hl ON hl.id = hll.leave_id
        INNER JOIN hr_leave_type HLT ON HLT.id = hl.holiday_status_id
        WHERE hll.state IN %(leave_states)s
          AND hll.date BETWEEN %(date_from)s AND %(date_to)s
        ORDER BY lbp.period_key, hll.date, HLT.code
        """

        params = {
            'contract_id': self._contract_id,
            'date_from': self._date_from,
            'date_to': self._date_to,
            'leave_states': self._leave_states,
        }

        return query, params
