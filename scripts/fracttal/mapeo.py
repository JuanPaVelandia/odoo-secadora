# -*- coding: utf-8 -*-
"""Reglas de mapeo Fracttal → Odoo.

Aquí vive todo lo que es "criterio de negocio" (a qué compañía va un activo,
qué ubicación de Fracttal corresponde a qué `secadora.lugar`), separado de la
mecánica de carga. Si algo hay que reclasificar, se toca este archivo.
"""
import re
import unicodedata

# --------------------------------------------------------------------------
# Compañías (ids reales en secadora_2)
# --------------------------------------------------------------------------
CIA_SECADORA = 'SECADORA LA GRAN COLOMBIA S.A.S'
CIA_JUAN_PABLO = 'JUAN PABLO VELANDIA CALA'
CIA_JOSE = 'JOSE EDUARDO VELANDIA OTALORA'
CIA_FELIPE = 'FELIPE LEONARDO TIBOCHA CALA'

# Sufijo en el nombre del activo → compañía propietaria.
# Decisión del usuario: FT=Felipe, JPV=Juan Pablo, JV=José, el resto (incl. LC
# y los que no traen sufijo) queda en José Velandia.
SUFIJO_COMPANIA = {
    'FT': CIA_FELIPE,
    'JPV': CIA_JUAN_PABLO,
    'JV': CIA_JOSE,
    'LC': CIA_JOSE,
}
COMPANIA_POR_DEFECTO = CIA_JOSE

# Los combinados ("FT/JPV") se asignan al primero listado.
_RE_SUFIJO = re.compile(r'\b(FT/JPV|JPV/FT|FT|JPV|JV|LC)\b')


