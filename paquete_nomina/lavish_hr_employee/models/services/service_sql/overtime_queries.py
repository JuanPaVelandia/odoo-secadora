# -*- coding: utf-8 -*-
"""
Consultas de Horas Extras
=========================

Builder especializado para consultas de hr_overtime.
"""
from typing import List, Optional, Dict, Any, Tuple
from datetime import date
from .base_query_builder import SQLQueryBuilder


# Tipos de horas extras con sus columnas en la tabla
OVERTIME_TYPES = {
    'RN': 'overtime_rn',
    'EXT-D': 'overtime_ext_d',
    'EXT-N': 'overtime_ext_n',
    'E-D-D/F': 'overtime_eddf',
    'E-N-D/F': 'overtime_endf',
    'D o F': 'overtime_dof',
    'RN-D/F': 'overtime_rndf',
    'R-D/F': 'overtime_rdf',
    'RN-F': 'overtime_rnf',
}

# Estados validos para horas extras
VALID_OVERTIME_STATES = ('validated', 'paid', 'done')


class OvertimeQueryBuilder(SQLQueryBuilder):
    """
    Builder especializado para consultas de horas extras (hr_overtime).

    Uso basico:
        builder = OvertimeQueryBuilder()
        query, params = (builder
            .for_employee(employee_id)
            .in_period(date_from, date_to)
            .accumulated_totals()
            .build()
        )
    """

    def __init__(self):
        super().__init__()
        self._setup_base()

    def _setup_base(self) -> 'OvertimeQueryBuilder':
        """Configura la tabla base."""
        self.from_table('hr_overtime', 'HO')
        return self

    # =========================================================================
    # FILTROS COMUNES
    # =========================================================================

    def for_employee(self, employee_id: int) -> 'OvertimeQueryBuilder':
        """Filtra por empleado."""
        return self.where('HO.employee_id = %(employee_id)s', employee_id=employee_id)

    def for_employees(self, employee_ids: List[int]) -> 'OvertimeQueryBuilder':
        """Filtra por multiples empleados."""
        return self.where_in('HO.employee_id', employee_ids, 'employee_ids')

    def in_period(self, date_from: date, date_to: date) -> 'OvertimeQueryBuilder':
        """Filtra por rango de fechas."""
        self.where('HO.date >= %(date_from)s', date_from=date_from)
        self.where('HO.date <= %(date_to)s', date_to=date_to)
        return self

    def with_valid_states(self) -> 'OvertimeQueryBuilder':
        """Filtra por estados validos (validated, paid, done)."""
        return self.where_in('HO.state', VALID_OVERTIME_STATES, 'overtime_states')

    # =========================================================================
    # SELECCIONES PREDEFINIDAS
    # =========================================================================

    def select_totals(self) -> 'OvertimeQueryBuilder':
        """Selecciona totales de cada tipo de hora extra."""
        for tipo, columna in OVERTIME_TYPES.items():
            self.select_coalesce(f'SUM(HO.{columna})', 0, columna)
        return self

    def select_by_date(self) -> 'OvertimeQueryBuilder':
        """Selecciona agrupando por fecha."""
        self.select('HO.date')
        for tipo, columna in OVERTIME_TYPES.items():
            self.select_coalesce(f'SUM(HO.{columna})', 0, columna)
        self.select_array_agg('HO.id', 'overtime_ids')
        return self

    # =========================================================================
    # ACUMULACIONES
    # =========================================================================

    def accumulated_totals(self) -> 'OvertimeQueryBuilder':
        """
        Configura para obtener totales acumulados por tipo de hora extra.

        Retorna columnas: rn, ext_d, ext_n, eddf, endf, dof, rndf, rdf, rnf, overtime_ids
        """
        self.with_valid_states()
        self._select_fields = []
        self.select_totals()
        self.select_array_agg('HO.id', 'overtime_ids')

        return self

    def accumulated_by_date(self) -> 'OvertimeQueryBuilder':
        """
        Configura para obtener totales agrupados por fecha.

        Retorna columnas: date, rn, ext_d, ..., overtime_ids
        """
        self.with_valid_states()
        self._select_fields = []
        self.select_by_date()
        self.group_by('HO.date')
        self.order_by('HO.date')

        return self

    # =========================================================================
    # QUERIES PREDEFINIDAS COMUNES
    # =========================================================================

    @classmethod
    def get_overtime_accumulated(
        cls,
        employee_id: int,
        date_from: date,
        date_to: date,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Query para obtener horas extras acumuladas.

        Equivalente a hr_slip_acumulacion._get_overtime_accumulated()

        Args:
            employee_id: ID del empleado
            date_from: Fecha inicio
            date_to: Fecha fin

        Returns:
            (query, params) donde el resultado tiene columnas de totales por tipo
        """
        builder = cls()
        builder.accumulated_totals()
        builder.for_employee(employee_id)
        builder.in_period(date_from, date_to)

        return builder.build()

    @classmethod
    def get_overtime_by_date(
        cls,
        employee_id: int,
        date_from: date,
        date_to: date,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Query para obtener horas extras agrupadas por fecha.

        Args:
            employee_id: ID del empleado
            date_from: Fecha inicio
            date_to: Fecha fin

        Returns:
            (query, params) donde el resultado tiene columnas (date, totales, overtime_ids)
        """
        builder = cls()
        builder.accumulated_by_date()
        builder.for_employee(employee_id)
        builder.in_period(date_from, date_to)

        return builder.build()

    @staticmethod
    def parse_totals_row(row: tuple) -> Dict[str, Any]:
        """
        Convierte una fila de resultados en diccionario de totales.

        Args:
            row: Fila con (rn, ext_d, ext_n, eddf, endf, dof, rndf, rdf, rnf, overtime_ids)

        Returns:
            dict: {'totals': {tipo: valor}, 'overtime_ids': [...]}
        """
        tipos = list(OVERTIME_TYPES.keys())
        totals = {}

        for i, tipo in enumerate(tipos):
            valor = row[i] or 0
            if valor > 0:
                totals[tipo] = valor

        overtime_ids = row[len(tipos)] or []

        return {
            'totals': totals,
            'total_hours': sum(totals.values()),
            'overtime_ids': overtime_ids,
        }

    @staticmethod
    def parse_by_date_row(row: tuple) -> Dict[str, Any]:
        """
        Convierte una fila agrupada por fecha en diccionario.

        Args:
            row: Fila con (date, rn, ext_d, ..., overtime_ids)

        Returns:
            dict: {'date': fecha, 'totals': {...}, 'hours': X, 'ids': [...]}
        """
        tipos = list(OVERTIME_TYPES.keys())
        fecha = row[0]
        totals = {}

        for i, tipo in enumerate(tipos):
            valor = row[i + 1] or 0
            if valor > 0:
                totals[tipo] = valor

        overtime_ids = row[len(tipos) + 1] or []

        return {
            'date': fecha,
            'totals': totals,
            'hours': sum(totals.values()),
            'ids': overtime_ids,
        }
