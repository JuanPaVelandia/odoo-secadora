# -*- coding: utf-8 -*-
{
    'name': 'Lavish - Work Entries Gantt',
    'summary': 'Vista Gantt para entradas de trabajo',
    'category': 'Human Resources/Employees',
    'version': '19.0.1.0.1',
    'author': 'Lavish S.A.S',
    'license': 'OPL-1',
    'depends': [
        'hr_work_entry_contract',
        'hr_gantt',
    ],
    'data': [
        'views/hr_work_entry_views.xml',
    ],
    'assets': {
        'web.assets_backend_lazy': [
            'lavish_hr_work_entry_gantt/static/src/work_entries_gantt_model.js',
            'lavish_hr_work_entry_gantt/static/src/work_entries_gantt_controller.js',
            'lavish_hr_work_entry_gantt/static/src/work_entries_gantt_controller.xml',
            'lavish_hr_work_entry_gantt/static/src/work_entries_gantt_view.js',
        ],
    },
    'installable': True,
    'auto_install': False,
}
