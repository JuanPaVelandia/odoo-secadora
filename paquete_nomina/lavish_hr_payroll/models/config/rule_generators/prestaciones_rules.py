# -*- coding: utf-8 -*-
"""
Generador de Reglas de Prestaciones Sociales
============================================
Genera reglas salariales para prima, cesantías e intereses de cesantías.
"""


class PrestacionesRulesGenerator:
    """Generador de reglas de prestaciones sociales"""
    
    @staticmethod
    def get_rules():
        """
        Retorna lista de reglas de prestaciones sociales.
        
        Returns:
            list: Lista de diccionarios con propiedades de reglas
        """
        return [
            # PRIMA
            {
                'code': 'PRIMA',
                'name': 'PRIMA BASE',
                'category_code': 'PRESTACIONES_SOCIALES',
                'sequence': 190,
                'process_code': 'prima'
            },
            
            # CESANTÍAS
            {
                'code': 'CESANTIAS',
                'name': 'CESANTIAS',
                'category_code': 'PRESTACIONES_SOCIALES',
                'sequence': 195,
                'process_code': 'cesantias'
            },
            {
                'code': 'CES_YEAR',
                'name': 'CESANTIAS AÑO ANTERIOR',
                'category_code': 'PRESTACIONES_SOCIALES',
                'sequence': 195,
                'process_code': 'cesantias'
            },
            
            # INTERESES DE CESANTÍAS
            {
                'code': 'INTCESANTIAS',
                'name': 'INTERESES DE CESANTIAS BASE',
                'category_code': 'PRESTACIONES_SOCIALES',
                'sequence': 196,
                'process_code': 'intereses_cesantias'
            },
            {
                'code': 'INTCES_YEAR',
                'name': 'INTERESES DE CESANTIAS AÑO ANTERIOR',
                'category_code': 'PRESTACIONES_SOCIALES',
                'sequence': 196,
                'process_code': 'intereses_cesantias'
            },
        ]
