# -*- coding: utf-8 -*-
"""
Handlers para Reportes Mensuales Comparativos Colombia - Completo
=================================================================
Version con filtros y funciones de expansion.
"""

from odoo import models, _
from collections import defaultdict
from datetime import datetime
from dateutil.relativedelta import relativedelta
import logging
import re

_logger = logging.getLogger(__name__)

MONTH_LABELS = {
    1: 'jan', 2: 'feb', 3: 'mar', 4: 'apr', 5: 'may', 6: 'jun',
    7: 'jul', 8: 'aug', 9: 'sep', 10: 'oct', 11: 'nov', 12: 'dec'
}

MONTH_NAMES_ES = {
    1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril', 5: 'Mayo', 6: 'Junio',
    7: 'Julio', 8: 'Agosto', 9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'
}


class MonthlyReportBaseMixin(models.AbstractModel):
    """Base mixin para reportes mensuales."""
    _name = 'monthly.report.base.mixin'
    _inherit = ['report.line.mixin', 'puc.hierarchy.mixin', 'grouping.mixin']
    _description = 'Base para Reportes Mensuales'

    def _get_company_id_for_sql(self):
        """Obtiene el ID de compania para queries SQL."""
        return str(self.env.company.root_id.id or self.env.company.id)

    def _get_account_code_sql(self):
        """Retorna la expresion SQL para obtener account.code en Odoo 18."""
        company_id = self._get_company_id_for_sql()
        return f"COALESCE(aa.code_store->>'{company_id}', '')"

    def _get_months_in_range(self, options):
        """Obtiene lista de meses en el rango."""
        date_from = datetime.strptime(options['date']['date_from'], '%Y-%m-%d')
        date_to = datetime.strptime(options['date']['date_to'], '%Y-%m-%d')
        months = []
        current = date_from.replace(day=1)

        while current <= date_to:
            months.append({
                'year': current.year,
                'month': current.month,
                'label': MONTH_LABELS[current.month],
                'name': MONTH_NAMES_ES[current.month],
                'date_from': current.strftime('%Y-%m-%d'),
                'date_to': (current + relativedelta(months=1, days=-1)).strftime('%Y-%m-%d'),
            })
            current = current + relativedelta(months=1)

        return months

    def _get_monthly_data_query(self, date_to, account_prefixes=None, date_from=None):
        """Query generica para obtener datos mensuales (compatible Odoo 18)."""
        account_code = self._get_account_code_sql()

        prefix_filter = ""
        if account_prefixes:
            patterns = ' OR '.join(f"{account_code} LIKE '{p}%'" for p in account_prefixes)
            prefix_filter = f"AND ({patterns})"

        date_filter = f"AND am.date <= '{date_to}'"
        if date_from:
            date_filter = f"AND am.date BETWEEN '{date_from}' AND '{date_to}'"

        return f"""
            SELECT
                SUBSTRING({account_code} FROM 1 FOR 2) as account_group,
                SUM(aml.balance) as balance
            FROM account_move_line aml
            JOIN account_account aa ON aa.id = aml.account_id
            JOIN account_move am ON am.id = aml.move_id
            WHERE am.state = 'posted' {date_filter} {prefix_filter}
            GROUP BY SUBSTRING({account_code} FROM 1 FOR 2)
        """

    def _get_detail_query(self, date_to, parent_code, date_from=None):
        """Query para obtener detalle de subcuentas."""
        account_code = self._get_account_code_sql()

        date_filter = f"AND am.date <= '{date_to}'"
        if date_from:
            date_filter = f"AND am.date BETWEEN '{date_from}' AND '{date_to}'"

        return f"""
            SELECT
                {account_code} as account_code,
                aa.id as account_id,
                SUM(aml.balance) as balance
            FROM account_move_line aml
            JOIN account_account aa ON aa.id = aml.account_id
            JOIN account_move am ON am.id = aml.move_id
            WHERE am.state = 'posted'
              AND {account_code} LIKE '{parent_code}%'
              {date_filter}
            GROUP BY {account_code}, aa.id
            HAVING SUM(aml.balance) != 0
            ORDER BY {account_code}
        """

    def _build_columns_from_options(self, report, options, col_map):
        """Construye columnas usando la definicion del XML."""
        columns = []
        for col in options.get('columns', []):
            expr_label = col.get('expression_label')
            value = col_map.get(expr_label, 0)
            columns.append(report._build_column_dict(value, col, options=options))
        return columns


