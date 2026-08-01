"""Le da su equipo a las ordenes de trabajo que nacieron sin el.

Una OT creada desde el flujo de costos (Costos > Asignacion de equipos) queda
sin equipo: el equipo se elige en el costo, no en la orden. Esas OT no salen
en el historial de su equipo y ademas heredan la compania activa de quien las
registro en vez de la del equipo, que es de donde deberia salir.

El equipo se deduce de los costos ya imputados a la OT. Solo se tocan las que
tienen un unico equipo entre sus costos: si una OT mezcla varios, cual es "el"
equipo es una decision de negocio y se deja como esta.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        UPDATE maintenance_request r
        SET equipment_id = t.equipment_id
        FROM (
            SELECT cl.request_id,
                   MIN(cl.equipment_id) AS equipment_id
            FROM maintenance_equipment_cost_line cl
            WHERE cl.request_id IS NOT NULL
              AND cl.equipment_id IS NOT NULL
            GROUP BY cl.request_id
            HAVING COUNT(DISTINCT cl.equipment_id) = 1
        ) t
        WHERE r.id = t.request_id
          AND r.equipment_id IS NULL
    """)
    _logger.info('Ordenes de trabajo que recuperaron su equipo: %s',
                 cr.rowcount)

    # La compania de la OT sigue a la del equipo: es trabajo sobre ese activo,
    # no de quien lo registro.
    cr.execute("""
        UPDATE maintenance_request r
        SET company_id = e.company_id
        FROM maintenance_equipment e
        WHERE r.equipment_id = e.id
          AND e.company_id IS NOT NULL
          AND r.company_id IS DISTINCT FROM e.company_id
    """)
    _logger.info('Ordenes de trabajo realineadas con la compania de su equipo: %s',
                 cr.rowcount)
