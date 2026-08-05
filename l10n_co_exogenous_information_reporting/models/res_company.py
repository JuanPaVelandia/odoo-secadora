# -*- coding: utf-8 -*-
from odoo import models


class ResCompany(models.Model):
    _inherit = 'res.company'

    def action_l10n_co_exogenous_replicate(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Replicar conceptos y retenciones',
            'res_model': 'l10n_co.exogenous_replicate_wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_source_company_id': self.id},
        }
