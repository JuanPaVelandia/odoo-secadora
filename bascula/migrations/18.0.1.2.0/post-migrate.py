# -*- coding: utf-8 -*-
import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Crear compañías hijas via ORM para que account/stock llenen todos los defaults."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    Company = env['res.company']
    IrModelData = env['ir.model.data']
    main_company = env.ref('base.main_company')

    # Renombrar empresa principal
    main_company.name = 'Secadora La Gran Colombia SAS'
    main_company.partner_id.name = 'Secadora La Gran Colombia SAS'

    companies = [
        ('company_jose_velandia', 'Jose Velandia'),
        ('company_juan_pablo_velandia', 'Juan Pablo Velandia'),
        ('company_felipe_tibocha', 'Felipe Tibocha'),
        ('company_luis_cubides', 'Luis Cubides'),
    ]

    created_ids = []
    for xmlid, name in companies:
        # Verificar si ya existe el xmlid
        existing = IrModelData.search([
            ('module', '=', 'bascula'),
            ('name', '=', xmlid),
        ], limit=1)
        if existing:
            _logger.info("Compañía %s ya existe (id=%s), omitiendo.", name, existing.res_id)
            created_ids.append(existing.res_id)
            continue

        # También buscar por nombre por si se creó manualmente
        existing_company = Company.search([
            ('name', '=', name),
            ('parent_id', '=', main_company.id),
        ], limit=1)
        if existing_company:
            _logger.info("Compañía %s encontrada por nombre (id=%s), registrando xmlid.", name, existing_company.id)
            IrModelData.create({
                'module': 'bascula',
                'name': xmlid,
                'model': 'res.company',
                'res_id': existing_company.id,
                'noupdate': True,
            })
            created_ids.append(existing_company.id)
            continue

        # Poner default en la columna para evitar NOT NULL violation
        cr.execute("""
            ALTER TABLE res_company
            ALTER COLUMN currency_interval_unit SET DEFAULT 'manually'
        """)

        # Crear via ORM (llena todos los defaults de account, stock, etc.)
        _logger.info("Creando compañía: %s", name)
        company = Company.create({
            'name': name,
            'parent_id': main_company.id,
        })
        # Registrar el xmlid
        IrModelData.create({
            'module': 'bascula',
            'name': xmlid,
            'model': 'res.company',
            'res_id': company.id,
            'noupdate': True,
        })
        created_ids.append(company.id)

    # Dar acceso al admin a todas las compañías
    admin = env.ref('base.user_admin')
    all_company_ids = [main_company.id] + created_ids
    admin.write({
        'company_ids': [(4, cid) for cid in all_company_ids],
    })
    _logger.info("Compañías configuradas correctamente. IDs: %s", all_company_ids)
