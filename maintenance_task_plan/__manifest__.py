{
    'name': 'Maintenance Task Plans',
    'version': '18.0.1.0.0',
    'category': 'Maintenance',
    'summary': 'Counter-based maintenance task plans with automatic work order generation',
    'description': """
        Extends the Maintenance module with counter-based task plans.
        Allows defining periodic maintenance tasks triggered by equipment
        usage counters (hour meters, odometers, tachometers, etc.).
        Automatically generates work orders when counters reach thresholds.
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
