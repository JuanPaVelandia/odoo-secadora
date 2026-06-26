# -*- coding: utf-8 -*-
"""
Consultas de Periodo para Nomina - Clase Base
==============================================

Builder base para consultas de periodo con filtros dinamicos.

Las implementaciones especificas estan en archivos separados:
- ibd_queries.py: IBDQueryBuilder (seguridad social)
- retenciones_queries.py: RetencionesQueryBuilder (retencion en la fuente)
- prestaciones_queries.py: PrestacionesQueryBuilder (prestaciones sociales)
- auxilio_transporte_queries.py: AuxilioTransporteQueryBuilder
- leave_period_queries.py: LeavePeriodQueryBuilder (ausencias por periodo)
"""
from typing import List, Dict, Any, Tuple
from datetime import date
from .base_query_builder import SQLQueryBuilder
from .field_sets import VALID_PAYSLIP_STATES, VALID_LEAVE_STATES


class PeriodQueryBuilder(SQLQueryBuilder):
    """
    Builder base para consultas de periodo de nomina.

    Configura la estructura comun:
    - CTEs para payslips y ausencias
    - Joins con reglas y categorias
    - Campos base de linea de nomina

    Esta es una clase base. Usar las implementaciones especificas:
    - IBDQueryBuilder para consultas de seguridad social
    - RetencionesQueryBuilder para consultas de retencion
    - PrestacionesQueryBuilder para consultas de prestaciones
    - AuxilioTransporteQueryBuilder para auxilio de transporte
    - LeavePeriodQueryBuilder para ausencias por periodo
    """

    def __init__(self):
        super().__init__()
        self._include_leave_cte = False
        self._contract_id = None
        self._date_from = None
        self._date_to = None
        self._exclude_payslip_id = None
        self._states = VALID_PAYSLIP_STATES
        self._leave_states = VALID_LEAVE_STATES

    def for_contract(self, contract_id: int) -> 'PeriodQueryBuilder':
        """Filtrar por contrato."""
        self._contract_id = contract_id
        return self

    def in_period(self, date_from: date, date_to: date) -> 'PeriodQueryBuilder':
        """Definir periodo de consulta."""
        self._date_from = date_from
        self._date_to = date_to
        return self

    def exclude_payslip(self, payslip_id: int) -> 'PeriodQueryBuilder':
        """Excluir nomina especifica (ej: la actual)."""
        self._exclude_payslip_id = payslip_id
        return self

    def with_states(self, states: Tuple[str, ...]) -> 'PeriodQueryBuilder':
        """Estados de nomina a incluir."""
        self._states = states
        return self

    def with_leave_info(self) -> 'PeriodQueryBuilder':
        """Incluir CTE de ausencias del periodo."""
        self._include_leave_cte = True
        return self

    def _build_payslip_cte(self) -> str:
        """CTE de nominas del periodo (busca solapamiento, no contencion)."""
        return """
        payslips_by_period AS (
            SELECT
                hp.id AS payslip_id,
                hp.number AS payslip_number,
                hp.date_from,
                hp.date_to,
                TO_CHAR(hp.date_from, 'YYYY-MM') AS period_key,
                EXTRACT(YEAR FROM hp.date_from) AS year,
                EXTRACT(MONTH FROM hp.date_from) AS month
            FROM hr_payslip hp
            WHERE hp.contract_id = %(contract_id)s
              AND hp.state IN %(states)s
              AND hp.date_from <= %(date_to)s
              AND hp.date_to >= %(date_from)s
              AND (hp.id != %(exclude_payslip_id)s OR %(exclude_payslip_id)s = 0)
        )"""

    def _build_leave_cte(self) -> str:
        """CTEs de ausencias del periodo."""
        return """
        leaves_current_period AS (
            SELECT
                hll.id AS leave_line_id,
                hll.leave_id,
                hll.date,
                TO_CHAR(hll.date, 'YYYY-MM') AS period_key,
                hl.contract_id
            FROM hr_leave_line hll
            INNER JOIN hr_leave hl ON hl.id = hll.leave_id
            WHERE hl.contract_id = %(contract_id)s
              AND hl.state = 'validate'
              AND hll.state IN %(leave_states)s
              AND hll.date BETWEEN %(date_from)s AND %(date_to)s
        ),
        leaves_by_period_agg AS (
            SELECT
                period_key,
                ARRAY_AGG(leave_line_id) AS leave_line_ids,
                ARRAY_AGG(DISTINCT leave_id) AS leave_ids
            FROM leaves_current_period
            GROUP BY period_key
        )"""

    def _get_base_select_fields(self) -> List[str]:
        """Campos SELECT base."""
        fields = [
            "hpl.id AS line_id",
            "hpl.slip_id AS payslip_id",
            "pbp.payslip_number",
            "hpl.date_from",
            "hpl.date_to",
            "hsr.code AS rule_code_full",
            "COALESCE(hsr.name->>'es_CO', hsr.name->>'en_US', hsr.code) AS rule_name",
            "hsrc.code AS category_code",
            "COALESCE(hsrc.name->>'es_CO', hsrc.name->>'en_US', hsrc.code) AS category_name",
            "hpl.total",
            "hpl.amount",
            "hpl.quantity",
            "pbp.period_key",
            "pbp.year",
            "pbp.month",
            "'payslip' AS source_type",
        ]

        if self._include_leave_cte:
            fields.extend([
                "COALESCE(lpa.leave_line_ids, ARRAY[]::int[]) AS leave_line_ids",
                "COALESCE(lpa.leave_ids, ARRAY[]::int[]) AS leave_ids",
            ])

        return fields

    def _get_extra_select_fields(self) -> List[str]:
        """Campos SELECT adicionales segun tipo. Override en subclases."""
        return []

    def _get_type_where_conditions(self) -> List[str]:
        """Condiciones WHERE segun tipo. Override en subclases."""
        return []

    def _get_base_params(self) -> Dict[str, Any]:
        """Parametros base."""
        return {
            'contract_id': self._contract_id,
            'date_from': self._date_from,
            'date_to': self._date_to,
            'exclude_payslip_id': self._exclude_payslip_id or 0,
            'states': self._states,
            'leave_states': self._leave_states,
        }

    def _get_extra_params(self) -> Dict[str, Any]:
        """Parametros adicionales segun tipo. Override en subclases."""
        return {}

    def build(self) -> Tuple[str, Dict[str, Any]]:
        """Construir query y parametros."""
        # Validar parametros requeridos
        if not self._contract_id:
            raise ValueError("contract_id es requerido. Usa .for_contract()")
        if not self._date_from or not self._date_to:
            raise ValueError("Periodo requerido. Usa .in_period()")

        # Construir CTEs
        ctes = [self._build_payslip_cte()]
        if self._include_leave_cte:
            ctes.append(self._build_leave_cte())

        # Construir SELECT
        select_fields = self._get_base_select_fields() + self._get_extra_select_fields()

        # Construir FROM y JOINs
        from_clause = """
        FROM hr_payslip_line hpl
        INNER JOIN payslips_by_period pbp ON pbp.payslip_id = hpl.slip_id
        INNER JOIN hr_salary_rule hsr ON hsr.id = hpl.salary_rule_id
        INNER JOIN hr_salary_rule_category hsrc ON hsrc.id = hpl.category_id
        LEFT JOIN hr_salary_rule_category hsrc_parent ON hsrc.parent_id = hsrc_parent.id"""

        if self._include_leave_cte:
            from_clause += """
        LEFT JOIN leaves_by_period_agg lpa ON lpa.period_key = pbp.period_key"""

        # Construir WHERE
        where_conditions = ["hpl.total > 0"] + self._get_type_where_conditions()

        # Construir query completa
        query = f"""
        WITH
        {','.join(ctes)}
        SELECT
            {','.join(select_fields)}
        {from_clause}
        WHERE {' AND '.join(where_conditions)}
        ORDER BY pbp.period_key, hpl.date_from, hsrc.code, hsr.code
        """

        # Construir parametros
        params = {**self._get_base_params(), **self._get_extra_params()}

        return query, params
