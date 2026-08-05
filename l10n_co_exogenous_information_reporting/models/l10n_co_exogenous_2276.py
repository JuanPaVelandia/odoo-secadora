from odoo import api, fields, models, _, Command
from odoo.exceptions import UserError
import base64


class ConfigAccounts(models.Model):
    _name = 'l10n_co.exogenous_2276_rule'
    _description = 'Configuración de reglas Reporte 2276'

    name = fields.Char(string='Nombre', required=True)
    code = fields.Char(string='Código', required=True)
    config_rule_line_ids = fields.One2many(
        comodel_name='l10n_co.exogenous_2276_rule_line',
        inverse_name='confi_id',
        string='Líneas de Configuración'
    )

    header_id = fields.Many2one('l10n_co.exogenous_income_cert_config',
        string='Configuración Certificado',
        help='Configuración de certificado de ingresos para cargar reglas automáticamente',
        check_company=True)

    # Mapeo de secuencias del certificado a columnas de exogena
    CERT_TO_EXOGENA = {
        36: '12',   # Salarios -> Pagos por Salarios
        37: '31',   # Bonos electrónicos
        38: '14',   # Honorarios
        39: '15',   # Servicios
        40: '16',   # Comisiones
        41: '17',   # Prestaciones sociales
        42: '18',   # Viáticos
        43: '19',   # Gastos representación
        44: '20',   # Compensaciones cooperativo
        45: '21',   # Otros pagos
        46: '22',   # Cesantías (al empleado)
        47: '22',   # Cesantías (al fondo) - misma columna, diferente severance_pay
        48: '23',   # Pensiones
        50: '25',   # Aportes salud
        51: '26',   # Aportes pensión
        53: '27',   # Aportes voluntarios pensión
        54: '28',   # AFC
        55: '30',   # Retenciones
    }

    def action_load_from_certificate_config(self):
        """Carga reglas salariales desde l10n_co.exogenous_income_cert_config"""
        self.ensure_one()

        if not self.header_id:
            raise UserError(_(
                'Debe seleccionar una configuración de certificado de ingresos.'
            ))

        self.config_rule_line_ids.unlink()

        created_count = 0
        for cert_line in self.header_id.line_ids:
            exogena_col = self.CERT_TO_EXOGENA.get(cert_line.sequence)

            if not exogena_col:
                continue

            if not cert_line.salary_rule_id:
                continue

            vals = {
                'confi_id': self.id,
                'column_selection': exogena_col,
                'calculation': 'sum_rule',
                'salary_rule_id': [Command.set(cert_line.salary_rule_id.ids)],
                'accumulated_previous_year': cert_line.accumulated_previous_year,
            }

            if cert_line.origin_severance_pay:
                vals['origin_severance_pay'] = cert_line.origin_severance_pay

            self.env['l10n_co.exogenous_2276_rule_line'].create(vals)
            created_count += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Carga Completada'),
                'message': _(
                    'Se crearon %s líneas de configuración desde el certificado.'
                ) % created_count,
                'type': 'success',
                'sticky': False,
            }
        }


    # Valores por defecto por columna: tipo de cálculo, origen cesantías,
    # tope UVT y cualquier otra metadata útil para precargar al usuario.
    DEFAULT_LINE_DEFAULTS = {
        # XSD attr -> defaults
        '12':  {'calculation': 'sum_rule'},   # pasa - Salarios
        '13':  {'calculation': 'sum_rule'},   # paec - Emolumentos eclesiásticos
        '14':  {'calculation': 'sum_rule'},   # paho - Honorarios
        '15':  {'calculation': 'sum_rule'},   # pase - Servicios
        '16':  {'calculation': 'sum_rule'},   # paco - Comisiones
        '17':  {'calculation': 'sum_rule'},   # papre - Prestaciones
        '18':  {'calculation': 'sum_rule'},   # pavia - Viáticos
        '19':  {'calculation': 'sum_rule'},   # paga - Gastos representación
        '20':  {'calculation': 'sum_rule'},   # patra - Compensaciones cooperativas
        '21':  {'calculation': 'sum_rule'},   # potro - Otros pagos
        '22':  {'calculation': 'sum_rule', 'origin_severance_pay': 'employee'},   # cein
        '22b': {'calculation': 'sum_rule', 'origin_severance_pay': 'fund'},       # ceco
        '22c': {'calculation': 'sum_rule'},                                       # auce
        '23':  {'calculation': 'sum_rule'},   # peju - Pensiones
        '24':  {'calculation': 'sum_rule'},   # tingbtp - Total ingresos brutos
        '25':  {'calculation': 'sum_rule'},   # apos - Aportes salud
        '26':  {'calculation': 'sum_rule'},   # apof - Aportes pensión obligatorios
        '26b': {'calculation': 'sum_rule'},   # aprais - Voluntarios RAIS
        '27':  {'calculation': 'sum_rule'},   # apov - Voluntarios pensiones
        '28':  {'calculation': 'sum_rule'},   # apafc - AFC
        '29':  {'calculation': 'sum_rule'},   # apavc - AVC
        '30':  {'calculation': 'sum_rule'},   # vare - Retenciones
        '31':  {'calculation': 'sum_rule'},   # pabop - Bonos electrónicos
        '32':  {'calculation': 'sum_rule'},   # vapo - Apoyos económicos
        '33':  {'calculation': 'sum_rule', 'limit_uvt_factor': 41.0},             # vaex >41 UVT
        '34':  {'calculation': 'sum_rule', 'limit_uvt_factor': 41.0},             # pagahuvt
        '35':  {'calculation': 'sum_rule'},   # identfc - manual
        '36':  {'calculation': 'sum_rule'},   # tdocpcc - manual
        '37':  {'calculation': 'sum_rule'},   # nitpcc - manual
        '38':  {'calculation': 'sum_accounting', 'account_move_type': 'credit'},  # ivav (contable)
        '39':  {'calculation': 'sum_accounting', 'account_move_type': 'credit'},  # rfiva (contable)
        '40':  {'calculation': 'average_rule'},                                   # vilap promedio 6 meses
    }

    def action_create_default_lines(self):
        """Crea una línea por cada columna disponible como estructura base.

        Aplica también los defaults razonables: cesantías al empleado vs fondo,
        topes UVT (41 UVT para alimentación), cálculo contable para IVA y rete
        IVA, y promedio mensual para vilap. El usuario solo asigna las reglas
        salariales / cuentas correspondientes después.
        """
        self.ensure_one()

        if self.config_rule_line_ids:
            raise UserError(_(
                'Ya existen líneas de configuración. '
                'Elimínelas primero si desea crear la estructura por defecto.'
            ))

        Concepts = self.env['l10n_co.exogenous_2276_rule_line']
        selection_list = Concepts._fields['column_selection'].selection

        created_count = 0
        for col_value, col_label in selection_list:
            vals = {
                'confi_id': self.id,
                'column_selection': col_value,
                'calculation': 'sum_rule',
            }
            vals.update(self.DEFAULT_LINE_DEFAULTS.get(col_value, {}))
            Concepts.create(vals)
            created_count += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Estructura Creada'),
                'message': _(
                    'Se crearon %s líneas de configuración. '
                    'Asigne las reglas salariales correspondientes.'
                ) % created_count,
                'type': 'success',
                'sticky': False,
            }
        }


