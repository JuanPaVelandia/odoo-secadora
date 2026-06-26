# -*- coding: utf-8 -*-
"""
Migracion 1.0.35 - Elimina modelos obsoletos de retencion en la fuente.

Modelos eliminados:
- hr.type.tax.retention
- hr.concepts.deduction.retention
- hr.employee.deduction.retention
- hr.employee.rtefte
- hr.calculation.rtefte.ordinary

Estos modelos fueron reemplazados por la logica integrada en reglas salariales.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    _logger.info("=== Migracion 1.0.35: Eliminando modelos obsoletos de RteFte ===")

    # Tablas a eliminar (en orden correcto por dependencias FK)
    tables_to_drop = [
        'hr_employee_deduction_retention',  # Depende de hr_employee_rtefte
        'hr_employee_rtefte',
        'hr_concepts_deduction_retention',  # Depende de hr_type_tax_retention
        'hr_type_tax_retention',
        'hr_calculation_rtefte_ordinary',
    ]

    # Modelos a eliminar de ir.model
    models_to_delete = [
        'hr.employee.deduction.retention',
        'hr.employee.rtefte',
        'hr.concepts.deduction.retention',
        'hr.type.tax.retention',
        'hr.calculation.rtefte.ordinary',
    ]

    # 1. Eliminar columna rtefte_id de hr_payslip si existe
    _logger.info("Verificando y eliminando columna rtefte_id de hr_payslip...")
    cr.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'hr_payslip' AND column_name = 'rtefte_id'
    """)
    if cr.fetchone():
        cr.execute("ALTER TABLE hr_payslip DROP COLUMN IF EXISTS rtefte_id CASCADE")
        _logger.info("Columna rtefte_id eliminada de hr_payslip")

    # 2. Eliminar registros de seguridad (ir.model.access)
    _logger.info("Eliminando registros de seguridad...")
    cr.execute("""
        DELETE FROM ir_model_access
        WHERE name IN (
            'access_hr_concepts_deduction_retention',
            'access_hr_employee_deduction_retention',
            'access_hr_type_tax_retention',
            'access_hr_calculation_rtefte_ordinary',
            'access_hr_employee_rtefte'
        )
    """)
    _logger.info(f"Eliminados {cr.rowcount} registros de ir_model_access")

    # 3. Eliminar vistas (ir.ui.view)
    _logger.info("Eliminando vistas...")
    for model in models_to_delete:
        cr.execute("DELETE FROM ir_ui_view WHERE model = %s", (model,))
        if cr.rowcount:
            _logger.info(f"Eliminadas {cr.rowcount} vistas para modelo {model}")

    # 4. Eliminar acciones de ventana (ir.actions.act_window)
    _logger.info("Eliminando acciones de ventana...")
    for model in models_to_delete:
        cr.execute("DELETE FROM ir_act_window WHERE res_model = %s", (model,))
        if cr.rowcount:
            _logger.info(f"Eliminadas {cr.rowcount} acciones para modelo {model}")

    # 5. Eliminar menus especificos de retencion
    _logger.info("Eliminando menus de retencion...")
    menus_to_delete = [
        'lavish_hr_payroll.menu_calculation_rtefte_ordinary',
        'lavish_hr_payroll.menu_type_tax_retention',
        'lavish_hr_payroll.menu_concepts_deduction_retention',
        'lavish_hr_payroll.menu_retention',
    ]
    # Primero eliminar menus hijos, luego el padre
    cr.execute("""
        DELETE FROM ir_ui_menu
        WHERE id IN (
            SELECT res_id FROM ir_model_data
            WHERE module = 'lavish_hr_payroll'
            AND name IN ('menu_calculation_rtefte_ordinary', 'menu_type_tax_retention',
                         'menu_concepts_deduction_retention', 'menu_retention')
        )
    """)
    _logger.info(f"Eliminados {cr.rowcount} menus")
    # Limpiar ir_model_data de los menus
    cr.execute("""
        DELETE FROM ir_model_data
        WHERE module = 'lavish_hr_payroll'
        AND name IN ('menu_calculation_rtefte_ordinary', 'menu_type_tax_retention',
                     'menu_concepts_deduction_retention', 'menu_retention')
    """)

    # 6. Eliminar campos de ir.model.fields
    _logger.info("Eliminando definiciones de campos...")
    for model in models_to_delete:
        cr.execute("DELETE FROM ir_model_fields WHERE model = %s", (model,))
        if cr.rowcount:
            _logger.info(f"Eliminados {cr.rowcount} campos para modelo {model}")

    # 7. Eliminar las tablas
    _logger.info("Eliminando tablas...")
    for table in tables_to_drop:
        cr.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        _logger.info(f"Tabla {table} eliminada")

    # 8. Eliminar modelos de ir.model
    _logger.info("Eliminando registros de ir.model...")
    for model in models_to_delete:
        cr.execute("DELETE FROM ir_model WHERE model = %s", (model,))
        if cr.rowcount:
            _logger.info(f"Modelo {model} eliminado de ir.model")

    # 9. Limpiar ir_model_data (referencias a datos eliminados)
    _logger.info("Limpiando ir_model_data...")
    cr.execute("""
        DELETE FROM ir_model_data
        WHERE model IN %s
    """, (tuple(models_to_delete),))
    _logger.info(f"Eliminados {cr.rowcount} registros de ir_model_data")

    _logger.info("=== Migracion 1.0.35 completada ===")
