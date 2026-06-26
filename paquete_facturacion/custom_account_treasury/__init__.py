from . import models
from . import wizards


def pre_init_hook(env):
    """Elimina vistas que pueden causar conflicto antes de la instalación"""
    env.cr.execute("""
        DELETE FROM ir_ui_view
        WHERE name IN (
            'account.move.form.inherit.treasury',
            'account.move.line.form.inherit.treasury',
            'account.move.form.inherit.force.partner',
            'account.move.form.inherit.force.fields',
            'account.move.line.payment.list',
            'account.move.list.inherit.treasury',
            'account.move.line.tree.inherit.multi.partner'
        )
    """)
