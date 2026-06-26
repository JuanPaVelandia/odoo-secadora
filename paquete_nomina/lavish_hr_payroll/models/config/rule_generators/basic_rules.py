# -*- coding: utf-8 -*-
"""
Generador de Reglas de Salario Básico
======================================
Genera reglas salariales para salarios básicos e integrales.
"""


class BasicRulesGenerator:
    """Generador de reglas de salario básico"""
    
    @staticmethod
    def get_rules():
        """
        Retorna lista de reglas de salario básico.
        
        Returns:
            list: Lista de diccionarios con propiedades de reglas
        """
        return [
            {
                'code': 'BASIC',
                'name': 'SALARIO BÁSICO',
                'category_code': 'BASIC',
                'sequence': 1,
                'process_code': 'nomina',
                'modality_value': 'diario'
            },
            {
                'code': 'BASIC002',
                'name': 'SALARIO INTEGRAL',
                'category_code': 'BASIC',
                'sequence': 2,
                'process_code': 'nomina',
                'modality_value': 'diario'
            },
            {
                'code': 'BASIC003',
                'name': 'AUXILIO DE SOSTENIMIENTO',
                'category_code': 'BASIC',
                'sequence': 3,
                'process_code': 'nomina',
                'modality_value': 'diario'
            },
            {
                'code': 'BASIC004',
                'name': 'SUELDO TIEMPO PARCIAL',
                'category_code': 'BASIC',
                'sequence': 4,
                'process_code': 'nomina',
                'modality_value': 'diario'
            },
            {
                'code': 'BASIC005',
                'name': 'SUELDO POR DIA',
                'category_code': 'BASIC',
                'sequence': 5,
                'process_code': 'nomina',
                'modality_value': 'diario'
            },
        ]
