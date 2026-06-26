# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Migracion 1.32: Prevenir eliminacion de estructuras de nomina con reglas asociadas.

    Marca los registros de hr.payroll.structure, hr.salary.rule.category y hr.salary.rule
    como noupdate=True para evitar que Odoo intente eliminarlos durante la actualizacion.
    """
    _logger.info("Iniciando migracion 1.32: Proteccion de estructuras de nomina...")

    # Prevenir que Odoo intente eliminar estructuras de nomina que tienen reglas asociadas
    _logger.info("Marcando estructuras de nomina como noupdate=True...")
    cr.execute("""
        UPDATE ir_model_data
        SET noupdate = TRUE
        WHERE model = 'hr.payroll.structure'
        AND module = 'lavish_hr_employee'
    """)
    if cr.rowcount:
        _logger.info(f"  Actualizados {cr.rowcount} registros de hr.payroll.structure a noupdate=True")

    # Marcar las categorias de reglas salariales
    cr.execute("""
        UPDATE ir_model_data
        SET noupdate = TRUE
        WHERE model = 'hr.salary.rule.category'
        AND module = 'lavish_hr_employee'
    """)
    if cr.rowcount:
        _logger.info(f"  Actualizados {cr.rowcount} registros de hr.salary.rule.category a noupdate=True")

    # Marcar las reglas salariales
    cr.execute("""
        UPDATE ir_model_data
        SET noupdate = TRUE
        WHERE model = 'hr.salary.rule'
        AND module = 'lavish_hr_employee'
    """)
    if cr.rowcount:
        _logger.info(f"  Actualizados {cr.rowcount} registros de hr.salary.rule a noupdate=True")

    # Marcar los tipos de cotizante
    cr.execute("""
        UPDATE ir_model_data
        SET noupdate = TRUE
        WHERE model = 'hr.tipo.cotizante'
        AND module = 'lavish_hr_employee'
    """)
    if cr.rowcount:
        _logger.info(f"  Actualizados {cr.rowcount} registros de hr.tipo.cotizante a noupdate=True")

    # Marcar los tipos de empleado
    cr.execute("""
        UPDATE ir_model_data
        SET noupdate = TRUE
        WHERE model = 'hr.type.employee'
        AND module = 'lavish_hr_employee'
    """)
    if cr.rowcount:
        _logger.info(f"  Actualizados {cr.rowcount} registros de hr.type.employee a noupdate=True")

    # Marcar los tipos de entrada de trabajo (work entry types)
    cr.execute("""
        UPDATE ir_model_data
        SET noupdate = TRUE
        WHERE model = 'hr.work.entry.type'
        AND module = 'lavish_hr_employee'
    """)
    if cr.rowcount:
        _logger.info(f"  Actualizados {cr.rowcount} registros de hr.work.entry.type a noupdate=True")

    # Marcar los tipos de ausencia (leave types)
    cr.execute("""
        UPDATE ir_model_data
        SET noupdate = TRUE
        WHERE model = 'hr.leave.type'
        AND module = 'lavish_hr_employee'
    """)
    if cr.rowcount:
        _logger.info(f"  Actualizados {cr.rowcount} registros de hr.leave.type a noupdate=True")

    # Marcar los indicadores especiales de pensiones
    cr.execute("""
        UPDATE ir_model_data
        SET noupdate = TRUE
        WHERE model = 'hr.indicador.especial.pensiones'
        AND module = 'lavish_hr_employee'
    """)
    if cr.rowcount:
        _logger.info(f"  Actualizados {cr.rowcount} registros de hr.indicador.especial.pensiones a noupdate=True")

    # Marcar structure types
    cr.execute("""
        UPDATE ir_model_data
        SET noupdate = TRUE
        WHERE model = 'hr.payroll.structure.type'
        AND module = 'lavish_hr_employee'
    """)
    if cr.rowcount:
        _logger.info(f"  Actualizados {cr.rowcount} registros de hr.payroll.structure.type a noupdate=True")

    _logger.info("Migracion 1.32 completada exitosamente")
