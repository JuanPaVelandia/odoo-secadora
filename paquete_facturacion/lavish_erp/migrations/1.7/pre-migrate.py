# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Pre-migracion: Eliminar campos branch_id de tablas HR y reglas
    que referencian branch_ids (que ya no existe en lavish_erp).

    Esto es necesario porque lavish.res.branch fue eliminado en v1.6
    pero otros modulos HR aun tenian referencias a branch_id/branch_ids.
    """
    if not version:
        return

    _logger.info("Pre-migracion lavish_erp 1.7: Limpiando referencias a branch")

    # 1. Eliminar reglas ir_rule que usan branch_ids en su dominio
    cr.execute("""
        SELECT id, name, domain_force FROM ir_rule
        WHERE domain_force LIKE '%branch_ids%'
           OR domain_force LIKE '%branch_id%'
    """)
    rules_to_delete = cr.fetchall()

    for rule_id, rule_name, domain in rules_to_delete:
        _logger.info(f"  Eliminando regla: {rule_name} (id={rule_id})")
        cr.execute("DELETE FROM ir_rule WHERE id = %s", (rule_id,))

    if rules_to_delete:
        _logger.info(f"  Total reglas eliminadas: {len(rules_to_delete)}")

    # 2. Tablas donde eliminar columna branch_id
    tables_with_branch = [
        'hr_employee',
        'hr_contract',
        'hr_payslip',
        'hr_payslip_run',
        'hr_leave',
        'hr_leave_allocation',
        'hr_overtime',
        'hr_executing_social_security',
        'hr_errors_social_security',
    ]

    for table_name in tables_with_branch:
        # Verificar si la tabla existe
        cr.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = %s
            )
        """, (table_name,))
        table_exists = cr.fetchone()[0]

        if not table_exists:
            continue

        # Verificar si la columna branch_id existe
        cr.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.columns
                WHERE table_name = %s AND column_name = 'branch_id'
            )
        """, (table_name,))
        column_exists = cr.fetchone()[0]

        if column_exists:
            _logger.info(f"  Eliminando columna {table_name}.branch_id")
            cr.execute(f"ALTER TABLE {table_name} DROP COLUMN IF EXISTS branch_id CASCADE")

    # 3. Eliminar campos ir_model_fields de branch_id
    cr.execute("""
        DELETE FROM ir_model_fields
        WHERE name = 'branch_id'
          AND model IN ('hr.employee', 'hr.contract', 'hr.payslip',
                        'hr.payslip.run', 'hr.leave', 'hr.leave.allocation',
                        'res.users', 'hr.overtime', 'hr.executing.social.security',
                        'hr.errors.social.security')
    """)
    deleted_fields = cr.rowcount
    if deleted_fields:
        _logger.info(f"  Eliminados {deleted_fields} registros de ir_model_fields para branch_id")

    # 4. Eliminar campos ir_model_fields de branch_ids (Many2many)
    cr.execute("""
        DELETE FROM ir_model_fields
        WHERE name = 'branch_ids'
          AND model IN ('res.users', 'hr.employee')
    """)
    deleted_m2m_fields = cr.rowcount
    if deleted_m2m_fields:
        _logger.info(f"  Eliminados {deleted_m2m_fields} registros de ir_model_fields para branch_ids")

    # 5. Limpiar ir_model_data que referencien campos branch
    cr.execute("""
        DELETE FROM ir_model_data
        WHERE model = 'ir.model.fields'
          AND name LIKE '%branch%'
          AND module LIKE 'lavish%'
    """)
    deleted_data = cr.rowcount
    if deleted_data:
        _logger.info(f"  Eliminados {deleted_data} registros de ir_model_data para branch")

    # 6. Limpiar vistas que referencien branch_id (marcar para regenerar)
    # arch_db es JSONB, necesitamos cast a text para usar LIKE
    cr.execute("""
        UPDATE ir_ui_view
        SET arch_updated = TRUE
        WHERE arch_db::text LIKE '%branch_id%'
           OR arch_db::text LIKE '%branch_ids%'
    """)
    updated_views = cr.rowcount
    if updated_views:
        _logger.info(f"  Marcadas {updated_views} vistas para actualizacion")

    _logger.info("Pre-migracion lavish_erp 1.7 completada")
