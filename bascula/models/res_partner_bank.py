# -*- coding: utf-8 -*-

from odoo import models, fields


class ResPartnerBank(models.Model):
    """Tipo de cuenta bancaria (Ahorros/Corriente/Nequi/Daviplata).

    En la v18 este campo lo aportaba el módulo de terceros lavish_erp, que no
    está en la v19. Se replica aquí con el MISMO nombre técnico y los mismos
    valores de selección: así los datos ya guardados en la base (columna
    type_account de res_partner_bank) reviven sin migración, y el reporte de
    viajes por pagar de secadora_transporte lo encuentra igual que antes.
    """
    _inherit = 'res.partner.bank'

    type_account = fields.Selection([
        ('A', 'Ahorros'),
        ('C', 'Corriente'),
        ('DP', 'Daviplata'),
        ('N', 'Nequi'),
    ], string='Tipo de Cuenta')
