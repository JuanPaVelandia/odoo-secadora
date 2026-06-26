# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Libros Contables Colombia',
    'version': '19.0.1.35.0',
    'category': 'Accounting/Accounting',
    'summary': 'Libros contables, estados financieros, auditoría y autoretenciones Colombia NIIF',
    'description': """
Libros Contables Colombia
=========================
Libros contables y estados financieros segun normativa colombiana NIIF/NIC.

LIBROS LEGALES:
- Libro Diario Oficial
- Libro Mayor Oficial
- Libro Auxiliar (con exportacion PDF/Excel optimizada)
- Libro Auxiliar Analitico (incluye cuenta analitica)
- Libro de Inventarios y Balances
- Balance de Prueba PUC (por niveles, con PDF/Excel)
- Balance de Prueba por Tercero (con PDF/Excel)

ESTADOS FINANCIEROS:
- Balance General Comparativo con Indicadores
- Estado de Resultados Comparativo
- Balance Comparativo por Mes
- Estado de Resultados por Mes
- Balance de Movimientos del Periodo (solo movimientos, drill-down a asientos)
- Estado de Flujos de Efectivo (NIC 7)
- Estado de Cambios en el Patrimonio
- Indicadores Financieros (KPIs)

AUDITORÍA CONTABLE:
- Auditoría de Consecutivos (detecta saltos en numeración)
- Documentos Modificados (registros editados post-creación)
- Conteo Mensual de Documentos
- Auditoría de Cuentas Bancarias de Terceros

AUTORETENCIONES:
- Autorretencion de ICA por municipio
- Autorretencion de Renta (Impuesto sobre la Renta)
- Calculo global desde cuentas de ingresos
- Generacion de asientos de autorretencion

FORMULARIOS DIAN:
- Formulario 300 - Declaracion IVA (Bimestral)
- Formulario 350 - Retencion en la Fuente (Mensual)
- Generacion de PDF con formato oficial DIAN
- Vista previa de calculos antes de generar

FILTROS AVANZADOS:
- Filtro por rango de cuentas (desde/hasta)
- Exclusion de cuentas especificas
- Busqueda de terceros por NIT/VAT
    """,
    'author': 'Donsson',
    'website': 'https://www.donsson.com',
    'depends': [
        'account',
        'account_reports',
        'l10n_latam_base',
        'tax_base_threshold',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/paperformat_data.xml',
        'data/all_financial_reports.xml',
        'views/account_tax_view.xml',
        'views/account_report_view.xml',
        'views/pdf_trial_balance_partner.xml',
        'views/self_withholding_views.xml',
        'wizard/dian_forms_wizard_views.xml',
        'wizard/report_export_wizard_views.xml',
    ],
    'assets': {
        'account_reports.assets_pdf_export': [
            'libros_contables_colombia/static/src/scss/trial_balance_partner_pdf.scss',
        ],
        'web.assets_backend': [
            'libros_contables_colombia/static/src/components/filters/filters.js',
            'libros_contables_colombia/static/src/components/filters/filters.xml',
            'libros_contables_colombia/static/src/components/filters/filter_account.xml',
            'libros_contables_colombia/static/src/components/filters/filter_tax.xml',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'OPL-1',
}
