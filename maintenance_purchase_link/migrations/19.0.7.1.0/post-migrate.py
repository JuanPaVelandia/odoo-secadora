"""Da a cada componente la ubicación de su máquina.

Los componentes (motores, alternadores) se importaron sin `lugar_id`, con la
idea de que heredaban la ubicación del padre. Pero al agrupar por ubicación
caían todos en "sin ubicación" en vez de bajo su finca: 66 motores de la
secadora no aparecían con ella.

Un componente está, físicamente, donde está la máquina que lo contiene.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    # Se repite por si hubiera componentes de componentes.
    for _ in range(5):
        cr.execute("""
            UPDATE maintenance_equipment hijo
            SET lugar_id = padre.lugar_id,
                origen_muestra_id = COALESCE(hijo.origen_muestra_id,
                                             padre.origen_muestra_id)
            FROM maintenance_equipment padre
            WHERE hijo.parent_equipment_id = padre.id
              AND padre.lugar_id IS NOT NULL
              AND hijo.lugar_id IS DISTINCT FROM padre.lugar_id
        """)
        if not cr.rowcount:
            break
        _logger.info('Componentes que heredan la ubicación del padre: %s',
                     cr.rowcount)

    # El historial de esos componentes también apuntaba a "sin ubicación".
    cr.execute("""
        UPDATE maintenance_equipment_location_history hist
        SET lugar_id = eq.lugar_id
        FROM maintenance_equipment eq
        WHERE hist.equipment_id = eq.id
          AND hist.lugar_id IS NULL
          AND eq.parent_equipment_id IS NOT NULL
          AND eq.lugar_id IS NOT NULL
    """)
    _logger.info('Tramos de historial de componentes corregidos: %s',
                 cr.rowcount)
