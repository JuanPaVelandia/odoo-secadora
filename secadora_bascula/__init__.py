from . import models


def _create_arroz_paddy(env):
    """Crea el producto Arroz Paddy y los picking types (post_init_hook)

    Se usa post_init_hook en vez de XML data porque modulos como sale y stock
    agregan constraints NOT NULL a nivel SQL que no se llenan via XML.
    El ORM aplica todos los defaults correctamente via create().
    """
    _create_product_arroz(env)
    _create_picking_types(env)


def _create_product_arroz(env):
    """Crea los productos Arroz Paddy Verde y Seco si no existen"""
    category = env.ref('secadora_bascula.product_category_arroz', raise_if_not_found=False)
    if not category:
        return

    uom_kg = env.ref('uom.product_uom_kgm', raise_if_not_found=False)

    # Renombrar "Arroz Paddy" existente a "Arroz Paddy Verde" si existe
    arroz_viejo = env['product.template'].search([('name', '=', 'Arroz Paddy')], limit=1)
    if arroz_viejo:
        arroz_viejo.write({'name': 'Arroz Paddy Verde'})

    productos = [
        {
            'name': 'Arroz Paddy Verde',
            'description': 'Arroz paddy verde (humedo, sin procesar)',
        },
        {
            'name': 'Arroz Paddy Seco',
            'description': 'Arroz paddy seco (procesado, listo para entregar)',
        },
    ]

    for prod in productos:
        existing = env['product.template'].search([('name', '=', prod['name'])], limit=1)
        if existing:
            continue

        env['product.template'].create({
            'name': prod['name'],
            'type': 'consu',
            'is_storable': True,
            'categ_id': category.id,
            'list_price': 0,
            'standard_price': 0,
            'uom_id': uom_kg.id if uom_kg else False,
            'uom_po_id': uom_kg.id if uom_kg else False,
            'description': prod['description'],
        })


def _create_picking_types(env):
    """Crea los picking types de bascula si no existen"""
    warehouse = env.ref('stock.warehouse0', raise_if_not_found=False)
    if not warehouse:
        return

    loc_stock = env.ref('stock.stock_location_stock', raise_if_not_found=False)
    loc_suppliers = env.ref('stock.stock_location_suppliers', raise_if_not_found=False)
    loc_customers = env.ref('stock.stock_location_customers', raise_if_not_found=False)
    loc_secado = env.ref('secadora_bascula.stock_location_secado', raise_if_not_found=False)

    picking_types = [
        {
            'xml_id': 'picking_type_recepcion_bascula',
            'vals': {
                'name': 'Recepcion Bascula',
                'code': 'incoming',
                'sequence_code': 'REC-BAS',
                'warehouse_id': warehouse.id,
                'default_location_src_id': loc_suppliers.id if loc_suppliers else False,
                'default_location_dest_id': loc_stock.id if loc_stock else False,
            },
        },
        {
            'xml_id': 'picking_type_despacho_bascula',
            'vals': {
                'name': 'Despacho Bascula',
                'code': 'outgoing',
                'sequence_code': 'DES-BAS',
                'warehouse_id': warehouse.id,
                'default_location_src_id': loc_stock.id if loc_stock else False,
                'default_location_dest_id': loc_customers.id if loc_customers else False,
            },
        },
        {
            'xml_id': 'picking_type_entrada_servicio',
            'vals': {
                'name': 'Entrada Servicio',
                'code': 'incoming',
                'sequence_code': 'ENT-SRV',
                'warehouse_id': warehouse.id,
                'default_location_src_id': loc_suppliers.id if loc_suppliers else False,
                'default_location_dest_id': loc_secado.id if loc_secado else False,
            },
        },
        {
            'xml_id': 'picking_type_salida_servicio',
            'vals': {
                'name': 'Salida Servicio',
                'code': 'outgoing',
                'sequence_code': 'SAL-SRV',
                'warehouse_id': warehouse.id,
                'default_location_src_id': loc_secado.id if loc_secado else False,
                'default_location_dest_id': loc_customers.id if loc_customers else False,
            },
        },
    ]

    IrModelData = env['ir.model.data']

    for pt in picking_types:
        xml_id = pt['xml_id']
        # Verificar si ya existe
        existing = IrModelData.search([
            ('module', '=', 'secadora_bascula'),
            ('name', '=', xml_id),
        ], limit=1)

        if existing:
            continue

        record = env['stock.picking.type'].create(pt['vals'])

        # Registrar XML ID para poder usar env.ref() despues
        IrModelData.create({
            'module': 'secadora_bascula',
            'name': xml_id,
            'model': 'stock.picking.type',
            'res_id': record.id,
            'noupdate': True,
        })
