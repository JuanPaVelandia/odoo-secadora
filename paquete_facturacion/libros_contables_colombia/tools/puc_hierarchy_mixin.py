# -*- coding: utf-8 -*-
from odoo import models
from collections import defaultdict


class PUCHierarchyMixin(models.AbstractModel):
    _name = 'puc.hierarchy.mixin'
    _description = 'Mixin de Jerarquia PUC Colombia'

    PUC_LEVELS = {
        1: {'name': 'Clase', 'digits': 1},
        2: {'name': 'Grupo', 'digits': 2},
        3: {'name': 'Cuenta', 'digits': 4},
        4: {'name': 'Subcuenta', 'digits': 6},
        5: {'name': 'Auxiliar', 'digits': 8},
        6: {'name': 'Subauxiliar', 'digits': 10},
    }

    PUC_NAMES = {
        '1': 'Activo',
        '2': 'Pasivo',
        '3': 'Patrimonio',
        '4': 'Ingresos',
        '5': 'Gastos',
        '6': 'Costos de Ventas',
        '7': 'Costos de Produccion',
        '8': 'Cuentas de Orden Deudoras',
        '9': 'Cuentas de Orden Acreedoras',
        '11': 'Disponible',
        '12': 'Inversiones',
        '13': 'Deudores',
        '14': 'Inventarios',
        '15': 'Propiedades, Planta y Equipo',
        '16': 'Intangibles',
        '17': 'Diferidos',
        '21': 'Obligaciones Financieras',
        '22': 'Proveedores',
        '23': 'Cuentas por Pagar',
        '24': 'Impuestos, Gravamenes y Tasas',
        '25': 'Obligaciones Laborales',
        '26': 'Pasivos Estimados y Provisiones',
        '31': 'Capital Social',
        '32': 'Superavit de Capital',
        '33': 'Reservas',
        '36': 'Resultados del Ejercicio',
        '37': 'Resultados de Ejercicios Anteriores',
        '41': 'Operacionales',
        '42': 'No Operacionales',
        '51': 'Operacionales de Administracion',
        '52': 'Operacionales de Ventas',
        '53': 'No Operacionales',
        '61': 'Costo de Ventas',
    }

    def get_puc_level(self, account_code):
        if not account_code:
            return 5
        code_len = len(str(account_code).strip())
        for level, config in sorted(self.PUC_LEVELS.items()):
            if code_len <= config['digits']:
                return level
        return 6

    def get_puc_level_name(self, prefix, fallback_name=''):
        if prefix in self.PUC_NAMES:
            return self.PUC_NAMES[prefix]
        group = self.env['account.group'].search([('code_prefix_start', '=', prefix)], limit=1)
        if group:
            return group.name
        account = self.env['account.account'].search([('code', '=', prefix)], limit=1)
        if account:
            return account.name
        return fallback_name or f'Grupo {prefix}'

    def group_by_puc_level(self, account_data, target_level):
        level_digits = self.PUC_LEVELS.get(target_level, {}).get('digits', 6)
        grouped = defaultdict(lambda: {
            'name': '',
            'initial': 0.0,
            'debit': 0.0,
            'credit': 0.0,
            'balance': 0.0,
            'final': 0.0,
            'accounts': [],
            'has_children': False,
        })
        for account_id, data in account_data.items():
            code = data.get('code', '') or ''
            prefix = code[:level_digits] if len(code) >= level_digits else code
            grouped[prefix]['initial'] += data.get('initial', 0)
            grouped[prefix]['debit'] += data.get('debit', 0)
            grouped[prefix]['credit'] += data.get('credit', 0)
            grouped[prefix]['balance'] += data.get('balance', 0)
            grouped[prefix]['final'] += data.get('final', 0)
            grouped[prefix]['accounts'].append({'id': account_id, 'code': code, **data})
            if not grouped[prefix]['name'] or len(code) <= len(grouped[prefix].get('_shortest_code', code)):
                grouped[prefix]['name'] = self.get_puc_level_name(prefix, data.get('name', ''))
                grouped[prefix]['_shortest_code'] = code
        for code, data in grouped.items():
            data['has_children'] = any(len(a['code']) > len(code) for a in data['accounts'])
            data.pop('_shortest_code', None)
        return dict(sorted(grouped.items()))

    def build_puc_hierarchy(self, account_data):
        hierarchy = {}
        for account_id, data in account_data.items():
            code = data.get('code', '') or ''
            if not code:
                continue
            for level, config in self.PUC_LEVELS.items():
                if len(code) >= config['digits']:
                    prefix = code[:config['digits']]
                    if prefix not in hierarchy:
                        hierarchy[prefix] = {
                            'code': prefix,
                            'name': self.get_puc_level_name(prefix, data.get('name', '')),
                            'level': level,
                            'level_name': config['name'],
                            'totals': defaultdict(float),
                            'children': [],
                        }
                    for key in ['initial', 'debit', 'credit', 'balance', 'final']:
                        hierarchy[prefix]['totals'][key] += data.get(key, 0)
        return hierarchy