class ConfigAccountsConcepts(models.Model):
    _name = 'l10n_co.exogenous_2276_rule_line'
    _description = 'Líneas Configuración de reglas Reporte 2276'

    # Las labels deben coincidir exactamente con las del header del Excel
    # generado por get_report_data() — el dispatch usa esto como clave.
    columnas = [
        ('12',  'pasa - Pagos por salarios'),
        ('13',  'paec - Pagos por emolumentos eclesiásticos'),
        ('14',  'paho - Pagos por honorarios'),
        ('15',  'pase - Pagos por servicios'),
        ('16',  'paco - Pagos por comisiones'),
        ('17',  'papre - Pagos por prestaciones sociales'),
        ('18',  'pavia - Pagos por viáticos'),
        ('19',  'paga - Pagos por gastos de representación'),
        ('20',  'patra - Pagos por compensaciones trabajo asociado cooperativo'),
        ('21',  'potro - Otros pagos'),
        ('22',  'cein - Cesantías e intereses pagadas al empleado'),
        ('22b', 'ceco - Cesantías consignadas al fondo'),
        ('22c', 'auce - Auxilio cesantías régimen tradicional CST'),
        ('23',  'peju - Pensiones de jubilación, vejez o invalidez'),
        ('24',  'tingbtp - Total ingresos brutos de rentas de trabajo y pensión'),
        ('25',  'apos - Aportes obligatorios a salud'),
        ('26',  'apof - Aportes obligatorios a pensión y solidaridad pensional'),
        ('26b', 'aprais - Aportes voluntarios al RAIS'),
        ('27',  'apov - Aportes voluntarios a fondos de pensiones voluntarias'),
        ('28',  'apafc - Aportes a cuentas AFC'),
        ('29',  'apavc - Aportes a cuentas AVC'),
        ('30',  'vare - Retenciones en la fuente por rentas de trabajo o pensión'),
        ('31',  'pabop - Pagos con bonos electrónicos / cheques / tarjetas / vales'),
        ('32',  'vapo - Apoyos económicos no reembolsables (Estado / programas educativos)'),
        ('33',  'vaex - Exceso pagos por alimentación >41 UVT'),
        ('34',  'pagahuvt - Pagos por alimentación hasta 41 UVT'),
        ('35',  'identfc - Identificación del fideicomiso o contrato'),
        ('36',  'tdocpcc - Tipo documento participante en contrato de colaboración'),
        ('37',  'nitpcc - Identificación participante en contrato de colaboración'),
        ('38',  'ivav - IVA mayor valor del costo o gasto'),
        ('39',  'rfiva - Retención en la fuente a título de IVA'),
        ('40',  'vilap - Ingreso laboral promedio últimos 6 meses'),
    ]
    confi_id = fields.Many2one('l10n_co.exogenous_2276_rule', ondelete='cascade')
    column_selection = fields.Selection(columnas, string='Columna')
    calculation = fields.Selection([
        ('sum_rule', 'Sumatoria Reglas (nómina)'),
        ('sum_accounting', 'Sumatoria Contable (account.move.line)'),
        ('average_rule', 'Promedio mensual (últimos 6 meses)'),
        ('dependents_type_vat', 'Dependientes - Tipo documento'),
        ('dependents_vat', 'Dependientes - No. Documento'),
        ('dependents_name', 'Dependientes - Apellidos y Nombres'),
        ('dependents_type', 'Dependientes - Parentesco'),
    ], string='Tipo Cálculo', default='sum_rule', required=True)
    salary_rule_id = fields.Many2many('hr.salary.rule', string='Regla Salarial')
    origin_severance_pay = fields.Selection(
        [('employee', 'Empleado'), ('fund', 'Fondo')],
        string='Pago cesantías'
    )
    accumulated_previous_year = fields.Boolean(string='Acumulado año anterior')

    # === Campos para cálculo contable (sum_accounting) ===
    account_ids = fields.Many2many(
        'account.account',
        'rule_2276_line_account_rel',
        'line_id',
        'account_id',
        string='Cuentas Contables',
        help='Cuentas a sumar cuando el tipo de cálculo es "Sumatoria Contable"',
    )
    account_move_type = fields.Selection([
        ('debit', 'Débito'),
        ('credit', 'Crédito'),
        ('both', 'Débito + Crédito (suma)'),
        ('balance', 'Saldo (Débito - Crédito)'),
    ], string='Tipo de movimiento', default='credit',
       help='Qué columna usar al agrupar las líneas contables.')
    move_state_filter = fields.Selection([
        ('posted', 'Solo publicados'),
        ('all', 'Todos'),
        ('draft', 'Solo borradores'),
    ], string='Estado de movimientos', default='posted')
    excluded_journal_ids = fields.Many2many(
        'account.journal',
        'rule_2276_line_journal_rel',
        'line_id',
        'journal_id',
        string='Diarios excluidos',
    )
    exclude_payroll_entries = fields.Boolean(
        string='Excluir asientos de nómina',
        default=False,
        help='Excluye diarios cuyo nombre contenga "nomina"/"payroll" para evitar duplicar nómina y contabilidad.',
    )

    # === Limites/topes (consistente con format_field y income_cert) ===
    limit_uvt_factor = fields.Float(
        string='Tope en UVT',
        help='Cantidad de UVT máxima a aplicar al valor calculado. Requiere uvt_value en el wizard.',
    )
    limit_fixed_value = fields.Float(
        string='Tope COP',
        help='Tope absoluto en COP a aplicar al valor calculado.',
    )


