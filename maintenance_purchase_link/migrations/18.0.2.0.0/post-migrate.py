"""Migrar datos M2M existentes a maintenance.equipment.cost.line con 100%."""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    # Verificar si la tabla M2M vieja existe
    cr.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'account_move_line_maintenance_equipment_rel'
        )
    """)
    if not cr.fetchone()[0]:
        _logger.info("Tabla M2M vieja no existe, nada que migrar.")
        return

    # Verificar si hay datos para migrar
    cr.execute("SELECT COUNT(*) FROM account_move_line_maintenance_equipment_rel")
    count = cr.fetchone()[0]
    if not count:
        _logger.info("No hay datos en tabla M2M vieja para migrar.")
        return

    _logger.info("Migrando %d relaciones equipo-factura a maintenance.equipment.cost.line...", count)

    cr.execute("""
        INSERT INTO maintenance_equipment_cost_line
            (move_line_id, equipment_id, percentage, create_uid, create_date, write_uid, write_date)
        SELECT
            rel.move_line_id,
            rel.equipment_id,
            100.0,
            1,
            NOW() AT TIME ZONE 'UTC',
            1,
            NOW() AT TIME ZONE 'UTC'
        FROM account_move_line_maintenance_equipment_rel rel
        ON CONFLICT DO NOTHING
    """)

    _logger.info("Migración completada: %d registros insertados.", cr.rowcount)
