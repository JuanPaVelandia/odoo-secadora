# -*- coding: utf-8 -*-
"""
Migration 1.27: Eliminar modelo hr.employee.endowment (dotación legacy)
El historial de dotación ahora se maneja mediante hr.epp.dotacion y delivery_line_ids.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Elimina el modelo hr.employee.endowment y sus datos relacionados.
    """
    if not version:
        return

    _logger.info("Iniciando migración 1.27: Eliminando hr.employee.endowment...")

    # 1. Eliminar registros de ir.model.data relacionados
    cr.execute("""
        DELETE FROM ir_model_data
        WHERE model = 'hr.employee.endowment'
    """)
    _logger.info("Eliminados registros de ir.model.data")

    # 2. Eliminar campos relacionados de ir.model.fields
    cr.execute("""
        DELETE FROM ir_model_fields
        WHERE model = 'hr.employee.endowment'
    """)
    _logger.info("Eliminados registros de ir.model.fields")

    # 3. Eliminar el modelo de ir.model
    cr.execute("""
        DELETE FROM ir_model
        WHERE model = 'hr.employee.endowment'
    """)
    _logger.info("Eliminado registro de ir.model")

    # 4. Eliminar el campo One2many de hr.contract si existe
    cr.execute("""
        DELETE FROM ir_model_fields
        WHERE name = 'employee_endowment_ids'
        AND model = 'hr.contract'
    """)
    _logger.info("Eliminado campo employee_endowment_ids de hr.contract")

    # 5. Eliminar la tabla si existe
    cr.execute("""
        DROP TABLE IF EXISTS hr_employee_endowment CASCADE
    """)
    _logger.info("Eliminada tabla hr_employee_endowment")

    _logger.info("Migración 1.27 completada exitosamente")
