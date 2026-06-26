# -*- coding: utf-8 -*-
"""
Generador de Reglas Totalizadoras
==================================
Genera reglas salariales para totalizadores (TOTALDEV, TOTALDED, NET, IBD, etc.).
"""


class TotalizerRulesGenerator:
    """Generador de reglas totalizadoras"""
    
    @staticmethod
    def get_rules():
        """
        Retorna lista de reglas totalizadoras.
        
        Returns:
            list: Lista de diccionarios con propiedades de reglas
        """
        return [
            {
                'code': 'DEDDEP',
                'name': 'DEPENDIENTES',
                'category_code': 'GROSS',
                'sequence': 15,
                'process_code': 'nomina',
                'appears_on_payslip': False
            },
            {
                'code': 'IBD',
                'name': 'IBC SEGURIDAD SOCIAL',
                'category_code': 'BASE_SEC',
                'sequence': 199,
                'process_code': 'nomina',
                'appears_on_payslip': False
            },
            {
                'code': 'TOTALDEV',
                'name': 'TOTAL DEVENGO',
                'category_code': 'TOTALDEV',
                'sequence': 199,
                'process_code': 'nomina',
                'rule_type': 'totalizador'
            },
            {
                'code': 'TOTALDED',
                'name': 'TOTAL DEDUCCIONES',
                'category_code': 'TOTALDED',
                'sequence': 299,
                'process_code': 'nomina',
                'rule_type': 'totalizador'
            },
            {
                'code': 'NET',
                'name': 'NETO A PAGAR SALARIO',
                'category_code': 'NET',
                'sequence': 300,
                'process_code': 'nomina',
                'rule_type': 'totalizador'
            },
        ]