class ExogenaWizard(models.TransientModel):
    _name = 'l10n_co.exogenous_2276_wizard'
    _description = 'Exogena 2276 Wizard'

    start_date = fields.Date('Fecha Inicio', required=True)
    end_date = fields.Date('Fecha Fin', required=True, default=fields.Datetime.now)
    confi_id = fields.Many2one(
        'l10n_co.exogenous_2276_rule',
        string='Configuración a Utilizar',
        required=True
    )
    only_with_payslips = fields.Boolean(
        string='Solo empleados con nóminas',
        default=True,
        help='Solo incluye empleados que tienen nóminas procesadas en el período'
    )
    uvt_value = fields.Float(
        string='Valor UVT',
        help='Valor de la UVT del año gravable. Se usa para los topes en UVT '
             '(ej. exceso alimentación 41 UVT). Si la regla del certificado '
             'de ingresos asociado tiene UVT, se toma de allí.',
    )

    @api.onchange('confi_id', 'start_date')
    def _onchange_uvt_from_header(self):
        for w in self:
            header = w.confi_id.header_id if w.confi_id else False
            if header and header.uvt_value:
                w.uvt_value = header.uvt_value

    def generate_xlsx_report(self):
        self.ensure_one()
        data = self.get_report_data()
        return self.create_excel_report(data)

    def _get_employees_with_payslips(self):
        """Obtiene solo los empleados con nóminas pagadas (state='done') en el período."""
        Payslip = self.env['hr.payslip']
        slips = Payslip.search([
            *Payslip._check_company_domain(self.env.company),
            ('state', '=', 'done'),
            ('date_from', '<=', self.end_date),
            ('date_to', '>=', self.start_date),
        ])
        return slips.mapped('employee_id')

    def _sum_accounting_lines(self, employee, date_from, date_to, line):
        """Suma debit/credit/saldo de account.move.line para el empleado/periodo/cuentas dadas.

        Replica la lógica de _get_accounting_value del income_cert_config: filtra
        por partner del empleado (partner_encab_id), cuentas, estado, diarios
        excluidos, y opcionalmente excluye diarios de nómina.
        """
        if not line.account_ids:
            return 0.0
        partner = employee.partner_encab_id or employee.work_contact_id
        domain = [
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('account_id', 'in', line.account_ids.ids),
        ]
        if partner:
            domain.append(('partner_id', '=', partner.id))
        if line.move_state_filter == 'posted':
            domain.append(('move_id.state', '=', 'posted'))
        elif line.move_state_filter == 'draft':
            domain.append(('move_id.state', '=', 'draft'))
        if line.excluded_journal_ids:
            domain.append(('journal_id', 'not in', line.excluded_journal_ids.ids))
        if line.exclude_payroll_entries:
            # account.move tiene payslip_run_id (hr_payroll_extended) — los
            # asientos generados por nómina llevan ese campo. Filtramos por él
            # en vez de adivinar por nombre del diario.
            domain.append(('move_id.payslip_run_id', '=', False))

        MoveLine = self.env['account.move.line']
        if line.account_move_type == 'debit':
            r = MoveLine.read_group(domain, fields=['debit:sum'], groupby=[], lazy=False)
            return float(r[0].get('debit') or 0.0) if r else 0.0
        elif line.account_move_type == 'credit':
            r = MoveLine.read_group(domain, fields=['credit:sum'], groupby=[], lazy=False)
            return float(r[0].get('credit') or 0.0) if r else 0.0
        elif line.account_move_type == 'both':
            r = MoveLine.read_group(domain, fields=['debit:sum', 'credit:sum'],
                                    groupby=[], lazy=False)
            if not r:
                return 0.0
            return float(r[0].get('debit') or 0.0) + float(r[0].get('credit') or 0.0)
        elif line.account_move_type == 'balance':
            r = MoveLine.read_group(domain, fields=['debit:sum', 'credit:sum'],
                                    groupby=[], lazy=False)
            if not r:
                return 0.0
            return float(r[0].get('debit') or 0.0) - float(r[0].get('credit') or 0.0)
        return 0.0

    def _average_payslip_value(self, employee, date_to, salary_rules,
                               origin_severance_pay=None, months=6):
        """Promedio mensual del valor de las reglas en los últimos N meses."""
        if not salary_rules:
            return 0.0
        from dateutil.relativedelta import relativedelta
        date_from = (date_to - relativedelta(months=months - 1)).replace(day=1)
        total = self._sum_payslip_rules(
            employee, date_from, date_to, salary_rules, origin_severance_pay)
        return float(total) / months if months else 0.0

    def _post_process_value(self, value, line):
        """Aplica límites UVT y fijo. Replica el patrón de format_field."""
        if not isinstance(value, (int, float)) or value is None:
            return value
        if line.limit_uvt_factor and self.uvt_value:
            cap = line.limit_uvt_factor * self.uvt_value
            if abs(value) > cap:
                value = cap if value > 0 else -cap
        if line.limit_fixed_value:
            if abs(value) > line.limit_fixed_value:
                value = line.limit_fixed_value if value > 0 else -line.limit_fixed_value
        return value

    def _sum_payslip_rules(self, employee, date_from, date_to, salary_rules, origin_severance_pay=None):
        """Suma 'total' de hr.payslip.line para un empleado/periodo/reglas dadas.

        Optimización (lavish_hr_payroll): hr.payslip.line tiene el related stored
        'state_slip' (= slip_id.state) y 'employee_id' directo, así evitamos
        JOIN contra hr_payslip para esos filtros.
        """
        if not salary_rules:
            return 0.0
        # hr.payslip.line tiene date_from/date_to/employee_id/state_slip
        # directos en la tabla (lavish_hr_payroll), evitando JOIN a hr_payslip
        domain = [
            ('employee_id', '=', employee.id),
            ('state_slip', 'in', ['done', 'paid']),
            ('date_from', '<=', date_to),
            ('date_to', '>=', date_from),
            ('salary_rule_id', 'in', salary_rules.ids),
        ]
        if origin_severance_pay == 'employee':
            domain.append(('slip_id.employee_severance_pay', '=', True))
        elif origin_severance_pay == 'fund':
            domain.append(('slip_id.employee_severance_pay', '=', False))
        result = self.env['hr.payslip.line'].read_group(
            domain, fields=['total:sum'], groupby=[], lazy=False)
        return float(result[0].get('total') or 0.0) if result else 0.0

    def get_report_data(self):
        columnas = [
            'Entidad Informante', 'Tipo de documento del beneficiario',
            'Número de Identificación del beneficiario',
            'Primer Apellido del beneficiario', 'Segundo Apellido del beneficiario',
            'Primer Nombre del beneficiario', 'Otros Nombres del beneficiario',
            'Dirección del beneficiario', 'Departamento del beneficiario',
            'Municipio del beneficiario', 'País del beneficiario',
            # Pagos por concepto (XSD 2276v4 attrs: pasa..potro)
            'pasa - Pagos por salarios',
            'paec - Pagos por emolumentos eclesiásticos',
            'paho - Pagos por honorarios',
            'pase - Pagos por servicios',
            'paco - Pagos por comisiones',
            'papre - Pagos por prestaciones sociales',
            'pavia - Pagos por viáticos',
            'paga - Pagos por gastos de representación',
            'patra - Pagos por compensaciones trabajo asociado cooperativo',
            'potro - Otros pagos',
            # Cesantías (cein/ceco/auce)
            'cein - Cesantías e intereses pagadas al empleado',
            'ceco - Cesantías consignadas al fondo',
            'auce - Auxilio cesantías régimen tradicional CST',
            # Pensiones y total
            'peju - Pensiones de jubilación, vejez o invalidez',
            'tingbtp - Total ingresos brutos de rentas de trabajo y pensión',
            # Aportes
            'apos - Aportes obligatorios a salud',
            'apof - Aportes obligatorios a pensión y solidaridad pensional',
            'aprais - Aportes voluntarios al RAIS',
            'apov - Aportes voluntarios a fondos de pensiones voluntarias',
            'apafc - Aportes a cuentas AFC',
            'apavc - Aportes a cuentas AVC',
            # Retención y bonos / apoyos
            'vare - Retenciones en la fuente por rentas de trabajo o pensión',
            'pabop - Pagos con bonos electrónicos / cheques / tarjetas / vales',
            'vapo - Apoyos económicos no reembolsables (Estado / programas educativos)',
            # Alimentación 41 UVT
            'vaex - Exceso pagos por alimentación >41 UVT',
            'pagahuvt - Pagos por alimentación hasta 41 UVT',
            # Fideicomiso / contrato colaboración
            'identfc - Identificación del fideicomiso o contrato',
            'tdocpcc - Tipo documento participante en contrato de colaboración',
            'nitpcc - Identificación participante en contrato de colaboración',
            # XSD 2276v4: campos nuevos
            'ivav - IVA mayor valor del costo o gasto',
            'rfiva - Retención en la fuente a título de IVA',
            'vilap - Ingreso laboral promedio últimos 6 meses',
        ]

        if self.only_with_payslips:
            employees = self._get_employees_with_payslips()
        else:
            Employee = self.env['hr.employee']
            employees = Employee.search(Employee._check_company_domain(self.env.company))

        reportlines = []
        for employee in employees:
            dataline = self.get_employee_data(employee, columnas)
            if dataline:
                reportlines.append(dataline)

        return {
            'start_date': self.start_date,
            'end_date': self.end_date,
            'lines': reportlines,
            'columns': columnas,
        }

    def get_employee_data(self, employee, columnas):
        """Obtiene datos de un empleado para el reporte usando el servicio compartido"""
        date_start = self.start_date
        date_end = self.end_date
        date_start_ant = date_start.replace(year=date_start.year - 1)
        date_end_ant = date_end.replace(year=date_end.year - 1)

        # En Odoo 19 no existe address_home_id: el tercero del empleado es
        # partner_encab_id (lavish_hr_employee) o work_contact_id (core hr).
        partner = employee.partner_encab_id or employee.work_contact_id
        city = partner.city_id
        # Inicializar todas las columnas con 0/'' para cumplir con el XSD que
        # exige que la mayoría de atributos numéricos sean obligatorios. Las
        # columnas que NO tengan rule_line configurada quedarán en 0 en el
        # archivo final en lugar de None.
        TEXT_COLUMNS = {
            'Entidad Informante',
            'Tipo de documento del beneficiario',
            'Número de Identificación del beneficiario',
            'Primer Apellido del beneficiario', 'Segundo Apellido del beneficiario',
            'Primer Nombre del beneficiario', 'Otros Nombres del beneficiario',
            'Dirección del beneficiario',
            'Departamento del beneficiario', 'Municipio del beneficiario',
            'País del beneficiario',
            'Identificación del fideicomiso o contrato',
            'Tipo documento participante en contrato de colaboración',
            'Identificación participante en contrato colaboración',
        }
        dataline = {col: ('' if col in TEXT_COLUMNS else 0) for col in columnas}
        dataline.update({
            'Entidad Informante': self.env.company.id,
            'Tipo de documento del beneficiario': self.get_document_type(employee),
            'Número de Identificación del beneficiario': partner.vat_co or partner.vat or '',
            'Primer Apellido del beneficiario': partner.x_first_lastname or '',
            'Segundo Apellido del beneficiario': partner.x_second_lastname or '',
            'Primer Nombre del beneficiario': partner.x_first_name or '',
            'Otros Nombres del beneficiario': partner.x_second_name or '',
            'Dirección del beneficiario': partner.street or '',
            'Departamento del beneficiario': city.code[0:2] if city and city.code else '',
            'Municipio del beneficiario': city.code[-3:] if city and city.code else '',
            'País del beneficiario': partner.country_id.code if partner.country_id else '',
        })

        has_values = False
        for line in self.confi_id.config_rule_line_ids:
            column_name = dict(line._fields['column_selection'].selection).get(line.column_selection)
            if column_name not in columnas:
                continue

            value = 0
            if line.calculation == 'sum_rule' and line.salary_rule_id:
                if line.accumulated_previous_year:
                    value = self._sum_payslip_rules(
                        employee, date_start_ant, date_end_ant,
                        line.salary_rule_id, line.origin_severance_pay,
                    )
                else:
                    value = self._sum_payslip_rules(
                        employee, date_start, date_end,
                        line.salary_rule_id, line.origin_severance_pay,
                    )

            elif line.calculation == 'sum_accounting' and line.account_ids:
                if line.accumulated_previous_year:
                    value = self._sum_accounting_lines(
                        employee, date_start_ant, date_end_ant, line)
                else:
                    value = self._sum_accounting_lines(
                        employee, date_start, date_end, line)

            elif line.calculation == 'average_rule' and line.salary_rule_id:
                # Promedio últimos 6 meses anclado a end_date
                value = self._average_payslip_value(
                    employee, date_end, line.salary_rule_id,
                    line.origin_severance_pay, months=6,
                )

            elif line.calculation in ('dependents_type_vat', 'dependents_vat',
                                      'dependents_name', 'dependents_type'):
                dataline[column_name] = self.get_dependents_info(
                    employee, line.calculation
                )
                continue
            else:
                dataline[column_name] = 0
                continue

            value = self._post_process_value(value, line)
            if value:
                has_values = True
            dataline[column_name] = abs(value) if value else 0

        if not has_values and self.only_with_payslips:
            return None

        return dataline

    # Mapeo del código semántico de l10n_co (v14 nativo) al código numérico
    # DIAN exigido por el reporte 2276. En v18 lavish_erp aporta un campo
    # dian_code en l10n_latam.identification.type; en v14 no existe, así que
    # mapeamos sobre l10n_co_document_code que sí está siempre presente.
    DIAN_DOCUMENT_TYPE_MAP = {
        'civil_registration':     '11',  # Registro Civil
        'id_card':                '12',  # Tarjeta de Identidad
        'id_document':            '12',
        'national_citizen_id':    '13',  # Cédula de ciudadanía (CC)
        'foreign_colombian_card': '21',  # Tarjeta de extranjería
        'foreign_resident_card':  '22',  # Cédula de extranjería (CE)
        'rut':                    '31',  # NIT
        'residence_document':     '47',  # PEP
        'passport':               '41',
        'foreign_id_card':        '42',
        'national_in_cont':       '43',
    }

    def get_document_type(self, employee):
        """Devuelve el código DIAN del tipo de documento del beneficiario.

        En v14 leemos `l10n_co_document_code` (string semántico) del tipo
        identificación y lo mapeamos al código DIAN numérico vía un dict
        local — evita depender de un campo dian_code que solo existe en v18.
        """
        partner = employee.partner_encab_id or employee.work_contact_id
        id_type = partner.l10n_latam_identification_type_id if partner else False
        if not id_type:
            return ''
        return self.DIAN_DOCUMENT_TYPE_MAP.get(id_type.l10n_co_document_code, '')

    def get_dependents_info(self, employee, info_type):
        """Obtiene información de dependientes marcados para reporte fiscal"""
        dependents = employee.dependents_information.filtered(
            lambda d: d.report_income_and_withholdings
        )
        if info_type == 'dependents_type_vat':
            return ', '.join(d.document_type or '' for d in dependents)
        elif info_type == 'dependents_vat':
            return ', '.join(d.vat or '' for d in dependents)
        elif info_type == 'dependents_name':
            return ', '.join(d.name or '' for d in dependents)
        elif info_type == 'dependents_type':
            return ', '.join(str(d.dependents_type or '').capitalize() for d in dependents)
        return ''

    def create_excel_report(self, data):
        """Genera Excel del reporte 2276 con xlsxwriter (sin dependencia externa).

        Adaptación a Odoo 14: el módulo `lavish_hr_payroll.report.excel_report_builder`
        no existe en este sistema, así que armamos el xlsx directamente con
        xlsxwriter. Mantenemos el layout original (encabezado de empresa,
        subtítulo de período, tabla con headers y filas).
        """
        import io
        import xlsxwriter

        company = self.env.company
        columns = data['columns']
        lines = data['lines']

        output = io.BytesIO()
        wb = xlsxwriter.Workbook(output, {'in_memory': True})
        ws = wb.add_worksheet('Exógena 2276')

        # ---- formatos ----
        title_fmt = wb.add_format({
            'bold': True, 'font_size': 14, 'align': 'center', 'valign': 'vcenter',
            'bg_color': '#003366', 'font_color': '#FFFFFF', 'border': 1,
        })
        subtitle_fmt = wb.add_format({
            'italic': True, 'font_size': 10, 'align': 'center',
            'bg_color': '#E8EEF7', 'border': 1,
        })
        company_fmt = wb.add_format({
            'bold': True, 'font_size': 10, 'align': 'left',
            'bg_color': '#F2F2F2', 'border': 1,
        })
        header_fmt = wb.add_format({
            'bold': True, 'font_size': 9, 'align': 'center', 'valign': 'vcenter',
            'bg_color': '#003366', 'font_color': '#FFFFFF', 'border': 1,
            'text_wrap': True,
        })
        cell_fmt = wb.add_format({'font_size': 9, 'border': 1, 'valign': 'top'})
        cell_alt_fmt = wb.add_format({
            'font_size': 9, 'border': 1, 'valign': 'top', 'bg_color': '#F9F9F9'
        })

        n_cols = len(columns)
        last_col_idx = max(n_cols - 1, 0)

        # ---- título ----
        ws.merge_range(0, 0, 0, last_col_idx,
                       f'Reporte Exógena 2276 - {company.name or ""}', title_fmt)
        ws.set_row(0, 28)

        # ---- subtítulo ----
        subtitle = (
            f'Período: {self.start_date.strftime("%d/%m/%Y") if self.start_date else "-"} - '
            f'{self.end_date.strftime("%d/%m/%Y") if self.end_date else "-"}'
            f' | Empleados: {len(lines)}'
        )
        ws.merge_range(1, 0, 1, last_col_idx, subtitle, subtitle_fmt)
        ws.set_row(1, 18)

        # ---- info empresa ----
        info = (
            f'NIT: {company.partner_id.vat or ""}    '
            f'Dirección: {company.street or ""}    '
            f'Ciudad: {company.city or ""}'
        )
        ws.merge_range(2, 0, 2, last_col_idx, info, company_fmt)
        ws.set_row(2, 18)

        # ---- header de la tabla ----
        header_row = 4
        for col_idx, col_name in enumerate(columns):
            ws.write(header_row, col_idx, str(col_name), header_fmt)
        ws.set_row(header_row, 32)

        # ---- filas de datos ----
        for row_idx, line in enumerate(lines, start=header_row + 1):
            fmt = cell_alt_fmt if (row_idx - header_row) % 2 == 0 else cell_fmt
            for col_idx, col_name in enumerate(columns):
                val = line.get(col_name, '')
                if val is None or val is False:
                    val = ''
                if isinstance(val, (int, float)) and not isinstance(val, bool):
                    ws.write_number(row_idx, col_idx, val, fmt)
                else:
                    ws.write(row_idx, col_idx, str(val), fmt)

        # ---- anchos columnas (estimación simple) ----
        for col_idx, col_name in enumerate(columns):
            max_len = max([len(str(col_name))] + [len(str(line.get(col_name, ''))) for line in lines[:200]])
            ws.set_column(col_idx, col_idx, min(max(max_len + 2, 12), 60))

        ws.freeze_panes(header_row + 1, 0)
        wb.close()

        excel_bytes = output.getvalue()
        output.close()

        filename = f'reporte_exogena_2276_{self.start_date}_{self.end_date}.xlsx'
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'datas': base64.b64encode(excel_bytes),
            'store_fname': filename,
            'type': 'binary',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }


