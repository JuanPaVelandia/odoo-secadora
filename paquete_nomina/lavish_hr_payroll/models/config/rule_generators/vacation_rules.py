# -*- coding: utf-8 -*-
"""
Generador de Reglas de Vacaciones
==================================
Genera reglas salariales para vacaciones disfrutadas y en dinero.
"""


class VacationRulesGenerator:
    """Generador de reglas de vacaciones"""
    
    @staticmethod
    def get_rules():
        """
        Retorna lista de reglas de vacaciones.
        
        Returns:
            list: Lista de diccionarios con propiedades de reglas
        """
        return [
            {
                'code': 'VACDISFRUTADAS',
                'name': 'VACACIONES DISFRUTADAS',
                'category_code': 'VACACIONES',
                'sequence': 26,
                'process_code': 'vacaciones',
                'is_leave': True
            },
            {
                'code': 'VACANOVE',
                'name': 'VACACIONES',
                'category_code': 'PRESTACIONES_SOCIALES',
                'sequence': 29,
                'process_code': 'vacaciones',
                'is_leave': True
            },
            {
                'code': 'VACCONTRATO',
                'name': 'VACACIONES',
                'category_code': 'PRESTACIONES_SOCIALES',
                'sequence': 190,
                'process_code': 'vacaciones'
            },
            {
                'code': 'VACATIONS_MONEY',
                'name': 'VACACIONES EN DINERO',
                'category_code': 'PRESTACIONES_SOCIALES',
                'sequence': 51,
                'process_code': 'vacaciones'
            },
        ]
