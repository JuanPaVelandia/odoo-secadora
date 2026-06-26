# -*- coding: utf-8 -*-
"""
Migracion 1.12: Mapear contract_type a contract_type_id
========================================================
Migra los valores del campo Selection contract_type al campo
relacional contract_type_id usando los tipos de contrato colombianos.

Esta migracion asegura que todos los contratos usen tipos
de contrato de Colombia (Ley 2466/2025).
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Pre-migracion: Mapear contract_type (Selection) a contract_type_id (Many2one)
    priorizando tipos de contrato colombianos.
    """
    _logger.info("=== INICIO PRE-MIGRACION 1.12: Mapear a tipos de contrato colombianos ===")

    # Obtener el ID de Colombia
    cr.execute("SELECT id FROM res_country WHERE code = 'CO' LIMIT 1")
    result = cr.fetchone()
    country_co = result[0] if result else None
    _logger.info(f"ID de Colombia: {country_co}")

    # Mapeo de contract_type (selection) a codigo de hr.contract.type colombiano
    mapping = {
        'obra': 'OBRA',
        'fijo': 'FIJO',
        'fijo_parcial': 'FIJO_PARCIAL',
        'indefinido': 'INDEFINIDO',
        'aprendizaje': 'APRENDIZAJE',
        'temporal': 'OCASIONAL',
        'agropecuario': 'AGROPECUARIO',
    }

    # Primero: Obtener el tipo INDEFINIDO colombiano como default
    cr.execute("""
        SELECT id FROM hr_contract_type
        WHERE code = 'INDEFINIDO' AND country_id = %s
        LIMIT 1
    """, (country_co,))
    result = cr.fetchone()
    default_type_id = result[0] if result else None
    _logger.info(f"Tipo INDEFINIDO colombiano ID: {default_type_id}")

    total_updated = 0

    # Paso 1: Migrar segun el campo contract_type (selection)
    for old_type, new_code in mapping.items():
        # Buscar tipo colombiano primero
        cr.execute("""
            SELECT id FROM hr_contract_type
            WHERE code = %s AND country_id = %s
            LIMIT 1
        """, (new_code, country_co))
        result = cr.fetchone()

        if result:
            new_type_id = result[0]
            # Actualizar contratos que tienen este contract_type
            cr.execute("""
                UPDATE hr_contract
                SET contract_type_id = %s
                WHERE contract_type = %s
            """, (new_type_id, old_type))

            updated = cr.rowcount
            total_updated += updated
            if updated > 0:
                _logger.info(
                    f"Migrados {updated} contratos '{old_type}' -> "
                    f"'{new_code}' (ID: {new_type_id})"
                )
        else:
            _logger.warning(f"No existe hr.contract.type '{new_code}' para Colombia")

    # Paso 2: Contratos con tipos no colombianos -> asignar tipo colombiano equivalente
    if default_type_id:
        cr.execute("""
            UPDATE hr_contract c
            SET contract_type_id = %s
            WHERE c.contract_type_id IN (
                SELECT id FROM hr_contract_type
                WHERE country_id IS NULL OR country_id != %s
            )
        """, (default_type_id, country_co))
        updated = cr.rowcount
        if updated > 0:
            total_updated += updated
            _logger.info(f"Migrados {updated} contratos con tipos no colombianos a INDEFINIDO")

    # Paso 3: Contratos sin contract_type_id -> asignar INDEFINIDO
    if default_type_id:
        cr.execute("""
            UPDATE hr_contract
            SET contract_type_id = %s
            WHERE contract_type_id IS NULL
        """, (default_type_id,))
        updated = cr.rowcount
        if updated > 0:
            total_updated += updated
            _logger.info(f"Asignado INDEFINIDO a {updated} contratos sin tipo")

    # Paso 4: Actualizar campo computado contract_type
    # Verificar si la columna contract_category existe en hr_contract_type
    cr.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name='hr_contract_type'
        AND column_name='contract_category'
    """)
    has_contract_category = cr.fetchone() is not None

    if has_contract_category:
        cr.execute("""
            UPDATE hr_contract c
            SET contract_type =
                CASE ct.contract_category
                    WHEN 'obra' THEN 'obra'
                    WHEN 'fijo' THEN 'fijo'
                    WHEN 'indefinido' THEN 'indefinido'
                    WHEN 'aprendizaje' THEN 'aprendizaje'
                    WHEN 'ocasional' THEN 'temporal'
                    WHEN 'agropecuario' THEN 'agropecuario'
                    ELSE 'indefinido'
                END
            FROM hr_contract_type ct
            WHERE c.contract_type_id = ct.id
            AND ct.contract_category IS NOT NULL
        """)
        _logger.info(f"Actualizado campo contract_type para {cr.rowcount} contratos")
    else:
        _logger.warning("La columna contract_category no existe en hr_contract_type, saltando paso 4")

    _logger.info(f"Total de contratos migrados: {total_updated}")
    _logger.info("=== FIN PRE-MIGRACION 1.12 ===")