class MonthlyBalanceReportHandler(models.AbstractModel):
    """Handler para Balance Comparativo por Mes."""
    _name = 'co.monthly.balance.report.handler'
    _inherit = ['account.report.custom.handler', 'monthly.report.base.mixin']
    _description = 'Balance Comparativo por Mes - Handler'

    _report_css_class = 'monthly_balance_report_co'

    BALANCE_STRUCTURE = [
        {'code': '1', 'name': 'ACTIVO', 'level': 0, 'type': 'total', 'sign': 1},
        {'code': '11', 'name': 'Disponible', 'level': 1, 'type': 'subtotal', 'sign': 1},
        {'code': '12', 'name': 'Inversiones', 'level': 1, 'type': 'subtotal', 'sign': 1},
        {'code': '13', 'name': 'Deudores', 'level': 1, 'type': 'subtotal', 'sign': 1},
        {'code': '14', 'name': 'Inventarios', 'level': 1, 'type': 'subtotal', 'sign': 1},
        {'code': '15', 'name': 'Propiedad, Planta y Equipo', 'level': 1, 'type': 'subtotal', 'sign': 1},
        {'code': '16', 'name': 'Intangibles', 'level': 1, 'type': 'subtotal', 'sign': 1},
        {'code': '17', 'name': 'Diferidos', 'level': 1, 'type': 'subtotal', 'sign': 1},
        {'code': '19', 'name': 'Valorizaciones', 'level': 1, 'type': 'subtotal', 'sign': 1},
        {'code': '2', 'name': 'PASIVO', 'level': 0, 'type': 'total', 'sign': -1},
        {'code': '21', 'name': 'Obligaciones Financieras', 'level': 1, 'type': 'subtotal', 'sign': -1},
        {'code': '22', 'name': 'Proveedores', 'level': 1, 'type': 'subtotal', 'sign': -1},
        {'code': '23', 'name': 'Cuentas por Pagar', 'level': 1, 'type': 'subtotal', 'sign': -1},
        {'code': '24', 'name': 'Impuestos, Gravamenes y Tasas', 'level': 1, 'type': 'subtotal', 'sign': -1},
        {'code': '25', 'name': 'Obligaciones Laborales', 'level': 1, 'type': 'subtotal', 'sign': -1},
        {'code': '26', 'name': 'Pasivos Estimados', 'level': 1, 'type': 'subtotal', 'sign': -1},
        {'code': '27', 'name': 'Diferidos', 'level': 1, 'type': 'subtotal', 'sign': -1},
        {'code': '28', 'name': 'Otros Pasivos', 'level': 1, 'type': 'subtotal', 'sign': -1},
        {'code': '3', 'name': 'PATRIMONIO', 'level': 0, 'type': 'total', 'sign': -1},
        {'code': '31', 'name': 'Capital Social', 'level': 1, 'type': 'subtotal', 'sign': -1},
        {'code': '32', 'name': 'Superavit de Capital', 'level': 1, 'type': 'subtotal', 'sign': -1},
        {'code': '33', 'name': 'Reservas', 'level': 1, 'type': 'subtotal', 'sign': -1},
        {'code': '36', 'name': 'Resultados del Ejercicio', 'level': 1, 'type': 'subtotal', 'sign': -1},
        {'code': '37', 'name': 'Resultados Ejercicios Anteriores', 'level': 1, 'type': 'subtotal', 'sign': -1},
    ]

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        """Genera lineas del balance mensual."""
        try:
            months = self._get_months_in_range(options)
            monthly_data = self._get_monthly_balance_data(months)
            lines = []
            for item in self.BALANCE_STRUCTURE:
                line = self._generate_line(report, options, item, monthly_data, months)
                if line:
                    lines.append((0, line))
            return lines
        except Exception as e:
            _logger.error(f"Error en balance mensual: {str(e)}")
            return [(0, self._get_error_line(report, options, str(e)))]

    def _get_monthly_balance_data(self, months):
        """Obtiene saldos por cuenta y mes."""
        data = defaultdict(lambda: defaultdict(float))

        for month_info in months:
            query = self._get_monthly_data_query(month_info['date_to'])
            self._cr.execute(query)

            for row in self._cr.dictfetchall():
                account_group = row['account_group']
                balance = row['balance'] or 0
                data[account_group][month_info['label']] = balance
                if len(account_group) >= 1:
                    data[account_group[0]][month_info['label']] += balance

        return data

    def _generate_line(self, report, options, item, monthly_data, months):
        """Genera una linea del balance usando columnas del XML."""
        code, sign = item['code'], item.get('sign', 1)
        line_id = report._get_generic_line_id(None, None, markup=f'balance_{code}')
        is_unfolded = line_id in options.get('unfolded_lines', [])

        # Construir mapa de valores por expression_label
        col_map = {'account_code': code}
        total = 0

        for month_info in months:
            balance = monthly_data.get(code, {}).get(month_info['label'], 0) * sign
            total += balance
            col_map[month_info['label']] = balance

        col_map['total'] = total

        can_expand = item['type'] in ['total', 'subtotal']

        return {
            'id': line_id,
            'name': f"{code} {item['name']}",
            'level': item['level'],
            'class': 'o_account_reports_level_total' if item['type'] == 'total' else '',
            'unfoldable': can_expand,
            'unfolded': is_unfolded or options.get('unfold_all', False),
            'expand_function': '_report_expand_unfoldable_line_monthly_balance' if can_expand else None,
            'columns': self._build_columns_from_options(report, options, col_map),
        }

    def _report_expand_unfoldable_line_monthly_balance(self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None):
        """Expande una linea del balance mensual para mostrar subcuentas."""
        report = self.env['account.report'].browse(options['report_id'])
        lines = []

        # Extraer codigo del markup
        match = re.search(r'balance_(\d+)', line_dict_id)
        if not match:
            return {'lines': [], 'offset_increment': 0, 'has_more': False}

        parent_code = match.group(1)
        months = self._get_months_in_range(options)

        # Buscar item padre para obtener sign
        sign = 1
        parent_level = 0
        for item in self.BALANCE_STRUCTURE:
            if item['code'] == parent_code:
                sign = item.get('sign', 1)
                parent_level = item['level']
                break

        # Obtener datos de subcuentas para cada mes
        child_data = defaultdict(lambda: defaultdict(float))

        for month_info in months:
            query = self._get_detail_query(month_info['date_to'], parent_code)
            self._cr.execute(query)

            for row in self._cr.dictfetchall():
                account_code = row['account_code']
                if account_code and len(account_code) > len(parent_code):
                    child_data[account_code][month_info['label']] = row['balance'] or 0
                    child_data[account_code]['account_id'] = row['account_id']

        # Generar lineas hijas
        for child_code in sorted(child_data.keys()):
            data = child_data[child_code]

            # Obtener nombre de cuenta
            account = self.env['account.account'].browse(data.get('account_id'))
            account_name = account.name if account else child_code

            col_map = {'account_code': child_code}
            total = 0

            for month_info in months:
                balance = data.get(month_info['label'], 0) * sign
                total += balance
                col_map[month_info['label']] = balance

            col_map['total'] = total

            child_line_id = report._get_generic_line_id(
                'account.account', data.get('account_id'),
                markup=f'balance_{child_code}',
                parent_line_id=line_dict_id
            )

            lines.append({
                'id': child_line_id,
                'name': f"{child_code} {account_name}",
                'level': parent_level + 2,
                'parent_id': line_dict_id,
                'unfoldable': False,
                'columns': self._build_columns_from_options(report, options, col_map),
                'caret_options': 'account.account',
            })

        return {'lines': lines, 'offset_increment': len(lines), 'has_more': False}


