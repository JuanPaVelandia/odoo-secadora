"""Unifica el grano partido: lo capturado en Molineria pasa al campo unico.

"Grano Partido" (parametros principales) y "Grano Partido Blanco" (molineria)
resultaron ser el mismo dato pedido dos veces, por estar en pestanas distintas.
En la practica el laboratorio siempre lo capturo en el de molineria, asi que el
campo que queda visible en ambas pestanas (`grano_partido`) esta vacio y sin
esto los analisis historicos apareceran en blanco.

Solo se copia donde el destino esta vacio: si algun analisis tuviera los dos
valores, el de parametros principales manda y se deja como esta.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        UPDATE secadora_analisis_lab
        SET grano_partido = grano_partido_blanco_pct
        WHERE COALESCE(grano_partido, 0) = 0
          AND COALESCE(grano_partido_blanco_pct, 0) <> 0
    """)
    _logger.info(
        'Analisis cuyo grano partido se trajo de molineria: %s', cr.rowcount)

    # Discrepancias: los dos campos con valor y distintos. No se tocan, pero
    # conviene saber que existen por si el laboratorio quiere revisarlas.
    cr.execute("""
        SELECT COUNT(*)
        FROM secadora_analisis_lab
        WHERE COALESCE(grano_partido, 0) <> 0
          AND COALESCE(grano_partido_blanco_pct, 0) <> 0
          AND grano_partido <> grano_partido_blanco_pct
    """)
    discrepancias = cr.fetchone()[0]
    if discrepancias:
        _logger.warning(
            'Analisis con los dos campos de partido distintos (se conserva el '
            'de parametros principales): %s', discrepancias)
