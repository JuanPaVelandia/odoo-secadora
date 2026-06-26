# -*- coding: utf-8 -*-
"""
Consultas de Lineas de Ausencia
===============================

Builder especializado para consultas de hr_leave_line.
"""
from typing import List, Optional, Dict, Any, Tuple
from datetime import date
from .base_query_builder import SQLQueryBuilder
from .field_sets import VALID_LEAVE_LINE_STATES, TABLE_ALIASES
from .result_types import LeaveLineResult, LeaveAccumulatedResult


class LeaveLineQueryBuilder(SQLQueryBuilder):
    """
    Builder especializado para consultas de lineas de ausencia.

    Uso basico:
        builder = LeaveLineQueryBuilder()
        query, params = (builder
            .for_contract(contract_id)
            .in_period(date_from, date_to)
            .accumulated_by_type()
            .build()
        )
    """

    def __init__(self):
        super().__init__()
        self._setup_base()

    def _setup_base(self) -> 'LeaveLineQueryBuilder':
        """Configura la tabla base y joins estandar."""
        self.from_table('hr_leave_line', 'HLL')
        self.join('hr_leave', 'HL', 'HL.id = HLL.leave_id')
        return self

    # =========================================================================
    # FILTROS COMUNES
    # =========================================================================

    def for_contract(self, contract_id: int) -> 'LeaveLineQueryBuilder':
        """Filtra por contrato."""
        return self.where_contract(contract_id, 'contract_id', 'HL')

    def for_contracts(self, contract_ids: List[int]) -> 'LeaveLineQueryBuilder':
        """Filtra por multiples contratos."""
        return self.where_contracts(contract_ids, 'contract_id', 'HL')

    def in_period(self, date_from: date, date_to: date) -> 'LeaveLineQueryBuilder':
        """Filtra por rango de fechas de la linea de ausencia."""
        return self.where_between('HLL.date', date_from, date_to)

    def with_states(self, states: Tuple[str, ...] = VALID_LEAVE_LINE_STATES) -> 'LeaveLineQueryBuilder':
        """Filtra por estados de linea de ausencia."""
        return self.where_leave_states(states)

    def for_leave_types(self, leave_type_ids: List[int]) -> 'LeaveLineQueryBuilder':
        """Filtra por tipos de ausencia especificos."""
        return self.where_in('HL.holiday_status_id', leave_type_ids, 'leave_type_ids')

    def for_novelty_types(self, novelty_codes: List[str]) -> 'LeaveLineQueryBuilder':
        """Filtra por tipos de novedad PILA."""
        self.with_leave_type_info()
        return self.where_in('HLT.novelty', novelty_codes, 'novelty_codes')

    def only_unpaid(self) -> 'LeaveLineQueryBuilder':
        """Solo ausencias no remuneradas."""
        self.with_leave_type_info()
        return self.where('HLT.unpaid_absences = TRUE')

    def only_paid(self) -> 'LeaveLineQueryBuilder':
        """Solo ausencias remuneradas."""
        self.with_leave_type_info()
        return self.where('COALESCE(HLT.unpaid_absences, FALSE) = FALSE')

    # =========================================================================
    # JOINS ADICIONALES
    # =========================================================================

    def with_leave_type_info(self) -> 'LeaveLineQueryBuilder':
        """Incluye informacion del tipo de ausencia."""
        if not any(j.table == 'hr_leave_type' for j in self._joins):
            self.join('hr_leave_type', 'HLT', 'HLT.id = HL.holiday_status_id')
        return self

    # =========================================================================
    # SELECCIONES PREDEFINIDAS
    # =========================================================================

    def select_minimal(self) -> 'LeaveLineQueryBuilder':
        """Selecciona campos minimos."""
        return self.select(
            'HLL.id',
            'HLL.leave_id',
            'HLL.date',
        )

    def select_standard(self) -> 'LeaveLineQueryBuilder':
        """Selecciona campos estandar."""
        return self.select(
            'HLL.id',
            'HLL.leave_id',
            'HLL.date',
            'HLL.amount',
            'HLL.state',
            'HLL.days_payslip',
        )

    def select_with_type(self) -> 'LeaveLineQueryBuilder':
        """Selecciona con info del tipo de ausencia."""
        self.with_leave_type_info()
        return self.select(
            'HLL.id',
            'HLL.leave_id',
            'HLL.date',
            'HLL.amount',
            'HLL.state',
            'HLT.code AS leave_type_code',
            'HLT.novelty AS leave_type_novelty',
            'HL.contract_id',
        )

    # =========================================================================
    # ACUMULACIONES
    # =========================================================================

    def accumulated_by_type(self) -> 'LeaveLineQueryBuilder':
        """
        Configura para obtener dias acumulados por tipo de ausencia.

        Retorna columnas:
        - leave_type_code, days_count, total_amount, line_ids
        """
        self.with_leave_type_info()
        self.with_states()

        self._select_fields = []
        self.select('HLT.code AS leave_type_code')
        self.select_aggregate('COUNT', 'HLL.id', 'days_count')
        self.select_coalesce('SUM(HLL.amount)', 0, 'total_amount')
        self.select_array_agg('HLL.id', 'line_ids')

        self.group_by('HLT.code')
        self.order_by('HLT.code')

        return self

    def accumulated_by_type_with_novelty(self) -> 'LeaveLineQueryBuilder':
        """
        Configura para obtener dias acumulados con info de novedad.

        Util para calculos de PILA.
        """
        self.accumulated_by_type()
        self.select(
            'HLT.novelty',
            'HLT.unpaid_absences AS unpaid',
        )
        self.group_by('HLT.novelty', 'HLT.unpaid_absences')

        return self

    def count_unpaid_days(self) -> 'LeaveLineQueryBuilder':
        """
        Cuenta dias de ausencia no remunerada.

        Retorna columnas: leave_type_code, days_count
        """
        self.with_leave_type_info()
        self.with_states()
        self.only_unpaid()

        self._select_fields = []
        self.select('HLT.code AS leave_type_code')
        self.select_aggregate('COUNT', 'HLL.id', 'days_count')

        self.group_by('HLT.code')

        return self

    def days_by_novelty_type(self) -> 'LeaveLineQueryBuilder':
        """
        Agrupa dias por tipo de novedad PILA.

        Retorna columnas: novelty, days_count, total_amount
        """
        self.with_leave_type_info()
        self.with_states()

        self._select_fields = []
        self.select('HLT.novelty')
        self.select_aggregate('COUNT', 'HLL.id', 'days_count')
        self.select_aggregate('SUM', 'COALESCE(HLL.amount, 0)', 'total_amount')

        self.where('HLT.novelty IS NOT NULL')
        self.group_by('HLT.novelty')

        return self

    # =========================================================================
    # QUERIES PREDEFINIDAS COMUNES
    # =========================================================================

    @classmethod
    def get_leave_days_accumulated(
        cls,
        contract_id: int,
        date_from: date,
        date_to: date,
        include_novelty_info: bool = False,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Query predefinida para obtener dias de ausencia acumulados.

        Equivalente a hr_slip_acumulacion._get_leave_days_accumulated()

        Args:
            contract_id: ID del contrato
            date_from: Fecha inicio
            date_to: Fecha fin
            include_novelty_info: Incluir info de novedad PILA

        Returns:
            (query, params)
        """
        builder = cls()

        if include_novelty_info:
            builder.accumulated_by_type_with_novelty()
        else:
            builder.accumulated_by_type()

        builder.for_contract(contract_id)
        builder.in_period(date_from, date_to)

        return builder.build()

    @classmethod
    def get_leave_days_no_pay(
        cls,
        contract_id: int,
        date_from: date,
        date_to: date,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Query para obtener dias de ausencia sin pago.

        Args:
            contract_id: ID del contrato
            date_from: Fecha inicio
            date_to: Fecha fin

        Returns:
            (query, params)
        """
        builder = cls()
        builder.count_unpaid_days()
        builder.for_contract(contract_id)
        builder.in_period(date_from, date_to)

        return builder.build()

    @classmethod
    def get_days_by_novelty(
        cls,
        contract_id: int,
        date_from: date,
        date_to: date,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Query para obtener dias agrupados por tipo de novedad PILA.

        Util para reportes de seguridad social.

        Args:
            contract_id: ID del contrato
            date_from: Fecha inicio
            date_to: Fecha fin

        Returns:
            (query, params)
        """
        builder = cls()
        builder.days_by_novelty_type()
        builder.for_contract(contract_id)
        builder.in_period(date_from, date_to)

        return builder.build()

    @classmethod
    def get_salary_in_leave(
        cls,
        contract_id: int,
        date_from: date,
        date_to: date,
        leave_type_codes: Optional[List[str]] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Query para obtener el salario que se debio pagar durante ausencias.

        Calcula el salario diario basado en historial de cambios de salario
        (hr_contract_change_wage) para cada dia de ausencia.

        Args:
            contract_id: ID del contrato
            date_from: Fecha inicio
            date_to: Fecha fin
            leave_type_codes: Codigos de tipos de ausencia (default: INC, INC_ARL, VAC, LIC_PAG)

        Returns:
            (query, params) donde el resultado tiene columna 'total_salary'
        """
        if leave_type_codes is None:
            leave_type_codes = ['INC', 'INC_ARL', 'VAC', 'LIC_PAG']

        query = """
            SELECT COALESCE(SUM(TMP.value_day), 0) AS total_salary
            FROM (
                SELECT DISTINCT ON(HLL.date)
                    HLL.date,
                    WUH.wage / 30 AS value_day
                FROM hr_leave_line AS HLL
                INNER JOIN hr_leave AS HL
                    ON HL.id = HLL.leave_id
                INNER JOIN hr_leave_type AS HLT
                    ON HLT.id = HL.holiday_status_id
                INNER JOIN hr_contract_change_wage AS WUH
                    ON WUH.contract_id = HL.contract_id
                WHERE
                    HL.contract_id = %(contract_id)s AND
                    HLL.state IN ('done', 'validated') AND
                    HLL.date BETWEEN %(date_from)s AND %(date_to)s AND
                    HLT.code = ANY(%(leave_type_codes)s) AND
                    HLL.date - WUH.date_start >= 0 AND
                    EXTRACT(DAY FROM HLL.date) < 31
                ORDER BY HLL.date, HLL.date - WUH.date_start
            ) AS TMP
        """

        params = {
            'contract_id': contract_id,
            'date_from': date_from,
            'date_to': date_to,
            'leave_type_codes': leave_type_codes,
        }

        return query, params
