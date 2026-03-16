# -*- coding: utf-8 -*-

from odoo import models


class OrdenServicio(models.Model):
    _inherit = 'secadora.orden.servicio'

    def aplicar_reglas_servicios(self):
        """Extiende para copiar es_cuadrilla de la regla a la línea generada."""
        self.ensure_one()

        # Guardar líneas existentes antes de aplicar reglas
        lineas_antes = self.linea_servicio_ids

        super().aplicar_reglas_servicios()

        # Detectar líneas nuevas y marcar es_cuadrilla según la regla
        lineas_nuevas = self.linea_servicio_ids - lineas_antes
        for linea in lineas_nuevas:
            if linea.es_automatica and linea.producto_id:
                regla = self.env['secadora.servicio.regla'].search([
                    ('producto_id', '=', linea.producto_id.id),
                    ('es_cuadrilla', '=', True),
                    ('active', '=', True),
                ], limit=1)
                if regla:
                    linea.es_cuadrilla = True
