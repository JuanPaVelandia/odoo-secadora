{
    'name': 'Planes de Tareas de Mantenimiento',
    'version': '18.0.1.0.0',
    'category': 'Maintenance',
    'summary': 'Planes de mantenimiento basados en contadores con generación automática de OTs',
    'description': """
        Extiende el módulo de Mantenimiento con planes de tareas basados en contadores.
        Permite definir tareas de mantenimiento periódicas disparadas por contadores
        de uso (horómetros, odómetros, tacómetros, etc.).
        Genera automáticamente órdenes de trabajo cuando los contadores alcanzan los umbrales.
    """,
    'author': 'Secadora La Gran Colombia S.A.S',
    'license': 'LGPL-3',
    'depends': [
        'maintenance',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/sequence_data.xml',
        'data/counter_type_data.xml',
        'data/cron_data.xml',
        'views/counter_type_views.xml',
        'views/task_plan_views.xml',
        'views/task_plan_line_views.xml',
        'views/maintenance_request_views.xml',
        'views/maintenance_equipment_views.xml',
        'wizards/update_counters_wizard_views.xml',
        'views/menu_views.xml',
    ],
    'demo': [
        'data/demo_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
