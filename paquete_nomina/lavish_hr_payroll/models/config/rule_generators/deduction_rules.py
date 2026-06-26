# -*- coding: utf-8 -*-
"""
Generador de Reglas de Deducciones
==================================
Genera reglas salariales para deducciones (retenciones, préstamos, embargos, etc.).
"""


class DeductionRulesGenerator:
    """Generador de reglas de deducciones"""
    
    @staticmethod
    def get_rules():
        """
        Retorna lista de reglas de deducciones.
        
        Returns:
            list: Lista de diccionarios con propiedades de reglas
        """
        return [
            # RETENCIÓN EN LA FUENTE
            {
                'code': 'RT_MET_01',
                'name': 'RETENCIÓN EN LA FUENTE',
                'category_code': 'DEDUCCIONES',
                'sequence': 204,
                'process_code': 'nomina',
                'dev_or_ded': 'deduccion'
            },
            {
                'code': 'RET_PRIMA',
                'name': 'RETENCION PRIMA',
                'category_code': 'DEDUCCIONES',
                'sequence': 205,
                'process_code': 'prima',
                'dev_or_ded': 'deduccion'
            },
            {
                'code': 'RTF_INDEM',
                'name': 'RETENCION INDEMNIZACIONES',
                'category_code': 'DEDUCCIONES',
                'sequence': 206,
                'process_code': 'contrato',
                'dev_or_ded': 'deduccion'
            },
            
            # PRÉSTAMOS
            {
                'code': 'P01',
                'name': 'PRESTAMO EMPLEADO',
                'category_code': 'DEDUCCIONES',
                'sequence': 206,
                'process_code': 'nomina',
                'dev_or_ded': 'deduccion'
            },
            
            # EMBARGOS
            {
                'code': 'EMBARGO001',
                'name': 'EMBARGO 1 - CONCEPTO',
                'category_code': 'EM',
                'sequence': 210,
                'process_code': 'nomina',
                'dev_or_ded': 'deduccion'
            },
            {
                'code': 'EMBARGO002',
                'name': 'EMBARGO 2 - CONCEPTO',
                'category_code': 'EM',
                'sequence': 211,
                'process_code': 'nomina',
                'dev_or_ded': 'deduccion'
            },
            {
                'code': 'EMBARGO003',
                'name': 'EMBARGO 3 - CONCEPTO',
                'category_code': 'EM',
                'sequence': 212,
                'process_code': 'nomina',
                'dev_or_ded': 'deduccion'
            },
            {
                'code': 'EMBARGO004',
                'name': 'EMBARGO 4 - CONCEPTO',
                'category_code': 'EM',
                'sequence': 213,
                'process_code': 'nomina',
                'dev_or_ded': 'deduccion'
            },
            {
                'code': 'EMBARGO005',
                'name': 'EMBARGO 5 - CONCEPTO',
                'category_code': 'EM',
                'sequence': 214,
                'process_code': 'nomina',
                'dev_or_ded': 'deduccion'
            },
            {
                'code': 'EMBARGO007',
                'name': 'EMBARGO SALARIAL %',
                'category_code': 'EM',
                'sequence': 215,
                'process_code': 'nomina',
                'dev_or_ded': 'deduccion',
                'modality_value': 'diario'
            },
            {
                'code': 'EMBARGO009',
                'name': 'EMBARGO SALARIAL FIJO',
                'category_code': 'EM',
                'sequence': 216,
                'process_code': 'nomina',
                'dev_or_ded': 'deduccion'
            },
            
            # OTRAS DEDUCCIONES
            {
                'code': 'MEDPRE',
                'name': 'MEDPRE',
                'category_code': 'DEDUCCIONES',
                'sequence': 215,
                'process_code': 'nomina',
                'dev_or_ded': 'deduccion'
            },
            {
                'code': 'VIATICOS',
                'name': 'VIATICOS OCASIONALES',
                'category_code': 'DEDUCCIONES',
                'sequence': 250,
                'process_code': 'nomina',
                'dev_or_ded': 'deduccion'
            },
            {
                'code': 'LIBRANZA',
                'name': 'LIBRANZA DESCUENTO',
                'category_code': 'DEDUCCIONES',
                'sequence': 260,
                'process_code': 'nomina',
                'dev_or_ded': 'deduccion'
            },
            {
                'code': 'ERROR',
                'name': 'DESCUENTO ERRORES',
                'category_code': 'DEDUCCIONES',
                'sequence': 261,
                'process_code': 'nomina',
                'dev_or_ded': 'deduccion'
            },
            {
                'code': 'HORAS',
                'name': 'DESCUENTO HORAS',
                'category_code': 'DEDUCCIONES',
                'sequence': 262,
                'process_code': 'nomina',
                'dev_or_ded': 'deduccion'
            },
            {
                'code': 'ANTICIPO',
                'name': 'ANTICIPO NÓMINA',
                'category_code': 'DEDUCCIONES',
                'sequence': 263,
                'process_code': 'nomina',
                'dev_or_ded': 'deduccion'
            },
            {
                'code': 'AVP',
                'name': 'APORTES VOLUNTARIOS PENSIÓN',
                'category_code': 'DEDUCCIONES',
                'sequence': 270,
                'process_code': 'nomina',
                'dev_or_ded': 'deduccion'
            },
            {
                'code': 'PRESTAMO',
                'name': 'PRESTAMO NOVEDAD',
                'category_code': 'DEDUCCIONES',
                'sequence': 270,
                'process_code': 'nomina',
                'dev_or_ded': 'deduccion'
            },
            {
                'code': 'DESCUENTO',
                'name': 'DESCUENTO',
                'category_code': 'DEDUCCIONES',
                'sequence': 270,
                'process_code': 'nomina',
                'dev_or_ded': 'deduccion'
            },
            {
                'code': 'AFC',
                'name': 'APORTES CUENTAS AFC',
                'category_code': 'DEDUCCIONES',
                'sequence': 271,
                'process_code': 'nomina',
                'dev_or_ded': 'deduccion'
            },
            {
                'code': 'DEV_AUX000',
                'name': 'DEVOLUCIÓN AUX DE TRANSPORTE',
                'category_code': 'DEDUCCIONES',
                'sequence': 280,
                'process_code': 'nomina',
                'dev_or_ded': 'deduccion'
            },
            {
                'code': 'DEV_AUX00C',
                'name': 'DEVOLUCIÓN AUX DE CONECTIVIDAD',
                'category_code': 'DEDUCCIONES',
                'sequence': 281,
                'process_code': 'nomina',
                'dev_or_ded': 'deduccion'
            },
            
            # LIQUIDACIÓN DE CONTRATO
            {
                'code': 'PREAVISO',
                'name': 'INDEMNIZACIÓN PREAVISO CLAUSULA 9NA DE CONTRATO',
                'category_code': 'DEDUCCIONES',
                'sequence': 201,
                'process_code': 'contrato',
                'dev_or_ded': 'deduccion'
            },
        ]
