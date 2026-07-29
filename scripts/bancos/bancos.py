# -*- coding: utf-8 -*-
"""Datos de las cuentas bancarias por compañía. Sin efectos secundarios.

Este es el archivo a revisar antes de aplicar nada: define la numeracion
definitiva del PUC y el nombre de cada cuenta y diario.

Fuente: "2. Archivos adicionales/1. Cuentas bancarias/Cuentas bancarias.xlsx"
(una hoja por compañía), con las correcciones acordadas con el usuario.

Los numeros de cuenta ya vienen sin el guion ni el digito posterior
(50584327-6 -> 50584327). Esa transformacion NO se hace en tiempo de ejecucion
a proposito: un digito de verificacion es dato contable y debe quedar visible
en la revision, no escondido en un split().
"""

# Compañías (id -> nombre en secadora_2), para los mensajes del script.
COMPANIAS = {
    1: 'SECADORA LA GRAN COLOMBIA S.A.S',
    2: 'JUAN PABLO VELANDIA CALA',
    3: 'JOSE EDUARDO VELANDIA OTALORA',
    4: 'FELIPE LEONARDO TIBOCHA CALA',
}

# El orden de cada lista define la numeracion: el indice 0 es el bloque X=1
# (11200510..13), el indice 1 el bloque X=2 (11200520..23), etc.
#
# El PRIMER elemento de cada compañía es, por construccion, la cuenta que ya
# existe hoy como 11200501 y que el paso 1 renumera a 11200510. Por eso el
# renombrado y la creacion comparten esta misma fuente de verdad.
#
# (banco, tipo de cuenta, numero, sufijo corto para el nombre)
BANCOS = {
    1: [
        ('Bancolombia',     'Ahorros',   '62900002327',  '2327'),
        ('Occidente',       'Corriente', '50584327',     '4327'),
    ],
    2: [
        ('Bancolombia',     'Ahorros',   '36517796292',  '6292'),
        ('Occidente',       'Ahorros',   '50583812',     '3812'),
        ('Nu Financiera',   'Ahorros',   '67415443',     '5443'),
        ('Nequi',           'Ahorros',   '3112264829',   '4829'),
    ],
    3: [
        ('Bancolombia',     'Corriente', '36579600553',  '0553'),
        ('Occidente',       'Corriente', '50582924',     '2924'),
        ('Davivienda',      'Ahorros',   '286070368167', '8167'),
        ('Banco de Bogota', 'Ahorros',   '646883314',    '3314'),
    ],
    4: [
        # El Excel traia 8596850455 (10 digitos), pero la cuenta real es de 11
        # y termina en 4555: coincide con los conceptos de los 3 pagos ya
        # publicados ("Bancolombia ahorros 4555"). Confirmado por el usuario.
        ('Bancolombia',     'Ahorros',   '85968504555',  '4555'),
        ('Bancolombia',     'Ahorros',   '62987243100',  '3100'),
        ('Occidente',       'Ahorros',   '50583811',     '3811'),
        ('Nequi',           'Ahorros',   '3212958465',   '8465'),
    ],
}

# Ultimo digito del codigo -> (sufijo del nombre, account_type, reconcile)
#
# reconcile=True en las tres auxiliares: sin eso no se pueden conciliar y los
# pagos quedan colgados sin poder cerrarse. La cuenta de banco va en False, que
# es el estandar de Odoo (se concilia por extracto bancario).
#
# Las auxiliares van a asset_current, no asset_cash: si fueran cash inflarian
# los reportes de disponible al duplicar los saldos en transito.
SUFIJOS = {
    0: ('',                    'asset_cash',    False),
    1: (' - Transitoria',      'asset_current', True),
    2: (' - Pagos entrantes',  'asset_current', True),
    3: (' - Pagos salientes',  'asset_current', True),
}

# Codigo de la cuenta que hoy existe en las 4 compañías y que se renumera.
CODIGO_VIEJO = '11200501'

# Lineas del asiento de apertura (APER, en borrador) que hay que reubicar.
# Hoy todas cayeron en la cuenta 11200501 de su compañía.
#
#   compañía -> {texto de la linea: codigo de cuenta destino}
#
# Lo que NO aparece aqui se queda donde esta, por decision del usuario:
#   - cia 1 "BANCOLOMBIA SA": ya esta en su bloque (11200510).
#   - cia 3 "BANCO DE BOGOTA" ($34.768.858): se queda en la cuenta de
#     Bancolombia 0553 aunque el concepto diga Bogota.
#   - cia 4 "BANCOLOMBIA SA" ($14.688.935): hay dos cuentas Bancolombia; se
#     queda en el bloque 1 (4555), donde ya estan sus pagos publicados.
#   - cia 4 "BANCO FALABELLA" ($33.609): no esta en el Excel, no tiene bloque.
APERTURAS = {
    1: {},
    2: {
        'NEQUI':              '11200540',
        'BANCO DE OCCIDENTE': '11200520',
        'NU COLOMBIA':        '11200530',
    },
    3: {},
    4: {
        'NEQUI':              '11200540',
        'BANCO DE OCCIDENTE': '11200530',
    },
}

# Pago en borrador cuyo concepto menciona una cuenta inexistente ("ahorros
# 0290"). Debe quedar en la cuenta principal de la compañía 3 (Bancolombia
# corriente 0553 = 11200510), que es donde ya esta: no requiere movimiento.
# Se deja anotado para que la verificacion lo confirme.
PAGO_0290_CIA = 3


def codigo(indice_bloque, digito):
    """(0, 1) -> '11200511'. indice_bloque es 0-based; el bloque X es +1."""
    return f'112005{indice_bloque + 1}{digito}'


def nombre_cuenta(banco, tipo, sufijo_corto, digito):
    """(Bancolombia, Ahorros, 2327, 1) -> 'Bancolombia Ahorros 2327 - Transitoria'"""
    return f'{banco} {tipo} {sufijo_corto}{SUFIJOS[digito][0]}'


def nombre_diario(banco, tipo, sufijo_corto):
    return f'{banco} {tipo} {sufijo_corto}'


def codigo_diario(cid, indice_bloque, usados):
    """Codigo corto y unico por compañía (account.journal.code, max 5 chars).

    El numero de cuenta no cabe, asi que se deriva del banco + indice. Si
    colisiona con algo existente (BBAN, BNAL...), se numera hasta encontrar
    hueco. `usados` es el conjunto de codigos ya tomados en esa compañía.
    """
    banco = BANCOS[cid][indice_bloque][0]
    base = {
        'Bancolombia': 'BCOL', 'Occidente': 'BOCC', 'Davivienda': 'BDAV',
        'Banco de Bogota': 'BBOG', 'Nu Financiera': 'BNU', 'Nequi': 'BNEQ',
    }.get(banco, 'BAN')
    for n in range(1, 10):
        propuesto = f'{base}{n}'[:5]
        if propuesto not in usados:
            return propuesto
    raise SystemExit(f'Sin codigo de diario libre para {banco} en cia {cid}')


def plan_cuentas(cid):
    """Todas las cuentas de una compañía: [(codigo, nombre, tipo, reconcile)]."""
    filas = []
    for i, (banco, tipo, _numero, corto) in enumerate(BANCOS[cid]):
        for d in (0, 1, 2, 3):
            _sufijo, account_type, reconcile = SUFIJOS[d]
            filas.append((codigo(i, d),
                          nombre_cuenta(banco, tipo, corto, d),
                          account_type, reconcile))
    return filas
