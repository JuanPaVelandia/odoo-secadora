"""Rellena `complete_name` en los equipos ya existentes.

Es un campo calculado con `store=True`, y los equipos se cargaron antes de
que existiera: sin esto la lista por ubicación saldría vacía.

Ojo: `maintenance.equipment.name` es traducible, así que en Postgres es una
columna `jsonb` ({"en_US": "..."}), no texto. Hay que extraer el valor con
`->>` antes de compararlo o concatenarlo.
"""
import logging

_logger = logging.getLogger(__name__)


def _expresion_nombre(cr, alias=''):
    """SQL que devuelve el nombre como texto, sea jsonb o varchar."""
    cr.execute("""
        SELECT data_type FROM information_schema.columns
        WHERE table_name = 'maintenance_equipment' AND column_name = 'name'
    """)
    fila = cr.fetchone()
    columna = f'{alias}.name' if alias else 'name'
    if fila and fila[0] == 'jsonb':
        return (f"COALESCE({columna}->>'es_CO', {columna}->>'es_ES', "
                f"{columna}->>'en_US', "
                f"(SELECT value FROM jsonb_each_text({columna}) LIMIT 1))")
    return columna


def migrate(cr, version):
    nombre = _expresion_nombre(cr)
    nombre_hijo = _expresion_nombre(cr, 'hijo')

    # Equipos raíz: su nombre completo es su propio nombre.
    cr.execute(f"""
        UPDATE maintenance_equipment
        SET complete_name = {nombre}
        WHERE parent_equipment_id IS NULL
          AND complete_name IS DISTINCT FROM {nombre}
    """)
    _logger.info('Equipos raíz con nombre completo: %s', cr.rowcount)

    # Componentes: "<padre> / <componente>". Se itera por si hubiera más de
    # un nivel de anidamiento.
    for _ in range(5):
        cr.execute(f"""
            UPDATE maintenance_equipment hijo
            SET complete_name = padre.complete_name || ' / ' || {nombre_hijo}
            FROM maintenance_equipment padre
            WHERE hijo.parent_equipment_id = padre.id
              AND padre.complete_name IS NOT NULL
              AND hijo.complete_name IS DISTINCT FROM
                  (padre.complete_name || ' / ' || {nombre_hijo})
        """)
        if not cr.rowcount:
            break
        _logger.info('Componentes con nombre completo: %s', cr.rowcount)
