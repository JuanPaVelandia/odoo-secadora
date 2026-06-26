# -*- coding: utf-8 -*-
"""
Migration 1.0.36 - Convertir campos date y date_end de Date a Datetime

Cambios:
- hr.overtime.date: Date -> Datetime
- hr.overtime.date_end: Date -> Datetime
- Nuevos campos computados: date_only, date_end_only (Date stored)
"""

import logging
from datetime import datetime

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Pre-migration: Convertir columnas de Date a Timestamp.
    La hora se establece a 00:00:00 para date y 23:59:59 para date_end.
    """
    if not version:
        return

    _logger.info("Migracion 1.0.36: Convirtiendo hr_overtime.date y date_end a Datetime...")

    # PRIMERO: Limpiar registros huerfanos para evitar errores de FK
    _logger.info("Limpiando registros huerfanos de payslip_run_id...")
    cr.execute("""
        UPDATE hr_overtime
        SET payslip_run_id = NULL
        WHERE payslip_run_id IS NOT NULL
        AND payslip_run_id NOT IN (SELECT id FROM hr_payslip)
    """)

    # Verificar si las columnas existen y son de tipo date
    cr.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'hr_overtime'
        AND column_name IN ('date', 'date_end')
    """)
    columns = {row[0]: row[1] for row in cr.fetchall()}

    if not columns:
        _logger.info("Tabla hr_overtime no existe o no tiene columnas date/date_end. Saltando migracion.")
        return

    # Convertir 'date' de Date a Timestamp si es necesario
    if columns.get('date') == 'date':
        _logger.info("Convirtiendo columna 'date' de Date a Timestamp...")
        cr.execute("""
            ALTER TABLE hr_overtime
            ALTER COLUMN date TYPE timestamp without time zone
            USING date::timestamp without time zone
        """)
        _logger.info("Columna 'date' convertida exitosamente.")

    # Convertir 'date_end' de Date a Timestamp si es necesario
    if columns.get('date_end') == 'date':
        _logger.info("Convirtiendo columna 'date_end' de Date a Timestamp...")
        # Establecer la hora a 23:59:59 para date_end
        cr.execute("""
            ALTER TABLE hr_overtime
            ALTER COLUMN date_end TYPE timestamp without time zone
            USING (date_end::timestamp without time zone + interval '23 hours 59 minutes 59 seconds')
        """)
        _logger.info("Columna 'date_end' convertida exitosamente.")

    # Agregar columnas date_only y date_end_only si no existen
    cr.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'hr_overtime'
        AND column_name IN ('date_only', 'date_end_only')
    """)
    existing_cols = [row[0] for row in cr.fetchall()]

    if 'date_only' not in existing_cols:
        _logger.info("Creando columna 'date_only'...")
        cr.execute("""
            ALTER TABLE hr_overtime
            ADD COLUMN date_only date
        """)
        # Poblar con datos existentes
        cr.execute("""
            UPDATE hr_overtime
            SET date_only = date::date
            WHERE date IS NOT NULL
        """)
        _logger.info("Columna 'date_only' creada y poblada.")

    if 'date_end_only' not in existing_cols:
        _logger.info("Creando columna 'date_end_only'...")
        cr.execute("""
            ALTER TABLE hr_overtime
            ADD COLUMN date_end_only date
        """)
        # Poblar con datos existentes
        cr.execute("""
            UPDATE hr_overtime
            SET date_end_only = date_end::date
            WHERE date_end IS NOT NULL
        """)
        _logger.info("Columna 'date_end_only' creada y poblada.")

    _logger.info("Migracion 1.0.36 completada exitosamente.")
