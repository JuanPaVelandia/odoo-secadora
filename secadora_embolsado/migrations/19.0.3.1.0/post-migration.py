# -*- coding: utf-8 -*-


def migrate(cr, version):
    """La impureza objetivo pasó de valor absoluto a % de la impureza inicial.

    Borrar el parámetro viejo para que no confunda; el nuevo
    (secadora_embolsado.impureza_objetivo_pct_inicial) lo crea el data XML.
    """
    cr.execute(
        "DELETE FROM ir_config_parameter WHERE key = 'secadora_embolsado.impureza_objetivo'"
    )
