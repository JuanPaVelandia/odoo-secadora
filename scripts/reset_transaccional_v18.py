# -*- coding: utf-8 -*-
# ============================================================
# RESET de datos TRANSACCIONALES de secadora — Odoo v18 (BD odoo_col)
#
# Borra SOLO registros de prueba de los módulos secadora.*:
# pesajes, órdenes, fletes, liquidaciones (incl. cuadrilla),
# análisis de lab, facturas por email, movimientos/posiciones de
# arroz, bultos, Y los stock.picking + account.move que ESTAS
# pruebas generaron (enlazados por x_pesaje_id / factura_id).
#
# NO toca: módulos, catálogos (variedades, vehículos, conductores,
# transportadoras, lugares, tarifas, precios, tipos), compañías,
# NI facturas/pickings ajenos a secadora.
#
# Uso (dentro del contenedor v18):
#   docker exec -it odoo_enterprise odoo shell -d odoo_col --no-http
# y pega este archivo, o:
#   >>> exec(open('/mnt/extra-addons/odoo-secadora/scripts/reset_transaccional_v18.py').read())
#
# CUENTA primero y pide confirmación explícita. No borra hasta que
# llames a borrar_todo().
# ============================================================

env = env(user=1)  # __system__: salta ir.rule y validaciones de negocio

# --- Registros secadora.*, en orden hijo -> padre ---
PLAN = [
    ('Análisis de laboratorio',        'secadora.analisis.lab'),
    ('Descuentos de calidad',          'secadora.descuento.calidad'),
    ('Deducción liq. cuadrilla',       'secadora.cuadrilla.liquidacion.deduccion'),
    ('Línea liq. cuadrilla',           'secadora.cuadrilla.liquidacion.linea'),
    ('Liquidación de cuadrilla',       'secadora.cuadrilla.liquidacion'),
    ('Deducción de liquidación',       'secadora.liquidacion.deduccion'),
    ('Línea de liquidación',           'secadora.liquidacion.linea'),
    ('Liquidación',                    'secadora.liquidacion'),
    ('Flete',                          'secadora.flete'),
    ('Factura por email',              'secadora.factura.email'),
    ('Movimiento de arroz',            'secadora.movimiento.arroz'),
    ('Posición de arroz',              'secadora.posicion.arroz'),
    ('Despacho de bultos',             'secadora.despacho.bultos'),
    ('Registro de bultos',             'secadora.registro.bultos'),
    ('Pesaje',                         'secadora.pesaje'),
    ('Línea de orden de servicio',     'secadora.orden.servicio.linea'),
    ('Orden de servicio',              'secadora.orden.servicio'),
]


def _sudo(modelo, dominio=None):
    if modelo not in env:
        return None
    return env[modelo].sudo().with_context(active_test=False).search(dominio or [])


def contar():
    print('\n===== CONTEO PREVIO (nada borrado aún) =====')
    total = 0
    for etiqueta, modelo in PLAN:
        recs = _sudo(modelo)
        if recs is None:
            print(f'  [—] {etiqueta:32} (modelo {modelo} no instalado)')
            continue
        print(f'  {len(recs):6} × {etiqueta}')
        total += len(recs)

    # Facturas y pickings ligados a secadora (se cuentan aparte)
    pickings = _sudo('stock.picking', [('x_pesaje_id', '!=', False)])
    fact_orden = _sudo('secadora.orden.servicio', [('factura_id', '!=', False)])
    fact_orden = fact_orden.mapped('factura_id') if fact_orden else env['account.move']
    print(f'  {len(pickings) if pickings else 0:6} × stock.picking (de pesajes)')
    print(f'  {len(fact_orden):6} × account.move (facturas de órdenes de secadora)')
    print(f'  ----- TOTAL registros secadora.*: {total} -----')
    print('\nRevisa los números. Si son los datos de PRUEBA que quieres')
    print('borrar, ejecuta:   borrar_todo()')


def _borrar_facturas_y_pickings():
    # 1. Facturas de órdenes de secadora: cancelar antes de borrar
    ordenes = _sudo('secadora.orden.servicio', [('factura_id', '!=', False)])
    facturas = ordenes.mapped('factura_id') if ordenes else env['account.move']
    # sumar facturas de flete y factura_email si existen
    for modelo, campo in [('secadora.flete', 'factura_transportadora_id'),
                          ('secadora.factura.email', 'factura_id')]:
        recs = _sudo(modelo)
        if recs and campo in recs._fields:
            facturas |= recs.mapped(campo)
    facturas = facturas.exists()
    if facturas:
        posted = facturas.filtered(lambda m: m.state == 'posted')
        if posted:
            posted.button_draft()      # posted -> draft
            posted.button_cancel()     # draft -> cancel
        facturas.filtered(lambda m: m.state == 'draft').button_cancel()
        facturas.unlink()
        print(f'  [OK] {len(facturas):6} × account.move (canceladas y borradas)')

    # 2. Pickings de pesajes: cancelar y borrar (con sus moves)
    pickings = _sudo('stock.picking', [('x_pesaje_id', '!=', False)])
    if pickings:
        activos = pickings.filtered(lambda p: p.state not in ('draft', 'cancel'))
        if activos:
            activos.action_cancel()
        pickings.unlink()
        print(f'  [OK] {len(pickings):6} × stock.picking (cancelados y borrados)')


def borrar_todo():
    print('\n===== BORRANDO =====')
    # Primero facturas/pickings, para soltar los enlaces hacia pesajes/órdenes
    try:
        _borrar_facturas_y_pickings()
    except Exception as e:
        print(f'  [FALLÓ facturas/pickings]: {e}')
        print('  -> NO se hace commit. Revisa y reintenta.')
        raise

    # Luego los registros secadora.* en orden hijo -> padre
    for etiqueta, modelo in PLAN:
        recs = _sudo(modelo)
        if not recs:
            continue
        try:
            n = len(recs)
            recs.unlink()
            print(f'  [OK] {n:6} × {etiqueta}')
        except Exception as e:
            print(f'  [FALLÓ] {etiqueta}: {e}')
            print('  -> NO se hace commit. Revisa y reintenta.')
            raise

    env.cr.commit()
    print('\n===== LISTO. Cambios guardados (commit hecho). =====')


# Al pegar/exec, corre el conteo automáticamente. El borrado es manual.
contar()
