# -*- coding: utf-8 -*-
"""
Post-migración para recrear la restricción de clave foránea con la configuración correcta
"""

import logging
from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Post-migración para recrear la restricción de clave foránea hr_payslip_line_salary_rule_id_fkey
    """
    _logger.info("Iniciando post-migración para lavish_hr_payroll")
    
    try:
        # Recrear la restricción de clave foránea con la configuración correcta
        _logger.info("Recreando restricción de clave foránea hr_payslip_line_salary_rule_id_fkey")
        
        # Verificar si la restricción ya existe
        cr.execute("""
            SELECT constraint_name 
            FROM information_schema.table_constraints 
            WHERE table_name = 'hr_payslip_line' 
            AND constraint_name = 'hr_payslip_line_salary_rule_id_fkey'
            AND constraint_type = 'FOREIGN KEY'
        """)
        
        if not cr.fetchone():
            # Crear la nueva restricción con SET NULL en lugar de RESTRICT
            cr.execute("""
                ALTER TABLE hr_payslip_line 
                ADD CONSTRAINT hr_payslip_line_salary_rule_id_fkey 
                FOREIGN KEY (salary_rule_id) 
                REFERENCES hr_salary_rule(id) 
                ON DELETE SET NULL
            """)
            _logger.info("Restricción de clave foránea recreada exitosamente con ON DELETE SET NULL")
        else:
            _logger.info("La restricción ya existe")
        
        # Verificar la integridad de los datos
        cr.execute("""
            SELECT COUNT(*) FROM hr_payslip_line hpl
            LEFT JOIN hr_salary_rule hsr ON hpl.salary_rule_id = hsr.id
            WHERE hpl.salary_rule_id IS NOT NULL AND hsr.id IS NULL
        """)
        
        orphan_count = cr.fetchone()[0]
        if orphan_count > 0:
            _logger.warning(f"Aún existen {orphan_count} registros con referencias inválidas")
        else:
            _logger.info("Verificación de integridad completada: todos los registros son válidos")
            
    except Exception as e:
        _logger.error(f"Error en post-migración: {e}")
        raise
    
    _logger.info("Post-migración completada exitosamente")
