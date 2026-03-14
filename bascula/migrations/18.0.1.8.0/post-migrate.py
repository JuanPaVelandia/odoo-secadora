# -*- coding: utf-8 -*-
import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def _delete_existing_companies(cr, names):
    """
    Borrar compañías existentes por nombre y TODOS sus registros dependientes.
    Usa SAVEPOINT para manejar errores de FK sin romper la transacción.
    """
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

    # Hacer varias pasadas para resolver dependencias anidadas
    for pass_num in range(3):
        for table_name, column_name in fk_tables:
            cr.execute("SAVEPOINT delete_fk")
            try:
                cr.execute(
                    'DELETE FROM "%s" WHERE "%s" IN %%s' % (table_name, column_name),
                    (tuple(company_ids),)
                )
                cr.execute("RELEASE SAVEPOINT delete_fk")
                if cr.rowcount:
                    _logger.info("  [Pasada %d] Borrados %d registros de %s",
                                 pass_num + 1, cr.rowcount, table_name)
            except Exception:
                cr.execute("ROLLBACK TO SAVEPOINT delete_fk")

    # Borrar partners asociados
    cr.execute(
        "SELECT partner_id FROM res_company WHERE id IN %s",
        (tuple(company_ids),)
    )
    partner_ids = [row[0] for row in cr.fetchall() if row[0]]

    # Borrar las compañías
    cr.execute("DELETE FROM res_company WHERE id IN %s", (tuple(company_ids),))
    _logger.info("  Compañías borradas.")

    # Borrar partners huérfanos
    if partner_ids:
        cr.execute("SAVEPOINT delete_partners")
        try:
            cr.execute("DELETE FROM res_partner WHERE id IN %s", (tuple(partner_ids),))
            cr.execute("RELEASE SAVEPOINT delete_partners")
        except Exception:
            cr.execute("ROLLBACK TO SAVEPOINT delete_partners")

    # Borrar xmlids huérfanos
    cr.execute("""
        DELETE FROM ir_model_data
        WHERE model = 'res.company' AND res_id IN %s
    """, (tuple(company_ids),))


def _create_company_sql(cr, name, parent_id, main_company_id):
    """
    Crear una compañía directamente por SQL, copiando todos los valores
    de la compañía principal. Así evitamos los hooks de account que
    intentan cargar chart of accounts.
    """
    # Obtener todas las columnas de res_company (excepto id, name, parent_id, partner_id)
    cr.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'res_company'
          AND column_name NOT IN ('id', 'name', 'parent_id', 'partner_id')
        ORDER BY ordinal_position
    """)
    columns = [row[0] for row in cr.fetchall()]

    # Crear el partner primero
    cr.execute("""
        INSERT INTO res_partner (name, is_company, company_id, active)
        VALUES (%s, true, %s, true)
        RETURNING id
    """, (name, parent_id))
    partner_id = cr.fetchone()[0]

    # Construir INSERT copiando valores de la compañía principal
    col_list = ', '.join('"%s"' % c for c in columns)
    cr.execute("""
        INSERT INTO res_company (name, parent_id, partner_id, %s)
        SELECT %%s, %%s, %%s, %s
        FROM res_company WHERE id = %%s
        RETURNING id
    """ % (col_list, col_list), (name, parent_id, partner_id, main_company_id))
    company_id = cr.fetchone()[0]

    # Actualizar el partner con el company_id correcto
    cr.execute(
        "UPDATE res_partner SET company_id = %s WHERE id = %s",
        (company_id, partner_id)
    )

    _logger.info("Compañía '%s' creada por SQL (id=%s, partner_id=%s)",
                 name, company_id, partner_id)
    return company_id


def migrate(cr, version):
    """Crear compañías hijas por SQL directo (sin hooks de account)."""
    company_names = [
        'Jose Velandia',
        'Juan Pablo Velandia',
        'Felipe Tibocha',
        'Luis Cubides',
    ]

    # Paso 1: Borrar compañías existentes y todas sus dependencias
    _delete_existing_companies(cr, company_names)

    # Obtener ID de la compañía principal
    cr.execute("SELECT id FROM res_company WHERE parent_id IS NULL LIMIT 1")
    main_company_id = cr.fetchone()[0]

    companies = [
        ('company_jose_velandia', 'Jose Velandia'),
        ('company_juan_pablo_velandia', 'Juan Pablo Velandia'),
        ('company_felipe_tibocha', 'Felipe Tibocha'),
        ('company_luis_cubides', 'Luis Cubides'),
    ]

    created_ids = []
    for xmlid, name in companies:
        company_id = _create_company_sql(cr, name, main_company_id, main_company_id)

        # Registrar xmlid
        cr.execute("""
            INSERT INTO ir_model_data (module, name, model, res_id, noupdate)
            VALUES ('bascula', %s, 'res.company', %s, true)
        """, (xmlid, company_id))

        created_ids.append(company_id)

    # Dar acceso al admin a todas las compañías
    cr.execute("SELECT id FROM res_users WHERE login = 'admin' OR id = 2 LIMIT 1")
    admin_row = cr.fetchone()
    if admin_row:
        admin_id = admin_row[0]
        for cid in [main_company_id] + created_ids:
            cr.execute("SAVEPOINT add_company")
            try:
                cr.execute("""
                    INSERT INTO res_company_users_rel (cid, user_id)
                    VALUES (%s, %s)
                """, (cid, admin_id))
                cr.execute("RELEASE SAVEPOINT add_company")
            except Exception:
                cr.execute("ROLLBACK TO SAVEPOINT add_company")

    _logger.info("Compañías configuradas correctamente. IDs: %s",
                 [main_company_id] + created_ids)
