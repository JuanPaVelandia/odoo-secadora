# -*- coding: utf-8 -*-
{
    'name': 'DIAN Document Processor Enhanced',
    'version': '19.0.1.0.7',
    'category': 'Accounting/Localizations',
    'summary': 'Procesamiento avanzado de documentos electrónicos DIAN Colombia',
    'description': """
DIAN Document Processor Enhanced
=================================

Módulo completo para procesamiento de documentos electrónicos DIAN con las siguientes características:

Funcionalidades Principales:
----------------------------
* Procesamiento de XML de facturas, notas crédito y notas débito
* Consulta de documentos por CUFE
* Validación automática de totales con advertencias
* Gestión de tasa de cambio automática
* Predicción inteligente de productos
* Actualización automática de códigos de productos y órdenes de compra

Tipos de Documentos Soportados:
-------------------------------
* Factura de Venta (01)
* Factura de Exportación (02)
* Factura de Contingencia (03)
* Factura Electrónica Tipo 04
* Documento Soporte (05)
* Nota Crédito (91)
* Nota Débito (92)

Características Avanzadas:
--------------------------
* Manejo de múltiples monedas con conversión automática
* Gestión de anticipos y descuentos
* Soporte para mandatos y terceros en líneas
* Validación de totales con múltiples estrategias de cálculo
* Asociación automática de documentos relacionados (NC/ND)
* Procesamiento en lote de múltiples XMLs

Validaciones:
------------
* Verificación de duplicados
* Validación de totales con tolerancia configurable
* Cálculo inteligente de precio unitario con múltiples estrategias
* Advertencias visuales para discrepancias

Integraciones:
-------------
* Creación automática de facturas en Odoo
* Actualización de productos y proveedores
* Sincronización con órdenes de compra
* Gestión de impuestos y retenciones DIAN

Matching con Órdenes de Compra:
-------------------------------
* Asociación inteligente de líneas de documentos DIAN con órdenes de compra
* Algoritmo de similitud multi-criterio (producto, descripción, cantidad, precio, UdM)
* Matching automático con umbral configurable (75% por defecto)
* Validación de unidades de medida (coincide/convertible/incompatible)
* Sugerencias automáticas de líneas de OC basadas en similitud
* Wizard para matching masivo de todas las líneas
* Vista previa de matches sugeridos antes de confirmar
* Control de cantidades pendientes de facturar en OC
    """,
    'author': 'Lavish S.A.S',
    'website': 'https://www.example.com',
    'depends': [
        'base',
        'account',
        'purchase',
        'product',
        'mail',
        'uom',
        'product_unspsc',
        'base_business_document_import',
        'l10n_co_e_invoice',
    ],
    'external_dependencies': {
        'python': ['xmltodict', 'lxml', 'requests'],
    },
    'data': [
        'security/ir.model.access.csv',
        'security/dian_security.xml',
        'data/xml_invoice_templates.xml',
        'data/dian_data.xml',
        'views/dian_document_processor_views.xml',
        'views/res_company_views.xml',
        'views/account_move_extended_views.xml',
        'views/purchase_order_matching_views.xml',
        'views/purchase_order_creation_views.xml',
        'wizard/dian_unify_lines_wizard_views.xml',
        # 'views/dian_document_relations_views.xml',  # Temporalmente desactivado
    ],
    'demo': [
        'demo/dian_demo.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'lavish_xml_invoice/static/src/css/dian_styles.css',
            'lavish_xml_invoice/static/src/js/dian_widgets.js',
        ],
    },
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
