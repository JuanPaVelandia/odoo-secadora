# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class TreasuryBankCommission(models.Model):
    """Configuracion de comisiones bancarias por metodo de pago"""
    _name = 'treasury.bank.commission'
    _description = 'Comisiones Bancarias por Metodo de Pago'
    _order = 'bank_id, journal_id, payment_method_id'

    name = fields.Char(
        string='Nombre',
        compute='_compute_name',
        store=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compania',
        required=True,
        default=lambda self: self.env.company
    )
    bank_id = fields.Many2one(
        'res.bank',
        string='Banco',
        help='Entidad bancaria. Si se especifica, aplica a todos los diarios de este banco.'
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Diario/Cuenta',
        domain="[('type', 'in', ['bank', 'cash'])]",
        help='Diario especifico. Si vacio con banco, aplica a todos los diarios del banco.'
    )
    payment_method_id = fields.Many2one(
        'account.payment.method',
        string='Metodo de Pago',
        help='Metodo especifico. Si vacio, aplica a todos los metodos.'
    )
    payment_type = fields.Selection([
        ('inbound', 'Recaudo'),
        ('outbound', 'Pago')
    ], string='Tipo', required=True, default='outbound')

    # Categoria de servicio bancario (basado en tarifario Bancolombia)
    service_category = fields.Selection([
        ('ach', 'Pagos ACH'),
        ('ach_same_bank', 'Transferencia Mismo Banco'),
        ('pse', 'PSE'),
        ('cheque', 'Cheques'),
        ('cheque_gerencia', 'Cheque Gerencia'),
        ('consignacion', 'Consignaciones'),
        ('recaudo_fisico', 'Recaudo Fisico'),
        ('recaudo_digital', 'Recaudo Digital'),
        ('pila', 'PILA'),
        ('sebra', 'SEBRA'),
        ('swift', 'Swift Internacional'),
        ('qr', 'Pago QR'),
        ('boton', 'Boton de Pagos'),
        ('cuota_manejo', 'Cuota de Manejo'),
        ('extracto', 'Extracto Bancario'),
        ('certificacion', 'Certificacion Bancaria'),
        ('chequera', 'Chequera'),
        ('otro', 'Otro')
    ], string='Categoria Servicio', required=True, default='ach',
       help='Categoria del servicio bancario segun tarifario')

    # Frecuencia de cobro
    charge_frequency = fields.Selection([
        ('transaction', 'Por Transaccion'),
        ('monthly', 'Mensual Fijo'),
        ('annual', 'Anual'),
        ('on_demand', 'A Demanda')
    ], string='Frecuencia de Cobro', required=True, default='transaction',
       help='Con que frecuencia se cobra esta comision')

    is_exempt = fields.Boolean(
        string='Exento',
        default=False,
        help='Marcar si este servicio esta exento de comision'
    )

    # Comisiones
    commission_type = fields.Selection([
        ('fixed', 'Valor Fijo'),
        ('percent', 'Porcentaje'),
        ('mixed', 'Fijo + Porcentaje')
    ], string='Tipo Comision', required=True, default='fixed')

    commission_fixed = fields.Monetary(
        string='Comision Fija',
        currency_field='currency_id',
        help='Valor fijo por transaccion'
    )
    commission_percent = fields.Float(
        string='% Comision',
        digits=(5, 4),
        help='Porcentaje sobre el monto de la transaccion'
    )
    min_commission = fields.Monetary(
        string='Comision Minima',
        currency_field='currency_id',
        help='Comision minima a cobrar (aplica solo para porcentaje)'
    )
    max_commission = fields.Monetary(
        string='Comision Maxima',
        currency_field='currency_id',
        help='Comision maxima a cobrar (0 = sin limite)'
    )
    tax_ids = fields.Many2many(
        'account.tax',
        'treasury_commission_tax_rel',
        'commission_id',
        'tax_id',
        string='Impuestos',
        domain="[('type_tax_use', '=', 'purchase')]",
        help='Impuestos aplicables a la comision bancaria'
    )

    # Cuenta contable para el gasto
    expense_account_id = fields.Many2one(
        'account.account',
        string='Cuenta Gasto Bancario',
        help='Cuenta contable para registrar el gasto (ej: 530505)'
    )

    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id'
    )
    active = fields.Boolean(default=True)
    notes = fields.Text(string='Notas')

    # Concepto de cobro (descripción del servicio)
    concept = fields.Char(
        string='Concepto',
        help='Descripcion del concepto de cobro segun tarifario bancario'
    )

    # IVA
    apply_iva = fields.Boolean(
        string='Aplica IVA',
        default=True,
        help='Indica si la comision esta sujeta a IVA (19%)'
    )

    @api.depends('bank_id', 'journal_id', 'payment_method_id', 'payment_type', 'service_category')
    def _compute_name(self):
        category_labels = dict(self._fields['service_category'].selection)
        for rec in self:
            parts = []
            if rec.bank_id:
                parts.append(rec.bank_id.name)
            elif rec.journal_id:
                parts.append(rec.journal_id.name)
            if rec.service_category:
                parts.append(category_labels.get(rec.service_category, rec.service_category))
            if rec.payment_method_id:
                parts.append(rec.payment_method_id.name)
            rec.name = ' - '.join(parts) if parts else 'Nuevo'

    @api.onchange('journal_id')
    def _onchange_journal_id(self):
        if self.journal_id and self.journal_id.bank_id:
            self.bank_id = self.journal_id.bank_id

    @api.constrains('bank_id', 'journal_id', 'payment_method_id', 'payment_type', 'service_category')
    def _check_unique(self):
        for rec in self:
            domain = [
                ('id', '!=', rec.id),
                ('bank_id', '=', rec.bank_id.id if rec.bank_id else False),
                ('journal_id', '=', rec.journal_id.id if rec.journal_id else False),
                ('payment_method_id', '=', rec.payment_method_id.id if rec.payment_method_id else False),
                ('payment_type', '=', rec.payment_type),
                ('service_category', '=', rec.service_category),
                ('company_id', '=', rec.company_id.id)
            ]
            if self.search_count(domain):
                raise ValidationError(
                    'Ya existe una configuracion de comision para esta combinacion de '
                    'banco, diario, categoria, metodo de pago y tipo.'
                )

    def calculate_commission(self, amount):
        """Calcula la comision para un monto dado incluyendo impuestos"""
        self.ensure_one()

        # Si está exento, retornar cero
        if self.is_exempt:
            return {
                'commission': 0.0,
                'taxes': [],
                'total_taxes': 0.0,
                'total': 0.0,
                'is_exempt': True
            }

        commission = 0.0

        if self.commission_type == 'fixed':
            commission = self.commission_fixed
        elif self.commission_type == 'percent':
            commission = amount * (self.commission_percent / 100)
        elif self.commission_type == 'mixed':
            commission = self.commission_fixed + (amount * (self.commission_percent / 100))

        # Aplicar minimo/maximo
        if self.min_commission and commission < self.min_commission:
            commission = self.min_commission
        if self.max_commission and commission > self.max_commission:
            commission = self.max_commission

        # Calcular impuestos usando compute_all de Odoo
        taxes_result = {'total_included': commission, 'total_excluded': commission, 'taxes': []}
        if self.tax_ids:
            taxes_result = self.tax_ids.compute_all(
                commission,
                currency=self.currency_id,
                quantity=1.0,
                product=None,
                partner=None
            )

        return {
            'commission': commission,
            'taxes': taxes_result.get('taxes', []),
            'total_taxes': taxes_result['total_included'] - taxes_result['total_excluded'],
            'total': taxes_result['total_included'],
            'is_exempt': False
        }


