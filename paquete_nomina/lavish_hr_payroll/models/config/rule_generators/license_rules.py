# -*- coding: utf-8 -*-
"""
Generador de Reglas de Licencias y Ausencias
=============================================
Genera reglas salariales para licencias remuneradas, no remuneradas y ausencias.
"""


class LicenseRulesGenerator:
    """Generador de reglas de licencias y ausencias"""
    
    @staticmethod
    def get_rules():
        """
        Retorna lista de reglas de licencias y ausencias.
        
        Returns:
            list: Lista de diccionarios con propiedades de reglas
        """
        return [
            # ACCIDENTE DE TRABAJO
            {
                'code': 'AT',
                'name': 'ACCIDENTE DE TRABAJO',
                'category_code': 'ACCIDENTE_TRABAJO',
                'sequence': 9,
                'process_code': 'nomina',
                'is_leave': True
            },
            {
                'code': 'EP',
                'name': 'ENFERMEDAD PROFESIONAL',
                'category_code': 'ACCIDENTE_TRABAJO',
                'sequence': 10,
                'process_code': 'nomina',
                'is_leave': True
            },
            
            # LICENCIAS REMUNERADAS
            {
                'code': 'MAT',
                'name': 'LICENCIA DE MATERNIDAD',
                'category_code': 'LICENCIA_MATERNIDAD',
                'sequence': 11,
                'process_code': 'nomina',
                'is_leave': True
            },
            {
                'code': 'PAT',
                'name': 'LICENCIA DE PATERNIDAD',
                'category_code': 'LICENCIA_MATERNIDAD',
                'sequence': 12,
                'process_code': 'nomina',
                'is_leave': True
            },
            {
                'code': 'LICENCIA001',
                'name': 'LICENCIA REMUNERADA',
                'category_code': 'LICENCIA_REMUNERADA',
                'sequence': 13,
                'process_code': 'nomina',
                'is_leave': True
            },
            {
                'code': 'LUTO',
                'name': 'LUTO',
                'category_code': 'LICENCIA_REMUNERADA',
                'sequence': 14,
                'process_code': 'nomina',
                'is_leave': True
            },
            
            # AUSENCIAS NO PAGADAS (No suman a TOTALDEV)
            {
                'code': 'LICENCIA_NO_REMUNERADA',
                'name': 'LICENCIA NO REMUNERADA',
                'category_code': 'AUSENCIA_NO_PAGO',
                'sequence': 16,
                'process_code': 'nomina',
                'is_leave': True
            },
            {
                'code': 'INAS_INJU',
                'name': 'INASISTENCIA INJUSTIFICADA',
                'category_code': 'AUSENCIA_NO_PAGO',
                'sequence': 17,
                'process_code': 'nomina',
                'is_leave': True
            },
            {
                'code': 'INAS_INJU_D',
                'name': 'AUSENCIA INJUSTIFICADA DOMINICAL',
                'category_code': 'AUSENCIA_NO_PAGO',
                'sequence': 17.5,
                'process_code': 'nomina',
                'is_leave': True
            },
            {
                'code': 'SUSP_CONTRATO',
                'name': 'SUSPENSIÓN DEL CONTRATO',
                'category_code': 'AUSENCIA_NO_PAGO',
                'sequence': 18,
                'process_code': 'nomina',
                'is_leave': True
            },
            {
                'code': 'SANCION',
                'name': 'SANCION',
                'category_code': 'SANCIONES',
                'sequence': 19,
                'process_code': 'nomina',
                'is_leave': True
            },
        ]
