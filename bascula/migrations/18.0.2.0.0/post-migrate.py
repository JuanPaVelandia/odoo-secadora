"""Migrar lote_finca (texto libre) al catálogo secadora.lote y asignar lote_id.

- Crea un lote por cada (finca, texto normalizado) distinto. La normalización
  es case-insensitive y colapsa espacios, para no crear "LOTE 5" y "lote 5"
  como dos lotes. Como nombre se toma la variante más frecuente.
- lote_finca NO se toca: queda como respaldo de auditoría.
- El log deja el informe de lotes creados por finca para depurar typos a mano.
"""
import logging
from collections import defaultdict

_logger = logging.getLogger(__name__)


def _clave(texto):
    """Clave de dedupe: mayúsculas y espacios colapsados."""
    return ' '.join(texto.split()).upper()


def migrate(cr, version):
    if not version:
        return

    cr.execute("""
        SELECT origen_id, TRIM(lote_finca) AS txt, COUNT(*) AS n
        FROM secadora_pesaje
        WHERE lote_finca IS NOT NULL
          AND TRIM(lote_finca) != ''
          AND lote_id IS NULL
        GROUP BY origen_id, TRIM(lote_finca)
    """)
    filas = cr.fetchall()
    if not filas:
        _logger.info("Migración de lotes: no hay pesajes con lote_finca pendiente.")
        return

    # Dedupe por (finca, clave normalizada): variante más frecuente como nombre
    grupos = defaultdict(lambda: defaultdict(int))  # (finca, clave) -> {variante: conteo}
    for origen_id, txt, n in filas:
        grupos[(origen_id, _clave(txt))][txt] += n

    creados = 0
    actualizados = 0
    informe = defaultdict(list)
    for (finca_id, clave), variantes in grupos.items():
        nombre = max(variantes.items(), key=lambda kv: kv[1])[0]

        # Buscar lote existente por clave normalizada (corridas repetidas / typos de caso)
        cr.execute("""
            SELECT id FROM secadora_lote
            WHERE finca_id = %s
              AND UPPER(regexp_replace(TRIM(name), '\\s+', ' ', 'g')) = %s
            LIMIT 1
        """, (finca_id, clave))
        row = cr.fetchone()
        if row:
            lote_id = row[0]
        else:
            cr.execute("""
                INSERT INTO secadora_lote
                    (name, finca_id, active, create_uid, create_date, write_uid, write_date)
                VALUES (%s, %s, true, 1, NOW() AT TIME ZONE 'UTC', 1, NOW() AT TIME ZONE 'UTC')
                RETURNING id
            """, (nombre, finca_id))
            lote_id = cr.fetchone()[0]
            creados += 1
            informe[finca_id].append(nombre)

        cr.execute("""
            UPDATE secadora_pesaje
            SET lote_id = %s
            WHERE origen_id = %s
              AND lote_id IS NULL
              AND lote_finca IS NOT NULL
              AND UPPER(regexp_replace(TRIM(lote_finca), '\\s+', ' ', 'g')) = %s
        """, (lote_id, finca_id, clave))
        actualizados += cr.rowcount

    for finca_id, nombres in sorted(informe.items()):
        cr.execute("SELECT name FROM secadora_lugar WHERE id = %s", (finca_id,))
        finca = cr.fetchone()
        _logger.info("Migración de lotes: finca '%s' -> lotes creados: %s",
                     finca[0] if finca else finca_id, ', '.join(sorted(nombres)))
    _logger.info("Migración de lotes completada: %d lotes creados, %d pesajes actualizados. "
                 "Revisar el listado anterior para depurar typos (archivar/fusionar en el catálogo).",
                 creados, actualizados)
