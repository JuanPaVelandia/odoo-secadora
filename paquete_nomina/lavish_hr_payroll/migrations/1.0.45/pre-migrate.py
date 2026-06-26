# -*- coding: utf-8 -*-
"""
Migration 1.0.45 - Reorganizacion de imports y estructura de modulos

Cambios:
- Reorganizacion de imports para corregir dependencias circulares
- Exports de clases generadoras en rule_generators/__init__.py
- Correccion de paths de imports internos
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Pre-migration: Reorganizacion de estructura de modulos.

    Esta migracion no requiere cambios en base de datos,
    solo reorganizacion de codigo Python que se aplica al
    actualizar el modulo.
    """
    if not version:
        return

    _logger.info("Migracion 1.0.45: Reorganizacion de imports y estructura")
    _logger.info("- Correccion de imports circulares en rule_generators")
    _logger.info("- Correccion de paths de imports en novedades/hr_period.py")
    _logger.info("- Correccion de paths de imports en nomina/hr_slip.py")
    _logger.info("Migracion 1.0.45 completada exitosamente.")
