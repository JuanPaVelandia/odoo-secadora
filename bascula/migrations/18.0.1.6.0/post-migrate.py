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


def _delete_existing_companies(cr, names):
    """
    Borrar compañías existentes por nombre y TODOS sus registros dependientes.
    Busca todas las FK que apuntan a res_company y borra en cascada.
    """
    # Obtener IDs de las compañías a borrar
    cr.execute(
        "SELECT id FROM res_company WHERE name IN %s",
        (tuple(names),)
    )
    company_ids = [row[0] for row in cr.fetchall()]
    if not company_ids:
        return

    _logger.info("Borrando compañías existentes: %s (IDs: %s)", names, company_ids)

    # Buscar TODAS las tablas con FK a res_company
    cr.execute("""
        SELECT DISTINCT tc.table_name, kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
        JOIN information_schema.constraint_column_usage ccu
            ON tc.constraint_name = ccu.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND ccu.table_name = 'res_company'
          AND ccu.column_name = 'id'
    """)
    fk_tables = cr.fetchall()

    # Borrar registros dependientes en todas las tablas con FK
    for table_name, column_name in fk_tables:
        try:
            cr.execute(
                'DELETE FROM "%s" WHERE "%s" IN %%s' % (table_name, column_name),
                (tuple(company_ids),)
            )
            if cr.rowcount:
                _logger.info("  Borrados %d registros de %s", cr.rowcount, table_name)
        except Exception as e:
            _logger.warning("  Error borrando de %s: %s", table_name, e)

    # Borrar los partners asociados
    cr.execute(
        "SELECT partner_id FROM res_company WHERE id IN %s",
        (tuple(company_ids),)
    )
    partner_ids = [row[0] for row in cr.fetchall() if row[0]]

    # Borrar las compañías
    cr.execute("DELETE FROM res_company WHERE id IN %s", (tuple(company_ids),))
    _logger.info("  Compañías borradas.")

    # Borrar los partners huérfanos
    if partner_ids:
        cr.execute("DELETE FROM res_partner WHERE id IN %s", (tuple(partner_ids),))
        _logger.info("  Partners asociados borrados.")

    # Borrar xmlids huérfanos
    cr.execute("""
        DELETE FROM ir_model_data
        WHERE model = 'res.company' AND res_id IN %s
    """, (tuple(company_ids),))


def migrate(cr, version):
    """Crear compañías hijas con defaults temporales en BD."""
    company_names = [
        'Jose Velandia',
        'Juan Pablo Velandia',
        'Felipe Tibocha',
        'Luis Cubides',
    ]

    # Paso 1: Borrar compañías existentes y todas sus dependencias
    _delete_existing_companies(cr, company_names)

    env = api.Environment(cr, SUPERUSER_ID, {})
    Company = env['res.company']
    IrModelData = env['ir.model.data']
    main_company = env.ref('base.main_company')

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
