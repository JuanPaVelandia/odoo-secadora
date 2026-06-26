# -*- coding: utf-8 -*-
"""
Migración 1.17: Unificar campos de auxilio de transporte
=========================================================

Copia datos de skip_commute_allowance a not_pay_auxtransportation
solo si skip_commute_allowance tiene valor True.

El campo skip_commute_allowance será eliminado (ya no existe en el modelo).
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Pre-migración: Copiar datos de campo duplicado antes de que se elimine.

    - skip_commute_allowance (campo eliminado) -> not_pay_auxtransportation (campo principal)
    - Solo copia si skip_commute_allowance = True y not_pay_auxtransportation = False
    """
    if not version:
        return

    _logger.info("=== Migración 1.17: Unificando campos de auxilio de transporte ===")

    # Verificar si el campo antiguo existe en la tabla
    cr.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'hr_contract'
        AND column_name = 'skip_commute_allowance'
    """)

    if not cr.fetchone():
        _logger.info("Campo skip_commute_allowance no existe, saltando migración")
        return

    # Contar registros afectados
    cr.execute("""
        SELECT COUNT(*)
        FROM hr_contract
        WHERE skip_commute_allowance = True
        AND (not_pay_auxtransportation = False OR not_pay_auxtransportation IS NULL)
    """)
    count = cr.fetchone()[0]

    if count == 0:
        _logger.info("No hay contratos con skip_commute_allowance=True para migrar")
        return

    _logger.info(f"Migrando {count} contratos: skip_commute_allowance -> not_pay_auxtransportation")

    # Copiar valor de skip_commute_allowance a not_pay_auxtransportation
    # Solo donde skip_commute_allowance es True y not_pay_auxtransportation no lo es
    cr.execute("""
        UPDATE hr_contract
        SET not_pay_auxtransportation = True
        WHERE skip_commute_allowance = True
        AND (not_pay_auxtransportation = False OR not_pay_auxtransportation IS NULL)
    """)

    _logger.info(f"Migración completada: {count} contratos actualizados")

    # Opcional: Eliminar el campo antiguo (Odoo lo hace automáticamente si no está en el modelo)
    # Pero podemos dejarlo para que Odoo lo maneje
    _logger.info("El campo skip_commute_allowance será eliminado por Odoo al actualizar el módulo")