class TreasuryWeekday(models.Model):
    """Dias de la semana para seleccion multiple"""
    _name = 'treasury.weekday'
    _description = 'Dia de la Semana'
    _order = 'sequence'

    name = fields.Char(string='Nombre', required=True)
    code = fields.Integer(string='Codigo', required=True, help='0=Lunes, 6=Domingo')
    sequence = fields.Integer(default=10)

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'El codigo del dia ya existe')
    ]


class TreasuryHoliday(models.Model):
    """Festivos para calendario de pagos"""
    _name = 'treasury.holiday'
    _description = 'Festivos'
    _order = 'date'

    name = fields.Char(string='Nombre', required=True)
    date = fields.Date(string='Fecha', required=True)
    company_id = fields.Many2one(
        'res.company',
        string='Compania',
        default=lambda self: self.env.company
    )
    recurring = fields.Boolean(
        string='Recurrente',
        help='Si es True, aplica cada año en la misma fecha'
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('date_company_unique', 'unique(date, company_id)', 'Ya existe un festivo en esta fecha')
    ]


class TreasuryPaymentSchedule(models.Model):
    """Calendario de dias de pago"""
    _name = 'treasury.payment.schedule'
    _description = 'Calendario de Pagos'
    _order = 'sequence, id'

    name = fields.Char(string='Nombre', required=True)
    company_id = fields.Many2one(
        'res.company',
        string='Compania',
        required=True,
        default=lambda self: self.env.company
    )
    schedule_type = fields.Selection([
        ('weekday', 'Dias de la Semana'),
        ('monthday', 'Dias del Mes')
    ], string='Tipo de Programacion', required=True, default='weekday')

    # Dias de la semana - Multi-seleccion
    weekday_ids = fields.Many2many(
        'treasury.weekday',
        'treasury_schedule_weekday_rel',
        'schedule_id',
        'weekday_id',
        string='Dias de la Semana'
    )

    # Dias del mes
    day_of_month_ids = fields.Many2many(
        'treasury.payment.schedule.day',
        string='Dias del Mes',
        help='Seleccione los dias del mes en que se realizan pagos'
    )

    # Manejo de festivos
    holiday_behavior = fields.Selection([
        ('ignore', 'Ignorar Festivos (pagar igual)'),
        ('skip', 'Omitir Festivos (no pagar)'),
        ('before', 'Dia Habil Anterior'),
        ('after', 'Dia Habil Siguiente')
    ], string='Comportamiento en Festivos', default='after',
       help='Que hacer cuando el dia de pago cae en festivo')

    only_business_days = fields.Boolean(
        string='Solo Dias Habiles',
        default=True,
        help='Excluir sabados y domingos automaticamente'
    )

    payment_type = fields.Selection([
        ('supplier', 'Pagos a Proveedores'),
        ('payroll', 'Nomina'),
        ('taxes', 'Impuestos'),
        ('loans', 'Prestamos'),
        ('other', 'Otros')
    ], string='Tipo de Pago', required=True)

    journal_id = fields.Many2one(
        'account.journal',
        string='Banco Predeterminado',
        domain="[('type', '=', 'bank')]"
    )
    payment_method_id = fields.Many2one(
        'account.payment.method',
        string='Metodo de Pago Predeterminado'
    )

    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    notes = fields.Text(string='Notas')

    def _is_holiday(self, check_date):
        """Verifica si una fecha es festivo"""
        Holiday = self.env['treasury.holiday']
        # Buscar festivo exacto
        holiday = Holiday.search([
            ('date', '=', check_date),
            '|', ('company_id', '=', self.company_id.id), ('company_id', '=', False),
            ('active', '=', True)
        ], limit=1)
        if holiday:
            return True
        # Buscar festivo recurrente (mismo dia/mes cualquier año)
        recurring = Holiday.search([
            ('recurring', '=', True),
            '|', ('company_id', '=', self.company_id.id), ('company_id', '=', False),
            ('active', '=', True)
        ])
        for h in recurring:
            if h.date.month == check_date.month and h.date.day == check_date.day:
                return True
        return False

    def _is_weekend(self, check_date):
        """Verifica si es fin de semana"""
        return check_date.weekday() >= 5  # 5=Sabado, 6=Domingo

    def _get_next_business_day(self, check_date, direction=1):
        """Obtiene el siguiente/anterior dia habil"""
        from datetime import timedelta
        result = check_date + timedelta(days=direction)
        max_iterations = 10
        iterations = 0
        while iterations < max_iterations:
            if not self._is_holiday(result) and not self._is_weekend(result):
                return result
            result += timedelta(days=direction)
            iterations += 1
        return check_date  # Fallback

    def _adjust_for_holiday(self, check_date):
        """Ajusta la fecha segun comportamiento de festivos"""
        is_holiday = self._is_holiday(check_date)
        is_weekend = self._is_weekend(check_date) if self.only_business_days else False

        if not is_holiday and not is_weekend:
            return check_date

        if self.holiday_behavior == 'ignore':
            return check_date
        elif self.holiday_behavior == 'skip':
            return None  # No pagar este dia
        elif self.holiday_behavior == 'before':
            return self._get_next_business_day(check_date, direction=-1)
        elif self.holiday_behavior == 'after':
            return self._get_next_business_day(check_date, direction=1)
        return check_date

    def get_payment_days_in_range(self, date_from, date_to):
        """Retorna lista de fechas de pago en el rango dado, considerando festivos"""
        self.ensure_one()
        from datetime import timedelta

        payment_days = []
        current_date = date_from
        weekday_codes = [w.code for w in self.weekday_ids]

        while current_date <= date_to:
            is_payment_day = False

            if self.schedule_type == 'weekday':
                if current_date.weekday() in weekday_codes:
                    is_payment_day = True

            elif self.schedule_type == 'monthday':
                day = current_date.day
                if any(d.day == day for d in self.day_of_month_ids):
                    is_payment_day = True

            if is_payment_day:
                adjusted_date = self._adjust_for_holiday(current_date)
                if adjusted_date and adjusted_date not in payment_days:
                    payment_days.append(adjusted_date)

            current_date += timedelta(days=1)

        return sorted(payment_days)


class TreasuryPaymentScheduleDay(models.Model):
    """Dias del mes para calendario de pagos"""
    _name = 'treasury.payment.schedule.day'
    _description = 'Dia del Mes para Pagos'
    _order = 'day'

    day = fields.Integer(
        string='Dia',
        required=True,
        help='Dia del mes (1-31). Si el mes no tiene ese dia, se usa el ultimo dia.'
    )
    name = fields.Char(string='Nombre', compute='_compute_name', store=True)

    @api.depends('day')
    def _compute_name(self):
        for rec in self:
            rec.name = f'Dia {rec.day}' if rec.day else ''

    @api.constrains('day')
    def _check_day(self):
        for rec in self:
            if rec.day < 1 or rec.day > 31:
                raise ValidationError('El dia debe estar entre 1 y 31')

    _sql_constraints = [
        ('day_unique', 'unique(day)', 'El dia ya existe')
    ]
