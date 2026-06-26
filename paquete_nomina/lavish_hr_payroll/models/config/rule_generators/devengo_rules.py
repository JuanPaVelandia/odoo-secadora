# -*- coding: utf-8 -*-
"""
Generador de Reglas de Devengos
================================
Genera reglas salariales para devengos salariales y no salariales.
"""


class DevengoRulesGenerator:
    """Generador de reglas de devengos"""
    
    @staticmethod
    def get_rules():
        """
        Retorna lista de reglas de devengos.
        
        Returns:
            list: Lista de diccionarios con propiedades de reglas
        """
        return [
            # DEVENGOS SALARIALES - NÓMINA
            {
                'code': 'BONIF',
                'name': 'BONIFICACIÓN',
                'category_code': 'DEV_SALARIAL',
                'sequence': 10,
                'process_code': 'nomina'
            },
            {
                'code': 'COMISIONES',
                'name': 'COMISIONES',
                'category_code': 'DEV_SALARIAL',
                'sequence': 31,
                'process_code': 'nomina'
            },
            {
                'code': 'AUX128',
                'name': 'MENOR VALOR PAGADO SALARIO',
                'category_code': 'DEV_SALARIAL',
                'sequence': 32,
                'process_code': 'nomina'
            },
            {
                'code': 'RETRO',
                'name': 'RETROACTIVO',
                'category_code': 'DEV_SALARIAL',
                'sequence': 33,
                'process_code': 'nomina'
            },
            
            # DEVENGOS NO SALARIALES - NÓMINA (condition_select='none', modality_value='fijo')
            {
                'code': 'BONOPRI',
                'name': 'BONO PRIMA',
                'category_code': 'DEV_NO_SALARIAL',
                'sequence': 44,
                'process_code': 'nomina'
            },
            {
                'code': 'AUX110',
                'name': 'AUXILIO DE ALIMENTACION',
                'category_code': 'DEV_NO_SALARIAL',
                'sequence': 45,
                'process_code': 'nomina'
            },
            {
                'code': 'AUX111',
                'name': 'AUXILIO DE MOVILIDAD',
                'category_code': 'DEV_NO_SALARIAL',
                'sequence': 46,
                'process_code': 'nomina'
            },
            {
                'code': 'AUX112',
                'name': 'AUXILIO DE HERRAMIENTAS',
                'category_code': 'DEV_NO_SALARIAL',
                'sequence': 47,
                'process_code': 'nomina'
            },
            {
                'code': 'DEV116',
                'name': 'DEVOLUCIÓN RETENCIÓN FUENTE',
                'category_code': 'DEV_NO_SALARIAL',
                'sequence': 48,
                'process_code': 'nomina'
            },
            {
                'code': 'AUX120',
                'name': 'AUXILIO DICIEMBRE',
                'category_code': 'DEV_NO_SALARIAL',
                'sequence': 60,
                'process_code': 'nomina'
            },
            {
                'code': 'BONNS',
                'name': 'BONIFICACIÓN NO SALARIAL',
                'category_code': 'DEV_NO_SALARIAL',
                'sequence': 75,
                'process_code': 'nomina'
            },
            
            # INTERESES DE VIVIENDA
            {
                'code': 'INTVIV',
                'name': 'INTERESE DE VIVIENDA',
                'category_code': 'INTVIV',
                'sequence': 34,
                'process_code': 'nomina'
            },
        ]
