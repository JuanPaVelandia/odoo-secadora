# -*- coding: utf-8 -*-
{
    'name': 'Reportes Fiscales Colombia',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Localizations/Reporting',
    'summary': 'Reportes fiscales DIAN - Formularios 300, 350, ICA, Auxiliares de Retenciones',
    'description': """
Módulo Completo de Reportes Fiscales para Colombia
===================================================

Características principales:
----------------------------
* **Formulario 300 - IVA Bimestral**:
  - Cálculo automático de IVA generado/descontable
  - Separación por tarifas (5%, 19%)
  - Devoluciones en ventas/compras

* **Formulario 350 - Retención en la Fuente**:
  - Retenciones PJ/PN separadas
  - Honorarios, comisiones, servicios, arrendamientos
  - ReteIVA régimen común

* **ICA Municipal**:
  - Configuración por ciudad/municipio
  - Tarifas CIIU 2022
  - Múltiples actividades económicas

* **Exportador Avanzado de Reportes**:
  - Agrupación multinivel configurable
  - Auxiliar de retenciones PJ/PN
  - Base sobre ingresos con fórmulas Python
  - Búsqueda flexible con queries nativos
  - Exportación a Excel/CSV

* **Integración con Odoo**:
  - Usa queries nativos (_get_query_tax_details)
  - Respeta include_base_amount y secuencias
  - Cálculo preciso de bases gravables

Configuración:
-------------
1. Configurar actividades CIIU por ciudad
2. Asignar tributos DIAN a impuestos (campo tributes)
3. Crear plantillas de formularios
4. Generar declaraciones desde wizard

Reportes Disponibles:
--------------------
- Detalle de impuestos con agrupación multinivel
- Auxiliar de retenciones (separado PJ/PN)
- Base sobre ingresos del mes
- Fórmulas personalizadas con Python
- Exportación a Excel con formato

Autor: Tu Empresa
Licencia: LGPL-3
    """,
    'author': 'Lavish S.A.S',
    'website': 'https://www.tuempresa.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'account',
        'l10n_co',
        'mail',
        'lavish_erp',  # Necesario para modelo lavish.ciiu
    ],
    'data': [
        # Seguridad
        'security/ir.model.access.csv',

        # Vistas
        'views/account_tax_views.xml',
        'views/account_tax_form_views.xml',

        # Wizard
        'wizard/tax_report_export_wizard_views.xml',
    ],
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'images': ['static/description/banner.png'],
    'external_dependencies': {
        'python': ['xlsxwriter'],
    },
}
