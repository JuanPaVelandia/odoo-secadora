"""Rellena la variedad de los bultos creados desde el tablero.

El wizard de despacho escribia la variedad solo como texto en `observaciones`
y no en `variedad_id`, asi que los bultos despachados desde el tablero salian
sin variedad y no aparecian en el inventario por variedad ni por codigo.

El wizard ya quedo corregido; esto recupera los que se crearon antes. Igual que
la migracion anterior, solo empareja cuando el texto corresponde a UNA variedad
del catalogo: si trae varias, se deja vacia.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        UPDATE secadora_registro_bultos b
        SET variedad_id = v.id
        FROM secadora_variedad_arroz v
        WHERE b.variedad_id IS NULL
          AND b.observaciones IS NOT NULL
          AND btrim(b.observaciones) <> ''
          AND lower(btrim(b.observaciones)) = lower(btrim(v.name))
    """)
    _logger.info('Bultos del tablero que recuperaron su variedad: %s', cr.rowcount)
