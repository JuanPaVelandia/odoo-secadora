# -*- coding: utf-8 -*-

from . import controllers
from . import models


def _post_init_assign_analytic_accounts(env):
    """Asigna cuentas analíticas a puntos operativos existentes."""
    env['secadora.lugar']._assign_analytic_accounts()
