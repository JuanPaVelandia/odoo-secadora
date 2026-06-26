# -*- coding: utf-8 -*-
"""
Modelo hr.contractual.modifications - Modificaciones contractuales y prorrogas.
Incluye constantes TOPES_DEDUCCIONES_RTF usadas por hr_contract_deductions_rtf.
"""
from odoo import models, fields, api, _

class HrContractualModifications(models.Model):
    _name = 'hr.contractual.modifications'
    _description = 'Modificaciones contractuales'

    contract_id = fields.Many2one('hr.contract', 'Contrato', required=True, ondelete='cascade',  index=True)
    date = fields.Date('Fecha', required=True)
    description = fields.Char('Descripción de modificacion contractual', required=True)
    attached = fields.Many2one('documents.document', string='Adjunto')
    prorroga = fields.Boolean(string='Prórroga')
    wage = fields.Float('Salario basico', help='Seguimento de los cambios en el salario basico')
    sequence = fields.Integer('Numero de Prórroga')
    date_from = fields.Date('Fecha de Inicio Prórroga')
    date_to = fields.Date('Fecha de Fin Prórroga')

    @api.onchange('wage')
    def _change_wage(self):
        for line in self:
            if line.wage !=0:
                line.contract_id.change_wage_ids.create({'wage': line.wage,
                                                                    'date_start' : self.date_from,
                                                                    'contract_id':  line.contract_id.id, }) 
                line.contract_id.change_wage()

# ═══════════════════════════════════════════════════════════════════════════════
# DEDUCCIONES PARA RETENCIÓN EN LA FUENTE
# Base Legal: Art. 387 ET, Art. 126-1 y 126-4 ET
# ═══════════════════════════════════════════════════════════════════════════════

# Constantes de topes normativos (UVT)
TOPES_DEDUCCIONES_RTF = {
    'DEDDEP': {'uvt_mensual': 32, 'uvt_anual': 384, 'base_legal': 'Art. 387 Num. 1 ET', 'porcentaje_base': 10},
    'MEDPRE': {'uvt_mensual': 16, 'uvt_anual': 192, 'base_legal': 'Art. 387 Num. 2 ET'},
    'INTVIV': {'uvt_mensual': 100, 'uvt_anual': 1200, 'base_legal': 'Art. 119 y 387 Num. 3 ET'},
    'AFC': {'uvt_mensual': 316.67, 'uvt_anual': 3800, 'base_legal': 'Art. 126-4 ET', 'porcentaje_limite': 30},
    'AVC': {'uvt_mensual': 316.67, 'uvt_anual': 3800, 'base_legal': 'Art. 126-1 ET', 'porcentaje_limite': 30},
}