class ExogenaReport(models.TransientModel):
    _name = 'l10n_co.exogenous_2276_report'
    _description = 'Exogena 2276 Report'

    name = fields.Char('Nombre', default='Exogena')
    col_1 = fields.Char('Columna 1')
    col_2 = fields.Char('Columna 2')
    col_3 = fields.Char('Columna 3')
    col_4 = fields.Char('Columna 4')
    col_5 = fields.Char('Columna 5')
    col_6 = fields.Char('Columna 6')
    col_7 = fields.Char('Columna 7')
    col_8 = fields.Char('Columna 8')
    col_9 = fields.Char('Columna 9')
    col_10 = fields.Char('Columna 10')
    col_11 = fields.Char('Columna 11')
    col_12 = fields.Char('Columna 12')
    col_13 = fields.Char('Columna 13')
    col_14 = fields.Char('Columna 14')
    col_15 = fields.Char('Columna 15')
    col_16 = fields.Char('Columna 16')
    col_17 = fields.Char('Columna 17')
    col_18 = fields.Char('Columna 18')
    col_19 = fields.Char('Columna 19')
    col_20 = fields.Char('Columna 20')
    col_21 = fields.Char('Columna 21')
    col_22 = fields.Char('Columna 22')
    col_23 = fields.Char('Columna 23')
    col_24 = fields.Char('Columna 24')
    col_25 = fields.Char('Columna 25')
    col_26 = fields.Char('Columna 26')
    col_27 = fields.Char('Columna 27')
    col_28 = fields.Char('Columna 28')
    col_29 = fields.Char('Columna 29')
    col_30 = fields.Char('Columna 30')
    col_31 = fields.Char('Columna 31')
    col_32 = fields.Char('Columna 32')
    col_33 = fields.Char('Columna 33')
    col_34 = fields.Char('Columna 34')
    col_35 = fields.Char('Columna 35')
    col_36 = fields.Char('Columna 36')
    col_37 = fields.Char('Columna 37')

    def clean_data(self):
        self.env['l10n_co.exogenous_2276_report'].search([]).unlink()
        return True

    def show_report(self, data):
        self.clean_data()
        columns = data['columns']
        lineas = data['lines']

        data_reg = {}
        for i, column in enumerate(columns, 1):
            data_reg[f'col_{i}'] = column

        self.env['l10n_co.exogenous_2276_report'].create(data_reg)

        for line in lineas:
            line_reg = {}
            for i, column in enumerate(columns, 1):
                line_reg[f'col_{i}'] = line.get(column, '')
            self.env['l10n_co.exogenous_2276_report'].create(line_reg)

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_co.exogenous_2276_report',
            'view_mode': 'list',
            'target': 'current'
        }
