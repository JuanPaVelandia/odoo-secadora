# -*- coding: utf-8 -*-
"""
Generador de Reglas de Horas Extras y Recargos
===============================================
Genera reglas salariales para horas extras y recargos dominicales/nocturnos.
"""


class OvertimeRulesGenerator:
    """Generador de reglas de horas extras y recargos"""
    
    @staticmethod
    def get_rules():
        """
        Retorna lista de reglas de horas extras y recargos.
        
        Returns:
            list: Lista de diccionarios con propiedades de reglas
        """
        return [
            {
                'code': 'HEYREC001',
                'name': 'HORAS EXTRA DIURNAS (125%)',
                'category_code': 'HEYREC',
                'sequence': 36,
                'process_code': 'nomina',
                'is_recargo': True
            },
            {
                'code': 'HEYREC002',
                'name': 'HORAS EXTRA DIURNAS DOMINICAL / FESTIVA (200%)',
                'category_code': 'HEYREC',
                'sequence': 37,
                'process_code': 'nomina',
                'is_recargo': True,
                'modality_value': 'diario'
            },
            {
                'code': 'HEYREC003',
                'name': 'HORAS EXTRA NOCTURNA (175%)',
                'category_code': 'HEYREC',
                'sequence': 38,
                'process_code': 'nomina',
                'is_recargo': True,
                'modality_value': 'diario'
            },
            {
                'code': 'HEYREC004',
                'name': 'HORAS RECARGO FESTIVO (0.75)',
                'category_code': 'HEYREC',
                'sequence': 39,
                'process_code': 'nomina',
                'is_recargo': True,
                'modality_value': 'diario'
            },
            {
                'code': 'HEYREC005',
                'name': 'HORAS RECARGO NOCTURNO (35%)',
                'category_code': 'HEYREC',
                'sequence': 40,
                'process_code': 'nomina',
                'is_recargo': True
            },
            {
                'code': 'HEYREC006',
                'name': 'HORAS EXTRA NOCTURNA DOMINICAL / FESTIVA (250%)',
                'category_code': 'HEYREC',
                'sequence': 41,
                'process_code': 'nomina',
                'is_recargo': True
            },
            {
                'code': 'HEYREC007',
                'name': 'HORAS DOMINICALES (1.75%)',
                'category_code': 'HEYREC',
                'sequence': 42,
                'process_code': 'nomina',
                'is_recargo': True,
                'modality_value': 'diario'
            },
            {
                'code': 'HEYREC008',
                'name': 'HORAS DE RECARGO NOCTURNO DOMINICAL/FESTIVO (1.1%)',
                'category_code': 'HEYREC',
                'sequence': 43,
                'process_code': 'nomina',
                'is_recargo': True,
                'modality_value': 'diario'
            },
            {
                'code': 'HEYREC009',
                'name': 'HORAS DE RECARGO NOCTURNO DOMINICAL/FESTIVO (210 %)',
                'category_code': 'HEYREC',
                'sequence': 43,
                'process_code': 'nomina',
                'is_recargo': True,
                'modality_value': 'diario'
            },
        ]