class MonthlyIncomeReportHandler(models.AbstractModel):
    """Handler para Estado de Resultados por Mes."""
    _name = 'co.monthly.income.report.handler'
    _inherit = ['account.report.custom.handler', 'monthly.report.base.mixin']
    _description = 'Estado de Resultados por Mes - Handler'

    _report_css_class = 'monthly_income_report_co'

    PL_STRUCTURE = [
        {'code': '4', 'name': 'INGRESOS', 'level': 0, 'type': 'total', 'sign': -1},
        {'code': '41', 'name': 'Operacionales', 'level': 1, 'type': 'subtotal', 'sign': -1},
        {'code': '42', 'name': 'No Operacionales', 'level': 1, 'type': 'subtotal', 'sign': -1},
        {'code': '5', 'name': 'GASTOS', 'level': 0, 'type': 'total', 'sign': 1},
        {'code': '51', 'name': 'Administracion', 'level': 1, 'type': 'subtotal', 'sign': 1},
        {'code': '52', 'name': 'Ventas', 'level': 1, 'type': 'subtotal', 'sign': 1},
        {'code': '53', 'name': 'No Operacionales', 'level': 1, 'type': 'subtotal', 'sign': 1},
        {'code': '54', 'name': 'Impuesto de Renta', 'level': 1, 'type': 'subtotal', 'sign': 1},
        {'code': '6', 'name': 'COSTO DE VENTAS', 'level': 0, 'type': 'total', 'sign': 1},
        {'code': '61', 'name': 'Costo de Ventas y Servicios', 'level': 1, 'type': 'subtotal', 'sign': 1},
        {'code': 'RES', 'name': 'RESULTADO DEL PERIODO', 'level': 0, 'type': 'calculated'},
    ]

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        """Genera lineas del estado de resultados mensual."""
        try:
            months = self._get_months_in_range(options)
            monthly_data = self._get_monthly_income_data(months)
            lines = []
            for item in self.PL_STRUCTURE:
                line = self._generate_line(report, options, item, monthly_data, months)
                if line:
                    lines.append((0, line))
            return lines
        except Exception as e:
            _logger.error(f"Error en estado de resultados mensual: {str(e)}")
            return [(0, self._get_error_line(report, options, str(e)))]

    def _get_monthly_income_data(self, months):
        """Obtiene movimientos por cuenta y mes para P&L."""
        data = defaultdict(lambda: defaultdict(float))

        for month_info in months:
            query = self._get_monthly_data_query(
                month_info['date_to'],
                account_prefixes=['4', '5', '6'],
                date_from=month_info['date_from']
            )
            self._cr.execute(query)

            for row in self._cr.dictfetchall():
                account_group = row['account_group']
                balance = row['balance'] or 0
                data[account_group][month_info['label']] = balance
                if len(account_group) >= 1:
                    main = account_group[0]
                    if main not in data:
                        data[main] = defaultdict(float)
                    data[main][month_info['label']] += balance

        return data

    def _generate_line(self, report, options, item, monthly_data, months):
        """Genera una linea del estado de resultados usando columnas del XML."""
        code, sign = item['code'], item.get('sign', 1)
        line_id = report._get_generic_line_id(None, None, markup=f'income_{code}')
        is_unfolded = line_id in options.get('unfolded_lines', [])

        # Construir mapa de valores por expression_label
        col_map = {'account_code': code if code != 'RES' else ''}
        total = 0

        if item['type'] == 'calculated':
            for month_info in months:
                label = month_info['label']
                ingresos = monthly_data.get('4', {}).get(label, 0) * -1
                gastos = monthly_data.get('5', {}).get(label, 0)
                costos = monthly_data.get('6', {}).get(label, 0)
                resultado = ingresos - gastos - costos
                total += resultado
                col_map[label] = resultado
        else:
            for month_info in months:
                balance = monthly_data.get(code, {}).get(month_info['label'], 0) * sign
                total += balance
                col_map[month_info['label']] = balance

        col_map['total'] = total

        can_expand = item['type'] in ['total', 'subtotal']

        return {
            'id': line_id,
            'name': f"{code} {item['name']}" if code != 'RES' else item['name'],
            'level': item['level'],
            'class': 'o_account_reports_level_total font-weight-bold' if item['type'] in ['total', 'calculated'] else '',
            'unfoldable': can_expand,
            'unfolded': is_unfolded or options.get('unfold_all', False),
            'expand_function': '_report_expand_unfoldable_line_monthly_income' if can_expand else None,
            'columns': self._build_columns_from_options(report, options, col_map),
        }

    def _report_expand_unfoldable_line_monthly_income(self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None):
        """Expande una linea del estado de resultados para mostrar subcuentas."""
        report = self.env['account.report'].browse(options['report_id'])
        lines = []

        # Extraer codigo del markup
        match = re.search(r'income_(\d+)', line_dict_id)
        if not match:
            return {'lines': [], 'offset_increment': 0, 'has_more': False}

        parent_code = match.group(1)
        months = self._get_months_in_range(options)

        # Buscar item padre para obtener sign
        sign = 1
        parent_level = 0
        for item in self.PL_STRUCTURE:
            if item['code'] == parent_code:
                sign = item.get('sign', 1)
                parent_level = item['level']
                break

        # Obtener datos de subcuentas para cada mes
        child_data = defaultdict(lambda: defaultdict(float))

        for month_info in months:
            query = self._get_detail_query(
                month_info['date_to'],
                parent_code,
                date_from=month_info['date_from']
            )
            self._cr.execute(query)

            for row in self._cr.dictfetchall():
                account_code = row['account_code']
                if account_code and len(account_code) > len(parent_code):
                    child_data[account_code][month_info['label']] = row['balance'] or 0
                    child_data[account_code]['account_id'] = row['account_id']

        # Generar lineas hijas
        for child_code in sorted(child_data.keys()):
            data = child_data[child_code]

            # Obtener nombre de cuenta
            account = self.env['account.account'].browse(data.get('account_id'))
            account_name = account.name if account else child_code

            col_map = {'account_code': child_code}
            total = 0

            for month_info in months:
                balance = data.get(month_info['label'], 0) * sign
                total += balance
                col_map[month_info['label']] = balance

            col_map['total'] = total

            child_line_id = report._get_generic_line_id(
                'account.account', data.get('account_id'),
                markup=f'income_{child_code}',
                parent_line_id=line_dict_id
            )

            lines.append({
                'id': child_line_id,
                'name': f"{child_code} {account_name}",
                'level': parent_level + 2,
                'parent_id': line_dict_id,
                'unfoldable': False,
                'columns': self._build_columns_from_options(report, options, col_map),
                'caret_options': 'account.account',
            })

        return {'lines': lines, 'offset_increment': len(lines), 'has_more': False}
