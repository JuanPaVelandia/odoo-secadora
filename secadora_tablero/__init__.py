# -*- coding: utf-8 -*-

from . import models
from . import wizard


def _post_init_es_comercial(env):
    """Inicializar campos nuevos en posiciones existentes."""
    PosicionArroz = env['secadora.posicion.arroz']

    # Marcar es_comercial en posiciones resultado de combinación
    posiciones_combinadas_ids = PosicionArroz.search([
        ('posicion_combinada_id', '!=', False),
    ]).mapped('posicion_combinada_id').ids

    if posiciones_combinadas_ids:
        posiciones_a_marcar = PosicionArroz.search([
            ('id', 'in', posiciones_combinadas_ids),
            ('es_comercial', '!=', True),
        ])
        if posiciones_a_marcar:
            posiciones_a_marcar.write({'es_comercial': True})

    # Copiar variedad, humedad e impurezas desde el pesaje para posiciones existentes
    posiciones_sin_datos = PosicionArroz.search([
        ('es_comercial', '!=', True),
        '|', '|',
        ('variedad_id', '=', False),
        ('humedad', '=', 0),
        ('impurezas', '=', 0),
    ])
    for pos in posiciones_sin_datos:
        if not pos.pesaje_id:
            continue
        vals = {}
        if not pos.variedad_id and pos.pesaje_id.variedad_id:
            vals['variedad_id'] = pos.pesaje_id.variedad_id.id
        if not pos.humedad and pos.pesaje_id.humedad:
            vals['humedad'] = pos.pesaje_id.humedad
        if not pos.impurezas and pos.pesaje_id.impurezas:
            vals['impurezas'] = pos.pesaje_id.impurezas
        if vals:
            pos.write(vals)
