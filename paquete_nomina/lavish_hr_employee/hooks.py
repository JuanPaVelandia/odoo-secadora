# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """
    Hook ejecutado después de instalar el módulo.

    1. Migra configuraciones existentes de hr.annual.parameters si existen
    2. Crea encabezados para el año actual y siguiente si no existen
    3. Asocia líneas huérfanas con el encabezado correspondiente

    En Odoo 19+, post_init_hook recibe directamente el Environment.
    """

    _logger.info("=" * 80)
    _logger.info("Iniciando post_init_hook para lavish_hr_employee")
    _logger.info("=" * 80)

    # 1. Buscar líneas de configuración sin encabezado (migraciones antiguas)
    orphan_lines = env['hr.conf.certificate.income'].search([
        ('header_id', '=', False),
        ('annual_parameters_id', '!=', False)
    ])

    if orphan_lines:
        _logger.info(f"Encontradas {len(orphan_lines)} líneas huérfanas de configuraciones antiguas")
        _migrate_orphan_lines(env, orphan_lines)

    # 2. Crear encabezados para años actuales si no existen
    _create_default_headers(env)

    # 3. Asociar líneas XML creadas con encabezados
    _associate_xml_lines_with_headers(env)

    # 4. Crear prioridades de deducciones por defecto
    _create_default_deduction_priorities(env)

    _logger.info("=" * 80)
    _logger.info("Finalizado post_init_hook para lavish_hr_employee")
    _logger.info("=" * 80)


def _migrate_orphan_lines(env, orphan_lines):
    """
    Migra líneas huérfanas creando encabezados por año y compañía
    """
    # Agrupar líneas por annual_parameters_id
    lines_by_params = {}
    for line in orphan_lines:
        if line.annual_parameters_id:
            key = line.annual_parameters_id.id
            if key not in lines_by_params:
                lines_by_params[key] = []
            lines_by_params[key].append(line)

    # Crear encabezados y asociar líneas
    for param_id, lines in lines_by_params.items():
        annual_param = env['hr.annual.parameters'].browse(param_id)

        if not annual_param.exists():
            continue

        companies = annual_param.company_ids or env.company
        company = companies[0]
        _logger.info(f"Migrando {len(lines)} líneas del parámetro anual {annual_param.year} - {company.name}")

        # Buscar o crear encabezado
        header = env['hr.certificate.income.header'].search([
            ('year', '=', annual_param.year),
            ('company_id', '=', company.id)
        ], limit=1)

        if not header:
            # Crear encabezado
            header = env['hr.certificate.income.header'].create({
                'name': f'Certificado {annual_param.year} - {company.name}',
                'company_id': company.id,
                'year': annual_param.year,
                'uvt_value': annual_param.value_uvt or 0.0,
            })
            _logger.info(f"  ✓ Creado encabezado: {header.name}")
        else:
            _logger.info(f"  ✓ Usando encabezado existente: {header.name}")

        # Asociar líneas con el encabezado
        for line in lines:
            line.write({'header_id': header.id})

        _logger.info(f"  ✓ Asociadas {len(lines)} líneas con el encabezado")


def _create_default_headers(env):
    """
    Crea encabezados por defecto para el año actual y siguiente
    en todas las compañías activas
    """
    from datetime import date
    current_year = date.today().year
    years = [current_year, current_year + 1]

    companies = env['res.company'].search([])

    for company in companies:
        for year in years:
            # Verificar si ya existe
            existing = env['hr.certificate.income.header'].search([
                ('year', '=', year),
                ('company_id', '=', company.id)
            ], limit=1)

            if existing:
                _logger.info(f"Encabezado ya existe para {year} - {company.name}")
                continue

            # Buscar parámetros anuales
            annual_params = env['hr.annual.parameters'].get_for_year(
                year,
                company_id=company.id,
                raise_if_not_found=False,
            )

            uvt_value = annual_params.value_uvt if annual_params else 0.0

            # No crear encabezado si UVT es 0 (se creará cuando se configure)
            if uvt_value <= 0:
                _logger.info(f"Saltando creación de encabezado para {year} - {company.name} (UVT no configurado)")
                continue

            # Crear encabezado
            header = env['hr.certificate.income.header'].create({
                'name': f'Certificado {year} - {company.name}',
                'company_id': company.id,
                'year': year,
                'uvt_value': uvt_value,
            })

            _logger.info(f"✓ Creado encabezado: {header.name} (UVT: {uvt_value})")

            # Asociar líneas XML con este encabezado
            _associate_lines_to_header(env, header)


def _associate_xml_lines_with_headers(env):
    """
    Asocia líneas creadas por XML que no tienen encabezado
    con los encabezados correspondientes de cada compañía
    """
    orphan_lines = env['hr.conf.certificate.income'].search([
        ('header_id', '=', False),
        ('annual_parameters_id', '=', False)
    ])

    if not orphan_lines:
        _logger.info("No hay líneas XML sin asociar")
        return

    _logger.info(f"Encontradas {len(orphan_lines)} líneas XML sin encabezado")

    from datetime import date
    current_year = date.today().year

    # Obtener todas las compañías
    companies = env['res.company'].search([])

    for company in companies:
        # Buscar o crear encabezado del año actual para esta compañía
        header = env['hr.certificate.income.header'].search([
            ('year', '=', current_year),
            ('company_id', '=', company.id)
        ], limit=1)

        if not header:
            # Buscar parámetros anuales para obtener UVT
            annual_params = env['hr.annual.parameters'].get_for_year(
                current_year,
                company_id=company.id,
                raise_if_not_found=False,
            )

            uvt_value = annual_params.value_uvt if annual_params else 0.0

            # No crear encabezado si UVT es 0 (se creará cuando se configure)
            if uvt_value <= 0:
                _logger.info(f"Saltando creación de encabezado para {current_year} - {company.name} (UVT no configurado)")
                continue

            # Crear encabezado
            header = env['hr.certificate.income.header'].create({
                'name': f'Certificado {current_year} - {company.name}',
                'company_id': company.id,
                'year': current_year,
                'uvt_value': uvt_value,
            })
            _logger.info(f"  ✓ Creado encabezado para {company.name}: {header.name}")

    # Ahora asociar todas las líneas huérfanas con el encabezado de la compañía principal
    main_company = env.ref('base.main_company', raise_if_not_found=False)
    if not main_company:
        main_company = companies[0] if companies else False

    if main_company:
        header = env['hr.certificate.income.header'].search([
            ('year', '=', current_year),
            ('company_id', '=', main_company.id)
        ], limit=1)

        if header and orphan_lines:
            orphan_lines.write({'header_id': header.id})
            _logger.info(f"✓ Asociadas {len(orphan_lines)} líneas XML con {header.name}")


def _associate_lines_to_header(env, header):
    """
    Asocia líneas huérfanas de XML al encabezado especificado
    """
    # Buscar líneas sin encabezado de la misma compañía
    orphan_lines = env['hr.conf.certificate.income'].search([
        ('header_id', '=', False),
        ('annual_parameters_id', '=', False)
    ])

    if orphan_lines and header.year == env.context.get('default_year', header.year):
        # Solo asociar si es el año actual o el contexto lo indica
        from datetime import date
        if header.year == date.today().year:
            orphan_lines.write({'header_id': header.id})
            _logger.info(f"  ✓ Asociadas {len(orphan_lines)} líneas con {header.name}")


def _create_default_deduction_priorities(env):
    """
    Crea las prioridades de deducciones por defecto.

    Lee las reglas de deducción existentes y crea prioridades
    basadas en su categoría y secuencia.
    """
    _logger.info("=" * 80)
    _logger.info("Creando prioridades de deducciones por defecto")
    _logger.info("=" * 80)

    # Verificar si ya existen prioridades
    existing_count = env['hr.deduction.priority'].search_count([])

    if existing_count > 0:
        _logger.info(f"Ya existen {existing_count} prioridades configuradas. Omitiendo creación por defecto.")
        return

    # Llamar al método del modelo para crear prioridades por defecto
    try:
        created = env['hr.deduction.priority'].create_default_priorities()
        if created:
            _logger.info(f"✓ Creadas {len(created)} prioridades por defecto:")
            for name in created[:10]:  # Mostrar las primeras 10
                _logger.info(f"  - {name}")
            if len(created) > 10:
                _logger.info(f"  ... y {len(created) - 10} más")
        else:
            _logger.info("No se crearon prioridades por defecto (sin reglas de deducción encontradas)")
    except Exception as e:
        _logger.error(f"Error al crear prioridades por defecto: {e}")
        # No lanzar excepción para no bloquear la instalación


def uninstall_hook(env):
    """
    Hook ejecutado antes de desinstalar el módulo.
    Limpia datos si es necesario.

    En Odoo 19+, uninstall_hook recibe directamente el Environment.
    """
    _logger.info("Ejecutando uninstall_hook para lavish_hr_employee")
    # No eliminamos datos para preservar histórico
    pass
