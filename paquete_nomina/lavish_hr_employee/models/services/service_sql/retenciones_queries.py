# -*- coding: utf-8 -*-
"""
Consultas de Retenciones
========================

Builder especializado para consultas de retencion en la fuente.
"""
from typing import List, Dict, Any
from .period_queries import PeriodQueryBuilder


class RetencionesQueryBuilder(PeriodQueryBuilder):
    """
    Builder para consultas de Retenciones en la fuente.

    Filtros:
    - excluir_ret = FALSE
    - Categorias configurables (BASIC, DEV_SALARIAL, etc.)
    - Codigos excluibles

    Uso:
        builder = RetencionesQueryBuilder()
        query, params = (builder
            .for_contract(contract_id)
            .in_period(date_from, date_to)
            .include_categories(['BASIC', 'DEV_SALARIAL', 'HEYREC'])
            .exclude_codes(['PRIMA', 'CES'])
            .build()
        )
    """

    DEFAULT_CATEGORIES = ['BASIC', 'DEV_SALARIAL', 'DEV_NO_SALARIAL', 'HEYREC', 'COMISIONES']

    def __init__(self):
        super().__init__()
        self._include_categories = self.DEFAULT_CATEGORIES.copy()
        self._exclude_codes: List[str] = []

    def include_categories(self, categories: List[str]) -> 'RetencionesQueryBuilder':
        """Categorias a incluir."""
        self._include_categories = categories
        return self

    def exclude_codes(self, codes: List[str]) -> 'RetencionesQueryBuilder':
        """Codigos de reglas a excluir."""
        self._exclude_codes = codes
        return self

    def _get_extra_select_fields(self) -> List[str]:
        return [
            """CASE
                WHEN hsrc.code = 'BASIC' THEN 'basic'
                WHEN hsrc.code IN ('DEV_SALARIAL', 'HEYREC', 'COMISIONES') THEN 'devengos'
                WHEN hsrc.code = 'DEV_NO_SALARIAL' THEN 'dev_no_salarial'
                ELSE 'other'
            END AS data_type"""
        ]

    def _get_type_where_conditions(self) -> List[str]:
        conditions = [
            "(hsr.excluir_ret = FALSE OR hsr.excluir_ret IS NULL)",
        ]

        # Filtro de categorias
        conditions.append(
            """(hsrc.code IN %(include_categories)s
                OR hsrc_parent.code IN %(include_categories)s)"""
        )

        # Filtro de codigos excluidos
        if self._exclude_codes:
            conditions.append("hsr.code NOT IN %(exclude_codes)s")

        return conditions

    def _get_extra_params(self) -> Dict[str, Any]:
        params = {
            'include_categories': tuple(self._include_categories) if self._include_categories else ('',),
        }
        if self._exclude_codes:
            params['exclude_codes'] = tuple(self._exclude_codes)
        return params
