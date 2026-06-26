# -*- coding: utf-8 -*-
"""
Migration 1.30: Convertir item_type Selection a Many2one hr.epp.item.type

Esta migración:
1. Crea la tabla hr_epp_item_type si no existe
2. Agrega columna item_type_id a las tablas que usan item_type
3. Preserva los datos originales en item_type_old para mapeo posterior
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
    'other': None,  # Se manejará como NULL o se asignará manualmente
}


def migrate(cr, version):
    """Pre-migration: Preparar estructura para el nuevo modelo."""
    if not version:
        return

    _logger.info("Migration 1.30: Preparando conversión item_type Selection -> Many2one")

    # 1. Renombrar columna item_type a item_type_old en tablas afectadas
    tables = [
        'hr_epp_configuration_line',
        'hr_epp_request_line',
        'hr_epp_delivery_line',
    ]

    for table in tables:
        # Verificar si la tabla existe
        cr.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = %s
            )
        """, (table,))

        if not cr.fetchone()[0]:
            _logger.info(f"  Tabla {table} no existe, saltando...")
            continue

        # Verificar si la columna item_type existe
        cr.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.columns
                WHERE table_name = %s AND column_name = 'item_type'
            )
        """, (table,))

        if not cr.fetchone()[0]:
            _logger.info(f"  Columna item_type no existe en {table}, saltando...")
            continue

        # Verificar si ya existe item_type_old (migración ya ejecutada)
        cr.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.columns
                WHERE table_name = %s AND column_name = 'item_type_old'
            )
        """, (table,))

        if cr.fetchone()[0]:
            _logger.info(f"  Columna item_type_old ya existe en {table}, saltando...")
            continue

        # Renombrar item_type a item_type_old
        _logger.info(f"  Renombrando item_type -> item_type_old en {table}")
        cr.execute(f"""
            ALTER TABLE {table}
            RENAME COLUMN item_type TO item_type_old
        """)

        # Agregar nueva columna item_type_id (Many2one)
        _logger.info(f"  Agregando columna item_type_id en {table}")
        cr.execute(f"""
            ALTER TABLE {table}
            ADD COLUMN IF NOT EXISTS item_type_id INTEGER
        """)

    _logger.info("Migration 1.30 pre-migrate completada")
