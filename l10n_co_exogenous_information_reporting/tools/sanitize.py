# -*- coding: utf-8 -*-
"""Funciones de sanitización para archivos planos de exógena distrital."""
import re
import unicodedata


def remove_accents(text):
    """Elimina acentos y diacríticos de un texto."""
    if not text or not isinstance(text, str):
        return text or ''
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if unicodedata.category(c) != 'Mn')


def remove_special_chars(text, allow_chars=''):
    """Elimina caracteres especiales, dejando alfanuméricos y espacios.

    Args:
        text: Texto a limpiar.
        allow_chars: Caracteres adicionales permitidos (ej: '.-#').
    """
    if not text or not isinstance(text, str):
        return text or ''
    pattern = rf'[^a-zA-Z0-9\s{re.escape(allow_chars)}]'
    return re.sub(pattern, '', text)


# Abreviaturas estándar colombianas para direcciones
_ADDRESS_REPLACEMENTS = [
    (r'\bCARRERA\b', 'CRA'),
    (r'\bCALLE\b', 'CL'),
    (r'\bAVENIDA\b', 'AV'),
    (r'\bTRANSVERSAL\b', 'TV'),
    (r'\bDIAGONAL\b', 'DG'),
    (r'\bCIRCULAR\b', 'CIR'),
    (r'\bNUMERO\b', 'NO'),
    (r'\bBARRIO\b', 'BR'),
    (r'\bURBANIZACION\b', 'URB'),
    (r'\bEDIFICIO\b', 'ED'),
    (r'\bAPARTAMENTO\b', 'APTO'),
    (r'\bOFICINA\b', 'OF'),
    (r'\bLOCAL\b', 'LC'),
    (r'\bPISO\b', 'PS'),
    (r'\bINTERIOR\b', 'IN'),
    (r'\bBLOQUE\b', 'BL'),
    (r'\bMANZANA\b', 'MZ'),
    (r'\bLOTE\b', 'LT'),
    (r'\bCONJUNTO\b', 'CJ'),
    (r'\bETAPA\b', 'ET'),
    (r'\bKILOMETRO\b', 'KM'),
    (r'\bSECTOR\b', 'SC'),
    (r'\bVEREDA\b', 'VDA'),
    (r'\bCORREGIMIENTO\b', 'COR'),
]


def standardize_address(text):
    """Estandariza una dirección colombiana con abreviaturas oficiales."""
    if not text or not isinstance(text, str):
        return text or ''
    result = text.upper().strip()
    for pattern, replacement in _ADDRESS_REPLACEMENTS:
        result = re.sub(pattern, replacement, result)
    return clean_spaces(result)


def clean_spaces(text):
    """Reduce múltiples espacios a uno solo y elimina espacios extremos."""
    if not text or not isinstance(text, str):
        return text or ''
    return re.sub(r'\s+', ' ', text).strip()


def sanitize_text_value(value, max_length=0, remove_accents_flag=True,
                        remove_special=True, standardize_addr=False):
    """Sanitiza un valor de texto individual.

    Args:
        value: Valor a sanitizar.
        max_length: Longitud máxima (0 = sin límite).
        remove_accents_flag: Eliminar acentos.
        remove_special: Eliminar caracteres especiales.
        standardize_addr: Estandarizar como dirección.
    """
    if value is None or (hasattr(value, '__len__') and len(str(value).strip()) == 0):
        return ''
    text = str(value).strip()
    if remove_accents_flag:
        text = remove_accents(text)
    if standardize_addr:
        text = standardize_address(text)
    if remove_special:
        text = remove_special_chars(text, allow_chars='.-#')
    text = clean_spaces(text)
    if max_length > 0:
        text = text[:max_length]
    return text


def sanitize_numeric_value(value, decimals=0):
    """Sanitiza un valor numérico.

    Args:
        value: Valor a convertir.
        decimals: Número de decimales (0 = entero).
    Returns:
        String numérico formateado.
    """
    if value is None:
        return '0'
    try:
        num = float(value)
        if decimals == 0:
            return str(int(round(num)))
        return f'{num:.{decimals}f}'
    except (ValueError, TypeError):
        return '0'


def sanitize_dataframe(df, sanitize=True, max_length=0, address_columns=None):
    """Sanitiza todas las columnas de texto de un DataFrame.

    Args:
        df: DataFrame de pandas.
        sanitize: Si True, aplica sanitización completa.
        max_length: Longitud máxima por campo.
        address_columns: Lista de nombres de columna que son direcciones.
    Returns:
        DataFrame sanitizado.
    """
    if not sanitize:
        return df
    address_columns = set(address_columns or [])
    df = df.copy()
    for col in df.columns:
        if df[col].dtype == 'object':
            is_addr = col.lower() in address_columns or 'direcc' in col.lower()
            df[col] = df[col].apply(
                lambda v: sanitize_text_value(
                    v, max_length=max_length,
                    standardize_addr=is_addr) if isinstance(v, str) else v)
    return df
