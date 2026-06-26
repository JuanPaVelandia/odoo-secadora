# -*- coding: utf-8 -*-
"""
Migration 1.30: Post-migración para mapear item_type_old a item_type_id

Esta migración:
1. Mapea los valores antiguos de item_type_old a los nuevos registros hr.epp.item.type
2. Elimina la columna item_type_old después del mapeo
"""
import logging

_logger = logging.getLogger(__name__)

# Mapeo de valores Selection antiguos a códigos del nuevo modelo
ITEM_TYPE_MAPPING = {
    # EPP items
    'helmet': 'EPP-HEAD',
    'glasses': 'EPP-EYES',
    'mask': 'EPP-RESP',
    'gloves': 'EPP-HANDS',
    'boots': 'EPP-FEET',
    'vest': 'EPP-BODY',
    # Dotación items
    'shirt': 'DOT-UPPER',
    'pants': 'DOT-LOWER',
    'shoes': 'DOT-FOOT',
    'other': None,
}


def migrate(cr, version):
    """Post-migration: Mapear valores antiguos al nuevo modelo."""
    if not version:
        return

    _logger.info("Migration 1.30: Mapeando item_type_old -> item_type_id")

    # Salir si la tabla del nuevo modelo aun no existe (caso primera instalacion v19)
    cr.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'hr_epp_item_type'
        )
    """)
    if not cr.fetchone()[0]:
        _logger.info("  Tabla hr_epp_item_type aun no existe; saltando migracion 1.30")
        return

    # Obtener IDs de los tipos por código
    cr.execute("""
        SELECT id, code FROM hr_epp_item_type WHERE code IS NOT NULL
    """)
    type_by_code = {row[1]: row[0] for row in cr.fetchall()}

    if not type_by_code:
        _logger.warning("  No se encontraron tipos en hr_epp_item_type, saltando mapeo...")
        return

    # Tablas a migrar
    tables = [
        'hr_epp_configuration_line',
        'hr_epp_request_line',
        'hr_epp_delivery_line',
    ]

    for table in tables:
        # Verificar si la tabla existe y tiene la columna item_type_old
        cr.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.columns
                WHERE table_name = %s AND column_name = 'item_type_old'
            )
        """, (table,))

        if not cr.fetchone()[0]:
            _logger.info(f"  Columna item_type_old no existe en {table}, saltando...")
            continue

        # Mapear cada valor antiguo al nuevo
        mapped_count = 0
        for old_value, new_code in ITEM_TYPE_MAPPING.items():
            if new_code and new_code in type_by_code:
                type_id = type_by_code[new_code]
                cr.execute(f"""
                    UPDATE {table}
                    SET item_type_id = %s
                    WHERE item_type_old = %s AND item_type_id IS NULL
                """, (type_id, old_value))
                mapped_count += cr.rowcount

        _logger.info(f"  {table}: {mapped_count} registros mapeados")

        # Opcional: Eliminar columna item_type_old después del mapeo
        # Comentado por seguridad - descomentar si se desea eliminar
        # cr.execute(f"""
        #     ALTER TABLE {table}
        #     DROP COLUMN IF EXISTS item_type_old
        # """)
        # _logger.info(f"  Columna item_type_old eliminada de {table}")

    _logger.info("Migration 1.30 post-migrate completada")
