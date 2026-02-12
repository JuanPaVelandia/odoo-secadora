from . import models


def _create_arroz_paddy(env):
    """Crea el producto Arroz Paddy si no existe (post_init_hook)"""
    category = env.ref('secadora_bascula.product_category_arroz', raise_if_not_found=False)
    if not category:
        return

    existing = env['product.template'].search([('name', '=', 'Arroz Paddy')], limit=1)
    if existing:
        return

    uom_kg = env.ref('uom.product_uom_kgm', raise_if_not_found=False)
    env['product.template'].create({
        'name': 'Arroz Paddy',
        'type': 'consu',
        'is_storable': True,
        'categ_id': category.id,
        'list_price': 0,
        'standard_price': 0,
        'uom_id': uom_kg.id if uom_kg else False,
        'uom_po_id': uom_kg.id if uom_kg else False,
        'description': 'Arroz paddy sin procesar (con cáscara)',
    })
