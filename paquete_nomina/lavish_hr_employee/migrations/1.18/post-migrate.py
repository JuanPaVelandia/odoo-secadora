# -*- coding: utf-8 -*-
"""
Post-migration script for lavish_hr_employee v1.18

Este script migra los datos despues de la actualizacion del modulo:
1. Migra datos de campos antiguos (city_id, etc.) a nuevos campos private_*
2. Sincroniza campos private_* con work_contact_id si existe
3. Establece valores por defecto para pais y tipo de documento
"""
import logging

_logger = logging.getLogger(__name__)


def _column_exists(cr, table_name, column_name):
    cr.execute("""
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = %s
          AND column_name = %s
        LIMIT 1
    """, (table_name, column_name))
    return bool(cr.fetchone())


def migrate(cr, version):
    """Post-migration: Migrar datos a nuevos campos private_*"""
    if not version:
        return

    _logger.info("Post-migration lavish_hr_employee 1.18: Migrando datos a campos private_*...")

    # 1. Migrar city_id a private_city_id si existe la columna antigua
    cr.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'hr_employee'
        AND column_name = 'city_id'
    """)
    if cr.fetchone():
        _logger.info("Migrando city_id a private_city_id...")
        cr.execute("""
            UPDATE hr_employee
            SET private_city_id = city_id
            WHERE city_id IS NOT NULL
            AND (private_city_id IS NULL OR private_city_id != city_id)
        """)
        migrated = cr.rowcount
        _logger.info(f"  - {migrated} registros migrados de city_id a private_city_id")

        # Actualizar private_city (Char) desde city_id
        cr.execute("""
            UPDATE hr_employee e
            SET private_city = c.name
            FROM res_city c
            WHERE e.city_id = c.id
            AND e.city_id IS NOT NULL
            AND (e.private_city IS NULL OR e.private_city = '')
        """)
        _logger.info(f"  - {cr.rowcount} registros actualizados en private_city")

    # 2. Migrar state_id a private_state_id
    cr.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'hr_employee'
        AND column_name = 'state_id'
    """)
    if cr.fetchone():
        _logger.info("Verificando sincronizacion de state_id con private_state_id...")
        cr.execute("""
            UPDATE hr_employee
            SET private_state_id = state_id
            WHERE state_id IS NOT NULL
            AND (private_state_id IS NULL OR private_state_id != state_id)
        """)
        _logger.info(f"  - {cr.rowcount} registros sincronizados")

    # 3. Migrar neighborhood_id a private_neighborhood_id si existe
    cr.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'hr_employee'
        AND column_name = 'neighborhood_id'
    """)
    if cr.fetchone():
        _logger.info("Migrando neighborhood_id a private_neighborhood_id...")
        cr.execute("""
            UPDATE hr_employee
            SET private_neighborhood_id = neighborhood_id
            WHERE neighborhood_id IS NOT NULL
            AND (private_neighborhood_id IS NULL OR private_neighborhood_id != neighborhood_id)
        """)
        _logger.info(f"  - {cr.rowcount} registros migrados")

    # 4. Migrar barrio a private_barrio si existe
    cr.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'hr_employee'
        AND column_name = 'barrio'
    """)
    if cr.fetchone():
        _logger.info("Migrando barrio a private_barrio...")
        cr.execute("""
            UPDATE hr_employee
            SET private_barrio = barrio
            WHERE barrio IS NOT NULL AND barrio != ''
            AND (private_barrio IS NULL OR private_barrio = '')
        """)
        _logger.info(f"  - {cr.rowcount} registros migrados")

    # 5. Migrar postal_code_id a private_postal_code_id si existe
    cr.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'hr_employee'
        AND column_name = 'postal_code_id'
    """)
    if cr.fetchone():
        _logger.info("Migrando postal_code_id a private_postal_code_id...")
        cr.execute("""
            UPDATE hr_employee
            SET private_postal_code_id = postal_code_id
            WHERE postal_code_id IS NOT NULL
            AND (private_postal_code_id IS NULL OR private_postal_code_id != postal_code_id)
        """)
        _logger.info(f"  - {cr.rowcount} registros migrados")

    # 6. Migrar full_address a private_full_address si existe
    cr.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'hr_employee'
        AND column_name = 'full_address'
    """)
    if cr.fetchone():
        _logger.info("Migrando full_address a private_full_address...")
        cr.execute("""
            UPDATE hr_employee
            SET private_full_address = full_address
            WHERE full_address IS NOT NULL AND full_address != ''
            AND (private_full_address IS NULL OR private_full_address = '')
        """)
        _logger.info(f"  - {cr.rowcount} registros migrados")

    # 7. Migrar address_street a private_street si existe
    cr.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'hr_employee'
        AND column_name = 'address_street'
    """)
    if cr.fetchone():
        _logger.info("Migrando address_street a private_street...")
        cr.execute("""
            UPDATE hr_employee
            SET private_street = address_street
            WHERE address_street IS NOT NULL AND address_street != ''
            AND (private_street IS NULL OR private_street = '')
        """)
        _logger.info(f"  - {cr.rowcount} registros migrados")

    # 8. Sincronizar desde work_contact_id para empleados sin datos private_*
    _logger.info("Sincronizando campos private_* desde work_contact_id...")

    # Sincronizar private_city_id desde partner.city_id
    if _column_exists(cr, 'hr_employee', 'private_city_id') and _column_exists(cr, 'res_partner', 'city_id'):
        cr.execute("""
            UPDATE hr_employee e
            SET private_city_id = p.city_id
            FROM res_partner p
            WHERE e.work_contact_id = p.id
            AND p.city_id IS NOT NULL
            AND e.private_city_id IS NULL
        """)
        _logger.info(f"  - {cr.rowcount} ciudades sincronizadas desde partner")
    else:
        _logger.info("  - Omitido: no existe private_city_id en hr_employee o city_id en res_partner")

    # Sincronizar private_state_id desde partner.state_id
    if _column_exists(cr, 'hr_employee', 'private_state_id') and _column_exists(cr, 'res_partner', 'state_id'):
        cr.execute("""
            UPDATE hr_employee e
            SET private_state_id = p.state_id
            FROM res_partner p
            WHERE e.work_contact_id = p.id
            AND p.state_id IS NOT NULL
            AND e.private_state_id IS NULL
        """)
        _logger.info(f"  - {cr.rowcount} departamentos sincronizados desde partner")
    else:
        _logger.info("  - Omitido: no existe private_state_id en hr_employee o state_id en res_partner")

    # Sincronizar private_country_id desde partner.country_id
    if _column_exists(cr, 'hr_employee', 'private_country_id') and _column_exists(cr, 'res_partner', 'country_id'):
        cr.execute("""
            UPDATE hr_employee e
            SET private_country_id = p.country_id
            FROM res_partner p
            WHERE e.work_contact_id = p.id
            AND p.country_id IS NOT NULL
            AND e.private_country_id IS NULL
        """)
        _logger.info(f"  - {cr.rowcount} paises sincronizados desde partner")
    else:
        _logger.info("  - Omitido: no existe private_country_id en hr_employee o country_id en res_partner")

    # 9. Establecer pais por defecto (Colombia) donde este vacio
    _logger.info("Estableciendo pais por defecto para empleados sin pais...")
    if _column_exists(cr, 'hr_employee', 'private_country_id'):
        cr.execute("""
            UPDATE hr_employee e
            SET private_country_id = (SELECT id FROM res_country WHERE code = 'CO' LIMIT 1)
            WHERE e.private_country_id IS NULL
            AND EXISTS (SELECT 1 FROM res_country WHERE code = 'CO')
        """)
        _logger.info(f"  - {cr.rowcount} empleados actualizados con pais Colombia")
    else:
        _logger.info("  - Omitido: no existe private_country_id en hr_employee")

    # 10. Limpiar columnas antiguas si ya no se usan (opcional - comentado por seguridad)
    # Descomentar solo si se confirma que los datos fueron migrados correctamente
    # _logger.info("Limpiando columnas antiguas...")
    # columns_to_drop = ['city_id', 'state_id', 'neighborhood_id', 'barrio',
    #                   'postal_code_id', 'full_address', 'address_street']
    # for col in columns_to_drop:
    #     try:
    #         cr.execute(f"ALTER TABLE hr_employee DROP COLUMN IF EXISTS {col}")
    #         _logger.info(f"  - Columna {col} eliminada")
    #     except Exception as e:
    #         _logger.warning(f"  - No se pudo eliminar columna {col}: {e}")

    _logger.info("Post-migration lavish_hr_employee 1.18 completada exitosamente")
