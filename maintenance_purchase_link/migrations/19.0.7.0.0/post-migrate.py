"""Rellena `complete_name` en los equipos ya existentes.

Es un campo calculado con `store=True`, y los equipos se cargaron antes de
que existiera: sin esto la lista jerárquica saldría vacía. Se resuelve en dos
niveles (equipo raíz y componente), que es toda la profundidad que hay.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    # Equipos raíz: el nombre completo es su propio nombre.
    cr.execute("""
        UPDATE maintenance_equipment
        SET complete_name = name
        WHERE parent_equipment_id IS NULL
          AND complete_name IS DISTINCT FROM name
    """)
    _logger.info('Equipos raíz con nombre completo: %s', cr.rowcount)

    # Componentes: "<padre> / <componente>". Se itera por si hubiera más de
    # un nivel de anidamiento.
    for _ in range(5):
        cr.execute("""
            UPDATE maintenance_equipment hijo
            SET complete_name = padre.complete_name || ' / ' || hijo.name
            FROM maintenance_equipment padre
            WHERE hijo.parent_equipment_id = padre.id
              AND padre.complete_name IS NOT NULL
              AND hijo.complete_name IS DISTINCT FROM
                  (padre.complete_name || ' / ' || hijo.name)
        """)
        if not cr.rowcount:
            break
        _logger.info('Componentes con nombre completo: %s', cr.rowcount)
