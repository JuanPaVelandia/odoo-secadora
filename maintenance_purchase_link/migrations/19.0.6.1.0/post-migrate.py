"""Numera las órdenes de trabajo con el formato OT-<n> que traía Fracttal.

Las OT importadas ya tienen su identificador de origen en `external_ref`
("OT-999"): ese pasa a ser su número oficial, para que las referencias que
la gente ya conoce sigan siendo válidas. Las que no lo tengan reciben un
número nuevo, y la secuencia se coloca por encima del máximo existente para
que las siguientes continúen la serie sin chocar.
"""
import logging

_logger = logging.getLogger(__name__)

CODIGO_SECUENCIA = 'maintenance.request.ot'


def migrate(cr, version):
    _numerar_importadas(cr)
    _numerar_resto(cr)
    _limpiar_nombres(cr)
    _ajustar_secuencia(cr)


def _numerar_importadas(cr):
    """El id de Fracttal (OT-999) pasa a ser el número oficial de la OT."""
    cr.execute("""
        UPDATE maintenance_request
        SET ot_number = external_ref
        WHERE ot_number IS NULL
          AND external_ref IS NOT NULL
          AND external_ref ~ '^OT-[0-9]+$'
          AND NOT EXISTS (
              SELECT 1 FROM maintenance_request otra
              WHERE otra.ot_number = maintenance_request.external_ref
          )
    """)
    _logger.info('OT numeradas desde su referencia de origen: %s', cr.rowcount)


def _numerar_resto(cr):
    """Numera las OT que no venían de una importación."""
    cr.execute("""
        SELECT COALESCE(MAX(CAST(SUBSTRING(ot_number FROM '^OT-([0-9]+)$')
                                 AS INTEGER)), 0)
        FROM maintenance_request
        WHERE ot_number ~ '^OT-[0-9]+$'
    """)
    siguiente = (cr.fetchone()[0] or 0) + 1

    cr.execute("SELECT id FROM maintenance_request WHERE ot_number IS NULL ORDER BY id")
    pendientes = [fila[0] for fila in cr.fetchall()]
    for id_request in pendientes:
        cr.execute("UPDATE maintenance_request SET ot_number = %s WHERE id = %s",
                   (f'OT-{siguiente}', id_request))
        siguiente += 1
    if pendientes:
        _logger.info('OT numeradas de nuevo: %s', len(pendientes))


def _limpiar_nombres(cr):
    """Quita el "[OT-999] " del nombre: ahora ese dato vive en `ot_number`."""
    cr.execute(r"""
        UPDATE maintenance_request
        SET name = TRIM(REGEXP_REPLACE(name, '^\[OT-[0-9]+\]\s*', ''))
        WHERE name ~ '^\[OT-[0-9]+\]'
          AND TRIM(REGEXP_REPLACE(name, '^\[OT-[0-9]+\]\s*', '')) <> ''
    """)
    _logger.info('Nombres de OT limpiados: %s', cr.rowcount)

    # Una versión anterior componía el nombre con un `name` vacío y dejaba el
    # literal "False" pegado ("[OT-1242] False").
    cr.execute(r"""
        UPDATE maintenance_request
        SET name = COALESCE(NULLIF(TRIM(task_name), ''), 'Solicitud de mantenimiento')
        WHERE name ~ '^\[OT-[0-9]+\]\s*False\s*$' OR name = 'False'
    """)
    if cr.rowcount:
        _logger.info('Nombres corruptos corregidos: %s', cr.rowcount)


def _ajustar_secuencia(cr):
    """Deja la secuencia por encima del número más alto en uso."""
    cr.execute("""
        SELECT COALESCE(MAX(CAST(SUBSTRING(ot_number FROM '^OT-([0-9]+)$')
                                 AS INTEGER)), 0)
        FROM maintenance_request
        WHERE ot_number ~ '^OT-[0-9]+$'
    """)
    siguiente = (cr.fetchone()[0] or 0) + 1

    cr.execute("""
        UPDATE ir_sequence SET number_next = %s
        WHERE code = %s AND number_next <= %s
    """, (siguiente, CODIGO_SECUENCIA, siguiente))
    if cr.rowcount:
        _logger.info('Secuencia %s ajustada: la próxima OT será OT-%s',
                     CODIGO_SECUENCIA, siguiente)

    # `no_gap` guarda el contador en una tabla propia; hay que moverla también.
    cr.execute("""
        SELECT id FROM ir_sequence
        WHERE code = %s AND implementation = 'no_gap'
    """, (CODIGO_SECUENCIA,))
    fila = cr.fetchone()
    if fila:
        cr.execute(
            "SELECT 1 FROM information_schema.sequences WHERE sequence_name = %s",
            (f'ir_sequence_{fila[0]:03d}',))
        if cr.fetchone():
            cr.execute(
                f'ALTER SEQUENCE ir_sequence_{fila[0]:03d} RESTART WITH {siguiente}')
