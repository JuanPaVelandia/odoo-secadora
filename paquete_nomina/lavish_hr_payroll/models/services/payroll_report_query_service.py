# -*- coding: utf-8 -*-
"""
Servicio optimizado de consultas para reportes de nomina.
Utiliza search_read y lookups en batch para evitar N+1 queries.
"""
from collections import defaultdict


class PayrollReportQueryService:
    """Servicio para consultas optimizadas de reportes de nomina."""

    def __init__(self, env):
        self.env = env

    def get_payslips_data(self, payslip_ids, fields=None):
        """
        Obtiene datos de nominas con search_read.

        Args:
            payslip_ids: IDs de nominas a consultar
            fields: Lista de campos a obtener (None = todos)

        Returns:
            dict: Diccionario {payslip_id: data}
        """
        if not payslip_ids:
            return {}

        default_fields = [
            'id', 'name', 'employee_id', 'contract_id', 'struct_id',
            'date_from', 'date_to', 'state', 'payslip_run_id',
            'company_id'
        ]

        fields = fields or default_fields

        payslips_data = self.env['hr.payslip'].search_read(
            [('id', 'in', payslip_ids)],
            fields
        )

        return {p['id']: p for p in payslips_data}

    def get_payslip_lines_by_payslip(self, payslip_ids, include_zero=False):
        """
        Obtiene lineas de nomina agrupadas por payslip usando search_read.

        Args:
            payslip_ids: IDs de nominas
            include_zero: Incluir lineas con total = 0

        Returns:
            dict: {payslip_id: [lines_data]}
        """
        if not payslip_ids:
            return {}

        domain = [('slip_id', 'in', payslip_ids)]
        if not include_zero:
            domain.append(('total', '!=', 0))

        lines_data = self.env['hr.payslip.line'].search_read(
            domain,
            [
                'id', 'slip_id', 'name', 'code', 'category_id',
                'salary_rule_id', 'sequence', 'quantity', 'rate',
                'amount', 'total', 'amount_base', 'entity_id',
                'days_unpaid_absences', 'initial_accrual_date',
                'final_accrual_date'
            ],
            order='slip_id, sequence'
        )

        # Agrupar por payslip
        result = defaultdict(list)
        for line in lines_data:
            slip_id = line['slip_id'][0] if line['slip_id'] else None
            if slip_id:
                result[slip_id].append(line)

        return dict(result)

    def get_worked_days_by_payslip(self, payslip_ids):
        """
        Obtiene dias trabajados agrupados por payslip.

        Args:
            payslip_ids: IDs de nominas

        Returns:
            dict: {payslip_id: [worked_days_data]}
        """
        if not payslip_ids:
            return {}

        worked_days_data = self.env['hr.payslip.worked_days'].search_read(
            [('payslip_id', 'in', payslip_ids)],
            [
                'id', 'payslip_id', 'name', 'code', 'work_entry_type_id',
                'number_of_days', 'number_of_hours', 'amount'
            ]
        )

        result = defaultdict(list)
        for wd in worked_days_data:
            slip_id = wd['payslip_id'][0] if wd['payslip_id'] else None
            if slip_id:
                result[slip_id].append(wd)

        return dict(result)

    def get_employees_data(self, employee_ids, fields=None):
        """
        Obtiene datos de empleados con search_read.

        Args:
            employee_ids: IDs de empleados
            fields: Campos a obtener

        Returns:
            dict: {employee_id: data}
        """
        if not employee_ids:
            return {}

        default_fields = [
            'id', 'name', 'identification_id', 'department_id',
            'job_id', 'address_id', 'work_contact_id',
            'analytic_account_id', 'company_id'
        ]

        fields = fields or default_fields

        employees_data = self.env['hr.employee'].search_read(
            [('id', 'in', employee_ids)],
            fields
        )

        return {e['id']: e for e in employees_data}

    def get_contracts_data(self, contract_ids, fields=None):
        """
        Obtiene datos de contratos con search_read.

        Args:
            contract_ids: IDs de contratos
            fields: Campos a obtener

        Returns:
            dict: {contract_id: data}
        """
        if not contract_ids:
            return {}

        default_fields = [
            'id', 'name', 'employee_id', 'date_start', 'date_end',
            'wage', 'contract_type', 'analytic_account_id',
            'code_sena', 'risk_id', 'state'
        ]

        fields = fields or default_fields

        contracts_data = self.env['hr.contract'].search_read(
            [('id', 'in', contract_ids)],
            fields
        )

        return {c['id']: c for c in contracts_data}

    def get_salary_rules_lookup(self, rule_ids=None):
        """
        Crea lookup de reglas salariales.

        Args:
            rule_ids: IDs especificos o None para todas

        Returns:
            dict: {rule_id: {code, name, short_name, category_id, dev_or_ded}}
        """
        domain = []
        if rule_ids:
            domain = [('id', 'in', rule_ids)]

        rules_data = self.env['hr.salary.rule'].search_read(
            domain,
            ['id', 'code', 'name', 'short_name', 'category_id',
             'dev_or_ded', 'sequence', 'appears_on_payslip']
        )

        return {r['id']: r for r in rules_data}

    def get_categories_lookup(self, category_ids=None):
        """
        Crea lookup de categorias de reglas.

        Args:
            category_ids: IDs especificos o None para todas

        Returns:
            dict: {category_id: {code, name}}
        """
        domain = []
        if category_ids:
            domain = [('id', 'in', category_ids)]

        categories_data = self.env['hr.salary.rule.category'].search_read(
            domain,
            ['id', 'code', 'name']
        )

        return {c['id']: c for c in categories_data}

    def get_social_security_data_batch(self, employee_ids, date_from, date_to):
        """
        Obtiene datos de seguridad social en batch.

        Args:
            employee_ids: IDs de empleados
            date_from: Fecha inicio
            date_to: Fecha fin

        Returns:
            dict: {employee_id: ss_data}
        """
        if not employee_ids or not date_from or not date_to:
            return {}

        ss_lines = self.env['hr.executing.social.security'].search_read(
            [
                ('employee_id', 'in', employee_ids),
                ('executing_social_security_id.date_start', '>=', date_from),
                ('executing_social_security_id.date_end', '<=', date_to)
            ],
            [
                'employee_id', 'nValorSaludEmpresa', 'nValorSaludEmpleado',
                'nValorSaludTotal', 'nDiferenciaSalud', 'nValorPensionEmpresa',
                'nValorPensionEmpleado', 'nValorPensionTotal', 'nDiferenciaPension',
                'nPorcAporteARP', 'nValorARP', 'nValorCajaCom',
                'nValorSENA', 'nValorICBF'
            ]
        )

        # Agrupar y sumar por empleado
        result = defaultdict(lambda: {
            'health_company': 0, 'health_employee': 0, 'health_total': 0,
            'health_diff': 0, 'pension_company': 0, 'pension_employee': 0,
            'pension_total': 0, 'pension_diff': 0, 'risk_level': 0,
            'arl': 0, 'ccf': 0, 'sena': 0, 'icbf': 0
        })

        for ss in ss_lines:
            emp_id = ss['employee_id'][0] if ss['employee_id'] else None
            if emp_id:
                data = result[emp_id]
                data['health_company'] += ss.get('nValorSaludEmpresa', 0) or 0
                data['health_employee'] += ss.get('nValorSaludEmpleado', 0) or 0
                data['health_total'] += ss.get('nValorSaludTotal', 0) or 0
                data['health_diff'] += ss.get('nDiferenciaSalud', 0) or 0
                data['pension_company'] += ss.get('nValorPensionEmpresa', 0) or 0
                data['pension_employee'] += ss.get('nValorPensionEmpleado', 0) or 0
                data['pension_total'] += ss.get('nValorPensionTotal', 0) or 0
                data['pension_diff'] += ss.get('nDiferenciaPension', 0) or 0
                data['arl'] += ss.get('nValorARP', 0) or 0
                data['ccf'] += ss.get('nValorCajaCom', 0) or 0
                data['sena'] += ss.get('nValorSENA', 0) or 0
                data['icbf'] += ss.get('nValorICBF', 0) or 0
                # Para risk_level, tomar el primero no-zero
                if data['risk_level'] == 0 and ss.get('nPorcAporteARP'):
                    data['risk_level'] = ss['nPorcAporteARP'] * 100

        return dict(result)

    def get_leaves_by_employee(self, employee_ids, date_from, date_to):
        """
        Obtiene ausencias agrupadas por empleado.

        Args:
            employee_ids: IDs de empleados
            date_from: Fecha inicio
            date_to: Fecha fin

        Returns:
            dict: {employee_id: [leave_names]}
        """
        if not employee_ids or not date_from or not date_to:
            return {}

        leaves = self.env['hr.leave'].search_read(
            [
                ('employee_id', 'in', employee_ids),
                ('state', '=', 'validate'),
                '|',
                '&', ('request_date_from', '>=', date_from), ('request_date_from', '<=', date_to),
                '&', ('request_date_to', '>=', date_from), ('request_date_to', '<=', date_to)
            ],
            ['employee_id', 'private_name', 'holiday_status_id']
        )

        result = defaultdict(list)
        for leave in leaves:
            emp_id = leave['employee_id'][0] if leave['employee_id'] else None
            if emp_id:
                name = leave.get('private_name') or (
                    leave['holiday_status_id'][1] if leave.get('holiday_status_id') else ''
                )
                if name:
                    result[emp_id].append(name)

        return {k: ' -\r\n '.join(v) for k, v in result.items()}

    def get_bank_accounts_by_partner(self, partner_ids):
        """
        Obtiene cuentas bancarias principales por partner.

        Args:
            partner_ids: IDs de partners

        Returns:
            dict: {partner_id: {bank_name, acc_number, dispersion_account}}
        """
        if not partner_ids:
            return {}

        bank_accounts = self.env['res.partner.bank'].search_read(
            [
                ('partner_id', 'in', partner_ids),
                ('is_main', '=', True)
            ],
            ['partner_id', 'bank_id', 'acc_number', 'payroll_dispersion_account']
        )

        result = {}
        for acc in bank_accounts:
            partner_id = acc['partner_id'][0] if acc['partner_id'] else None
            if partner_id:
                result[partner_id] = {
                    'bank_name': acc['bank_id'][1] if acc.get('bank_id') else '',
                    'acc_number': acc.get('acc_number', ''),
                    'dispersion_account': acc['payroll_dispersion_account'][1] if acc.get('payroll_dispersion_account') else ''
                }

        return result

    def prepare_payslip_report_data(self, payslips, options):
        """
        Prepara todos los datos necesarios para el reporte en batch.

        Args:
            payslips: recordset de hr.payslip
            options: dict con opciones del reporte

        Returns:
            dict con todos los datos preparados
        """
        if not payslips:
            return {}

        payslip_ids = payslips.ids
        employee_ids = list(set(payslips.mapped('employee_id.id')))
        contract_ids = list(set(payslips.mapped('contract_id.id')))

        # Cargar todos los datos en batch
        payslips_data = self.get_payslips_data(payslip_ids)
        lines_by_slip = self.get_payslip_lines_by_payslip(payslip_ids)
        worked_days_by_slip = self.get_worked_days_by_payslip(payslip_ids)
        employees_data = self.get_employees_data(employee_ids)
        contracts_data = self.get_contracts_data(contract_ids)

        # Cargar lookups
        all_rule_ids = []
        all_category_ids = []
        for lines in lines_by_slip.values():
            for line in lines:
                if line.get('salary_rule_id'):
                    all_rule_ids.append(line['salary_rule_id'][0])
                if line.get('category_id'):
                    all_category_ids.append(line['category_id'][0])

        rules_lookup = self.get_salary_rules_lookup(list(set(all_rule_ids)))
        categories_lookup = self.get_categories_lookup(list(set(all_category_ids)))

        # Obtener fechas min/max
        dates = [(p.date_from, p.date_to) for p in payslips]
        min_date = min(d[0] for d in dates) if dates else None
        max_date = max(d[1] for d in dates) if dates else None

        # Datos opcionales
        ss_data = {}
        leaves_data = {}

        if options.get('show_social_security'):
            ss_data = self.get_social_security_data_batch(employee_ids, min_date, max_date)

        leaves_data = self.get_leaves_by_employee(employee_ids, min_date, max_date)

        # Obtener datos de bancos
        partner_ids = [e.get('work_contact_id', [None])[0] for e in employees_data.values() if e.get('work_contact_id')]
        bank_data = self.get_bank_accounts_by_partner([p for p in partner_ids if p])

        return {
            'payslips': payslips_data,
            'lines_by_slip': lines_by_slip,
            'worked_days_by_slip': worked_days_by_slip,
            'employees': employees_data,
            'contracts': contracts_data,
            'rules': rules_lookup,
            'categories': categories_lookup,
            'social_security': ss_data,
            'leaves': leaves_data,
            'bank_accounts': bank_data,
            'min_date': min_date,
            'max_date': max_date
        }

    def calculate_totals_by_category(self, lines_by_slip, categories_lookup, allowed_codes):
        """
        Calcula totales por categoria usando datos pre-cargados.

        Args:
            lines_by_slip: dict de lineas por payslip
            categories_lookup: lookup de categorias
            allowed_codes: lista de codigos permitidos

        Returns:
            dict: {category_code: total}
        """
        totals = defaultdict(float)

        for lines in lines_by_slip.values():
            for line in lines:
                cat_id = line['category_id'][0] if line.get('category_id') else None
                if cat_id and cat_id in categories_lookup:
                    cat_code = categories_lookup[cat_id].get('code', '')
                    if cat_code in allowed_codes or cat_code in ['TOTALDEV', 'TOTALDED', 'NET']:
                        totals[cat_code] += line.get('total', 0) or 0

        return dict(totals)

    def calculate_totals_by_department(self, payslips_data, employees_data, lines_by_slip):
        """
        Calcula totales por departamento.

        Args:
            payslips_data: datos de payslips
            employees_data: datos de empleados
            lines_by_slip: lineas por payslip

        Returns:
            dict: {dept_name: {devengos, deducciones, neto, empleados}}
        """
        dept_totals = defaultdict(lambda: {
            'devengos': 0, 'deducciones': 0, 'neto': 0, 'empleados': set()
        })

        for slip_id, slip_data in payslips_data.items():
            emp_id = slip_data['employee_id'][0] if slip_data.get('employee_id') else None
            if not emp_id or emp_id not in employees_data:
                continue

            emp_data = employees_data[emp_id]
            dept_name = emp_data['department_id'][1] if emp_data.get('department_id') else 'Sin Departamento'

            dept_totals[dept_name]['empleados'].add(emp_id)

            lines = lines_by_slip.get(slip_id, [])
            for line in lines:
                rule_code = line.get('code', '')
                total = line.get('total', 0) or 0

                if rule_code == 'TOTALDEV':
                    dept_totals[dept_name]['devengos'] += total
                elif rule_code == 'TOTALDED':
                    dept_totals[dept_name]['deducciones'] += total
                elif rule_code == 'NET':
                    dept_totals[dept_name]['neto'] += total

        # Convertir sets a conteos
        result = {}
        for dept, data in dept_totals.items():
            result[dept] = {
                'devengos': data['devengos'],
                'deducciones': data['deducciones'],
                'neto': data['neto'],
                'empleados': len(data['empleados'])
            }

        return result
