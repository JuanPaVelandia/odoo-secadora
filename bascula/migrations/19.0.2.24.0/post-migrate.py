"""Marca los bultos que llegaron por traslado y cuadra los ingresos corregidos.

Dos arreglos sobre datos que ya existen:

1. Las copias creadas por un traslado no sabian de que registro venian, asi que
   los totales de la orden contaban dos veces el mismo arroz. Se emparejan por
   el movimiento de traslado, que si guarda el pesaje y la bodega de origen.

2. El movimiento de ingreso se anotaba al crear el registro y no se
   actualizaba si despues se corregia la cantidad. Se pone al dia.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    # 1. Emparejar cada copia con el registro del que salio.
    #
    # La copia se reconoce porque comparte pesaje con el traslado y esta en la
    # bodega de destino; el original es el que despacho ese mismo pesaje.
    cr.execute("""
        UPDATE secadora_registro_bultos copia
        SET trasladado_de_id = d.registro_bultos_id
        FROM secadora_movimiento_bultos m
        JOIN secadora_despacho_bultos d ON d.pesaje_id = m.pesaje_id
        WHERE m.registro_bultos_id = copia.id
          AND m.tipo = 'traslado'
          AND copia.trasladado_de_id IS NULL
          AND d.registro_bultos_id <> copia.id
          AND d.cantidad = copia.cantidad
    """)
    _logger.info('Bultos marcados como trasladados: %s', cr.rowcount)

    # 2. Poner al dia los ingresos que quedaron con la cantidad vieja.
    cr.execute("""
        UPDATE secadora_movimiento_bultos m
        SET cantidad = b.cantidad
        FROM secadora_registro_bultos b
        WHERE m.registro_bultos_id = b.id
          AND m.tipo = 'ingreso'
          AND m.cantidad <> b.cantidad
    """)
    _logger.info('Ingresos que se cuadraron con su registro: %s', cr.rowcount)
