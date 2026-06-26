# -*- coding: utf-8 -*-
"""
Generador de Reglas de Incapacidad
===================================
Genera reglas salariales para incapacidades EPS y compañía.
"""


class IncapacityRulesGenerator:
    """Generador de reglas de incapacidad"""
    
    @staticmethod
    def get_rules():
        """
        Retorna lista de reglas de incapacidad.
        
        Returns:
            list: Lista de diccionarios con propiedades de reglas
        """
        return [
            {
                'code': 'INCAPACIDAD001',
                'name': 'INCAPACIDAD EPS',
                'category_code': 'INCAPACIDAD',
                'sequence': 5,
                'process_code': 'nomina',
                'is_leave': True
            },
            {
                'code': 'INCAPACIDAD002',
                'name': 'INCAPACIDAD COMPAÑÍA',
                'category_code': 'INCAPACIDAD',
                'sequence': 6,
                'process_code': 'nomina',
                'is_leave': True
            },
            {
                'code': 'INCAPACIDAD007',
                'name': 'INCAPACIDAD EPS 50%',
                'category_code': 'INCAPACIDAD',
                'sequence': 7,
                'process_code': 'nomina',
                'is_leave': True
            },
            {
                'code': 'EGH',
                'name': 'AUSENCIA POR ENFERMEDAD 66%',
                'category_code': 'INCAPACIDAD',
                'sequence': 8,
                'process_code': 'nomina',
                'is_leave': True
            },
        ]
