# -*- coding: utf-8 -*-
"""
Utilidades para procesar nombres
================================

Divide nombres completos en componentes (nombres, apellidos) considerando
particulas como "de", "del", "la", "los", "van", "von", etc.

Ejemplos de uso:
    >>> from odoo.addons.lavish_erp.utils.name_parser import split_nombre_hispano
    >>> split_nombre_hispano("Juan Carlos Garcia Lopez")
    ('Juan Carlos', 'Garcia', 'Lopez')
    >>> split_nombre_hispano("Maria de la Cruz Perez")
    ('Maria', 'de la Cruz', 'Perez')
    >>> split_nombre_hispano("Garcia Lopez, Juan Carlos")
    ('Juan Carlos', 'Garcia', 'Lopez')
"""
import re
import unicodedata
from typing import List, Optional, Tuple, Union


# Particulas que suelen "pegarse" a la palabra siguiente (de la Cruz, del Rio, van Helsing, etc.)
_PREFIX_PARTICLES = {"da", "de", "di", "do", "del", "la", "las", "le", "los", "van", "von", "san", "santa"}

# Conectores que suelen unir dos partes: "Garcia y Vega", "Lopez i Roca"
_JOIN_PARTICLES = {"y", "i"}

# Para dar formato: particulas en minuscula cuando van en medio
_LOWER_PARTICLES = {"da", "de", "di", "do", "del", "la", "las", "le", "los", "van", "von", "y", "i"}
_CAP_PARTICLES = {"san", "santa"}

_ROMAN_RE = re.compile(r"^[IVXLCDM]+$")  # II, III, IV, etc.


def _strip_accents(s: str) -> str:
    """Quita acentos SOLO para comparar (no para devolver)."""
    return "".join(
        ch for ch in unicodedata.normalize("NFD", s)
        if unicodedata.category(ch) != "Mn"
    )


def _norm(s: str) -> str:
    """Normaliza a minusculas sin acentos para comparaciones."""
    return _strip_accents(s).lower()


def _tokenize_ws(s: str) -> List[str]:
    """Separa por espacios (colapsando multiples espacios)."""
    return [t for t in re.split(r"\s+", s.strip()) if t]


def _group_name_parts(tokens: List[str]) -> List[str]:
    """
    Agrupa tokens para formar "bloques" como:
      ["Juan", "de la Cruz", "Garcia y Vega", "Perez"]
    """
    groups: List[str] = []
    buf: List[str] = []
    i = 0

    while i < len(tokens):
        tok = tokens[i]
        tl = _norm(tok)

        # Prefijos (de, del, la, los, van, von, san, santa...) se acumulan para pegarse al siguiente
        if tl in _PREFIX_PARTICLES:
            buf.append(tok)
            i += 1
            continue

        # Conectores (y / i) se pegan al grupo anterior + siguiente (y de la Vega, i Roca, etc.)
        if tl in _JOIN_PARTICLES:
            if buf:
                # caso raro: si quedo algo en buf, lo volcamos como grupo
                groups.append(" ".join(buf).strip())
                buf = []

            if groups and i + 1 < len(tokens):
                addition = [tok]
                j = i + 1

                # permitir "y de la Vega" (con prefijos tras el conector)
                while j < len(tokens) and _norm(tokens[j]) in _PREFIX_PARTICLES:
                    addition.append(tokens[j])
                    j += 1

                if j < len(tokens):
                    addition.append(tokens[j])
                    groups[-1] = groups[-1] + " " + " ".join(addition)
                    i = j + 1
                    continue

            # fallback
            if groups:
                groups[-1] = groups[-1] + " " + tok
            else:
                buf.append(tok)
            i += 1
            continue

        # Token normal: si habia buf, lo pegamos; si no, nuevo grupo
        if buf:
            groups.append(" ".join(buf + [tok]).strip())
            buf = []
        else:
            groups.append(tok)

        i += 1

    if buf:
        groups.append(" ".join(buf).strip())

    return groups


def _smart_title(phrase: str) -> str:
    """
    Formato tipo Title Case, conservando particulas en minuscula cuando van en medio:
    "Juan de la Cruz" (no "Juan De La Cruz" en el medio)
    """
    phrase = phrase.strip()
    if not phrase:
        return ""

    words = phrase.split()
    out: List[str] = []

    for i, w in enumerate(words):
        wl = _norm(w)

        # particulas en medio en minuscula
        if i > 0 and wl in _LOWER_PARTICLES:
            out.append(wl)
            continue

        if wl in _CAP_PARTICLES:
            out.append(wl.capitalize())
            continue

        # Manejar guiones y apostrofes: O'Neill, Perez-Gomez
        parts = re.split(r"([\-\''])", w)
        new_parts: List[str] = []

        for p in parts:
            if p in {"-", "'", "'"}:
                new_parts.append(p)
                continue
            if not p:
                continue

            # Mantener sufijos/romanos en mayuscula si vienen asi
            if p.isupper() and (_ROMAN_RE.match(p) or p in {"JR", "SR"}):
                new_parts.append(p)
                continue

            pl = _norm(p)
            if pl.startswith("mc") and len(p) > 2:
                new_parts.append("Mc" + p[2:].capitalize())
            elif pl.startswith("mac") and len(p) > 3:
                new_parts.append("Mac" + p[3:].capitalize())
            else:
                new_parts.append(p[:1].upper() + p[1:].lower())

        out.append("".join(new_parts))

    return " ".join(out)


