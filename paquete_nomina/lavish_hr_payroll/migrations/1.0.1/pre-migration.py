# -*- coding: utf-8 -*-
"""
Migración para manejar la restricción de clave foránea en hr.payslip.line.salary_rule_id
"""

import logging
from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Pre-migración para manejar la restricción de clave foránea hr_payslip_line_salary_rule_id_fkey
    """
    _logger.info("Iniciando pre-migración para lavish_hr_payroll")
    
    # Verificar si la restricción existe
    cr.execute("""
        SELECT constraint_name 
        FROM information_schema.table_constraints 
        WHERE table_name = 'hr_payslip_line' 
        AND constraint_name = 'hr_payslip_line_salary_rule_id_fkey'
        AND constraint_type = 'FOREIGN KEY'
    """)
    
    if cr.fetchone():
        _logger.info("Eliminando restricción de clave foránea hr_payslip_line_salary_rule_id_fkey")
        try:
            # Eliminar la restricción de clave foránea
            cr.execute("ALTER TABLE hr_payslip_line DROP CONSTRAINT IF EXISTS hr_payslip_line_salary_rule_id_fkey")
            cr.commit()
            _logger.info("Restricción eliminada exitosamente")
        except Exception as e:
            _logger.error(f"Error al eliminar la restricción: {e}")
            cr.rollback()
            raise
    else:
        _logger.info("La restricción hr_payslip_line_salary_rule_id_fkey no existe")
    
    # Limpiar registros huérfanos si los hay
    _logger.info("Verificando registros huérfanos en hr_payslip_line")
    cr.execute("""
        SELECT COUNT(*) FROM hr_payslip_line hpl
        LEFT JOIN hr_salary_rule hsr ON hpl.salary_rule_id = hsr.id
        WHERE hpl.salary_rule_id IS NOT NULL AND hsr.id IS NULL
    """)
    
    orphan_count = cr.fetchone()[0]
    if orphan_count > 0:
        _logger.warning(f"Se encontraron {orphan_count} registros huérfanos en hr_payslip_line")
        
        # Opción 1: Eliminar registros huérfanos (descomentar si es necesario)
        # cr.execute("""
        #     DELETE FROM hr_payslip_line 
        #     WHERE salary_rule_id NOT IN (SELECT id FROM hr_salary_rule WHERE id IS NOT NULL)
        #     AND salary_rule_id IS NOT NULL
        # """)
        
        # Opción 2: Asignar a una regla por defecto (recomendado)
        cr.execute("SELECT id FROM hr_salary_rule LIMIT 1")
        default_rule = cr.fetchone()
        
        if default_rule:
            default_rule_id = default_rule[0]
            _logger.info(f"Asignando registros huérfanos a la regla por defecto ID: {default_rule_id}")
            cr.execute("""
                UPDATE hr_payslip_line 
                SET salary_rule_id = %s
                WHERE salary_rule_id NOT IN (SELECT id FROM hr_salary_rule WHERE id IS NOT NULL)
                AND salary_rule_id IS NOT NULL
            """, (default_rule_id,))
        else:
            _logger.error("No se encontró ninguna regla salarial para asignar los registros huérfanos")
    else:
        _logger.info("No se encontraron registros huérfanos")
    
    _logger.info("Pre-migración completada exitosamente")
