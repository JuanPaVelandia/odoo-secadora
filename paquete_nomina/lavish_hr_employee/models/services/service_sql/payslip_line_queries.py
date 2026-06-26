# -*- coding: utf-8 -*-
"""
Consultas de Lineas de Nomina
=============================

Builder especializado para consultas de hr_payslip_line.
"""
from typing import List, Optional, Dict, Any, Tuple
from datetime import date
from .base_query_builder import SQLQueryBuilder
from .field_sets import (
    PAYSLIP_LINE_FIELDS,
    VALID_PAYSLIP_STATES,
    TABLE_ALIASES,
)
from .result_types import PayslipLineResult, CategoryAccumulatedResult, AccumulatedResult


class PayslipLineQueryBuilder(SQLQueryBuilder):
    """
    Builder especializado para consultas de lineas de nomina.

    Uso basico:
        builder = PayslipLineQueryBuilder()
        query, params = (builder
            .for_contract(contract_id)
            .in_period(date_from, date_to)
            .with_category_info()
            .accumulated_by_category()
            .build()
        )

    Ejecutar:
        cr.execute(query, params)
        results = [CategoryAccumulatedResult.from_row(row, columns) for row in cr.fetchall()]
    """

    def __init__(self):
        super().__init__()
        self._setup_base()

    def _setup_base(self) -> 'PayslipLineQueryBuilder':
        """Configura la tabla base y joins estandar."""
        self.from_table('hr_payslip_line', 'HPL')
        self.join('hr_payslip', 'HP', 'HP.id = HPL.slip_id')
        return self

    # =========================================================================
    # FILTROS COMUNES
    # =========================================================================

    def for_contract(self, contract_id: int) -> 'PayslipLineQueryBuilder':
        """Filtra por contrato."""
        return self.where_contract(contract_id, 'contract_id', 'HP')

    def for_contracts(self, contract_ids: List[int]) -> 'PayslipLineQueryBuilder':
        """Filtra por multiples contratos."""
        return self.where_contracts(contract_ids, 'contract_id', 'HP')

    def in_period(self, date_from: date, date_to: date) -> 'PayslipLineQueryBuilder':
        """Filtra por periodo de nomina."""
        self.where('HP.date_from >= %(period_from)s', period_from=date_from)
        self.where('HP.date_to <= %(period_to)s', period_to=date_to)
        return self

    def with_states(self, states: Tuple[str, ...] = VALID_PAYSLIP_STATES) -> 'PayslipLineQueryBuilder':
        """Filtra por estados de nomina."""
        return self.where_payslip_states(states)

    def exclude_payslips(self, payslip_ids: List[int]) -> 'PayslipLineQueryBuilder':
        """Excluye nominas especificas (ej: la nomina actual)."""
        return self.where_exclude_payslips(payslip_ids)

    def with_positive_total(self) -> 'PayslipLineQueryBuilder':
        """Solo lineas con total > 0."""
        return self.where('HPL.total > 0')

    def for_categories(self, category_ids: List[int]) -> 'PayslipLineQueryBuilder':
        """Filtra por categorias especificas."""
        return self.where_in('HPL.category_id', category_ids, 'category_ids')

    def for_rules(self, rule_codes: List[str]) -> 'PayslipLineQueryBuilder':
        """Filtra por codigos de regla."""
        # Evitar duplicar el join si ya existe
        if not any(j.table == 'hr_salary_rule' for j in self._joins):
            self.join('hr_salary_rule', 'HSR', 'HSR.id = HPL.salary_rule_id')
        return self.where_in('HSR.code', rule_codes, 'rule_codes')

    # =========================================================================
    # JOINS ADICIONALES
    # =========================================================================

    def with_category_info(self) -> 'PayslipLineQueryBuilder':
        """Incluye informacion de categoria."""
        self.join('hr_salary_rule_category', 'HSRC', 'HSRC.id = HPL.category_id')
        return self

    def with_rule_info(self) -> 'PayslipLineQueryBuilder':
        """Incluye informacion de regla."""
        # Evitar duplicar el join
        if not any(j.table == 'hr_salary_rule' for j in self._joins):
            self.join('hr_salary_rule', 'HSR', 'HSR.id = HPL.salary_rule_id')
        return self

    def with_leave_info(self) -> 'PayslipLineQueryBuilder':
        """Incluye informacion de ausencia relacionada."""
        self.left_join('hr_leave', 'HL', 'HL.id = HPL.leave_id')
        self.left_join('hr_leave_type', 'HLT', 'HLT.id = HL.holiday_status_id')
        return self

    # =========================================================================
    # SELECCIONES PREDEFINIDAS
    # =========================================================================

    def select_minimal(self) -> 'PayslipLineQueryBuilder':
        """Selecciona campos minimos."""
        return self.select(
            'HPL.id',
            'HPL.total',
            'HPL.category_id',
            'HPL.salary_rule_id',
        )

    def select_standard(self) -> 'PayslipLineQueryBuilder':
        """Selecciona campos estandar."""
        return self.select(
            'HPL.id',
            'HPL.slip_id',
            'HPL.total',
            'HPL.amount',
            'HPL.quantity',
            'HPL.rate',
            'HPL.category_id',
            'HPL.salary_rule_id',
        )

    def select_with_category(self) -> 'PayslipLineQueryBuilder':
        """Selecciona con info de categoria."""
        self.with_category_info()
        self.with_rule_info()
        return self.select(
            'HPL.id',
            'HPL.slip_id',
            'HPL.total',
            'HPL.amount',
            'HPL.quantity',
            'HPL.rate',
            'HSRC.code AS category_code',
            'HSR.code AS rule_code',
            'HSR.id AS rule_id',
        )

    # =========================================================================
    # ACUMULACIONES
    # =========================================================================

    def accumulated_by_category(self) -> 'PayslipLineQueryBuilder':
        """
        Configura para obtener acumulados por categoria.

        Retorna columnas:
        - contract_id, category_code, rule_code, rule_id
        - total_amount, amount, quantity, rate
        - line_ids (array)
        """
        self.with_category_info()
        self.with_rule_info()
        self.with_states()

        self._select_fields = []  # Reset select
        self.select(
            'HP.contract_id',
            'HSRC.code AS category_code',
            'HSR.code AS rule_code',
            'HSR.id AS rule_id',
        )
        self.select_aggregate('SUM', 'HPL.total', 'total_amount')
        self.select_aggregate('SUM', 'HPL.amount', 'amount')
        self.select_aggregate('SUM', 'HPL.quantity', 'quantity')
        self.select_aggregate('AVG', 'HPL.rate', 'rate')
        self.select_array_agg('HPL.id', 'line_ids')

        self.group_by('HP.contract_id', 'HSRC.code', 'HSR.code', 'HSR.id')
        self.order_by('HP.contract_id', 'HSRC.code', 'HSR.code')

        return self

    def accumulated_by_category_with_leave(self) -> 'PayslipLineQueryBuilder':
        """
        Configura para obtener acumulados por categoria incluyendo info de ausencia.

        Util para calculos de IBD donde se necesita saber el tipo de novedad.
        """
        self.accumulated_by_category()
        self.with_leave_info()

        self.select(
            'MAX(HL.id) AS leave_id',
            'MAX(HLT.novelty) AS leave_novelty',
            'MAX(HLT.liquidacion_value) AS leave_liquidacion_value',
        )

        return self

    def accumulated_by_concept(self, concept_codes: List[str]) -> 'PayslipLineQueryBuilder':
        """
        Configura para obtener acumulados de conceptos especificos.

        Args:
            concept_codes: Lista de codigos de regla (ej: ['PRIMA', 'CES', 'DED_PENS'])
        """
        self.with_rule_info()
        self.with_states()
        self.for_rules(concept_codes)

        self._select_fields = []
        self.select(
            'HP.contract_id',
            'HSR.code AS concept_code',
        )
        self.select_aggregate('SUM', 'HPL.total', 'total')
        self.select_array_agg('HPL.id', 'line_ids')

        self.group_by('HP.contract_id', 'HSR.code')
        self.order_by('HP.contract_id', 'HSR.code')

        return self

    def sum_by_parent_category(self, parent_codes: List[str]) -> 'PayslipLineQueryBuilder':
        """
        Suma totales por categoria padre.

        Args:
            parent_codes: Codigos de categorias padre (ej: ['BASIC', 'DEV_SALARIAL'])
        """
        self.with_category_info()
        self.with_states()

        # Join con categoria padre
        self.left_join('hr_salary_rule_category', 'HSRC_P', 'HSRC_P.id = HSRC.parent_id')

        self._select_fields = []
        self.select(
            'HP.contract_id',
            "COALESCE(HSRC_P.code, HSRC.code) AS parent_code",
        )
        self.select_aggregate('SUM', 'HPL.total', 'total')

        self.where_in('COALESCE(HSRC_P.code, HSRC.code)', parent_codes, 'parent_codes')
        self.group_by('HP.contract_id', 'COALESCE(HSRC_P.code, HSRC.code)')

        return self

    # =========================================================================
    # QUERIES PREDEFINIDAS COMUNES
    # =========================================================================

    @classmethod
    def get_categories_accumulated(
        cls,
        contract_ids: List[int],
        date_from: date,
        date_to: date,
        category_ids: Optional[List[int]] = None,
        exclude_payslip_ids: Optional[List[int]] = None,
        include_leave_info: bool = False,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Query predefinida para obtener acumulados por categoria.

        Equivalente a hr_slip_acumulacion._get_categories_accumulated()

        Args:
            contract_ids: IDs de contratos
            date_from: Fecha inicio
            date_to: Fecha fin
            category_ids: Filtrar por categorias (opcional)
            exclude_payslip_ids: IDs de nominas a excluir
            include_leave_info: Incluir info de ausencia

        Returns:
            (query, params) para ejecutar con cr.execute()
        """
        builder = cls()

        if include_leave_info:
            builder.accumulated_by_category_with_leave()
        else:
            builder.accumulated_by_category()

        builder.for_contracts(contract_ids)
        builder.in_period(date_from, date_to)

        if category_ids:
            builder.for_categories(category_ids)

        if exclude_payslip_ids:
            builder.exclude_payslips(exclude_payslip_ids)

        return builder.build()

    @classmethod
    def get_concepts_accumulated(
        cls,
        contract_id: int,
        date_from: date,
        date_to: date,
        concept_codes: List[str],
        exclude_payslip_ids: Optional[List[int]] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Query predefinida para obtener acumulados de conceptos especificos.

        Args:
            contract_id: ID del contrato
            date_from: Fecha inicio
            date_to: Fecha fin
            concept_codes: Codigos de conceptos a buscar

        Returns:
            (query, params)
        """
        builder = cls()
        builder.accumulated_by_concept(concept_codes)
        builder.for_contract(contract_id)
        builder.in_period(date_from, date_to)

        if exclude_payslip_ids:
            builder.exclude_payslips(exclude_payslip_ids)

        return builder.build()

    @classmethod
    def get_salary_in_leave(
        cls,
        contract_id: int,
        date_from: date,
        date_to: date,
        rule_codes: List[str],
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Query para obtener salario pagado en ausencias.

        Args:
            contract_id: ID del contrato
            date_from: Fecha inicio
            date_to: Fecha fin
            rule_codes: Codigos de reglas de ausencia

        Returns:
            (query, params)
        """
        builder = cls()
        builder.with_rule_info()
        builder.with_states()

        builder.select(
            'HSR.code AS rule_code',
        )
        builder.select_aggregate('SUM', 'HPL.amount', 'amount')

        builder.for_contract(contract_id)
        builder.in_period(date_from, date_to)
        builder.for_rules(rule_codes)

        builder.group_by('HSR.code')

        return builder.build()

    @classmethod
    def get_accumulated_by_category_ids(
        cls,
        contract_ids: List[int],
        date_from: date,
        date_to: date,
        category_ids: List[int],
        exclude_payslip_ids: Optional[List[int]] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Query para obtener totales acumulados por lista de IDs de categoria.

        Util para sumar categorias padre + hijas.

        Args:
            contract_ids: IDs de contratos
            date_from: Fecha inicio
            date_to: Fecha fin
            category_ids: IDs de categorias a incluir
            exclude_payslip_ids: IDs de nominas a excluir

        Returns:
            (query, params) donde el resultado tiene columnas
            (contract_id, total_amount, line_ids)
        """
        builder = cls()
        builder.with_states()

        builder._select_fields = []
        builder.select('HP.contract_id')
        builder.select_aggregate('SUM', 'HPL.total', 'total_amount')
        builder.select_array_agg('HPL.id', 'line_ids')

        builder.for_contracts(contract_ids)
        builder.in_period(date_from, date_to)
        builder.for_categories(category_ids)

        if exclude_payslip_ids:
            builder.exclude_payslips(exclude_payslip_ids)

        builder.group_by('HP.contract_id')

        return builder.build()

    @classmethod
    def get_lines_by_rule_code(
        cls,
        contract_id: int,
        rule_code: str,
        date_from: date,
        date_to: date,
        states: Tuple[str, ...] = VALID_PAYSLIP_STATES,
        limit: Optional[int] = None,
        order_desc: bool = True,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Query para obtener lineas de nomina por codigo de regla.

        Equivalente a _get_payslip_lines_summary_sql() en otros.py

        Args:
            contract_id: ID del contrato
            rule_code: Codigo de la regla salarial (ej: 'IBD')
            date_from: Fecha inicio
            date_to: Fecha fin
            states: Estados validos de nomina
            limit: Limite de registros (opcional)
            order_desc: Ordenar descendente por fecha

        Returns:
            (query, params) donde el resultado tiene columnas
            (id, payslip_id, date_from, date_to, total, amount, quantity, payslip_number)
        """
        builder = cls()
        builder._select_fields = []

        # Agregar join con nomina para obtener numero
        builder.select(
            'HPL.id',
            'HPL.slip_id AS payslip_id',
            'HP.date_from',
            'HP.date_to',
            'HPL.total',
            'HPL.amount',
            'HPL.quantity',
            'HP.number AS payslip_number',
        )

        builder.where_contract(contract_id, 'contract_id', 'HPL')
        builder.with_rule_info()
        builder.where('HSR.code = %(rule_code)s', rule_code=rule_code)
        builder.where_payslip_states(states)
        builder.where('HP.date_from >= %(date_from)s', date_from=date_from)
        builder.where('HP.date_to <= %(date_to)s', date_to=date_to)

        if order_desc:
            builder.order_by('HP.date_to DESC', 'HPL.id DESC')
        else:
            builder.order_by('HP.date_to', 'HPL.id')

        if limit:
            builder.limit(limit)

        return builder.build()

    @classmethod
    def get_compensation_accumulated(
        cls,
        contract_id: int,
        employee_id: int,
        date_from: date,
        date_to: date,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Query para obtener compensacion acumulada (base_compensation=true).

        Equivalente a la query UNION en indemnizacion.py
        Combina hr_payslip_line y hr_accumulated_payroll.

        Args:
            contract_id: ID del contrato
            employee_id: ID del empleado
            date_from: Fecha inicio
            date_to: Fecha fin

        Returns:
            (query, params) donde el resultado tiene columna 'accumulated'
        """
        query = """
            SELECT COALESCE(SUM(accumulated), 0) as accumulated
            FROM (
                SELECT COALESCE(SUM(pl.total), 0) as accumulated
                FROM hr_payslip as hp
                INNER JOIN hr_payslip_line as pl ON hp.id = pl.slip_id
                INNER JOIN hr_salary_rule hc ON pl.salary_rule_id = hc.id
                    AND hc.base_compensation = true
                INNER JOIN hr_salary_rule_category hsc ON hc.category_id = hsc.id
                    AND (hsc.code != 'BASIC' OR hc.code = 'BASICTURNOS')
                WHERE hp.state = 'done'
                    AND hp.contract_id = %(contract_id)s
                    AND (hp.date_from BETWEEN %(date_from)s AND %(date_to)s
                        OR hp.date_to BETWEEN %(date_from)s AND %(date_to)s)

                UNION ALL

                SELECT COALESCE(SUM(pl.amount), 0) as accumulated
                FROM hr_accumulated_payroll as pl
                INNER JOIN hr_salary_rule hc ON pl.salary_rule_id = hc.id
                    AND hc.base_compensation = true
                INNER JOIN hr_salary_rule_category hsc ON hc.category_id = hsc.id
                    AND (hsc.code != 'BASIC' OR hc.code = 'BASICTURNOS')
                WHERE pl.employee_id = %(employee_id)s
                    AND pl.date BETWEEN %(date_from)s AND %(date_to)s
            ) AS A
        """

        params = {
            'contract_id': contract_id,
            'employee_id': employee_id,
            'date_from': date_from,
            'date_to': date_to,
        }

        return query, params
