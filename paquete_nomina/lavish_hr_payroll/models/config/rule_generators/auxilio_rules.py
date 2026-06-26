# -*- coding: utf-8 -*-
"""
Generador de Reglas de Auxilios
================================
Genera reglas salariales para auxilio de transporte y conectividad.
"""


class AuxilioRulesGenerator:
    """Generador de reglas de auxilios"""
    
    @staticmethod
    def get_rules():
        """
        Retorna lista de reglas de auxilios.
        
        Returns:
            list: Lista de diccionarios con propiedades de reglas
        """
        return [
            {
                'code': 'AUX00C',
                'name': 'AUXILIO DE CONECTIVIDAD',
                'category_code': 'AUX',
                'sequence': 51,
                'process_code': 'nomina',
                'modality_value': 'diario'
            },
            {
                'code': 'AUX000',
                'name': 'AUXILIO DE TRANSPORTE',
                'category_code': 'AUX',
                'sequence': 182,
                'process_code': 'nomina',
                'modality_value': 'diario'
            },
            {
                'code': 'INDEM',
                'name': 'INDEMNIZACIONES',
                'category_code': 'INDEM',
                'sequence': 189,
                'process_code': 'contrato'
            },
        ]
