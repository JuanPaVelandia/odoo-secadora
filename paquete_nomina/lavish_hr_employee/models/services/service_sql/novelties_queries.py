# -*- coding: utf-8 -*-
"""
Consultas de Novedades
======================

Builder especializado para consultas de hr_novelties_different_concepts.
"""
from typing import List, Optional, Dict, Any, Tuple
from datetime import date
from .base_query_builder import SQLQueryBuilder


# Estados validos para novedades
VALID_NOVELTY_STATES = ('approved', 'processed')


class NoveltiesQueryBuilder(SQLQueryBuilder):
    """
    Builder especializado para consultas de novedades (hr_novelties_different_concepts).

    Uso basico:
        builder = NoveltiesQueryBuilder()
        query, params = (builder
            .for_employee(employee_id)
            .in_period(date_from, date_to)
            .not_processed()
            .accumulated_by_rule()
            .build()
        )
    """

    def __init__(self):
        super().__init__()
        self._setup_base()

    def _setup_base(self) -> 'NoveltiesQueryBuilder':
        """Configura la tabla base y joins estandar."""
        self.from_table('hr_novelties_different_concepts', 'HND')
        self.join('hr_salary_rule', 'HSR', 'HSR.id = HND.salary_rule_id')
        return self

    # =========================================================================
    # FILTROS COMUNES
    # =========================================================================

    def for_employee(self, employee_id: int) -> 'NoveltiesQueryBuilder':
        """Filtra por empleado."""
        return self.where('HND.employee_id = %(employee_id)s', employee_id=employee_id)

    def for_employees(self, employee_ids: List[int]) -> 'NoveltiesQueryBuilder':
        """Filtra por multiples empleados."""
        return self.where_in('HND.employee_id', employee_ids, 'employee_ids')

    def for_contract(self, contract_id: int) -> 'NoveltiesQueryBuilder':
        """Filtra por contrato (a traves de empleado)."""
        # Necesita join con hr_contract
        self.join('hr_contract', 'HC', 'HC.employee_id = HND.employee_id')
        return self.where('HC.id = %(contract_id)s', contract_id=contract_id)

    def in_period(self, date_from: date, date_to: date) -> 'NoveltiesQueryBuilder':
        """Filtra por rango de fechas."""
        return self.where_between('HND.date', date_from, date_to)

    def with_valid_states(self) -> 'NoveltiesQueryBuilder':
        """Filtra por estados validos (approved, processed)."""
        return self.where_in('HND.state', VALID_NOVELTY_STATES, 'novelty_states')

    def not_processed(self) -> 'NoveltiesQueryBuilder':
        """Solo novedades no procesadas (sin nomina asignada)."""
        return self.where('HND.payslip_id IS NULL')

    def for_rules(self, rule_codes: List[str]) -> 'NoveltiesQueryBuilder':
        """Filtra por codigos de regla salarial."""
        return self.where_in('HSR.code', rule_codes, 'rule_codes')

    # =========================================================================
    # SELECCIONES PREDEFINIDAS
    # =========================================================================

    def select_minimal(self) -> 'NoveltiesQueryBuilder':
        """Selecciona campos minimos."""
        return self.select(
            'HND.id',
            'HND.amount',
            'HSR.code AS rule_code',
        )

    def select_standard(self) -> 'NoveltiesQueryBuilder':
        """Selecciona campos estandar."""
        return self.select(
            'HND.id',
            'HND.amount',
            'HND.date',
            'HND.state',
            'HND.employee_id',
            'HSR.code AS rule_code',
            'HSR.id AS rule_id',
        )

    # =========================================================================
    # ACUMULACIONES
    # =========================================================================

    def accumulated_by_rule(self) -> 'NoveltiesQueryBuilder':
        """
        Configura para obtener totales acumulados por regla salarial.

        Retorna columnas: rule_code, total_amount, novelty_count, novelty_ids
        """
        self.with_valid_states()
        self.not_processed()

        self._select_fields = []
        self.select('HSR.code AS rule_code')
        self.select_aggregate('SUM', 'HND.amount', 'total_amount')
        self.select_aggregate('COUNT', 'HND.id', 'novelty_count')
        self.select_array_agg('HND.id', 'novelty_ids')

        self.group_by('HSR.code')
        self.order_by('HSR.code')

        return self

    def accumulated_by_employee_rule(self) -> 'NoveltiesQueryBuilder':
        """
        Configura para obtener totales por empleado y regla.

        Retorna columnas: employee_id, rule_code, total_amount, novelty_count, novelty_ids
        """
        self.with_valid_states()
        self.not_processed()

        self._select_fields = []
        self.select(
            'HND.employee_id',
            'HSR.code AS rule_code',
        )
        self.select_aggregate('SUM', 'HND.amount', 'total_amount')
        self.select_aggregate('COUNT', 'HND.id', 'novelty_count')
        self.select_array_agg('HND.id', 'novelty_ids')

        self.group_by('HND.employee_id', 'HSR.code')
        self.order_by('HND.employee_id', 'HSR.code')

        return self

    # =========================================================================
    # QUERIES PREDEFINIDAS COMUNES
    # =========================================================================

    @classmethod
    def get_novelties_accumulated(
        cls,
        employee_id: int,
        date_from: date,
        date_to: date,
        rule_codes: Optional[List[str]] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Query para obtener novedades acumuladas por regla.

        Equivalente a hr_slip_acumulacion._get_novelties_accumulated()

        Args:
            employee_id: ID del empleado
            date_from: Fecha inicio
            date_to: Fecha fin
            rule_codes: Codigos de reglas a filtrar (opcional)

        Returns:
            (query, params) donde el resultado tiene columnas
            (rule_code, total_amount, novelty_count, novelty_ids)
        """
        builder = cls()
        builder.accumulated_by_rule()
        builder.for_employee(employee_id)
        builder.in_period(date_from, date_to)

        if rule_codes:
            builder.for_rules(rule_codes)

        return builder.build()

    @classmethod
    def get_novelties_for_payslip(
        cls,
        employee_id: int,
        date_from: date,
        date_to: date,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Query para obtener novedades pendientes para una nomina.

        Args:
            employee_id: ID del empleado
            date_from: Fecha inicio
            date_to: Fecha fin

        Returns:
            (query, params) donde el resultado tiene detalles de novedades
        """
        builder = cls()
        builder.select_standard()
        builder.with_valid_states()
        builder.not_processed()
        builder.for_employee(employee_id)
        builder.in_period(date_from, date_to)
        builder.order_by('HND.date', 'HSR.code')

        return builder.build()

    @staticmethod
    def parse_accumulated_row(row: tuple) -> Dict[str, Any]:
        """
        Convierte una fila de acumulados en diccionario.

        Args:
            row: Fila con (rule_code, total_amount, novelty_count, novelty_ids)

        Returns:
            dict: {'amount': X, 'count': Y, 'novelty_ids': [...]}
        """
        return {
            'amount': row[1] or 0,
            'count': row[2] or 0,
            'novelty_ids': row[3] or [],
        }
