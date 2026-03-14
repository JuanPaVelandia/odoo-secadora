# -*- coding: utf-8 -*-
import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def _set_not_null_defaults(cr, main_company_id):
    """
    Busca TODAS las columnas NOT NULL sin DEFAULT en res_company
    y les pone DEFAULT copiando los valores de la compañía principal.
    """
    cr.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'res_company'
          AND is_nullable = 'NO'
          AND column_default IS NULL
          AND column_name != 'id'
    """)
    columns = [row[0] for row in cr.fetchall()]

    if not columns:
        return

    _logger.info("Columnas NOT NULL sin default: %s", columns)

    for col_name in columns:
        cr.execute(
            'SELECT "%(col)s" FROM res_company WHERE id = %%s' % {'col': col_name},
            (main_company_id,)
        )
        row = cr.fetchone()
        if row and row[0] is not None:
            val = row[0]
            if isinstance(val, bool):
                default_val = 'true' if val else 'false'
            elif isinstance(val, (int, float)):
                default_val = str(val)
            else:
                default_val = "'%s'" % str(val).replace("'", "''")

            cr.execute(
                'ALTER TABLE res_company ALTER COLUMN "%(col)s" SET DEFAULT %(val)s'
                % {'col': col_name, 'val': default_val}
            )
            _logger.info("SET DEFAULT %s en %s", default_val, col_name)


def migrate(cr, version):
    """Crear compañías hijas con defaults temporales en BD."""
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

    # Poner defaults temporales en TODAS las columnas NOT NULL
    _set_not_null_defaults(cr, main_company.id)

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

        # Buscar por nombre (sin filtrar parent_id, por si se creó manualmente)
        existing_company = Company.search([
            ('name', '=', name),
        ], limit=1)
        if existing_company:
            _logger.info("Compañía %s encontrada por nombre (id=%s), registrando xmlid.",
                         name, existing_company.id)
            # Asegurar que tenga parent_id correcto
            if not existing_company.parent_id:
                existing_company.parent_id = main_company.id
            IrModelData.create({
                'module': 'bascula',
                'name': xmlid,
                'model': 'res.company',
                'res_id': existing_company.id,
                'noupdate': True,
            })
            created_ids.append(existing_company.id)
            continue

        # Crear via ORM
        _logger.info("Creando compañía: %s", name)
        company = Company.create({
            'name': name,
            'parent_id': main_company.id,
        })
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
