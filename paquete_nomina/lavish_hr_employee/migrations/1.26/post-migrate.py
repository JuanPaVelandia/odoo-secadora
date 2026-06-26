# -*- coding: utf-8 -*-
"""
Migración 1.26: Separación de checks base_* para provisión y liquidación.

Inicializa los nuevos checks separados copiando el valor legacy para
mantener comportamiento previo inmediatamente después de actualizar.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    _logger.info("=== INICIO POST-MIGRACIÓN 1.26: base_* provision/liquidacion ===")

    field_pairs = [
        ("base_prima", "base_prima_provision", "base_prima_liquidacion"),
        ("base_cesantias", "base_cesantias_provision", "base_cesantias_liquidacion"),
        (
            "base_intereses_cesantias",
            "base_intereses_cesantias_provision",
            "base_intereses_cesantias_liquidacion",
        ),
        ("base_vacaciones", "base_vacaciones_provision", "base_vacaciones_liquidacion"),
        (
            "base_vacaciones_dinero",
            "base_vacaciones_dinero_provision",
            "base_vacaciones_dinero_liquidacion",
        ),
    ]

    for legacy_field, provision_field, liquidation_field in field_pairs:
        cr.execute(
            f"""
            UPDATE hr_salary_rule
               SET {provision_field} = {legacy_field}
             WHERE {provision_field} IS DISTINCT FROM {legacy_field}
            """
        )
        updated_provision = cr.rowcount

        cr.execute(
            f"""
            UPDATE hr_salary_rule
               SET {liquidation_field} = {legacy_field}
             WHERE {liquidation_field} IS DISTINCT FROM {legacy_field}
            """
        )
        updated_liquidation = cr.rowcount

        _logger.info(
            "[1.26] %s -> %s (%s registros), %s (%s registros)",
            legacy_field,
            provision_field,
            updated_provision,
            liquidation_field,
            updated_liquidation,
        )

    _logger.info("=== FIN POST-MIGRACIÓN 1.26 ===")

