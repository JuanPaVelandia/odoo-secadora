# -*- coding: utf-8 -*-

from . import models
from . import wizard


def _crear_producto_silobolsa(env):
    """Crea el producto Silobolsa si no existe (post_init_hook).

    Igual que Arroz Paddy en secadora_bascula: por hook y no por XML data,
    porque el xmlid bascula.product_category_empaques no existe en la BD
    (su data está comentado en el manifest de bascula) y porque sale/stock
    agregan constraints SQL que el ORM llena bien vía create().
    """
    if env['product.template'].search([('name', '=', 'Silobolsa')], limit=1):
        return

    categoria = env['product.category'].search([('name', '=', 'Empaques')], limit=1)
    uom_unidad = env.ref('uom.product_uom_unit', raise_if_not_found=False)

    env['product.template'].create({
        'name': 'Silobolsa',
        'type': 'consu',
        'is_storable': True,
        'categ_id': categoria.id if categoria else False,
        'list_price': 0,
        'standard_price': 0,
        'uom_id': uom_unidad.id if uom_unidad else False,
        'description': 'Silobolsa para almacenamiento de arroz paddy',
    })
