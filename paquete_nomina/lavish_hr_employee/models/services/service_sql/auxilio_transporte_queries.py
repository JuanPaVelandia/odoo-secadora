# -*- coding: utf-8 -*-
"""
Consultas de Auxilio de Transporte
==================================

Builder especializado para consultas de auxilio de transporte.
"""
from typing import List
from .period_queries import PeriodQueryBuilder


class AuxilioTransporteQueryBuilder(PeriodQueryBuilder):
    """
    Builder para consultas de Auxilio de Transporte.

    Dos modos:
    - Tope: Devengos que hacen base para el tope de 2 SMMLV
        * Excluye: BASIC y reglas con excluir_auxtransporte_tope=True
        * Incluye: DEV_SALARIAL o base_auxtransporte_tope=True (según solo_marcadas)
    - Pagado: Valores de auxilio pagados (para promedio en prestaciones)
        * Incluye: Categoria AUX (o parent AUX) o es_auxilio_transporte=True
        * Opcional: BASIC (si include_basic=True)

    Uso:
        # Para tope
        builder = AuxilioTransporteQueryBuilder()
        query, params = (builder
            .for_contract(contract_id)
            .in_period(date_from, date_to)
            .mode_tope()
            .build()
        )

        # Para auxilio pagado
        builder = AuxilioTransporteQueryBuilder()
        query, params = (builder
            .for_contract(contract_id)
            .in_period(date_from, date_to)
            .mode_pagado()
            .build()
        )
    """

    def __init__(self):
        super().__init__()
        self._mode = 'tope'  # 'tope' o 'pagado'
        self._solo_marcadas = False
        self._include_basic = False

    def mode_tope(self, solo_marcadas: bool = False) -> 'AuxilioTransporteQueryBuilder':
        """Modo tope: devengos que hacen base para el tope."""
        self._mode = 'tope'
        self._solo_marcadas = solo_marcadas
        return self

    def mode_pagado(self, include_basic: bool = False) -> 'AuxilioTransporteQueryBuilder':
        """
        Modo pagado: valores de auxilio pagados.

        Args:
            include_basic: Si True, incluye categoría BASIC en el filtro.
                          Si False, solo usa categoría AUX + bool es_auxilio_transporte.
                          Default False para usar solo categoria y bool (prestaciones).
        """
        self._mode = 'pagado'
        self._include_basic = include_basic
        return self

    def _get_extra_select_fields(self) -> List[str]:
        if self._mode == 'tope':
            return []  # No necesita campos extra
        else:  # pagado
            return [
                "hsrc_parent.code AS parent_category_code",
                """CASE
                    WHEN hsrc.code = 'AUX' OR hsrc_parent.code = 'AUX' THEN 'auxilio'
                    WHEN hsr.es_auxilio_transporte = TRUE THEN 'auxilio'
                    WHEN hsrc.code = 'BASIC' THEN 'basic'
                    ELSE 'other'
                END AS tipo_concepto""",
                """CASE WHEN EXTRACT(DAY FROM pbp.date_to) <= 15 THEN 1 ELSE 2 END AS quincena""",
            ]

    def _get_type_where_conditions(self) -> List[str]:
        if self._mode == 'tope':
            conditions = [
                "hsr.code != 'BASIC'",
                "(hsr.excluir_auxtransporte_tope = FALSE OR hsr.excluir_auxtransporte_tope IS NULL)",
            ]

            if self._solo_marcadas:
                conditions.append("hsr.base_auxtransporte_tope = TRUE")
            else:
                conditions.append(
                    """(hsrc.code = 'DEV_SALARIAL'
                        OR hsrc_parent.code = 'DEV_SALARIAL'
                        OR hsr.base_auxtransporte_tope = TRUE)"""
                )
            return conditions

        else:  # pagado
            # Solo categoria AUX + bool es_auxilio_transporte
            conditions = [
                """(hsrc.code = 'AUX' OR hsrc_parent.code = 'AUX'
                    OR hsr.es_auxilio_transporte = TRUE""",
            ]

            # BASIC solo si se solicita explícitamente
            if self._include_basic:
                conditions[0] += " OR hsrc.code = 'BASIC')"
            else:
                conditions[0] += ")"

            return conditions
