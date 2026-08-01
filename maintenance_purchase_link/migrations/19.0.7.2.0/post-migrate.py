"""Corrige los costos de mantenimiento que ya estaban mal grabados.

Tres arreglos, en el orden en que se pisan entre sí:

1. La compañía del costo se tomaba de la compañía activa de quien publicaba la
   factura, no de la factura. Con varias compañías en el grupo, el costo caía
   en la equivocada y el total del equipo salía distinto según con qué
   compañías estuviera uno mirando.

2. Al publicar nace un costo sin equipo. Si el equipo se asignaba después, se
   creaba OTRO costo en vez de rellenar el que ya estaba: el mismo gasto
   quedaba dos veces (uno huérfano y otro con equipo) y el total se inflaba.

3. Las facturas anteriores a la fecha pivote ya vienen del histórico importado
   de Fracttal. Como las facturas de contabilidad se migran desde enero, esas
   generaron costos que duplican el histórico.

Solo toca costos con respaldo de factura (`move_line_id`): el histórico
importado y los registros manuales se dejan como están.
"""
import logging

_logger = logging.getLogger(__name__)

FECHA_PIVOTE_POR_DEFECTO = '2026-07-20'


def migrate(cr, version):
    # --- 1. La compañía y la moneda mandan desde la factura ---
    cr.execute("""
        UPDATE maintenance_equipment_cost_line cl
        SET company_id = am.company_id
        FROM account_move_line aml
        JOIN account_move am ON am.id = aml.move_id
        WHERE cl.move_line_id = aml.id
          AND am.company_id IS NOT NULL
          AND cl.company_id IS DISTINCT FROM am.company_id
    """)
    _logger.info('Costos reasignados a la compañía de su factura: %s',
                 cr.rowcount)

    cr.execute("""
        UPDATE maintenance_equipment_cost_line cl
        SET currency_id = aml.currency_id
        FROM account_move_line aml
        WHERE cl.move_line_id = aml.id
          AND aml.currency_id IS NOT NULL
          AND cl.currency_id IS DISTINCT FROM aml.currency_id
    """)
    _logger.info('Costos con la moneda de su factura: %s', cr.rowcount)

    # --- 2. Huérfanas que quedaron al lado de un costo ya asignado ---
    # Se borra la huérfana (sin equipo) solo cuando esa misma línea de factura
    # ya tiene otro costo CON equipo: ahí la huérfana es el duplicado que
    # inflaba el total. Una huérfana sola es una asignación pendiente legítima
    # y no se toca.
    cr.execute("""
        DELETE FROM maintenance_equipment_cost_line huerfana
        WHERE huerfana.equipment_id IS NULL
          AND huerfana.move_line_id IS NOT NULL
          AND EXISTS (
              SELECT 1
              FROM maintenance_equipment_cost_line hermana
              WHERE hermana.move_line_id = huerfana.move_line_id
                AND hermana.equipment_id IS NOT NULL
          )
    """)
    _logger.info('Costos huérfanos duplicados eliminados: %s', cr.rowcount)

    # --- 3. Facturas anteriores al pivote: las cubre el histórico ---
    cr.execute("""
        SELECT value FROM ir_config_parameter
        WHERE key = 'maintenance_purchase_link.fecha_pivote_costos'
    """)
    fila = cr.fetchone()
    fecha_pivote = (fila[0] if fila and fila[0] else FECHA_PIVOTE_POR_DEFECTO)

    cr.execute("""
        DELETE FROM maintenance_equipment_cost_line cl
        WHERE cl.move_line_id IS NOT NULL
          AND EXISTS (
              SELECT 1
              FROM account_move_line aml
              JOIN account_move am ON am.id = aml.move_id
              WHERE aml.id = cl.move_line_id
                AND COALESCE(am.invoice_date, am.date) < %s
          )
    """, (fecha_pivote,))
    _logger.info('Costos de facturas anteriores a %s eliminados: %s',
                 fecha_pivote, cr.rowcount)

    # Los totales por equipo están almacenados: hay que recalcularlos.
    cr.execute("""
        UPDATE maintenance_equipment eq
        SET maintenance_cost_total = COALESCE(t.total, 0),
            maintenance_invoice_count = COALESCE(t.cantidad, 0)
        FROM (
            SELECT e.id,
                   SUM(cl.amount) AS total,
                   COUNT(cl.id) AS cantidad
            FROM maintenance_equipment e
            LEFT JOIN maintenance_equipment_cost_line cl
                   ON cl.equipment_id = e.id
            GROUP BY e.id
        ) t
        WHERE eq.id = t.id
    """)
    _logger.info('Totales de costo por equipo recalculados: %s', cr.rowcount)
