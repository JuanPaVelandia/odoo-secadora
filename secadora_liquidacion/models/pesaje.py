# -*- coding: utf-8 -*-

from odoo import models, fields
from odoo.tools import float_compare


class SecadoraPesaje(models.Model):
    _inherit = 'secadora.pesaje'

    liquidacion_id = fields.Many2one(
        'secadora.liquidacion',
        string='Liquidación',
        index=True,
        readonly=True,
        copy=False,
    )

    # Campos del pesaje cuyo cambio afecta el peso comercial o el precio
    # sugeridos de una línea de liquidación.
    _CAMPOS_AFECTAN_LIQUIDACION = (
        'peso_bruto', 'peso_tara', 'variedad_id', 'tercero_id', 'fecha',
    )

    def write(self, vals):
        # Capturar, ANTES de escribir, el peso/precio que cada línea de
        # liquidación en borrador tenía sugerido. Tras el cambio, solo
        # re-sincronizamos las líneas cuyo valor aún coincide con el sugerido
        # viejo (es decir, no fueron ajustadas a mano por el liquidador).
        afecta = any(c in vals for c in self._CAMPOS_AFECTAN_LIQUIDACION)
        pendientes = []  # (linea, sugerido_peso_viejo, sugerido_precio_viejo)
        if afecta:
            LineaLiq = self.env['secadora.liquidacion.linea']
            lineas = LineaLiq.search([
                ('pesaje_id', 'in', self.ids),
                ('liquidacion_id.state', '=', 'borrador'),
            ])
            for linea in lineas:
                pendientes.append((
                    linea,
                    linea._peso_comercial_sugerido(),
                    linea._precio_sugerido(),
                ))

        res = super().write(vals)

        for linea, peso_viejo, precio_viejo in pendientes:
            sync_vals = {}
            # Solo actualizar si la línea NO fue editada a mano (aún coincide
            # con lo que el pesaje sugería antes del cambio).
            if float_compare(linea.peso_comercial, peso_viejo, precision_digits=2) == 0:
                nuevo = linea._peso_comercial_sugerido()
                if float_compare(nuevo, peso_viejo, precision_digits=2) != 0:
                    sync_vals['peso_comercial'] = nuevo
            if float_compare(linea.precio, precio_viejo, precision_digits=2) == 0:
                nuevo = linea._precio_sugerido()
                if float_compare(nuevo, precio_viejo, precision_digits=2) != 0:
                    sync_vals['precio'] = nuevo
            if sync_vals:
                linea.write(sync_vals)

        return res
