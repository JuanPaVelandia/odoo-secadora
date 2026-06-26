# -*- coding: utf-8 -*-
"""
Consultas de IBD (Ingreso Base de Cotizacion)
=============================================

Builder especializado para consultas de IBD (seguridad social).
"""
from typing import List
from .period_queries import PeriodQueryBuilder


class IBDQueryBuilder(PeriodQueryBuilder):
    """
    Builder para consultas de IBD (Ingreso Base de Cotizacion).

    Filtros:
    - base_seguridad_social = TRUE
    - excluir_seguridad_social = FALSE
    - Categorias DEV_SALARIAL o DEV_NO_SALARIAL

    Uso:
        builder = IBDQueryBuilder()
        query, params = (builder
            .for_contract(contract_id)
            .in_period(date_from, date_to)
            .with_leave_info()
            .build()
        )
    """

    def _get_extra_select_fields(self) -> List[str]:
        return [
            """CASE
                WHEN hsrc.code = 'DEV_SALARIAL' OR hsrc_parent.code = 'DEV_SALARIAL'
                THEN 'salary'
                WHEN hsrc.code = 'DEV_NO_SALARIAL' OR hsrc_parent.code = 'DEV_NO_SALARIAL'
                THEN 'no_salary'
                ELSE 'other'
            END AS data_type"""
        ]

    def _get_type_where_conditions(self) -> List[str]:
        return [
            "hsr.base_seguridad_social = TRUE",
            "(hsr.excluir_seguridad_social = FALSE OR hsr.excluir_seguridad_social IS NULL)",
            """(hsrc.code IN ('DEV_SALARIAL', 'DEV_NO_SALARIAL')
                OR hsrc_parent.code IN ('DEV_SALARIAL', 'DEV_NO_SALARIAL'))""",
        ]
