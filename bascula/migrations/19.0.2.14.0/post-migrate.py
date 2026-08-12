"""Rescata la variedad de los bultos, que se guardaba como texto libre.

Hasta ahora `_onchange_producto_id` escribia los nombres de variedad en
`observaciones` separados por coma. Eso no permitia filtrar ni agrupar, que es
justo lo que hace falta para el inventario por bodega.

Se rellena `variedad_id` unicamente cuando el texto corresponde a UNA variedad
que existe en el catalogo. Si trae varias (carga mixta) o no coincide con
ninguna, se deja vacia: adivinar seria peor que dejar que alguien la corrija.

`observaciones` no se toca — en las cargas mixtas es el unico sitio donde se
ven todas las variedades juntas.
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
    _logger.info('Bultos que recuperaron su variedad: %s', cr.rowcount)

    # Los que traen varias variedades quedan sin asignar a proposito.
    cr.execute("""
        SELECT COUNT(*) FROM secadora_registro_bultos
        WHERE variedad_id IS NULL
          AND observaciones IS NOT NULL AND btrim(observaciones) <> ''
    """)
    pendientes = cr.fetchone()[0]
    if pendientes:
        _logger.warning(
            'Bultos con variedad en texto que no se pudo emparejar (carga '
            'mixta o nombre distinto): %s. Hay que asignarlas a mano si se '
            'quieren ver en el inventario por variedad.', pendientes)

    # La semilla se deduce de los pesajes de entrada de la orden.
    cr.execute("""
        UPDATE secadora_registro_bultos b
        SET es_semilla = TRUE
        WHERE b.es_semilla IS NOT TRUE
          AND EXISTS (
              SELECT 1 FROM secadora_pesaje p
              WHERE p.orden_servicio_id = b.orden_id
                AND p.direccion = 'entrada'
                AND p.es_semilla IS TRUE
          )
    """)
    _logger.info('Bultos marcados como semilla: %s', cr.rowcount)
