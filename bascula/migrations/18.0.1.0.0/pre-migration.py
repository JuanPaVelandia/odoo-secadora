# -*- coding: utf-8 -*-
"""
Pre-migración para agregar campo tipo_servicio_id a órdenes de servicio existentes
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Migración para cambiar tipo_servicio (Selection) a tipo_servicio_id (Many2one)

    Pasos:
    1. Crear columna tipo_servicio_id
    2. Mapear valores antiguos a IDs de secadora.tipo.operacion
    3. El campo tipo_servicio se convierte en computed (se maneja en el modelo)
    """

    _logger.info("="*80)
    _logger.info("Iniciando migración: tipo_servicio -> tipo_servicio_id")
    _logger.info("="*80)

    # 1. Verificar si la columna ya existe
    cr.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name='secadora_orden_servicio'
        AND column_name='tipo_servicio_id'
    """)

    if cr.fetchone():
        _logger.info("La columna tipo_servicio_id ya existe, saltando migración")
        return

    # 2. Agregar columna tipo_servicio_id
    _logger.info("Agregando columna tipo_servicio_id...")
    cr.execute("""
        ALTER TABLE secadora_orden_servicio
        ADD COLUMN tipo_servicio_id INTEGER
    """)

    # 3. Obtener IDs de tipos de operación
    _logger.info("Obteniendo IDs de tipos de operación...")

    # Buscar por código (más confiable que external ID)
    tipo_ops = {}
    cr.execute("""
        SELECT id, codigo
        FROM secadora_tipo_operacion
        WHERE codigo IN ('SECAMIENTO', 'PRELIMPIEZA', 'SEC_PRELIM')
    """)
    for row in cr.fetchall():
        tipo_ops[row[1]] = row[0]

    _logger.info(f"Tipos de operación encontrados: {tipo_ops}")

    # 4. Mapear valores antiguos a nuevos IDs
    mapeo = {
        'secamiento': tipo_ops.get('SECAMIENTO'),
        'prelimpieza': tipo_ops.get('PRELIMPIEZA'),
        'secamiento_prelimpieza': tipo_ops.get('SEC_PRELIM'),
    }

    # 5. Actualizar registros existentes
    _logger.info("Actualizando registros existentes...")

    # Verificar si tipo_servicio todavía es columna (no computed)
    cr.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name='secadora_orden_servicio'
        AND column_name='tipo_servicio'
    """)

    if cr.fetchone():
        for valor_antiguo, tipo_id in mapeo.items():
            if tipo_id:
                cr.execute("""
                    UPDATE secadora_orden_servicio
                    SET tipo_servicio_id = %s
                    WHERE tipo_servicio = %s
                """, (tipo_id, valor_antiguo))
                count = cr.rowcount
                _logger.info(f"  - Actualizados {count} registros de '{valor_antiguo}' -> tipo_id {tipo_id}")

    # 6. Para registros sin tipo_servicio, usar SECAMIENTO por defecto
    if tipo_ops.get('SECAMIENTO'):
        cr.execute("""
            UPDATE secadora_orden_servicio
            SET tipo_servicio_id = %s
            WHERE tipo_servicio_id IS NULL
        """, (tipo_ops['SECAMIENTO'],))
        count = cr.rowcount
        if count > 0:
            _logger.info(f"  - Establecido SECAMIENTO por defecto en {count} registros sin tipo")

    # 7. Hacer NOT NULL la columna
    _logger.info("Estableciendo tipo_servicio_id como NOT NULL...")
    cr.execute("""
        ALTER TABLE secadora_orden_servicio
        ALTER COLUMN tipo_servicio_id SET NOT NULL
    """)

    # 8. Agregar foreign key constraint
    _logger.info("Agregando foreign key constraint...")
    cr.execute("""
        ALTER TABLE secadora_orden_servicio
        ADD CONSTRAINT secadora_orden_servicio_tipo_servicio_id_fkey
        FOREIGN KEY (tipo_servicio_id)
        REFERENCES secadora_tipo_operacion(id)
        ON DELETE RESTRICT
    """)

    # 9. Ahora podemos eliminar la columna antigua tipo_servicio
    # (se convierte en computed en el modelo)
    _logger.info("Eliminando columna antigua tipo_servicio...")
    cr.execute("""
        ALTER TABLE secadora_orden_servicio
        DROP COLUMN IF EXISTS tipo_servicio
    """)

    _logger.info("="*80)
    _logger.info("Migración completada exitosamente")
    _logger.info("="*80)
