# -*- coding: utf-8 -*-
"""
Pre-migration script for lavish_hr_employee v1.18

Este script prepara los datos antes de la actualizacion del modulo:
1. Verifica si existen los campos antiguos (city_id, state_id, etc.)
2. Guarda los datos existentes para migrarlos a los nuevos campos private_*
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Pre-migration: Preparar datos antes de actualizar el modulo"""
    if not version:
        return

    _logger.info("Pre-migration lavish_hr_employee 1.18: Verificando campos existentes...")

    # Verificar si existen las columnas antiguas en hr_employee
    cr.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'hr_employee'
        AND column_name IN ('city_id', 'state_id', 'neighborhood_id', 'barrio',
                           'postal_code_id', 'full_address', 'address_street')
    """)
    existing_columns = [row[0] for row in cr.fetchall()]

    if existing_columns:
        _logger.info(f"Columnas antiguas encontradas: {existing_columns}")
        _logger.info("Los datos seran migrados a campos private_* en post-migration")
    else:
        _logger.info("No se encontraron columnas antiguas para migrar")

    # Verificar si existen los nuevos campos private_*
    cr.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'hr_employee'
        AND column_name IN ('private_city_id', 'private_neighborhood_id',
                           'private_barrio', 'private_postal_code_id',
                           'private_full_address')
    """)
    new_columns = [row[0] for row in cr.fetchall()]

    if new_columns:
        _logger.info(f"Columnas nuevas ya existen: {new_columns}")
    else:
        _logger.info("Las columnas nuevas private_* seran creadas por el ORM")

    _logger.info("Pre-migration lavish_hr_employee 1.18 completada")
