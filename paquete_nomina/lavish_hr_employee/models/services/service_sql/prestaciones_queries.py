# -*- coding: utf-8 -*-
"""
Consultas de Prestaciones
=========================

Builder especializado para consultas de prestaciones sociales.
"""
from typing import List, Dict, Any
from .period_queries import PeriodQueryBuilder


class PrestacionesQueryBuilder(PeriodQueryBuilder):
    """
    Builder para consultas de Prestaciones sociales.

    Filtros:
    - base_prima, base_cesantias, base_vacaciones, etc.
    - Categorias excluibles

    Uso:
        builder = PrestacionesQueryBuilder()
        query, params = (builder
            .for_contract(contract_id)
            .in_period(date_from, date_to)
            .tipo_prestacion('prima')
            .exclude_categories(['BASIC', 'DED', 'PROV'])
            .build()
        )
    """

    DEFAULT_EXCLUDED_CATEGORIES = ['BASIC', 'DED', 'PROV', 'SSOCIAL', 'PRESTACIONES_SOCIALES', 'NET']

    BASE_FIELD_MAP = {
        'prima': 'base_prima',
        'cesantias': 'base_cesantias',
        'vacaciones': 'base_vacaciones',
        'vacaciones_dinero': 'base_vacaciones_dinero',
        'intereses_cesantias': 'base_intereses_cesantias',
    }

    def __init__(self):
        super().__init__()
        self._tipo_prestacion = 'all'
        self._excluded_categories = self.DEFAULT_EXCLUDED_CATEGORIES.copy()

    def tipo_prestacion(self, tipo: str) -> 'PrestacionesQueryBuilder':
        """Tipo de prestacion: 'prima', 'cesantias', 'vacaciones', 'intereses_cesantias', 'all'."""
        self._tipo_prestacion = tipo
        return self

    def exclude_categories(self, categories: List[str]) -> 'PrestacionesQueryBuilder':
        """Categorias a excluir."""
        self._excluded_categories = categories
        return self

    def _get_extra_select_fields(self) -> List[str]:
        return [
            """CASE
                WHEN hsr.base_prima THEN 'base_prima'
                WHEN hsr.base_cesantias THEN 'base_cesantias'
                WHEN hsr.base_vacaciones THEN 'base_vacaciones'
                WHEN hsr.base_vacaciones_dinero THEN 'base_vacaciones_dinero'
                WHEN hsr.base_intereses_cesantias THEN 'base_intereses_cesantias'
                ELSE NULL
            END AS base_field""",
            """CASE
                WHEN hsrc.code = 'BASIC' THEN 'basic'
                ELSE 'variable'
            END AS data_type""",
            # Campo para identificar auxilio de transporte
            "COALESCE(hsr.es_auxilio_transporte, FALSE) AS es_auxilio_transporte",
        ]

    def _get_type_where_conditions(self) -> List[str]:
        conditions = []

        # Filtro de base segun tipo_prestacion
        if self._tipo_prestacion == 'all':
            conditions.append(
                """(hsr.base_prima = TRUE OR hsr.base_cesantias = TRUE
                    OR hsr.base_vacaciones = TRUE OR hsr.base_vacaciones_dinero = TRUE
                    OR hsr.base_intereses_cesantias = TRUE)"""
            )
        else:
            base_field = self.BASE_FIELD_MAP.get(self._tipo_prestacion, 'base_prima')
            conditions.append(f"hsr.{base_field} = TRUE")

        # Filtro de categorias excluidas
        if self._excluded_categories:
            conditions.append("hsrc.code NOT IN %(excluded_categories)s")

        return conditions

    def _get_extra_params(self) -> Dict[str, Any]:
        params = {}
        if self._excluded_categories:
            params['excluded_categories'] = tuple(self._excluded_categories)
        return params