def split_nombre_hispano(
    nombre: str,
    num_apellidos: Union[int, str] = 2,
    max_nombres: Optional[int] = None,
    formatear: bool = True
) -> Tuple[str, str, str]:
    """
    Divide 'nombre' en (nombres, apellido1, apellido2).

    Parametros:
      - num_apellidos: 1, 2 o "auto".
          * 2 asume formato ideal: Nombres + Apellido1 + Apellido2
          * 1 si tu sistema solo maneja un apellido
          * "auto" hace una decision simple segun cantidad de partes (util pero NO perfecto)
      - max_nombres: si lo pones (ej. 2), fuerza a usar como nombres maximo 2 bloques
                    y manda el resto a apellidos (util para formularios).
      - formatear: True => devuelve capitalizado "bonito".

    Soporta:
      - "Perez Gomez, Juan Carlos"
      - "Juan de la Cruz Perez Gomez"
      - "Garcia y Vega" (como bloque)

    Returns:
        Tupla (nombres, apellido1, apellido2)
    """
    if not nombre or not str(nombre).strip():
        return ("", "", "")

    s = re.sub(r"\s+", " ", str(nombre).strip())

    # Caso: "Apellidos, Nombres"
    if "," in s:
        left, right = [p.strip() for p in s.split(",", 1)]
        nom_groups = _group_name_parts(_tokenize_ws(right))
        ape_groups = _group_name_parts(_tokenize_ws(left))

        nombres = " ".join(nom_groups)

        if num_apellidos == "auto":
            n_ap = 2 if len(ape_groups) >= 2 else 1
        else:
            n_ap = int(num_apellidos)

        if n_ap >= 2:
            if len(ape_groups) >= 2:
                apellido1 = " ".join(ape_groups[:-1])  # deja compuestos en apellido1
                apellido2 = ape_groups[-1]
            elif len(ape_groups) == 1:
                apellido1, apellido2 = ape_groups[0], ""
            else:
                apellido1 = apellido2 = ""
        else:
            apellido1 = " ".join(ape_groups) if ape_groups else ""
            apellido2 = ""

    else:
        groups = _group_name_parts(_tokenize_ws(s))

        if num_apellidos == "auto":
            # heuristica simple (ajustala si quieres)
            if len(groups) >= 4:
                n_ap = 2
            elif len(groups) == 2:
                n_ap = 1
            elif len(groups) == 3:
                n_ap = 2
            else:
                n_ap = 0
        else:
            n_ap = int(num_apellidos)

        if n_ap <= 0:
            nombres = " ".join(groups)
            apellido1 = apellido2 = ""

        elif max_nombres is not None:
            # fuerza maximo N bloques de nombres; lo demas pasa a apellidos
            nombres = " ".join(groups[:max_nombres])
            rest = groups[max_nombres:]

            if n_ap >= 2:
                if len(rest) >= 2:
                    apellido1 = rest[0]
                    apellido2 = " ".join(rest[1:])  # deja compuestos en apellido2
                elif len(rest) == 1:
                    apellido1, apellido2 = rest[0], ""
                else:
                    apellido1 = apellido2 = ""
            else:
                apellido1 = " ".join(rest) if rest else ""
                apellido2 = ""

        else:
            # split "natural": ultimos apellidos y el resto nombres
            if n_ap >= 2:
                if len(groups) >= 3:
                    nombres = " ".join(groups[:-2])
                    apellido1 = groups[-2]
                    apellido2 = groups[-1]
                elif len(groups) == 2:
                    nombres, apellido1, apellido2 = groups[0], groups[1], ""
                elif len(groups) == 1:
                    nombres, apellido1, apellido2 = groups[0], "", ""
                else:
                    nombres = apellido1 = apellido2 = ""
            else:
                if len(groups) >= 2:
                    nombres = " ".join(groups[:-1])
                    apellido1 = groups[-1]
                    apellido2 = ""
                elif len(groups) == 1:
                    nombres, apellido1, apellido2 = groups[0], "", ""
                else:
                    nombres = apellido1 = apellido2 = ""

    if formatear:
        return (_smart_title(nombres), _smart_title(apellido1), _smart_title(apellido2))

    return (nombres, apellido1, apellido2)


def split_nombre_completo(
    nombre: str,
    formatear: bool = True
) -> dict:
    """
    Divide un nombre completo en sus componentes para res.partner.

    Args:
        nombre: Nombre completo a dividir
        formatear: Si True, aplica formato Title Case

    Returns:
        Diccionario con:
        - first_name: Primer nombre
        - second_name: Segundo nombre (si existe)
        - first_lastname: Primer apellido
        - second_lastname: Segundo apellido
    """
    nombres, apellido1, apellido2 = split_nombre_hispano(
        nombre,
        num_apellidos=2,
        max_nombres=2,
        formatear=formatear
    )

    # Separar primer y segundo nombre
    nombres_parts = nombres.split() if nombres else []
    first_name = ""
    second_name = ""

    if nombres_parts:
        # El primer bloque es el primer nombre
        first_name = nombres_parts[0]
        # El resto es segundo nombre
        if len(nombres_parts) > 1:
            second_name = " ".join(nombres_parts[1:])

    return {
        'first_name': first_name,
        'second_name': second_name,
        'first_lastname': apellido1,
        'second_lastname': apellido2,
    }
