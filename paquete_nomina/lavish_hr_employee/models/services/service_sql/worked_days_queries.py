# -*- coding: utf-8 -*-
"""
Consultas de Dias Trabajados
============================

Builder especializado para consultas de hr_payslip_day.
"""
from typing import List, Optional, Dict, Any, Tuple
from datetime import date
from .base_query_builder import SQLQueryBuilder
from .field_sets import VALID_PAYSLIP_STATES, TABLE_ALIASES


class WorkedDaysQueryBuilder(SQLQueryBuilder):
    """
    Builder especializado para consultas de dias trabajados (hr_payslip_day).

    Uso basico:
        builder = WorkedDaysQueryBuilder()
        query, params = (builder
            .for_contract(contract_id)
            .for_period(period_id)
            .select_day_types()
            .build()
        )
    """

    def __init__(self):
        super().__init__()
        self._setup_base()

    def _setup_base(self) -> 'WorkedDaysQueryBuilder':
        """Configura la tabla base y joins estandar."""
        self.from_table('hr_payslip_day', 'HPD')
        self.join('hr_payslip', 'HP', 'HP.id = HPD.payslip_id')
        return self

    # =========================================================================
    # FILTROS COMUNES
    # =========================================================================

    def for_contract(self, contract_id: int) -> 'WorkedDaysQueryBuilder':
        """Filtra por contrato."""
        return self.where_contract(contract_id, 'contract_id', 'HP')

    def for_contracts(self, contract_ids: List[int]) -> 'WorkedDaysQueryBuilder':
        """Filtra por multiples contratos."""
        return self.where_contracts(contract_ids, 'contract_id', 'HP')

    def for_period(self, period_id: int) -> 'WorkedDaysQueryBuilder':
        """Filtra por periodo de nomina."""
        return self.where('HP.period_id = %(period_id)s', period_id=period_id)

    def in_period(self, date_from: date, date_to: date) -> 'WorkedDaysQueryBuilder':
        """Filtra por rango de fechas de nomina."""
        self.where('HP.date_from >= %(period_from)s', period_from=date_from)
        self.where('HP.date_to <= %(period_to)s', period_to=date_to)
        return self

    def with_states(self, states: Tuple[str, ...] = VALID_PAYSLIP_STATES) -> 'WorkedDaysQueryBuilder':
        """Filtra por estados de nomina."""
        return self.where_payslip_states(states)

    def exclude_payslip(self, payslip_id: int) -> 'WorkedDaysQueryBuilder':
        """Excluye una nomina especifica (la actual)."""
        return self.where('HP.id != %(exclude_payslip_id)s', exclude_payslip_id=payslip_id)

    def exclude_payslips(self, payslip_ids: List[int]) -> 'WorkedDaysQueryBuilder':
        """Excluye nominas especificas."""
        return self.where_exclude_payslips(payslip_ids)

    # =========================================================================
    # SELECCIONES PREDEFINIDAS
    # =========================================================================

    def select_day_types(self) -> 'WorkedDaysQueryBuilder':
        """Selecciona dia y tipo de dia."""
        return self.select(
            'HPD.day',
            'HPD.day_type',
        )

    def select_with_details(self) -> 'WorkedDaysQueryBuilder':
        """Selecciona con detalles adicionales."""
        return self.select(
            'HPD.id',
            'HPD.payslip_id',
            'HPD.day',
            'HPD.day_type',
            'HP.contract_id',
        )

    # =========================================================================
    # ACUMULACIONES
    # =========================================================================

    def count_by_day_type(self) -> 'WorkedDaysQueryBuilder':
        """
        Cuenta dias por tipo.

        Retorna columnas: day_type, count
        """
        self.with_states()

        self._select_fields = []
        self.select('HPD.day_type')
        self.select_aggregate('COUNT', 'HPD.id', 'day_count')

        self.group_by('HPD.day_type')
        self.order_by('HPD.day_type')

        return self

    def days_as_dict(self) -> 'WorkedDaysQueryBuilder':
        """
        Configura para obtener dias como diccionario {dia: tipo}.

        Retorna columnas: day, day_type
        """
        self.with_states()
        self.select_day_types()
        self.order_by('HPD.day')

        return self

    # =========================================================================
    # QUERIES PREDEFINIDAS COMUNES
    # =========================================================================

    @classmethod
    def get_worked_days_processed(
        cls,
        period_id: int,
        contract_id: int,
        exclude_payslip_id: Optional[int] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Query para obtener dias ya procesados en otras nominas del mismo periodo.

        Equivalente a hr_slip_acumulacion._get_worked_days_processed()

        Args:
            period_id: ID del periodo
            contract_id: ID del contrato
            exclude_payslip_id: ID de nomina a excluir (opcional)

        Returns:
            (query, params) donde el resultado tiene columnas (day, day_type)
        """
        builder = cls()
        builder.days_as_dict()
        builder.for_contract(contract_id)
        builder.for_period(period_id)

        if exclude_payslip_id:
            builder.exclude_payslip(exclude_payslip_id)

        return builder.build()

    @classmethod
    def get_day_type_counts(
        cls,
        period_id: int,
        contract_id: int,
        exclude_payslip_id: Optional[int] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Query para contar dias por tipo en un periodo.

        Args:
            period_id: ID del periodo
            contract_id: ID del contrato
            exclude_payslip_id: ID de nomina a excluir (opcional)

        Returns:
            (query, params) donde el resultado tiene columnas (day_type, day_count)
        """
        builder = cls()
        builder.count_by_day_type()
        builder.for_contract(contract_id)
        builder.for_period(period_id)

        if exclude_payslip_id:
            builder.exclude_payslip(exclude_payslip_id)

        return builder.build()

    @classmethod
    def get_worked_days_in_range(
        cls,
        date_from: date,
        date_to: date,
        contract_id: int,
        exclude_payslip_ids: Optional[List[int]] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Query para obtener dias trabajados en un rango de fechas.

        Args:
            date_from: Fecha inicio
            date_to: Fecha fin
            contract_id: ID del contrato
            exclude_payslip_ids: IDs de nominas a excluir (opcional)

        Returns:
            (query, params) donde el resultado tiene columnas (day, day_type)
        """
        builder = cls()
        builder.days_as_dict()
        builder.for_contract(contract_id)
        builder.in_period(date_from, date_to)

        if exclude_payslip_ids:
            builder.exclude_payslips(exclude_payslip_ids)

        return builder.build()