def normalizar(texto):
    """Mayúsculas, sin tildes y con espacios colapsados, para comparar nombres."""
    if not texto:
        return ''
    txt = unicodedata.normalize('NFKD', str(texto))
    txt = ''.join(c for c in txt if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', txt).strip().upper()


def compania_de_activo(nombre):
    """Devuelve el nombre de la compañía dueña según el sufijo del activo."""
    m = _RE_SUFIJO.search(normalizar(nombre))
    if not m:
        return COMPANIA_POR_DEFECTO
    tag = m.group(1)
    if '/' in tag:                      # "FT/JPV" → el primero
        tag = tag.split('/')[0]
    return SUFIJO_COMPANIA.get(tag, COMPANIA_POR_DEFECTO)


# --------------------------------------------------------------------------
# Ubicaciones
# --------------------------------------------------------------------------
# Ubicación Fracttal → `secadora.lugar` que YA existe en Odoo.
# No se crean lugares nuevos para estas: se reusa el punto operativo.
LUGAR_EXISTENTE = {
    'FINCA CAMELIAS': 'FINCA CAMELIAS',
    'FINCA EL CAIRO': 'FINCA EL CAIRO',
    'FINCA ALIANZA': 'FINCA LA ALIANZA',          # nombre distinto en Odoo
    'FINCA RINCON DE PALMARITO (PAUTO)': 'FINCA RINCON DE PALMARITO (PAUTO)',
    'SECADORA GRAN COLOMBIA': 'SECADORA LA GRAN COLOMBIA',
    'FINCA LA MILAGROSA': 'FINCA LA MILAGROSA',
    'FINCA DON RUPERTO': 'FINCA DON RUPERTO',
    'FINCA MATA DE COROZO': 'HATO COROZAL',       # Mata de Corozo está en Hato Corozal
}

# Fincas de Fracttal que pueden no existir en Odoo. Solo se crean si faltan:
# en `secadora_2` La Milagrosa ya está, en `odoo_prueba_4` no.
LUGAR_A_CREAR = {
    'FINCA LA MILAGROSA': {'tipo': 'finca', 'municipio': 'YOPAL',
                           'departamento': 'CASANARE', 'codigo': 'F-MIL'},
    'FINCA DON RUPERTO': {'tipo': 'finca', 'municipio': 'NUNCHIA',
                          'departamento': 'CASANARE', 'codigo': 'F-DR'},
}

# Áreas internas de la planta. NO son `secadora.lugar`: se reusa el catálogo
# `secadora.origen.muestra` de secadora_calidad (decisión del usuario).
# El activo queda con lugar = SECADORA LA GRAN COLOMBIA + área de proceso.
AREA_PLANTA = {
    'PRELIMPIEZA SGC': 'Prelimpieza',
    'SECAMIENTO SGC': 'Secamiento',
    'ALMACENAMIENTO SGC': 'Almacenamiento',
    'LABORATORIO SGC': 'Laboratorio',        # se crea, no existe aún
    'SUBESTACION SGC': 'Subestación',        # se crea, no existe aún
}
AREA_A_CREAR = {
    'Laboratorio': 'LAB',
    'Subestación': 'SUB',
}
# Todo lo que esté en un área de planta vive físicamente en la secadora.
LUGAR_DE_PLANTA = 'SECADORA LA GRAN COLOMBIA'

# Talleres: no son ubicación de maquinaria sino quien presta el servicio.
# Se crean como `res.partner` (proveedor) y se usan en el costo histórico.
TALLERES = {
    'TALLER DAIRO', 'TALLER DON HELI', 'TALLER FREDY', 'TALLER LORENZO',
    'TALLER LUCHO', 'TALLER LUYMA', 'TALLER YULEVINSON', 'SOLUCIONES HIDRAULICAS',
    'REPUESTOS',
}

# El nombre del taller en las OT no siempre coincide con el del catálogo de
# ubicaciones ("TALLER HELI" vs "TALLER DON HELI"), así que se empareja por
# estas equivalencias además de por nombre normalizado.
ALIAS_FUENTE = {
    'TALLER HELI': 'TALLER DON HELI',
    'TALLER DON HELI': 'TALLER DON HELI',
    'EXTERNA: YULEVINSON': 'TALLER YULEVINSON',
}

# Fuentes que no son un proveedor real: son el almacén propio o marcadores
# genéricos del sistema de origen. No se crean como partner.
FUENTE_NO_PROVEEDOR = {
    'ALMACEN JV OFICINA YOPAL',
    'EXTERNA: 1', 'EXTERNA', 'EXTERNA: 2', 'EXTERNA: 3',
}


# El campo "Fuente del Recurso" es texto libre: junto a proveedores reales hay
# descripciones del trabajo ("MOTOR NUEVO", "TAPIZADO", "ZARANDA DE REPASO").
# Solo se crea contacto para las fuentes que se repiten en el histórico; las de
# una sola aparición conservan el texto en `source_name` y no ensucian el
# catálogo de contactos, que se comparte con contabilidad.
MIN_APARICIONES_PROVEEDOR = 2


def proveedor_de_fuente(fuente):
    """Nombre de proveedor a crear/buscar para una fuente de recurso.

    Devuelve None si la fuente no representa un tercero (almacén propio,
    marcadores vacíos).
    """
    norm = normalizar(fuente)
    if not norm or norm in FUENTE_NO_PROVEEDOR:
        return None
    if norm in ALIAS_FUENTE:
        return ALIAS_FUENTE[norm]
    # "Externa: NOMBRE" → NOMBRE
    if norm.startswith('EXTERNA:'):
        resto = norm.split(':', 1)[1].strip()
        if not resto or resto.isdigit():
            return None
        return ALIAS_FUENTE.get(resto, resto)
    return norm

# Nodos raíz de la jerarquía de Fracttal: no representan un lugar real.
UBICACION_IGNORAR = {'FINCAS', 'TALLERES', ''}


# --------------------------------------------------------------------------
# Categorías de equipo
# --------------------------------------------------------------------------
# Prefijo del nombre del activo → `maintenance.equipment.category` existente.
CATEGORIA_POR_PREFIJO = {
    # Maquinaria agrícola de campo
    'TRACT': 'Campo/Cultivo', 'COMB': 'Campo/Cultivo', 'RASTRA': 'Campo/Cultivo',
    'SEMBR': 'Campo/Cultivo', 'FUMIG': 'Campo/Cultivo', 'DRON': 'Campo/Cultivo',
    'TOLVO': 'Campo/Cultivo', 'PULIDOR': 'Campo/Cultivo', 'TAIPA': 'Campo/Cultivo',
    'CABALLONEADOR': 'Campo/Cultivo', 'ZANJADORA': 'Campo/Cultivo',
    'CORTAMALEZA': 'Campo/Cultivo', 'VOLEADORA': 'Campo/Cultivo',
    'ENCAL': 'Campo/Cultivo', 'CILINDRO': 'Campo/Cultivo', 'RETRO': 'Campo/Cultivo',
    'ZORRO': 'Campo/Cultivo', 'CAMA': 'Campo/Cultivo', 'PLUMA': 'Campo/Cultivo',
    'MULA': 'Campo/Cultivo', 'BOMBA': 'Campo/Cultivo', 'VARILLA': 'Campo/Cultivo',
    # Proceso
    'SECADORA': 'Secado', 'HORNO': 'Secado',
    'SCALPER': 'Recepción', 'ZARANDA': 'Recepción', 'CICLÓN': 'Recepción',
    'CICLON': 'Recepción', 'DUOASPIRADORA': 'Recepción', 'LIMPIADORA': 'Recepción',
    'PRELIMPIEZA': 'Recepción', 'BASCULA': 'Recepción',
    'SILO': 'Almacenamiento', 'BARREDORA': 'Almacenamiento',
    'EMBOLSADORA': 'Empaque', 'DESEMBOLSADORA': 'Empaque',
    'MOLINO': 'Molienda',
    # Transporte interno y servicios
    'ELEVADOR': 'Servicios generales', 'BANDA': 'Servicios generales',
    'REDLER': 'Servicios generales', 'SINFIN': 'Servicios generales',
    'WINCHE': 'Servicios generales', 'MOTOR': 'Servicios generales',
    'MOTORREDUCTOR': 'Servicios generales', 'TRAFO': 'Servicios generales',
    'BANCO': 'Servicios generales', 'ALTERNADOR': 'Servicios generales',
    'CONTROLADOR': 'Servicios generales', 'EJE': 'Servicios generales',
    'ESTUFA': 'Servicios generales', 'PROBADOR': 'Servicios generales',
}
CATEGORIA_POR_DEFECTO = 'Servicios generales'


def categoria_de_activo(nombre):
    """Categoría de equipo a partir del primer token del nombre."""
    tokens = normalizar(nombre).split()
    if not tokens:
        return CATEGORIA_POR_DEFECTO
    # Se compara sin tildes; las claves con tilde se normalizan al vuelo.
    for clave, cat in CATEGORIA_POR_PREFIJO.items():
        if normalizar(clave) == tokens[0]:
            return cat
    return CATEGORIA_POR_DEFECTO


# --------------------------------------------------------------------------
# Órdenes de trabajo
# --------------------------------------------------------------------------
# Estado Fracttal → (stage técnico, done)
# Odoo trae 4 etapas: New Request / In Progress / Repaired / Scrap.
ESTADO_ETAPA = {
    'Finalizadas': ('Repaired', True),
    'En Proceso': ('In Progress', False),
    'En Revisión': ('In Progress', False),
    'Cancelado': ('Scrap', False),
}

TIPO_MANTENIMIENTO = {
    'PREVENTIVA': 'preventive',
    'CORRECTIVA': 'corrective',
}

TIPO_RECURSO = {
    'Inventario': 'inventory',
    'Servicios': 'service',
    'Recursos Humanos': 'human',
}

# Variantes de nombre en las OT que apuntan a un activo con otro nombre.
ALIAS_ACTIVO = {
    'COMB JHON DEERE 1175 HYDRO JV 1': 'COMB JOHN DEERE 1175 HYDRO JV 1',
    'TRACT JHON DEERE 6603 JV 1': 'TRACT JOHN DEERE 6603 JV 1',
    # El export de OT nombra el motor sin la cilindrada, y hay dos (100cc y
    # 80cc). Se imputa a la máquina que los contiene, que sí es inequívoca.
    'MOTOR HIDRAULICO ORB "SAUER DANF" (DESEMB-ALM-1)':
        'DESEMBOLSADORA AKRON ALM 1',
    'BANDA TRANSP INVEIN RECIBE PULMONES VERDE PREL 1':
        'ELEVADOR IMSAFE LLENA PULMONES VERDE PREL 4',
}

# Algunas OT se registraron contra la ubicación completa y no contra una
# máquina ("FINCA CAMELIAS  SAN LUIS DE PALENQUE ... { F-CAM }"). Son
# mantenimientos de la finca (adecuación de vías, cercas, etc.). Para no
# perder el costo se crea un equipo genérico por finca que los recibe.
_RE_OT_UBICACION = re.compile(r'\{\s*([A-Z-]+)\s*\}\s*$')


def es_ot_de_ubicacion(nombre_activo):
    """True si la OT apunta a una ubicación y no a una máquina."""
    return bool(_RE_OT_UBICACION.search((nombre_activo or '').strip()))


def finca_de_ot_ubicacion(nombre_activo):
    """'FINCA CAMELIAS  SAN LUIS...  { F-CAM }' → 'FINCA CAMELIAS'."""
    txt = _RE_OT_UBICACION.sub('', (nombre_activo or '').strip()).strip()
    # El texto es "NOMBRE  MUNICIPIO  DEPTO PAIS" separado por doble espacio.
    return re.split(r'\s{2,}', txt)[0].strip()


# Nombre del equipo genérico que agrupa el mantenimiento de una ubicación.
def equipo_generico_de(finca):
    return f'{finca} - INFRAESTRUCTURA'
