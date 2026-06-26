# -*- coding: utf-8 -*-
"""Mixin para agrupaciones dinamicas de datos contables."""

from odoo import models
from collections import defaultdict, OrderedDict


class GroupingMixin(models.AbstractModel):
    """Mixin para agrupaciones dinamicas de datos."""

    _name = 'grouping.mixin'
    _description = 'Mixin de Agrupaciones Dinamicas'

    def group_data_by_field(self, data, group_field, sum_fields=None, count_field=None):
        """
        Agrupa datos por un campo especifico.

        Args:
            data: Lista de dicts con datos
            group_field: Campo por el cual agrupar
            sum_fields: Campos a sumar (lista)
            count_field: Campo para contar

        Returns:
            OrderedDict: Datos agrupados
        """
        sum_fields = sum_fields or ['debit', 'credit', 'balance']
        grouped = defaultdict(lambda: {
            'items': [],
            'totals': {f: 0.0 for f in sum_fields},
            'count': 0,
        })

        for item in data:
            key = item.get(group_field, '')
            grouped[key]['items'].append(item)
            grouped[key]['count'] += 1
            for field in sum_fields:
                grouped[key]['totals'][field] += item.get(field, 0) or 0

        return OrderedDict(sorted(grouped.items()))

    def group_data_multi_level(self, data, group_fields, sum_fields=None):
        """
        Agrupa datos por multiples niveles.

        Args:
            data: Lista de dicts con datos
            group_fields: Lista de campos para agrupar (jerarquico)
            sum_fields: Campos a sumar

        Returns:
            dict: Datos agrupados jerarquicamente
        """
        sum_fields = sum_fields or ['debit', 'credit', 'balance']

        def group_recursive(items, fields, level=0):
            if not fields:
                return {
                    'items': items,
                    'totals': {f: sum(i.get(f, 0) or 0 for i in items) for f in sum_fields},
                    'count': len(items),
                    'level': level,
                }

            current_field = fields[0]
            remaining_fields = fields[1:]

            grouped = defaultdict(list)
            for item in items:
                key = item.get(current_field, '')
                grouped[key].append(item)

            result = {}
            for key, group_items in sorted(grouped.items()):
                result[key] = group_recursive(group_items, remaining_fields, level + 1)

            return {
                'groups': result,
                'totals': {f: sum(g['totals'][f] for g in result.values()) for f in sum_fields},
                'count': sum(g['count'] for g in result.values()),
                'level': level,
            }

        return group_recursive(data, group_fields)

    def group_by_date_period(self, data, date_field='date', period='month'):
        """
        Agrupa datos por periodo de fecha.

        Args:
            data: Lista de dicts con datos
            date_field: Campo de fecha
            period: 'day', 'week', 'month', 'quarter', 'year'

        Returns:
            OrderedDict: Datos agrupados por periodo
        """
        from datetime import datetime

        def get_period_key(date_value):
            if not date_value:
                return 'Sin Fecha'
            if isinstance(date_value, str):
                date_value = datetime.strptime(date_value[:10], '%Y-%m-%d')

            if period == 'day':
                return date_value.strftime('%Y-%m-%d')
            elif period == 'week':
                return date_value.strftime('%Y-W%W')
            elif period == 'month':
                return date_value.strftime('%Y-%m')
            elif period == 'quarter':
                quarter = (date_value.month - 1) // 3 + 1
                return f"{date_value.year}-Q{quarter}"
            else:  # year
                return str(date_value.year)

        grouped = defaultdict(lambda: {
            'items': [],
            'totals': {'debit': 0, 'credit': 0, 'balance': 0},
            'count': 0,
        })

        for item in data:
            key = get_period_key(item.get(date_field))
            grouped[key]['items'].append(item)
            grouped[key]['count'] += 1
            for field in ['debit', 'credit', 'balance']:
                grouped[key]['totals'][field] += item.get(field, 0) or 0

        return OrderedDict(sorted(grouped.items()))

    def group_by_account_type(self, data, code_field='account_code'):
        """
        Agrupa datos por tipo de cuenta (primer digito PUC).

        Args:
            data: Lista de dicts
            code_field: Campo con codigo de cuenta

        Returns:
            OrderedDict: Agrupado por tipo
        """
        type_names = {
            '1': 'Activo',
            '2': 'Pasivo',
            '3': 'Patrimonio',
            '4': 'Ingresos',
            '5': 'Gastos',
            '6': 'Costos de Ventas',
            '7': 'Costos de Produccion',
            '8': 'Cuentas de Orden Deudoras',
            '9': 'Cuentas de Orden Acreedoras',
        }

        grouped = defaultdict(lambda: {
            'name': '',
            'items': [],
            'totals': {'debit': 0, 'credit': 0, 'balance': 0},
        })

        for item in data:
            code = str(item.get(code_field, '') or '')
            type_code = code[0] if code else '0'
            grouped[type_code]['name'] = type_names.get(type_code, f'Tipo {type_code}')
            grouped[type_code]['items'].append(item)
            for field in ['debit', 'credit', 'balance']:
                grouped[type_code]['totals'][field] += item.get(field, 0) or 0

        return OrderedDict(sorted(grouped.items()))

    def group_with_subtotals(self, data, group_field, sum_fields=None, include_grand_total=True):
        """
        Agrupa datos e incluye subtotales.

        Args:
            data: Lista de dicts
            group_field: Campo para agrupar
            sum_fields: Campos a sumar
            include_grand_total: Incluir total general

        Returns:
            list: Lista con items y subtotales intercalados
        """
        sum_fields = sum_fields or ['debit', 'credit', 'balance']
        grouped = self.group_data_by_field(data, group_field, sum_fields)

        result = []
        grand_totals = {f: 0.0 for f in sum_fields}

        for key, group_data in grouped.items():
            result.append({
                'type': 'header',
                'name': key,
                'level': 0,
            })

            for item in group_data['items']:
                item['type'] = 'data'
                item['level'] = 1
                result.append(item)

            subtotal = {
                'type': 'subtotal',
                'name': f'Subtotal {key}',
                'level': 0,
                **group_data['totals'],
            }
            result.append(subtotal)

            for f in sum_fields:
                grand_totals[f] += group_data['totals'][f]

        if include_grand_total:
            result.append({
                'type': 'total',
                'name': 'TOTAL GENERAL',
                'level': 0,
                **grand_totals,
            })

        return result

    def pivot_data(self, data, row_field, col_field, value_field, aggregate='sum'):
        """
        Crea tabla pivot de los datos.

        Args:
            data: Lista de dicts
            row_field: Campo para filas
            col_field: Campo para columnas
            value_field: Campo con valores
            aggregate: 'sum', 'count', 'avg', 'max', 'min'

        Returns:
            dict: Estructura pivot con rows, cols, values
        """
        rows = set()
        cols = set()
        values = defaultdict(lambda: defaultdict(list))

        for item in data:
            row = item.get(row_field, '')
            col = item.get(col_field, '')
            val = item.get(value_field, 0) or 0

            rows.add(row)
            cols.add(col)
            values[row][col].append(val)

        def aggregate_values(val_list):
            if not val_list:
                return 0
            if aggregate == 'sum':
                return sum(val_list)
            elif aggregate == 'count':
                return len(val_list)
            elif aggregate == 'avg':
                return sum(val_list) / len(val_list)
            elif aggregate == 'max':
                return max(val_list)
            elif aggregate == 'min':
                return min(val_list)
            return sum(val_list)

        pivot_values = {}
        for row in rows:
            pivot_values[row] = {}
            for col in cols:
                pivot_values[row][col] = aggregate_values(values[row][col])

        row_totals = {row: sum(pivot_values[row].values()) for row in rows}
        col_totals = {col: sum(pivot_values[row][col] for row in rows) for col in cols}
        grand_total = sum(row_totals.values())

        return {
            'rows': sorted(rows),
            'cols': sorted(cols),
            'values': pivot_values,
            'row_totals': row_totals,
            'col_totals': col_totals,
            'grand_total': grand_total,
        }

    def flatten_grouped_data(self, grouped_data, level=0):
        """
        Aplana datos agrupados jerarquicamente para exportacion.

        Args:
            grouped_data: Datos agrupados con group_data_multi_level
            level: Nivel actual

        Returns:
            list: Lista plana con niveles
        """
        result = []

        if 'groups' in grouped_data:
            for key, subgroup in grouped_data['groups'].items():
                result.append({
                    'type': 'header',
                    'name': key,
                    'level': level,
                    **grouped_data.get('totals', {}),
                })
                result.extend(self.flatten_grouped_data(subgroup, level + 1))
        elif 'items' in grouped_data:
            for item in grouped_data['items']:
                item['level'] = level
                item['type'] = 'data'
                result.append(item)

        return result

    def calculate_running_balance(self, data, balance_field='balance', date_field='date'):
        """
        Calcula saldo acumulado (running balance).

        Args:
            data: Lista de dicts ordenada por fecha
            balance_field: Campo de balance
            date_field: Campo de fecha

        Returns:
            list: Datos con campo running_balance agregado
        """
        sorted_data = sorted(data, key=lambda x: x.get(date_field, ''))
        running = 0

        for item in sorted_data:
            running += item.get(balance_field, 0) or 0
            item['running_balance'] = running

        return sorted_data

    def group_and_compare(self, data_period_1, data_period_2, group_field, value_field='balance'):
        """
        Agrupa y compara dos periodos.

        Args:
            data_period_1: Datos del primer periodo
            data_period_2: Datos del segundo periodo
            group_field: Campo para agrupar
            value_field: Campo a comparar

        Returns:
            list: Datos con comparacion (value_1, value_2, variation, percentage)
        """
        grouped_1 = self.group_data_by_field(data_period_1, group_field, [value_field])
        grouped_2 = self.group_data_by_field(data_period_2, group_field, [value_field])

        all_keys = set(grouped_1.keys()) | set(grouped_2.keys())
        result = []

        for key in sorted(all_keys):
            val_1 = grouped_1.get(key, {}).get('totals', {}).get(value_field, 0)
            val_2 = grouped_2.get(key, {}).get('totals', {}).get(value_field, 0)
            variation = val_2 - val_1

            if val_1 != 0:
                percentage = (variation / abs(val_1)) * 100
            else:
                percentage = 100 if val_2 > 0 else (-100 if val_2 < 0 else 0)

            result.append({
                group_field: key,
                'value_period_1': val_1,
                'value_period_2': val_2,
                'variation': variation,
                'percentage': percentage,
            })

        return result
