# -*- coding: utf-8 -*-
"""
Migracion 1.15: Configurar use_calendar_days para tipos de ausencia

Segun normativa colombiana:
- Incapacidades (EPS/ARL): cuentan todos los dias calendario
- Licencias de maternidad/paternidad: cuentan dias calendario
- Licencia de luto: 5 dias calendario
"""
import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

def migrate(cr, version):
    """Configura use_calendar_days=True para tipos de ausencia que usan dias calendario"""

    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})

    # Tipos de ausencia que deben usar dias calendario (por novelty)
    calendar_day_novelties = [
        'ige',   # Incapacidad EPS
        'irl',   # Incapacidad ARL
        'lma',   # Licencia Maternidad
        'lpa',   # Licencia Paternidad
        'lt',    # Licencia de Luto
    ]

    leave_types = env['hr.leave.type'].search([
        ('novelty', 'in', calendar_day_novelties)
    ])

    if leave_types:
        leave_types.write({'use_calendar_days': True})
        _logger.info(
            f"Migracion 1.15: Configurado use_calendar_days=True para {len(leave_types)} tipos de ausencia: "
            f"{', '.join(leave_types.mapped('code'))}"
        )
    else:
        _logger.info("Migracion 1.15: No se encontraron tipos de ausencia para actualizar")
