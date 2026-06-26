# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Migracion 1.33: Prevenir eliminacion de registros con foreign keys.

    Marca todos los registros de datos maestros como noupdate=True para evitar
    que Odoo intente eliminarlos durante la actualizacion del modulo.
    """
    _logger.info("Iniciando migracion 1.33: Proteccion de datos maestros...")

    # Lista de modelos a proteger
    models_to_protect = [
        'hr.payroll.structure',
        'hr.payroll.structure.type',
        'hr.salary.rule.category',
        'hr.salary.rule',
        'hr.tipo.cotizante',
        'hr.type.employee',
        'hr.work.entry.type',
        'hr.leave.type',
        'hr.indicador.especial.pensiones',
        'hr.contract.type',
        'hr.contribution.register',
    ]

    for model in models_to_protect:
        cr.execute("""
            UPDATE ir_model_data
            SET noupdate = TRUE
            WHERE model = %s
            AND module = 'lavish_hr_employee'
        """, (model,))
        if cr.rowcount:
            _logger.info(f"  Actualizados {cr.rowcount} registros de {model} a noupdate=True")

    # Proteger hr.work.entry.type de TODOS los modulos (tienen muchas referencias en nominas)
    cr.execute("""
        UPDATE ir_model_data
        SET noupdate = TRUE
        WHERE model = 'hr.work.entry.type'
    """)
    if cr.rowcount:
        _logger.info(f"  Actualizados {cr.rowcount} registros de hr.work.entry.type (todos los modulos) a noupdate=True")

    # Proteger hr.leave.type de TODOS los modulos
    cr.execute("""
        UPDATE ir_model_data
        SET noupdate = TRUE
        WHERE model = 'hr.leave.type'
    """)
    if cr.rowcount:
        _logger.info(f"  Actualizados {cr.rowcount} registros de hr.leave.type (todos los modulos) a noupdate=True")

    # Eliminar vista heredada de hr.employee que referencia campo type_employee (ya no existe)
    # Esto fuerza a Odoo a recrearla con el XML actualizado
    _logger.info("Eliminando vista obsoleta view_lavish_hr_employee_form_employee...")
    cr.execute("""
        DELETE FROM ir_ui_view
        WHERE id IN (
            SELECT res_id FROM ir_model_data
            WHERE module = 'lavish_hr_employee'
            AND name = 'view_lavish_hr_employee_form_employee'
            AND model = 'ir.ui.view'
        )
    """)
    if cr.rowcount:
        _logger.info(f"  Vista eliminada, sera recreada con el XML actualizado")
    cr.execute("""
        DELETE FROM ir_model_data
        WHERE module = 'lavish_hr_employee'
        AND name = 'view_lavish_hr_employee_form_employee'
        AND model = 'ir.ui.view'
    """)

    _logger.info("Migracion 1.33 completada exitosamente")
