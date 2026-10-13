# -*- coding: utf-8 -*-
"""Las líneas marcadas antes de existir el tipo eran todas de finca."""


def migrate(cr, version):
    cr.execute("""
        UPDATE account_move_line
           SET acpm_tipo = 'finca'
         WHERE acpm_es AND acpm_tipo IS NULL
    """)
