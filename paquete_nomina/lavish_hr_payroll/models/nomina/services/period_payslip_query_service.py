# -*- coding: utf-8 -*-
"""
Extensión del Servicio de Consultas Consolidadas para Nómina
============================================================

Este módulo extiende el servicio base de lavish_hr_employee con métodos
específicos de nómina para facilitar el uso.
"""

from odoo import models


class PeriodPayslipQueryServicePayroll(models.AbstractModel):
    """
    Extensión del servicio de consultas consolidadas con métodos específicos de nómina.
    
    Hereda del servicio base en lavish_hr_employee y agrega métodos wrapper
    para facilitar el uso en cálculos de nómina.
    """
    _name = 'period.payslip.query.service'
    _inherit = 'period.payslip.query.service'
    _description = 'Servicio de consultas consolidadas por período (Extensión Nómina)'

    def get_ibd_data(self, contract_id, date_from, date_to, exclude_payslip_id=None, states=('done', 'paid')):
        """
        Wrapper para obtener datos de IBD usando la consulta de nómina.
        
        Args:
            contract_id: ID del contrato
            date_from: Fecha inicio del período de acumulación
            date_to: Fecha fin del período de acumulación
            exclude_payslip_id: ID de nómina a excluir
            states: Estados de nómina a incluir
        
        Returns:
            dict: {
                'total': float,
                'total_salary': float,
                'total_no_salary': float,
                'list': [...],
                'by_period': {...}
            }
        """
        result = self.get_period_payslip_data(
            contract_id=contract_id,
            date_from=date_from,
            date_to=date_to,
            calculation_type='ibd',
            exclude_payslip_id=exclude_payslip_id,
            states=states,
        )
        
        # Adaptar estructura de retorno para compatibilidad
        return {
            'total': result['total'],
            'total_salary': result['totals_by_type']['total_salary'],
            'total_no_salary': result['totals_by_type']['total_no_salary'],
            'list': result['tree'],
            'by_period': result['by_period'],
        }

    def get_retenciones_data(
        self,
        contract_id,
        date_from,
        date_to,
        exclude_payslip_id=None,
        states=('done', 'paid'),
        exclude_codes=None,
        include_categories=None
    ):
        """
        Wrapper para obtener datos de retención usando la consulta genérica.
        
        Args:
            contract_id: ID del contrato
            date_from: Fecha inicio del período de acumulación
            date_to: Fecha fin del período de acumulación
            exclude_payslip_id: ID de nómina a excluir
            states: Estados de nómina a incluir
            exclude_codes: Lista de códigos de reglas a excluir
            include_categories: Lista de categorías a incluir
        
        Returns:
            dict: {
                'total': float,
                'total_basic': float,
                'total_devengos': float,
                'total_dev_no_salarial': float,
                'list': [...],
                'by_period': {...},
                'by_category': {...}
            }
        """
        result = self.get_period_payslip_data(
            contract_id=contract_id,
            date_from=date_from,
            date_to=date_to,
            calculation_type='retenciones',
            exclude_payslip_id=exclude_payslip_id,
            states=states,
            exclude_codes=exclude_codes,
            include_categories=include_categories,
        )
        
        # Adaptar estructura de retorno
        return {
            'total': result['total'],
            'total_basic': result['totals_by_type']['total_basic'],
            'total_devengos': result['totals_by_type']['total_devengos'],
            'total_dev_no_salarial': result['totals_by_type']['total_dev_no_salarial'],
            'list': result['tree'],
            'by_period': result['by_period'],
            'by_category': result.get('by_category', {}),
        }

    def get_prestaciones_data(
        self,
        contract_id,
        date_from,
        date_to,
        tipo_prestacion,
        exclude_payslip_id=None,
        states=('done', 'paid'),
        excluded_categories=None
    ):
        """
        Wrapper para obtener datos de prestaciones usando la consulta genérica.
        
        Args:
            contract_id: ID del contrato
            date_from: Fecha inicio del período de acumulación
            date_to: Fecha fin del período de acumulación
            tipo_prestacion: Tipo de prestación ('prima', 'cesantias', 'vacaciones', 'intereses_cesantias', 'all')
            exclude_payslip_id: ID de nómina a excluir
            states: Estados de nómina a incluir
            excluded_categories: Lista de categorías a excluir
        
        Returns:
            dict: {
                'total': float,
                'total_basic': float,
                'total_variables': float,
                'list': [...],
                'by_period': {...},
                'by_base_field': {...}
            }
        """
        result = self.get_period_payslip_data(
            contract_id=contract_id,
            date_from=date_from,
            date_to=date_to,
            calculation_type='prestaciones',
            exclude_payslip_id=exclude_payslip_id,
            states=states,
            tipo_prestacion=tipo_prestacion,
            excluded_categories=excluded_categories,
        )
        
        # Adaptar estructura de retorno
        return {
            'total': result['total'],
            'total_basic': result['totals_by_type']['total_basic'],
            'total_variables': result['totals_by_type']['total_variables'],
            'tree': result['tree'],
            'by_period': result['by_period'],
            'by_base_field': result.get('by_base_field', {}),
        }
