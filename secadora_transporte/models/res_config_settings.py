# -*- coding: utf-8 -*-

from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # lugar_planta_id ahora vive en bascula (bascula.lugar_planta_id)
