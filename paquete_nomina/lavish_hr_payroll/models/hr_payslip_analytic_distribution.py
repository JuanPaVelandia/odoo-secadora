# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    # Campo para distribución analítica múltiple
    analytic_distribution = fields.Json(
        string='Distribución Analítica',
        help='Distribución analítica para esta nómina. Permite distribuir los costos entre múltiples cuentas analíticas.'
    )
    
    # Mantener el campo existente para compatibilidad
    analytic_account_id = fields.Many2one(
        'account.analytic.account', 
        string='Cuenta Analítica Principal',
        help='Cuenta analítica principal (para compatibilidad). Usar Distribución Analítica para distribución múltiple.'
    )

    @api.onchange('employee_id')
    def _onchange_employee_id_analytic(self):
        """Establecer cuenta analítica por defecto desde el contrato"""
        if self.employee_id and self.contract_id and self.contract_id.analytic_account_id:
            # Si hay cuenta analítica en el contrato, establecerla al 100%
            self.analytic_distribution = {
                str(self.contract_id.analytic_account_id.id): 100.0
            }
            self.analytic_account_id = self.contract_id.analytic_account_id

    @api.constrains('analytic_distribution')
    def _check_analytic_distribution(self):
        """Validar que la distribución analítica sume 100%"""
        for payslip in self:
            if payslip.analytic_distribution:
                total = sum(payslip.analytic_distribution.values())
                if abs(total - 100.0) > 0.01:  # Tolerancia de 0.01%
                    raise ValidationError(
                        _('La distribución analítica debe sumar 100%%. Actual: %s%%') % total
                    )

    def get_effective_analytic_distribution(self):
        """Obtener la distribución analítica efectiva para esta nómina"""
        self.ensure_one()
        
        # 1. Si hay distribución específica en la nómina, usarla
        if self.analytic_distribution:
            return self.analytic_distribution
                
        # 2. Si hay cuenta analítica en el contrato, usarla al 100%
        if self.contract_id and self.contract_id.analytic_account_id:
            return {str(self.contract_id.analytic_account_id.id): 100.0}
            
        # 3. Si hay cuenta analítica directa (campo legacy), usarla
        if self.analytic_account_id:
            return {str(self.analytic_account_id.id): 100.0}
            
        return {}


class HrPayslipLine(models.Model):
    _inherit = 'hr.payslip.line'

    def get_analytic_distribution(self):
        """Obtener distribución analítica para esta línea de nómina"""
        self.ensure_one()
        return self.slip_id.get_effective_analytic_distribution()
