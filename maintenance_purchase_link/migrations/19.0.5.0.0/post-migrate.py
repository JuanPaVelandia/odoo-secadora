"""Unifica los costos de mantenimiento en un solo modelo.

Antes: `maintenance.equipment.cost.line` era un trozo de línea de factura (sus
datos eran `related` de `move_line_id`) y el histórico sin factura vivía aparte
en `maintenance.historic.cost` — dos listas y dos totales para lo mismo.

Ahora los campos descriptivos están almacenados en la cost line y la factura es
opcional, así que:
  1. Se rellenan esos campos en las líneas existentes desde su factura.
  2. Se traen las líneas de `maintenance.historic.cost` (si el modelo llegó a
     existir en esta base) como líneas con `origin = 'historic'`.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    _rellenar_desde_factura(cr)
    _absorber_historicos(cr)
    _recalcular_totales(cr)


def _rellenar_desde_factura(cr):
    """Copia a la cost line los datos que antes leía de la factura."""
    cr.execute("""
        UPDATE maintenance_equipment_cost_line cl
        SET origin = 'invoice',
            date = COALESCE(cl.date, aml.date),
            name = COALESCE(cl.name, aml.name, 'Costo de mantenimiento'),
            partner_id = COALESCE(cl.partner_id, aml.partner_id),
            product_id = COALESCE(cl.product_id, aml.product_id),
            quantity = COALESCE(NULLIF(cl.quantity, 0), aml.quantity),
            unit_cost = COALESCE(NULLIF(cl.unit_cost, 0), aml.price_unit),
            currency_id = COALESCE(cl.currency_id, aml.currency_id),
            company_id = COALESCE(cl.company_id, am.company_id)
        FROM account_move_line aml
        JOIN account_move am ON am.id = aml.move_id
        WHERE cl.move_line_id = aml.id
    """)
    _logger.info('Costos con factura actualizados: %s', cr.rowcount)

    # Red de seguridad: `date` y `name` ahora son obligatorios.
    cr.execute("""
        UPDATE maintenance_equipment_cost_line
        SET date = COALESCE(date, create_date::date, CURRENT_DATE),
            name = COALESCE(name, 'Costo de mantenimiento'),
            origin = COALESCE(origin, CASE WHEN move_line_id IS NOT NULL
                                           THEN 'invoice' ELSE 'manual' END)
        WHERE date IS NULL OR name IS NULL OR origin IS NULL
    """)


def _absorber_historicos(cr):
    """Trae `maintenance.historic.cost` a la cost line unificada."""
    cr.execute("""
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'maintenance_historic_cost'
    """)
    if not cr.fetchone():
        _logger.info('No hay tabla maintenance_historic_cost: nada que absorber.')
        return

    # Idempotente: no se reimporta lo que ya se trajo en una pasada anterior.
    cr.execute("""
        INSERT INTO maintenance_equipment_cost_line (
            origin, equipment_id, request_id, date, name, code, resource_type,
            partner_id, source_name, quantity, uom_name, unit_cost, amount,
            currency_id, company_id, external_ref, notes, percentage,
            create_uid, create_date, write_uid, write_date
        )
        SELECT
            'historic', hc.equipment_id, hc.request_id, hc.date,
            COALESCE(hc.name, 'Costo de mantenimiento'), hc.code,
            hc.resource_type, hc.partner_id, hc.source_name,
            COALESCE(hc.quantity, 1), hc.uom_name, hc.unit_cost,
            COALESCE(hc.amount, 0), hc.currency_id, hc.company_id,
            hc.external_ref, hc.notes, 100.0,
            hc.create_uid, hc.create_date, hc.write_uid, hc.write_date
        FROM maintenance_historic_cost hc
        WHERE NOT EXISTS (
            SELECT 1 FROM maintenance_equipment_cost_line cl
            WHERE cl.origin = 'historic'
              AND cl.equipment_id IS NOT DISTINCT FROM hc.equipment_id
              AND cl.request_id IS NOT DISTINCT FROM hc.request_id
              AND cl.date = hc.date
              AND cl.name = COALESCE(hc.name, 'Costo de mantenimiento')
              AND cl.amount = COALESCE(hc.amount, 0)
        )
    """)
    _logger.info('Costos históricos absorbidos: %s', cr.rowcount)

    # La tabla vieja se conserva por si hay que auditar el traslado; el modelo
    # ya no existe, así que Odoo no la usa. Se puede borrar a mano una vez
    # comprobados los totales.
    cr.execute("SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM maintenance_historic_cost")
    filas, total = cr.fetchone()
    _logger.info('Tabla maintenance_historic_cost conservada para auditoría: '
                 '%s filas, total %s', filas, total)


def _recalcular_totales(cr):
    """Recalcula los totales por equipo.

    `maintenance_cost_total` y `maintenance_invoice_count` son campos
    calculados con `store=True`, y las filas se insertaron por SQL directo:
    el ORM no se entera y los totales quedarían en cero. Se recalculan aquí
    con la misma fórmula del compute.
    """
    cr.execute("""
        UPDATE maintenance_equipment eq
        SET maintenance_cost_total = COALESCE(t.total, 0),
            maintenance_invoice_count = COALESCE(t.n, 0)
        FROM (
            SELECT e.id,
                   SUM(cl.amount) AS total,
                   COUNT(cl.id) AS n
            FROM maintenance_equipment e
            LEFT JOIN maintenance_equipment_cost_line cl
                   ON cl.equipment_id = e.id
            GROUP BY e.id
        ) t
        WHERE eq.id = t.id
          AND (eq.maintenance_cost_total IS DISTINCT FROM COALESCE(t.total, 0)
               OR eq.maintenance_invoice_count IS DISTINCT FROM COALESCE(t.n, 0))
    """)
    _logger.info('Totales de equipo recalculados: %s', cr.rowcount)
