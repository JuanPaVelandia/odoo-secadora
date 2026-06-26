# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Pre-migracion: Eliminar campos branch_id/branch_ids de todas las tablas HR
    y reglas ir_rule que referencian branch.

    El modelo lavish.res.branch fue eliminado y ya no existe en el sistema.
    Esta migracion limpia todas las referencias restantes en la base de datos.
    """
    if not version:
        return

    _logger.info("Pre-migracion lavish_hr_employee 1.9: Limpiando branch_id/branch_ids")

    # 1. Eliminar campos de ir_model_fields PRIMERO (antes de setup_models)
    cr.execute("""
        DELETE FROM ir_model_fields
        WHERE name IN ('branch_id', 'branch_ids', 'branch')
        RETURNING model, name
    """)
    deleted_fields = cr.fetchall()
    for model, field_name in deleted_fields:
        _logger.info(f"  Campo eliminado de ir_model_fields: {model}.{field_name}")
    if deleted_fields:
        _logger.info(f"  Total campos eliminados: {len(deleted_fields)}")

    # 2. Eliminar reglas ir_rule que usan branch en su dominio
    cr.execute("""
        DELETE FROM ir_rule
        WHERE domain_force LIKE '%branch_ids%'
           OR domain_force LIKE '%branch_id%'
           OR name ILIKE '%branch%'
        RETURNING id, name
    """)
    deleted_rules = cr.fetchall()
    for rule_id, rule_name in deleted_rules:
        _logger.info(f"  Regla eliminada: {rule_name} (id={rule_id})")
    if deleted_rules:
        _logger.info(f"  Total reglas eliminadas: {len(deleted_rules)}")

    # 3. Tablas donde eliminar columna branch_id (Many2one)
    tables_with_branch_id = [
        'hr_employee',
        'hr_contract',
        'hr_payslip',
        'hr_payslip_run',
        'hr_leave',
        'hr_leave_allocation',
        'hr_overtime',
        'hr_executing_social_security',
        'hr_errors_social_security',
        'hr_payslip_worked_days',
        'hr_payslip_input',
        'hr_work_entry',
    ]
    for table_name in tables_with_branch_id:
        _drop_column_if_exists(cr, table_name, 'branch_id')

    # 4. Tablas M2M a eliminar (relaciones branch_ids)
    m2m_tables_to_drop = [
        'lavish_res_branch_res_users_rel',
        'res_users_lavish_res_branch_rel',
        'hr_employee_lavish_res_branch_rel',
        'hr_payslip_run_lavish_res_branch_rel',
        'lavish_res_branch_hr_payslip_run_rel',
    ]
    for m2m_table in m2m_tables_to_drop:
        _drop_table_if_exists(cr, m2m_table)

    # 5. Limpiar ir_model_data que referencien campos branch
    cr.execute("""
        DELETE FROM ir_model_data
        WHERE model = 'ir.model.fields'
          AND name LIKE '%branch%'
        RETURNING module, name
    """)
    deleted_data = cr.fetchall()
    if deleted_data:
        _logger.info(f"  Eliminados {len(deleted_data)} registros de ir_model_data")

    # 6. Eliminar la tabla lavish_res_branch si aun existe
    _drop_table_if_exists(cr, 'lavish_res_branch')

    # 7. Eliminar el modelo ir_model de lavish.res.branch
    cr.execute("""
        DELETE FROM ir_model WHERE model = 'lavish.res.branch'
    """)
    if cr.rowcount:
        _logger.info("  Modelo lavish.res.branch eliminado de ir_model")

    _logger.info("Pre-migracion lavish_hr_employee 1.9 completada")


def _drop_column_if_exists(cr, table_name, column_name):
    """Elimina una columna si existe en la tabla"""
    cr.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s
        )
    """, (table_name, column_name))
    if cr.fetchone()[0]:
        _logger.info(f"  Eliminando columna {table_name}.{column_name}")
        cr.execute(f"ALTER TABLE {table_name} DROP COLUMN IF EXISTS {column_name} CASCADE")
        return True
    return False


def _drop_table_if_exists(cr, table_name):
    """Elimina una tabla si existe"""
    cr.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = %s
        )
    """, (table_name,))
    if cr.fetchone()[0]:
        _logger.info(f"  Eliminando tabla {table_name}")
        cr.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
        return True
    return False
