# -*- coding: utf-8 -*-

from odoo import models, fields, api


class PosicionArroz(models.Model):
    _inherit = 'secadora.posicion.arroz'

    peso_estimado_seco_kg = fields.Float(
        string='Peso Estimado Seco (Kg)',
        digits=(12, 2),
        compute='_compute_peso_estimado_seco',
        help='Estimación por doble descuento: '
             'peso × (100−humedad)/(100−humedad objetivo) × (100−impurezas)/(100−impureza objetivo), '
             'donde la impureza objetivo es un porcentaje de la impureza inicial.',
    )

    def _objetivos_doble_descuento(self):
        """Umbrales configurables de la fórmula de doble descuento.

        La impureza objetivo se expresa como % de la impureza inicial de cada
        tarjeta (60 → el arroz seco conserva el 60% de la impureza medida).
        """
        Param = self.env['ir.config_parameter'].sudo()
        h_obj = float(Param.get_param('secadora_embolsado.humedad_objetivo', '13.0'))
        i_pct = float(Param.get_param('secadora_embolsado.impureza_objetivo_pct_inicial', '60.0'))
        return h_obj, i_pct

    def _estimar_peso_seco(self):
        """Peso seco estimado por doble descuento (humedad e impureza).

        Misma matemática que el modo 'doble_descuento' de secadora.descuento.calidad
        (factores (100−valor)/(100−umbral) con tope en 1.0), replicada aquí porque
        esas reglas están ancladas a tipo de operación y análisis de pesajes, no a
        posiciones del tablero. El umbral de impureza es relativo: un porcentaje
        de la impureza inicial de la tarjeta. Sin humedad registrada se devuelve
        el peso verde.
        """
        self.ensure_one()
        if not self.humedad:
            return self.peso_kg
        h_obj, i_pct = self._objetivos_doble_descuento()
        factor_h = min((100.0 - self.humedad) / (100.0 - h_obj), 1.0) if h_obj < 100 else 1.0
        factor_i = 1.0
        if self.impurezas:
            i_obj = self.impurezas * i_pct / 100.0
            if i_obj < 100:
                factor_i = min((100.0 - self.impurezas) / (100.0 - i_obj), 1.0)
        return self.peso_kg * factor_h * factor_i

    @api.depends('peso_kg', 'humedad', 'impurezas')
    def _compute_peso_estimado_seco(self):
        for rec in self:
            rec.peso_estimado_seco_kg = rec._estimar_peso_seco()

    @api.model
    def get_tablero_grid_data(self):
        res = super().get_tablero_grid_data()

        sitios_seco = set(self.env['secadora.sitio.muestra'].search([
            ('es_contenedor', '=', True),
            ('mostrar_estimacion_seco', '=', True),
        ]).ids)
        for s in res['sitios']:
            s['mostrar_estimacion_seco'] = s['id'] in sitios_seco

        pos_flag_ids = [p['id'] for p in res['posiciones'] if p['sitio_id'] in sitios_seco]
        estimados = {rec.id: rec._estimar_peso_seco() for rec in self.browse(pos_flag_ids)}
        for p in res['posiciones']:
            p['peso_estimado_seco'] = estimados.get(p['id'], 0.0)

        return res
