# -*- coding: utf-8 -*-

from . import controllers
from . import models
from . import report
from . import wizard
from .hooks import post_init_hook, uninstall_hook

def pre_init_hook(env):
    import logging
    _logger = logging.getLogger(__name__)

    # Verificar si la tabla existe antes de modificar
    env.cr.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'res_company'
        )
    """)
    if not env.cr.fetchone()[0]:
        _logger.info("Tabla res_company no existe, saltando pre_init_hook")
        return

    # Eliminar constraint de foreign key de validated_certificate si existe
    try:
        env.cr.execute("""
            ALTER TABLE res_company
            DROP CONSTRAINT IF EXISTS res_company_validated_certificate_fkey
        """)
        _logger.info("Constraint res_company_validated_certificate_fkey eliminado")
    except Exception as e:
        _logger.warning(f"No se pudo eliminar constraint: {e}")

    # Importar Environment solo si se necesita

    # Limpiar vistas de portal en caché (Odoo 19 compatible)
    try:
        env.cr.execute("""
            DELETE FROM ir_ui_view
            WHERE key LIKE 'lavish_hr_employee.employee_portal%%'
            AND type = 'qweb'
        """)
        _logger.info("Vistas de portal limpiadas correctamente")
    except Exception as e:
        _logger.warning(f"No se pudieron limpiar vistas de portal: {e}")

    # Limpiar datos de caché en ir_model_data
    try:
        env.cr.execute("""
            DELETE FROM ir_model_data
            WHERE module = 'lavish_hr_employee'
            AND model = 'ir.ui.view'
            AND name LIKE '%%portal%%'
        """)
        _logger.info("Datos de caché de portal limpiados")
    except Exception as e:
        _logger.warning(f"No se pudieron limpiar datos de caché: {e}")

    # Renombrar campos personalizados legacy
    fields_to_rename = [
        ('res.partner', 'x_type_thirdparty', 'type_thirdparty'),
        ('res.partner', 'x_document_type', 'document_type'),
        ('res.partner', 'x_digit_verification', 'digit_verification'),
        ('res.partner', 'x_business_name', 'business_name'),
        ('res.partner', 'x_first_name', 'first_name'),
        ('res.partner', 'x_second_name', 'second_name'),
        ('res.partner', 'x_first_lastname', 'first_lastname'),
        ('res.partner', 'x_second_lastname', 'second_lastname'),
        ('res.partner', 'x_digit_verification', 'digit_verification'),
    ]

    for model, old_field_name, new_field_name in fields_to_rename:
        if env['ir.model.fields'].search([('model', '=', model), ('name', '=', old_field_name)]):
            env.cr.execute(f'ALTER TABLE {model.replace(".", "_")} RENAME COLUMN {old_field_name} TO {new_field_name}')

    # Normalizar loan_id en hr_loan_request para evitar choques de tipo
    # al actualizar módulos que esperan loan_id como Many2one (integer).
    try:
        env.cr.execute("""
            SELECT data_type
            FROM information_schema.columns
            WHERE table_name = 'hr_loan_request'
              AND column_name = 'loan_id'
        """)
        row = env.cr.fetchone()
        if row and row[0] in ('character varying', 'text'):
            env.cr.execute("""
                ALTER TABLE hr_loan_request
                DROP CONSTRAINT IF EXISTS hr_loan_request_loan_id_fkey
            """)
            env.cr.execute("""
                ALTER TABLE hr_loan_request
                ALTER COLUMN loan_id TYPE integer
                USING (
                    CASE
                        WHEN loan_id IS NULL OR loan_id = '' THEN NULL
                        WHEN loan_id ~ '^[0-9]+$' THEN loan_id::integer
                        WHEN loan_id ~ '^hr\\.loan,[0-9]+$' THEN split_part(loan_id, ',', 2)::integer
                        ELSE NULL
                    END
                )
            """)
            env.cr.execute("""
                UPDATE hr_loan_request req
                SET loan_id = NULL
                WHERE loan_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM hr_loan l
                      WHERE l.id = req.loan_id
                  )
            """)
            _logger.info("loan_id en hr_loan_request normalizado a integer para FK con hr_loan")
    except Exception as e:
        _logger.warning(f"No se pudo normalizar hr_loan_request.loan_id: {e}")

    # Normalizar loan_category_id en hr_loan_request para FK con hr_loan_category.
    try:
        env.cr.execute("""
            SELECT data_type
            FROM information_schema.columns
            WHERE table_name = 'hr_loan_request'
              AND column_name = 'loan_category_id'
        """)
        row = env.cr.fetchone()
        if row and row[0] in ('character varying', 'text'):
            env.cr.execute("""
                ALTER TABLE hr_loan_request
                DROP CONSTRAINT IF EXISTS hr_loan_request_loan_category_id_fkey
            """)
            env.cr.execute("""
                ALTER TABLE hr_loan_request
                ALTER COLUMN loan_category_id TYPE integer
                USING (
                    CASE
                        WHEN loan_category_id IS NULL OR loan_category_id = '' THEN NULL
                        WHEN loan_category_id ~ '^[0-9]+$' THEN loan_category_id::integer
                        WHEN loan_category_id ~ '^hr\\.loan\\.category,[0-9]+$' THEN split_part(loan_category_id, ',', 2)::integer
                        ELSE NULL
                    END
                )
            """)
            env.cr.execute("""
                UPDATE hr_loan_request req
                SET loan_category_id = NULL
                WHERE loan_category_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM hr_loan_category c
                      WHERE c.id = req.loan_category_id
                  )
            """)
            _logger.info("loan_category_id en hr_loan_request normalizado a integer para FK con hr_loan_category")
    except Exception as e:
        _logger.warning(f"No se pudo normalizar hr_loan_request.loan_category_id: {e}")

    # Normalizar salary_increase_id en hr_contract_change_wage para FK con hr_salary_increase.
    try:
        env.cr.execute("""
            SELECT data_type
            FROM information_schema.columns
            WHERE table_name = 'hr_contract_change_wage'
              AND column_name = 'salary_increase_id'
        """)
        row = env.cr.fetchone()
        if row and row[0] in ('character varying', 'text'):
            env.cr.execute("""
                ALTER TABLE hr_contract_change_wage
                DROP CONSTRAINT IF EXISTS hr_contract_change_wage_salary_increase_id_fkey
            """)
            env.cr.execute("""
                ALTER TABLE hr_contract_change_wage
                ALTER COLUMN salary_increase_id TYPE integer
                USING (
                    CASE
                        WHEN salary_increase_id IS NULL OR salary_increase_id = '' THEN NULL
                        WHEN salary_increase_id ~ '^[0-9]+$' THEN salary_increase_id::integer
                        WHEN salary_increase_id ~ '^hr\\.salary\\.increase,[0-9]+$' THEN split_part(salary_increase_id, ',', 2)::integer
                        ELSE NULL
                    END
                )
            """)
            env.cr.execute("""
                UPDATE hr_contract_change_wage cw
                SET salary_increase_id = NULL
                WHERE salary_increase_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM hr_salary_increase si
                      WHERE si.id = cw.salary_increase_id
                  )
            """)
            _logger.info("salary_increase_id en hr_contract_change_wage normalizado a integer para FK con hr_salary_increase")
    except Exception as e:
        _logger.warning(f"No se pudo normalizar hr_contract_change_wage.salary_increase_id: {e}")
