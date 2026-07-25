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

# Fincas de Fracttal que no existen en Odoo y hay que crear como `secadora.lugar`.
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
}
