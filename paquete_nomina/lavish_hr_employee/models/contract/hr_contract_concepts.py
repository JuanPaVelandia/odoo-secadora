# -*- coding: utf-8 -*-
"""
Modelo HrContractConcepts - Deducciones y Devengos de Contrato
Gestiona conceptos recurrentes de nómina: préstamos, ahorros, libranzas, embargos, etc.
"""
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from dateutil.relativedelta import relativedelta
from datetime import timedelta
import calendar
import logging

_logger = logging.getLogger(__name__)

# =============================================================================
# DICCIONARIO DE LÓGICA DE CÁLCULO PARA WIDGET DE EXPLICACIÓN
# Documenta cada paso del proceso de cálculo de conceptos
# =============================================================================
CALCULATION_LOGIC = {
    'steps': {
        1: {
            'name': 'base_amount',
            'description': 'Cálculo del monto base',
            'formula': 'Si porcentaje: (salario × porcentaje / 100), Si fijo: monto configurado',
            'fields': ['amount_select', 'amount', 'contract_id.wage'],
        },
        2: {
            'name': 'modality_adjustment',
            'description': 'Ajuste por modalidad de valor',
            'formula': {
                'fijo': 'monto_base (sin cambios)',
                'diario': 'monto_base / 30 × días_trabajados',
                'diario_efectivo': 'monto_base / 30 × días_efectivos',
            },
            'fields': ['modality_value'],
        },
        3: {
            'name': 'monthly_behavior',
            'description': 'Comportamiento mensual (distribución)',
            'formula': {
                'equal': 'Mismo valor completo en cada quincena',
                'divided': 'monto / 2 si aplica siempre, completo si quincena específica',
                'proportional': 'monto × días_período / días_mes',
            },
            'fields': ['monthly_behavior', 'aplicar'],
        },
        4: {
            'name': 'daily_adjustment',
            'description': 'Ajuste por distribución diaria (opcional)',
            'formula': 'monto × días_reales / días_esperados',
            'fields': ['adjust_by_daily_distribution'],
            'condition': 'Solo si adjust_by_daily_distribution = True',
        },
        5: {
            'name': 'exclusions',
            'description': 'Exclusión de días',
            'formula': 'Restar días excluidos (sábados, domingos, festivos, día 31)',
            'fields': ['excluir_sabados', 'excluir_domingos', 'excluir_festivos', 'descontar_dia_31'],
        },
        6: {
            'name': 'skip_check',
            'description': 'Verificación de saltos programados',
            'formula': 'Si hay salto: 0, Si salto con recuperación: monto × 2',
            'fields': ['skip_ids'],
        },
        7: {
            'name': 'sign_adjustment',
            'description': 'Ajuste de signo según tipo',
            'formula': 'Si deducción: monto × -1, Si devengo: monto (positivo)',
            'fields': ['input_id.dev_or_ded'],
        },
    },
    'behaviors': {
        'equal': {
            'description': 'Mismo valor en ambas quincenas',
            'example': 'Monto $100,000 → Q1: $100,000, Q2: $100,000',
            'use_case': 'Préstamos con cuota fija, seguros mensuales',
        },
        'divided': {
            'description': 'Dividir monto total entre quincenas',
            'example': 'Monto $100,000 → Q1: $50,000, Q2: $50,000',
            'use_case': 'Ahorros programados, aportes voluntarios',
        },
        'proportional': {
            'description': 'Proporcional a días del período',
            'example': 'Monto $100,000, Q1 (15 días de 30) → $50,000',
            'use_case': 'Subsidios, bonificaciones proporcionales',
        },
    },
    'modalities': {
        'fijo': {
            'description': 'Valor fijo sin importar días',
            'calculation': 'monto_configurado',
        },
        'diario': {
            'description': 'Valor diario por días trabajados',
            'calculation': 'monto / 30 × días_trabajo',
        },
        'diario_efectivo': {
            'description': 'Valor diario por días efectivos (sin exclusiones)',
            'calculation': 'monto / 30 × (días_trabajo - días_excluidos)',
        },
    },
}

class HrContractConcepts(models.Model):
    _name = 'hr.contract.concepts'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Deducciones o Devengos, conceptos de nómina'
    _order = 'sequence, date_start desc, id desc'

    name = fields.Char('Nombre', compute='_compute_name', store=True)
    sequence = fields.Integer('Secuencia', default=10)
    # Usar employee_type nativo de Odoo (valores: employee, student, trainee, contractor, freelance)
    employee_type = fields.Selection(
        selection=[
            ('employee', 'Empleado'),
            ('student', 'Estudiante'),
            ('trainee', 'Aprendiz'),
            ('contractor', 'Contratista'),
            ('freelance', 'Freelance'),
        ],
        string='Tipo de Empleado',
        store=True,
        readonly=True
    )
    active = fields.Boolean('Activo', default=True)
    company_id = fields.Many2one('res.company', string='Compañía', default=lambda self: self.env.company)
    
    # Campos de configuración principal
    input_id = fields.Many2one('hr.salary.rule', 'Regla', required=True, 
                              help='Regla salarial', domain=[('novedad_ded','=','cont')])
    show_voucher = fields.Boolean('Mostrar', default=False,
                                   help='Indica si se muestra o no en el comprobante de nómina')
    
    # Campos de clasificación
    type_deduction = fields.Selection([
        ('P', 'Prestamo empresa'),
        ('A', 'Ahorro'),
        ('S', 'Seguro'),
        ('L', 'Libranza'),
        ('E', 'Embargo'),
        ('R', 'Retencion'),
        ('O', 'Otros')
    ], 'Tipo deduccion')
    
    monthly_behavior = fields.Selection([
        ('equal', 'Mismo valor en ambas quincenas'),
        ('proportional', 'Proporcional a días'),
        ('divided', 'Dividir en partes iguales')
    ], string='Comportamiento Mensual', default='equal', tracking=True)
    
    type_emb = fields.Selection([
        ('ECA', 'Emb. Cuotas alimentarias'),
        ('EDJ', 'Emb. Depósito judicial'),
        ('EI', 'Emb. ICETEX'),
        ('EJ', 'Emb. Ejecutivo'),
        ('O', 'Otros')
    ], 'Tipo Embargo')
    
    # Campos de configuración de período
    period = fields.Selection([
        ('limited', 'Limitado'),
        ('indefinite', 'Indefinido')
    ], 'Limite')
    
    # Campos de configuración de monto
    amount_select = fields.Selection([
        ('percentage', 'Porcentaje (%)'),
        ('fix', 'Monto fijo'),
        ('min', 'Base minimo'),
    ], string='Tipo de Monto', index=True, required=True, default='fix')
    
    amount = fields.Float('Importe/porcentaje', required=True)
    minimum_amount = fields.Float('Monto Mínimo', help='Monto mínimo a aplicar cuando se usa porcentaje')
    maximum_amount = fields.Float('Monto Máximo', help='Monto máximo a aplicar cuando se usa porcentaje')
    
    # Campos de control de aplicación
    aplicar = fields.Selection([
        ('15','Primera quincena'),
        ('30','Segunda quincena'),
        ('0','Siempre')
    ], 'Aplicar cobro', required=True)
    
    modality_value = fields.Selection([
        ('fijo', 'Valor fijo'),
        ('diario', 'Valor diario'),
        ('diario_efectivo', 'Valor diario del día efectivamente laborado')
    ], 'Modalidad de valor', default='fijo', tracking=True)
    
    # Campos de exclusión de días
    excluir_sabados = fields.Boolean('Excluir sábados', default=False)
    excluir_domingos = fields.Boolean('Excluir domingos', default=False)
    excluir_festivos = fields.Boolean('Excluir festivos', default=False)
    descontar_dia_31 = fields.Boolean('Descontar día 31', default=True,
        help='Si está marcado, se descontará el día 31 del mes (como en la nómina colombiana)')

    # Campo de ajuste por distribución diaria
    adjust_by_daily_distribution = fields.Boolean(
        'Ajustar por distribución diaria',
        default=False,
        tracking=True,
        help='''Si está marcado, el monto final se ajustará proporcionalmente
según los días reales del período vs los días esperados.

Ejemplo: Si el período tiene 14 días pero se esperaban 15:
  - Monto base: $100,000
  - Factor: 14/15 = 0.9333
  - Monto ajustado: $93,333

Útil para: Conceptos que deben reflejar exactamente los días trabajados,
como subsidios de transporte o alimentación proporcionales.'''
    )
    
    # Campos de fechas
    date_start = fields.Date('Fecha Inicial')
    date_end = fields.Date('Fecha Final')
    
    # Campos de relación
    partner_id = fields.Many2one('hr.employee.entities', 'Entidad')
    contract_id = fields.Many2one('hr.contract', 'Contrato', required=True,
                                 ondelete='cascade', index=True)
    employee_id = fields.Many2one(related='contract_id.employee_id', store=True)
    payroll_structure_ids = fields.Many2many('hr.payroll.structure', 
                                           string='Estructuras Salariales')
    payslip_ids = fields.Many2many('hr.payslip', string='Nóminas Relacionadas')
    base_structure_only = fields.Boolean('Aplicar solo en estructuras base', 
        default=True,
        help='Si está marcado, el concepto se aplicará solo en estructuras base')
    
    # Campos de control de descuentos
    discount_rule = fields.Many2many('hr.salary.rule', string='Reglas de descuento')
    discount_categoria = fields.Many2many('hr.salary.rule.category',
                                        string='Categorías de descuento')
    description = fields.Char(string='Descripción')    
    
    # Campos de control de pagos dobles
    force_double_payment = fields.Boolean('Forzar Pago Doble', default=False)
    double_payment_date = fields.Date('Fecha Pago Doble')
    last_double_payment = fields.Date('Último Pago Doble', readonly=True)

    # =========================================================================
    # CAMPOS DE PROYECCION
    # =========================================================================
    proyectar_nomina = fields.Boolean(
        'Proyectar en Nomina',
        default=False,
        tracking=True,
        help='Si esta marcado, el concepto se proyectara en la nomina quincenal. '
             'Util para conceptos que se aplican mensualmente pero deben '
             'reflejarse proporcionalmente en cada quincena.'
    )
    proyectar_retencion = fields.Boolean(
        'Proyectar en Retencion',
        default=False,
        tracking=True,
        help='Si esta marcado, el concepto se incluira en la base de '
             'calculo de retencion en la fuente proyectada.'
    )
    proyectar_seguridad_social = fields.Boolean(
        'Proyectar en Seguridad Social',
        default=False,
        tracking=True,
        help='Si esta marcado, el concepto se incluira en la base de '
             'calculo de IBC (Ingreso Base de Cotizacion).'
    )
    proyectar_prestaciones = fields.Boolean(
        'Proyectar en Prestaciones',
        default=False,
        tracking=True,
        help='Si esta marcado, el concepto se incluira en la base de '
             'calculo de prestaciones sociales (prima, cesantias, vacaciones).'
    )
    factor_proyeccion = fields.Float(
        'Factor de Proyeccion',
        default=2.0,
        help='Factor multiplicador para proyeccion. '
             'Default: 2.0 (duplicar para proyeccion quincenal a mensual)'
    )

    # Campos de control de saltos
    skip_ids = fields.One2many('hr.contract.concept.skip', 'concept_id', 'Control de Saltos')
    # Campos informativos
    detail = fields.Text('Notas', help='Notas')
    embargo_judged = fields.Char('Juzgado')
    embargo_process = fields.Char('Proceso')
    
    # Campos de documento
    attached = fields.Binary('Adjunto')
    attached_name = fields.Char('Nombre adjunto')
    
    # Campos de estado y tracking
    state = fields.Selection([
        ('draft', 'Por Aprobar'),
        ('done', 'Aprobado'),
        ('closed', 'Cerrado'),
        ('cancel', 'Cancelado / Finalizado')
    ], string='Estado', default='draft', required=True, tracking=True)

    # Campos de cierre
    closed_date = fields.Date('Fecha de Cierre', readonly=True)
    closed_payslip_id = fields.Many2one('hr.payslip', string='Nómina de Cierre', readonly=True)
    allow_skips = fields.Boolean('Permitir Saltos', default=True,
        help='Permite crear saltos de cuotas para este concepto')
    close_ready = fields.Boolean('Listo para Cerrar', compute='_compute_close_ready', store=True,
        help='Indica si el concepto está listo para ser cerrado (saldo cercano a cero)')

    # Campos computados
    balance = fields.Float('Saldo Pendiente', compute='_compute_balance', store=True)
    total_paid = fields.Float('Total Pagado', compute='_compute_balance', store=True)
    next_payment_date = fields.Date('Próximo Pago', compute='_compute_next_payment')
    simulation_text = fields.Html('Detalle de Simulación', compute='_compute_simulation_details')
    active_period = fields.Boolean('Periodo Activo', compute='_compute_active_period')
    accumulated_amount = fields.Float('Monto Acumulado', compute='_compute_accumulated')
    remaining_installments = fields.Integer('Cuotas Restantes', compute='_compute_remaining')

    # NOTA: El campo line_ids (One2many a hr.payslip.line) se define en lavish_hr_payroll
    # para evitar dependencia circular. Aquí usamos _get_payslip_lines() para acceder.

    # Campos computados desde las líneas de nómina (usan _get_payslip_lines())
    line_count = fields.Integer(
        'Número de Aplicaciones',
        compute='_compute_line_stats',
        help='Cantidad de veces que se ha aplicado este concepto en nóminas'
    )
    last_applied_date = fields.Date(
        'Última Aplicación',
        compute='_compute_line_stats',
        help='Fecha de la última nómina donde se aplicó este concepto'
    )
    first_applied_date = fields.Date(
        'Primera Aplicación',
        compute='_compute_line_stats',
        help='Fecha de la primera nómina donde se aplicó este concepto'
    )
    average_amount = fields.Float(
        'Monto Promedio',
        compute='_compute_line_stats',
        help='Promedio del monto aplicado en todas las nóminas'
    )
    min_amount_applied = fields.Float(
        'Monto Mínimo Aplicado',
        compute='_compute_line_stats',
        help='Menor monto aplicado en una nómina'
    )
    max_amount_applied = fields.Float(
        'Monto Máximo Aplicado',
        compute='_compute_line_stats',
        help='Mayor monto aplicado en una nómina'
    )
    line_summary_html = fields.Html(
        'Resumen de Aplicaciones',
        compute='_compute_line_summary_html',
        help='Resumen visual de las aplicaciones en nóminas'
    )

    payroll_account_id = fields.Many2one('account.account', string="Cuenta Contable")
    
    _check_amount_positive = models.Constraint('CHECK(amount >= 0)', 'El monto debe ser positivo')
    _date_check = models.Constraint('CHECK((date_start IS NULL AND date_end IS NULL) OR (date_start <= date_end))',
                                    'La fecha final debe ser posterior a la fecha inicial')

    @api.depends('input_id', 'contract_id', 'type_deduction')
    def _compute_name(self):
        for record in self:
            name_parts = []
            if record.id:
                name_parts.append(f'# {record.id}')
            if record.input_id:
                name_parts.append(record.input_id.name)
            if record.type_deduction:
                name_parts.append(dict(record._fields['type_deduction'].selection).get(record.type_deduction))
            record.name = " - ".join(filter(None, name_parts))

    # ══════════════════════════════════════════════════════════════════════════
    # METODOS HELPER PARA LINEAS DE NOMINA
    # Definidos aqui para evitar dependencia circular.
    # Se sobrescriben en lavish_hr_payroll para usar el campo line_ids.
    # ══════════════════════════════════════════════════════════════════════════

    def _get_payslip_lines(self):
        """Obtiene las lineas de nomina relacionadas con este concepto."""
        PayslipLine = self.env.get('hr.payslip.line')
        if PayslipLine is None:
            return self.env['hr.payslip.line'].browse()
        return PayslipLine.search([('concept_id', '=', self.id)])

    def _get_done_payslip_lines(self):
        """Obtiene solo las lineas de nominas confirmadas o pagadas."""
        return self._get_payslip_lines().filtered(
            lambda l: l.slip_id.state in ['done', 'paid']
        )

    def _get_pending_payslip_lines(self):
        """Obtiene lineas de nominas en borrador o verificadas."""
        return self._get_payslip_lines().filtered(
            lambda l: l.slip_id.state in ['draft', 'verify']
        )

    def _get_lines_by_period(self, date_from, date_to):
        """Obtiene lineas de nomina en un periodo especifico."""
        return self._get_payslip_lines().filtered(
            lambda l: l.slip_id.date_from >= date_from and l.slip_id.date_to <= date_to
        )

    # ══════════════════════════════════════════════════════════════════════════
    # DEPENDENCIAS DINAMICAS PARA CAMPOS COMPUTADOS
    # Permite que modulos hijos agreguen dependencias adicionales
    # ══════════════════════════════════════════════════════════════════════════

    def _get_accumulated_depends(self):
        """Retorna las dependencias para _compute_accumulated.
        Se sobrescribe en lavish_hr_payroll para agregar line_ids."""
        return ()

    def _get_balance_depends(self):
        """Retorna las dependencias para _compute_balance.
        Se sobrescribe en lavish_hr_payroll para agregar line_ids."""
        return ('period', 'amount', 'date_end', 'date_start', 'aplicar',
                'modality_value', 'amount_select', 'monthly_behavior')

    def _get_remaining_depends(self):
        """Retorna las dependencias para _compute_remaining.
        Se sobrescribe en lavish_hr_payroll para agregar line_ids."""
        return ('balance', 'date_end')

    def _get_next_payment_depends(self):
        """Retorna las dependencias para _compute_next_payment.
        Se sobrescribe en lavish_hr_payroll para agregar line_ids."""
        return ('date_start', 'aplicar', 'skip_ids')

    @api.depends(lambda self: self._get_accumulated_depends())
    def _compute_accumulated(self):
        for record in self:
            lines = record._get_payslip_lines()
            record.accumulated_amount = sum(lines.mapped('total'))

    @api.depends(lambda self: self._get_balance_depends())
    def _compute_balance(self):
        for record in self:
            lines = record._get_payslip_lines()
            total_paid = sum(lines.mapped('total'))
            record.total_paid = total_paid

            if record.period == 'indefinite':
                record.balance = 0
                continue

            base_per_period = record._get_amount_per_period()
            total_periods = record._calculate_total_periods()
            total_expected = base_per_period * total_periods
            record.balance = total_expected - total_paid

    @api.depends('balance', 'period', 'state')
    def _compute_close_ready(self):
        """Determina si el concepto esta listo para cerrar"""
        for record in self:
            if record.state != 'done':
                record.close_ready = False
            elif record.period == 'indefinite':
                record.close_ready = True  # Los indefinidos siempre pueden cerrarse
            else:
                # Listo para cerrar si el saldo es menor al 5% del monto original
                threshold = abs(record.amount * 0.05) if record.amount else 0
                record.close_ready = abs(record.balance) <= threshold

    def _compute_line_stats(self):
        """Calcula estadísticas de las líneas de nómina relacionadas"""
        for record in self:
            lines = record._get_done_payslip_lines()

            if not lines:
                record.line_count = 0
                record.last_applied_date = False
                record.first_applied_date = False
                record.average_amount = 0.0
                record.min_amount_applied = 0.0
                record.max_amount_applied = 0.0
                continue

            amounts = lines.mapped('total')
            dates = lines.mapped('slip_id.date_to')

            record.line_count = len(lines)
            record.last_applied_date = max(dates) if dates else False
            record.first_applied_date = min(dates) if dates else False
            record.average_amount = sum(amounts) / len(amounts) if amounts else 0.0
            record.min_amount_applied = min(amounts) if amounts else 0.0
            record.max_amount_applied = max(amounts) if amounts else 0.0

    def _compute_line_summary_html(self):
        """Genera HTML con resumen de las aplicaciones en nóminas"""
        for record in self:
            lines = record._get_done_payslip_lines().sorted(
                lambda l: l.slip_id.date_to, reverse=True
            )

            if not lines:
                record.line_summary_html = '''
                <div style="padding: 15px; background-color: #f8f9fa; border-radius: 4px; text-align: center; color: #6c757d;">
                    No hay aplicaciones registradas en nóminas confirmadas
                </div>
                '''
                continue

            # Estadísticas generales
            amounts = lines.mapped('total')
            total = sum(amounts)
            avg = total / len(amounts) if amounts else 0
            min_amt = min(amounts) if amounts else 0
            max_amt = max(amounts) if amounts else 0

            # Últimas 5 aplicaciones
            recent_lines = lines[:5]
            recent_html = ''
            for line in recent_lines:
                period_indicator = '1Q' if line.slip_id.date_to.day <= 15 else '2Q'
                month_year = f"{line.slip_id.date_to.month}/{line.slip_id.date_to.year}"
                state_color = '#28a745' if line.slip_id.state == 'paid' else '#17a2b8'
                state_text = 'Pagado' if line.slip_id.state == 'paid' else 'Confirmado'
                recent_html += f'''
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid #dee2e6;">{period_indicator} {month_year}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #dee2e6; text-align: right;">${abs(line.total):,.2f}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #dee2e6;">
                        <span style="padding: 2px 8px; border-radius: 4px; background-color: {state_color}; color: white; font-size: 0.8em;">
                            {state_text}
                        </span>
                    </td>
                </tr>
                '''

            record.line_summary_html = f'''
            <div style="font-family: system-ui; max-width: 800px;">
                <!-- Estadísticas generales -->
                <div style="display: flex; gap: 15px; margin-bottom: 20px; flex-wrap: wrap;">
                    <div style="flex: 1; min-width: 120px; padding: 15px; background-color: #e3f2fd; border-radius: 4px; text-align: center;">
                        <div style="font-size: 0.8em; color: #1565c0;">Total Aplicaciones</div>
                        <div style="font-size: 1.5em; font-weight: bold; color: #0d47a1;">{len(lines)}</div>
                    </div>
                    <div style="flex: 1; min-width: 120px; padding: 15px; background-color: #e8f5e9; border-radius: 4px; text-align: center;">
                        <div style="font-size: 0.8em; color: #2e7d32;">Total Pagado</div>
                        <div style="font-size: 1.5em; font-weight: bold; color: #1b5e20;">${abs(total):,.2f}</div>
                    </div>
                    <div style="flex: 1; min-width: 120px; padding: 15px; background-color: #fff3e0; border-radius: 4px; text-align: center;">
                        <div style="font-size: 0.8em; color: #e65100;">Promedio</div>
                        <div style="font-size: 1.5em; font-weight: bold; color: #bf360c;">${abs(avg):,.2f}</div>
                    </div>
                </div>

                <!-- Rango de montos -->
                <div style="margin-bottom: 20px; padding: 10px; background-color: #f8f9fa; border-radius: 4px;">
                    <div style="display: flex; justify-content: space-between;">
                        <span style="color: #6c757d;">Monto Mínimo: <strong>${abs(min_amt):,.2f}</strong></span>
                        <span style="color: #6c757d;">Monto Máximo: <strong>${abs(max_amt):,.2f}</strong></span>
                    </div>
                </div>

                <!-- Últimas aplicaciones -->
                <div style="margin-top: 15px;">
                    <div style="font-weight: bold; margin-bottom: 10px; color: #212529;">Últimas Aplicaciones</div>
                    <table style="width: 100%; border-collapse: collapse;">
                        <thead>
                            <tr style="background-color: #f8f9fa;">
                                <th style="padding: 8px; text-align: left; border-bottom: 2px solid #dee2e6;">Período</th>
                                <th style="padding: 8px; text-align: right; border-bottom: 2px solid #dee2e6;">Monto</th>
                                <th style="padding: 8px; text-align: left; border-bottom: 2px solid #dee2e6;">Estado</th>
                            </tr>
                        </thead>
                        <tbody>
                            {recent_html}
                        </tbody>
                    </table>
                    {f'<div style="margin-top: 10px; color: #6c757d; font-size: 0.9em;">Mostrando 5 de {len(lines)} aplicaciones</div>' if len(lines) > 5 else ''}
                </div>
            </div>
            '''

    def _get_amount_per_period(self):
        """Calcula el monto por período considerando el comportamiento mensual.

        Comportamientos:
        - equal: Mismo valor completo en cada quincena donde aplique
        - divided: Divide el monto total entre las quincenas donde aplique
        - proportional: Calcula proporcional a los días del período (15/30)
        """
        base_amount = self._calculate_base_amount()

        if self.modality_value != 'fijo':
            # Para modalidad diaria, se calcula por día usando 30 días base
            daily_amount = base_amount / 30
            if self.aplicar == '0':
                return daily_amount * 30
            else:
                return daily_amount * 15

        # Para valor fijo, aplicar comportamiento mensual
        if self.monthly_behavior == 'equal':
            # Mismo valor completo en cada aplicación
            return base_amount
        elif self.monthly_behavior == 'divided':
            # Divide el monto entre quincenas
            if self.aplicar == '0':
                return base_amount / 2  # Aplica siempre: mitad cada quincena
            else:
                return base_amount  # Quincena específica: monto completo
        elif self.monthly_behavior == 'proportional':
            # Proporcional a días del período
            if self.aplicar == '0':
                return base_amount / 2  # 15 días de 30 = 50%
            else:
                return base_amount / 2  # Una quincena = 15 días = 50%

        return base_amount

    def _calculate_total_periods(self):
        """Calcula el número total de períodos"""
        if not self.date_start or not self.date_end:
            return 1

        start_date = self.date_start
        end_date = self.date_end
        months = (end_date.year - start_date.year) * 12 + end_date.month - start_date.month + 1

        if self.aplicar == '0':
            total_periods = months * 2
            if start_date.day > 15:
                total_periods -= 1
            if end_date.day < 15:
                total_periods -= 1
        else:
            total_periods = months
            if self.aplicar == '15' and start_date.day > 15:
                total_periods -= 1
            elif self.aplicar == '30' and start_date.day <= 15:
                total_periods -= 1

        return max(total_periods, 1)

    @api.depends(lambda self: self._get_remaining_depends())
    def _compute_remaining(self):
        for record in self:
            if record.period == 'indefinite' or not record.balance:
                record.remaining_installments = 0
                continue
            total_periods = record._calculate_total_periods()
            lines = record._get_done_payslip_lines()
            applied_periods = len(lines)
            record.remaining_installments = max(total_periods - applied_periods, 0)

    def _calculate_next_payment_date(self, reference_date):
        """Calcula la próxima fecha de pago considerando saltos y reglas"""
        self.ensure_one()

        if not self._is_period_active(reference_date):
            return False

        next_date = self._get_base_payment_date(reference_date)
        if not next_date:
            return False

        last_payslip_line = self._get_last_payslip_line()
        if last_payslip_line:
            next_date = self._adjust_date_after_last_payment(last_payslip_line, next_date)

        next_date = self._adjust_for_payment_rules(next_date)
        
        # Verificar saltos confirmados
        active_skip = self._get_active_skip(next_date, next_date)
        if active_skip:
            # Saltar al siguiente período
            if self.aplicar == '15':
                if next_date.day <= 15:
                    next_date = next_date + relativedelta(day=16)
                else:
                    next_date = next_date + relativedelta(months=1, day=1)
            elif self.aplicar == '30':
                next_date = next_date + relativedelta(months=1, day=1)
            else:
                next_date = next_date + relativedelta(days=15)

        return next_date

    def _is_period_active(self, reference_date):
        """Verifica si el período está activo"""
        if self.date_start and self.date_start > reference_date:
            return False
        if self.date_end and self.date_end < reference_date:
            return False
        return True

    def _get_base_payment_date(self, reference_date):
        """Obtiene la fecha base inicial para el cálculo"""
        if self.date_start and self.date_start > reference_date:
            return self.date_start
        return reference_date

    def _get_last_payslip_line(self):
        """Obtiene la ultima linea de nomina procesada"""
        lines = self._get_payslip_lines()
        return lines.filtered(
            lambda l: l.slip_id.state in ['done', 'paid']
        ).sorted(lambda l: l.slip_id.date_to, reverse=True)[:1]

    def _adjust_date_after_last_payment(self, last_line, next_date):
        """Ajusta la fecha considerando el último pago"""
        if not last_line:
            return next_date
            
        last_date = last_line.slip_id.date_to
        
        if next_date <= last_date:
            if self.aplicar == '15':
                if last_date.day <= 15:
                    return last_date.replace(day=16)
                return last_date + relativedelta(months=1, day=1)
            elif self.aplicar == '30':
                if last_date.day <= 15:
                    return last_date.replace(day=16)
                return last_date + relativedelta(months=1, day=1)
            else:
                return last_date + relativedelta(days=1)
                
        return next_date

    def _adjust_for_payment_rules(self, date):
        """Ajusta la fecha según las reglas de quincena"""
        if self.aplicar == '15':
            if date.day > 15:
                return date + relativedelta(months=1, day=1)
        elif self.aplicar == '30':
            if date.day <= 15:
                return date + relativedelta(day=16)
        return date

    @api.depends('date_start', 'date_end')
    def _compute_active_period(self):
        """Calcula si el período está activo"""
        today = fields.Date.today()
        for record in self:
            record.active_period = record._is_period_active(today)

    @api.depends(lambda self: self._get_next_payment_depends())
    def _compute_next_payment(self):
        """Calcula la proxima fecha de pago"""
        today = fields.Date.today()
        for record in self:
            record.next_payment_date = record._calculate_next_payment_date(today)

    @api.depends('amount', 'modality_value', 'amount_select', 'aplicar', 'type_deduction',
                 'skip_ids', 'force_double_payment', 'monthly_behavior', 'excluir_sabados',
                 'excluir_domingos', 'excluir_festivos', 'descontar_dia_31',
                 'adjust_by_daily_distribution')
    def _compute_simulation_details(self):
        for record in self:
            simulation_text = record._generate_simulation_text()
            record.simulation_text = simulation_text

    def _generate_simulation_text(self):
        """Genera el texto detallado de la simulación con comportamiento mensual y exclusiones"""
        self.ensure_one()
        
        # Cálculo base del monto
        base_amount = self._calculate_base_amount()
        
        # Determinar valores por quincena según comportamiento
        if self.modality_value == 'fijo':
            if self.monthly_behavior == 'equal':
                first_fortnight = base_amount if self.aplicar in ['15', '0'] else 0
                second_fortnight = base_amount if self.aplicar in ['30', '0'] else 0
            elif self.monthly_behavior == 'divided':
                half_amount = base_amount / 2
                first_fortnight = half_amount if self.aplicar in ['15', '0'] else 0
                second_fortnight = half_amount if self.aplicar in ['30', '0'] else 0
            else:  # proportional
                first_fortnight = (base_amount * 15 / 30) if self.aplicar in ['15', '0'] else 0
                second_fortnight = (base_amount * 15 / 30) if self.aplicar in ['30', '0'] else 0
        else:
            # Para modalidad diaria
            daily_amount = base_amount / 30
            first_fortnight = daily_amount * 15 if self.aplicar in ['15', '0'] else 0
            second_fortnight = daily_amount * 15 if self.aplicar in ['30', '0'] else 0
        
        # Cálculo diario
        daily_amount = base_amount / 30 if self.modality_value != 'fijo' else 0
        
        # Ejemplo con días normales y con exclusiones
        normal_days = 30
        excluded_days = 0
        if self.excluir_sabados:
            excluded_days += 4
        if self.excluir_domingos:
            excluded_days += 4
        if self.descontar_dia_31:
            excluded_days += 1 if calendar.monthrange(fields.Date.today().year, fields.Date.today().month)[1] == 31 else 0
        
        working_days = normal_days - excluded_days
        
        behavior_text = dict(self._fields['monthly_behavior'].selection).get(self.monthly_behavior, '')
        
        return f"""
        <div style="font-family: system-ui; max-width: 800px; line-height: 1.6;">
            <!-- Información de comportamiento mensual -->
            <div style="margin-bottom: 20px; padding: 15px; background-color: #e3f2fd; border-radius: 4px; border: 1px solid #bbdefb;">
                <div style="font-size: 0.9em; color: #1565c0; font-weight: bold;">Comportamiento Mensual: {behavior_text}</div>
                {(self.excluir_sabados or self.excluir_domingos or self.excluir_festivos or self.descontar_dia_31) and f'''
                <div style="margin-top: 10px; font-size: 0.85em; color: #0d47a1;">
                    Exclusiones activas:
                    {self.excluir_sabados and '<span style="margin-right: 10px;">✓ Sábados</span>' or ''}
                    {self.excluir_domingos and '<span style="margin-right: 10px;">✓ Domingos</span>' or ''}
                    {self.excluir_festivos and '<span style="margin-right: 10px;">✓ Festivos</span>' or ''}
                    {self.descontar_dia_31 and '<span style="margin-right: 10px;">✓ Día 31</span>' or ''}
                </div>''' or ''}
                {self.adjust_by_daily_distribution and f'''
                <div style="margin-top: 10px; padding: 8px; background-color: #fff3e0; border-radius: 4px; border: 1px solid #ffcc80;">
                    <span style="color: #e65100; font-weight: bold;">⚡ Ajuste por distribución diaria activo</span>
                    <div style="font-size: 0.85em; color: #bf360c; margin-top: 5px;">
                        El monto final se ajustará según: días_reales / días_esperados (15)
                    </div>
                </div>''' or ''}
            </div>
            
            <!-- Valores por quincena -->
            <div style="display: flex; gap: 20px; margin-bottom: 20px;">
                <div style="flex: 1; padding: 15px; background-color: #f8f9fa; border-radius: 4px; border: 1px solid #dee2e6;">
                    <div style="font-size: 0.9em; color: #6c757d;">Primera Quincena</div>
                    <div style="font-size: 1.4em; font-weight: bold; color: #212529; margin: 8px 0;">
                        ${first_fortnight:,.2f}
                    </div>
                    <div style="font-size: 0.8em; color: #6c757d;">
                        {self.aplicar == '15' and '100%' or self.aplicar == '0' and ('50%' if self.monthly_behavior == 'divided' else 'Proporcional') or 'No aplica'}
                    </div>
                </div>
                <div style="flex: 1; padding: 15px; background-color: #f8f9fa; border-radius: 4px; border: 1px solid #dee2e6;">
                    <div style="font-size: 0.9em; color: #6c757d;">Segunda Quincena</div>
                    <div style="font-size: 1.4em; font-weight: bold; color: #212529; margin: 8px 0;">
                        ${second_fortnight:,.2f}
                    </div>
                    <div style="font-size: 0.8em; color: #6c757d;">
                        {self.aplicar == '30' and '100%' or self.aplicar == '0' and ('50%' if self.monthly_behavior == 'divided' else 'Proporcional') or 'No aplica'}
                    </div>
                </div>
            </div>

            {daily_amount > 0 and f'''
            <div style="margin-top: 20px; padding: 15px; background-color: #f8f9fa; border-radius: 4px; border: 1px solid #dee2e6;">
                <div style="margin-bottom: 15px;">
                    <div style="font-size: 0.9em; color: #6c757d;">Valor por día</div>
                    <div style="font-size: 1.4em; font-weight: bold; color: #212529;">
                        ${daily_amount:,.2f}
                    </div>
                </div>

                <div style="display: flex; gap: 20px;">
                    <div style="flex: 1; padding: 10px; background-color: white; border-radius: 4px;">
                        <div style="font-size: 0.9em; color: #6c757d;">Mes Completo ({normal_days} días)</div>
                        <div style="font-size: 1.2em; color: #212529; margin-top: 5px;">
                            ${daily_amount * normal_days:,.2f}
                        </div>
                    </div>
                    <div style="flex: 1; padding: 10px; background-color: white; border-radius: 4px;">
                        <div style="font-size: 0.9em; color: #6c757d;">
                            Con Exclusiones ({working_days} días)
                        </div>
                        <div style="font-size: 1.2em; color: #212529; margin-top: 5px;">
                            ${daily_amount * working_days:,.2f}
                        </div>
                        <div style="font-size: 0.8em; color: #dc3545;">
                            -{excluded_days} días excluidos
                        </div>
                    </div>
                </div>
            </div>''' or ''}

            {self.skip_ids and f'''
            <div style="margin-top: 20px; padding: 15px; background-color: #fff3cd; border-radius: 4px; border: 1px solid #ffeeba;">
                <div style="font-size: 0.9em; color: #856404;">Casos con Saltos</div>
                <div style="display: flex; gap: 20px; margin-top: 10px;">
                    <div style="flex: 1; padding: 10px; background-color: white; border-radius: 4px;">
                        <div style="font-size: 0.9em; color: #856404;">Con Salto</div>
                        <div style="font-size: 1.2em; color: #856404; margin-top: 5px;">
                            $0.00
                        </div>
                    </div>
                    <div style="flex: 1; padding: 10px; background-color: white; border-radius: 4px;">
                        <div style="font-size: 0.9em; color: #856404;">Recuperación ({self.monthly_behavior == 'divided' and 'Mitad y mitad' or self.monthly_behavior == 'equal' and 'Mismo valor' or 'Proporcional'})</div>
                        <div style="font-size: 1.2em; color: #856404; margin-top: 5px;">
                            ${base_amount * 2 if self.monthly_behavior == 'equal' else base_amount:,.2f}
                        </div>
                    </div>
                </div>
            </div>''' or ''}
        </div>
        """

    def _calculate_base_amount(self):
        """Calcula el monto base según el tipo de cálculo"""
        if self.amount_select == 'percentage':
            base_salary = self.contract_id.wage
            return (base_salary * self.amount / 100)
        return self.amount

    def _calculate_days_excluded(self, start_date, end_date):
        """
        Calcula los días excluidos en un período según la configuración
        Returns: tupla (días_excluidos, sabados, domingos, festivos)
        """
        current_date = start_date
        dias_excluidos = 0
        sabados = 0
        domingos = 0
        festivos = 0
        
        while current_date <= end_date:
            if current_date.weekday() == 5 and self.excluir_sabados:
                sabados += 1
                dias_excluidos += 1
            elif current_date.weekday() == 6 and self.excluir_domingos:
                domingos += 1
                dias_excluidos += 1
            elif current_date.day == 31 and self.descontar_dia_31:
                dias_excluidos += 1
                
            if self.excluir_festivos:
                is_holiday = self.env['lavish.holidays'].search_count([('date', '=', current_date)])
                if is_holiday:
                    festivos += 1
                    if current_date.weekday() < 5: 
                        dias_excluidos += 1
                        
            current_date += timedelta(days=1)
            
        return (dias_excluidos, sabados, domingos, festivos)

    def get_amount_for_period_payslip(self, date_from, date_to):
        """Obtener monto para un período específico considerando todas las reglas"""
        self.ensure_one()
        
        if not self._is_valid_period(date_from, date_to):
            return 0

        base_amount = self._calculate_period_amount_slip(date_from, date_to)
        multiplier = self._get_period_multiplier(date_from, date_to)
        sign = 1        
        if self.input_id.dev_or_ded == 'deduccion':
            sign = -1
        return base_amount * multiplier * sign

    def _calculate_period_amount_slip(self, date_from, date_to):
        """Calcula el monto base para el período según la modalidad"""
        base_amount = self.amount
        if self.input_id.dev_or_ded == 'deduccion':
            base_amount = base_amount * -1
        if self.modality_value == 'fijo':
            return base_amount
            
        days = (date_to - date_from).days + 1
        if self.modality_value == 'diario_efectivo':
            return (base_amount / 30) * days
            
        if self.modality_value == 'diario':
            worked_days = self._get_worked_days(date_from, date_to)
            qty = 0
            if worked_days:
                qty = sum(d.number_of_days for d in worked_days)
            return (base_amount / 30) * qty
            
        return base_amount

    def get_amount_for_period(self, date_from, date_to):
        """Obtener monto para un período específico considerando todas las reglas"""
        self.ensure_one()
        
        if not self._is_valid_period(date_from, date_to):
            return 0

        base_amount = self._calculate_period_amount(date_from, date_to)
        multiplier = self._get_period_multiplier(date_from, date_to)
        sign = 1        
        if self.input_id.dev_or_ded == 'deduccion':
            sign = -1
        return base_amount * multiplier * sign

    def _is_valid_period(self, date_from, date_to):
        """
        Valida si el período es válido para aplicar el concepto.

        Usado por: get_amount_for_period (cálculo simple sin payslip)

        Condiciones:
        1. Estado debe ser 'done'
        2. El período debe estar dentro del rango del concepto
        3. El concepto debe estar en período activo
        """
        # Estado debe ser aprobado
        if self.state != 'done':
            return False
        # El período no puede empezar antes que el concepto
        if self.date_start and date_from < self.date_start:
            return False
        # El período no puede terminar después que el concepto
        if self.date_end and date_to > self.date_end:
            return False
        # Verificar que estemos en período activo
        if not self.active_period:
            return False
        return True

    def _calculate_period_amount(self, date_from, date_to):
        """Calcula el monto base para el período según modalidad y comportamiento"""
        base_amount = self._calculate_base_amount()
        
        # Si es valor fijo, aplicar comportamiento mensual
        if self.modality_value == 'fijo':
            if self.monthly_behavior == 'equal':
                # Mismo valor en ambas quincenas
                return base_amount
            elif self.monthly_behavior == 'divided':
                # Dividir en partes iguales
                if self.aplicar == '0':  # Aplica siempre
                    return base_amount / 2
                else:
                    return base_amount
            elif self.monthly_behavior == 'proportional':
                # Proporcional a días del período
                days_in_period = (date_to - date_from).days + 1
                days_in_month = calendar.monthrange(date_to.year, date_to.month)[1]
                return (base_amount * days_in_period) / days_in_month
        
        # Para modalidad diaria, calcular según días trabajados
        days = (date_to - date_from).days + 1
        if self.modality_value == 'diario_efectivo':
            # Restar días excluidos
            excluded, _, _, _ = self._calculate_days_excluded(date_from, date_to)
            days = days - excluded
            return (base_amount / 30) * days
        elif self.modality_value == 'diario':
            worked_days = self._get_worked_days(date_from, date_to)
            qty = sum(d.number_of_days for d in worked_days) if worked_days else days
            return (base_amount / 30) * qty
        
        return base_amount

    def _get_worked_days(self, date_from, date_to):
        """Obtiene los días efectivamente trabajados en el período"""
        return self.env['hr.payslip.worked_days'].search([
            ('payslip_id.employee_id', '=', self.contract_id.employee_id.id),
            ('payslip_id.date_from', '>=', date_from),
            ('payslip_id.struct_id.process', '=', 'nomina'),
            ('payslip_id.date_to', '<=', date_to),
            ('code', '=', 'WORK100'),
        ])

    def _get_period_multiplier(self, date_from, date_to):
        """
        Obtiene el multiplicador del período.

        Multiplicadores posibles:
        - 0: No aplicar (salto sin recuperación o quincena incorrecta)
        - 1: Aplicar normal
        - 2: Pago doble (salto con recuperación o pago doble forzado)

        Orden de verificación:
        1. Pago doble forzado (prioridad máxima)
        2. Saltos programados
        3. Verificación de quincena (para get_amount_for_period que no usa _should_apply_in_period)
        """
        # 1. Verificar pago doble forzado
        if self.force_double_payment and self.double_payment_date:
            if date_from <= self.double_payment_date <= date_to:
                self._mark_double_payment_applied()
                return 2

        # 2. Verificar saltos programados
        skip = self._get_active_skip(date_from, date_to)
        if skip:
            if skip.period_double:
                return 2  # Salto con recuperación: pagar doble
            return 0  # Salto sin recuperación: no pagar

        # 3. Verificar quincena (para métodos que no usan _should_apply_in_period)
        if self.aplicar == '15' and date_to.day > 15:
            return 0  # Concepto de 1ra quincena, pero es 2da
        if self.aplicar == '30' and date_from.day <= 15:
            return 0  # Concepto de 2da quincena, pero es 1ra

        return 1

    def _get_active_skip(self, date_from, date_to):
        """Obtiene el salto activo para el período si existe"""
        for skip in self.skip_ids:
            if skip.check_skip_applies(date_from, date_to):
                return skip
        return False

    def _mark_double_payment_applied(self):
        """Marca el pago doble como aplicado"""
        self.write({
            'force_double_payment': False,
            'last_double_payment': self.double_payment_date,
            'double_payment_date': False
        })

    def get_computed_amount_for_payslip(self, payslip, date_from, date_to, localdict):
        """
        Calcula el monto para la nómina según configuración y localdict.

        OPTIMIZACIÓN: Usa worked_days del localdict en lugar de filtrar cada vez.
        """
        self.ensure_one()
        precision = 2
        contract = localdict['contract']
        # OPTIMIZADO: Obtener WORK100 del localdict (ya pre-calculado)
        worked_days = localdict.get('worked_days', {})
        wd100 = worked_days.get('WORK100')
        annual_params = localdict['annual_parameters']
        
        if not self._should_apply_in_period(payslip, date_from, date_to, localdict):
            return self._no_apply(
                _("""El concepto no se aplica en el período seleccionado. 
                Verifique la configuración de fechas y condiciones."""),
                f"{date_from} - {date_to}"
            )
        
        # Aviso si contrato mensual con concepto quincenal
        aviso = None
        if contract.method_schedule_pay == 'monthly' and self.aplicar in ('15', '30'):
            aviso = _('[AVISO] Contrato mensual con concepto quincenal, se usará periodo real')
        
        days = 0
        # Días naturales en el periodo
        raw_days = (date_to - date_from).days + 1
        
        # Calcular días según WORK100 o exclusiones
        if wd100 and not contract.subcontract_type:
            if payslip.struct_type_id.wage_type == 'hourly':
                raw_days = wd100.number_of_hours / annual_params.hours_daily
            else:
                raw_days = wd100.number_of_days
            
            excluded = 0
            if self.excluir_sabados:
                excluded += localdict.get('sabado', 0)
            if self.excluir_domingos:
                excluded += localdict.get('domingos', 0)
            if self.excluir_festivos:
                excluded += localdict.get('festivos', 0)
            
            days = max(0, raw_days - excluded)
        else:
            days = raw_days
            
        # Limitar días al máximo del mes y redondear
        max_days = calendar.monthrange(date_to.year, date_to.month)[1]
        days = min(days, max_days)
        days = round(days, precision)

        # Construir pasos
        steps = []
        step = 1
        if aviso:
            steps.append(f"{step}. {aviso}")
            step += 1
            
        # Base
        if self.amount_select == 'percentage':
            base_amt = contract.wage * (self.amount / 100)
            steps.append(f"{step}. Base: {self.amount}% de {contract.wage:,.2f} = {base_amt:,.2f}")
        else:
            base_amt = self.amount
            steps.append(f"{step}. Base fija: {base_amt:,.2f}")
        step += 1
        
        # Modalidad
        modal = dict(self._fields['modality_value'].selection)[self.modality_value]
        steps.append(f"{step}. Modalidad valor: {modal}")
        step += 1
        
        # Comportamiento mensual
        behavior = dict(self._fields['monthly_behavior'].selection)[self.monthly_behavior]
        steps.append(f"{step}. Comportamiento mensual: {behavior}")
        step += 1
        
        # Días
        steps.append(f"{step}. Días computados: {days:.2f}")
        step += 1

        # Cálculo final según modalidad y comportamiento
        if self.modality_value == 'fijo':
            if self.monthly_behavior == 'equal':
                amt = base_amt
                steps.append(f"{step}. Valor fijo con comportamiento igual: {amt:,.2f}")
                fmt = f"{base_amt:,.2f}"
            elif self.monthly_behavior == 'divided':
                if self.aplicar == '0':
                    amt = base_amt / 2
                    fmt = f"{base_amt:,.2f} ÷ 2 = {amt:,.2f}"
                    steps.append(f"{step}. Dividido en partes iguales: {fmt}")
                else:
                    amt = base_amt
                    fmt = f"{base_amt:,.2f}"
                    steps.append(f"{step}. Valor completo para quincena: {amt:,.2f}")
            else:  # proportional
                days_in_period = (date_to - date_from).days + 1
                days_in_month = calendar.monthrange(date_to.year, date_to.month)[1]
                amt = (base_amt * days_in_period) / days_in_month
                fmt = f"({base_amt:,.2f} × {days_in_period}) ÷ {days_in_month} = {amt:,.2f}"
                steps.append(f"{step}. Proporcional a días: {fmt}")
        else:
            daily = base_amt / 30
            steps.append(f"{step}. Valor diario: {base_amt:,.2f} ÷ 30 = {daily:,.2f}")
            step += 1
            amt = daily * days
            fmt = f"{daily:,.2f} × {days:.2f} = {amt:,.2f}"
            steps.append(f"{step}. Cálculo diario × días = {fmt}")
        step += 1

        # Verificar saltos
        skip = self._get_active_skip(date_from, date_to)
        if skip:
            if skip.period_double:
                amt = amt * 2
                steps.append(f"{step}. Aplicando pago doble por salto: {amt:,.2f}")
                step += 1
            else:
                amt = 0
                steps.append(f"{step}. Período saltado: monto = 0")
                step += 1

        # Ajuste por distribución diaria (si está habilitado)
        if self.adjust_by_daily_distribution and amt != 0:
            # Calcular días esperados vs días reales
            if self.aplicar == '0':
                expected_days = 15  # Cada quincena espera 15 días
            else:
                expected_days = 15  # Quincena específica espera 15 días

            actual_days = days
            if actual_days != expected_days and expected_days > 0:
                adjustment_factor = actual_days / expected_days
                amt_before = amt
                amt = amt * adjustment_factor
                fmt = f"{amt_before:,.2f} × ({actual_days:.2f}/{expected_days}) = {amt:,.2f}"
                steps.append(f"{step}. Ajuste distribución diaria: {fmt}")
                step += 1

        # Signo
        result_amt = round(amt, precision)
        is_deduction = self.input_id.dev_or_ded == 'deduccion' if self.input_id else False
        if is_deduction and result_amt > 0:
            result_amt = -result_amt
            fmt += " ×(-1)"
            steps.append(f"{step}. Ajuste signo deducción = {result_amt:,.2f}")

        # Actualizar estado
        self.write({
            'payslip_ids': [(4, payslip.id)]
        })
        
        if self.total_paid:
            step += 1
            steps.append(f"{step}. Total pagado previo = {self.total_paid:,.2f}")

        # Construir nombre dinámico
        indicator = '1Q' if date_to.day <= 15 else '2Q'
        name = f"{self.input_id.name} - {indicator} {date_to.month}/{date_to.year}"
        if self.modality_value != 'fijo':
            name += f" ({days:.0f}d)"

        detail_html = self._build_concept_html_log(
            periodo=f"{indicator} {date_to.month}/{date_to.year}",
            aplicado=True,
            descripcion=_('Calculo de') + f" {self.input_id.name}",
            rango_log=[
                ('Monto base', f"{base_amt:,.2f}"),
                ('Dias', f"{days:.2f}"),
                ('Comportamiento', behavior)
            ],
            pasos=steps,
            monto_final=result_amt,
            formula=fmt
        )
        return {
            'create_line': True,
            'values': {
                'name': name,
                'code': self.input_id.code,
                'amount': result_amt,
                'quantity': 1 if self.modality_value == 'fijo' else days,
                'rate': 100,
                'concept_id': self.id,
            },
            'skip_info': {},
            'formula': fmt,
            'detail_html': detail_html
        }
    def _should_apply_in_period(self, payslip, date_from, date_to, localdict):
        """
        Verifica si el concepto debe aplicarse en el período dado.

        Condiciones verificadas:
        1. Estado del concepto debe ser 'done' (aprobado)
        2. Quincena correcta según campo 'aplicar':
           - '15': Solo primera quincena (día 1-15)
           - '30': Solo segunda quincena (día 16-31)
           - '0': Ambas quincenas
        3. Fechas del concepto deben incluir el período:
           - date_start <= date_to (el concepto ya empezó)
           - date_end >= date_from (el concepto no ha terminado)
        """
        # 1. Verificar estado
        if self.state != 'done':
            return False

        # 2. Verificar quincena según 'aplicar'
        if self.aplicar == '30' and date_from.day <= 15:
            # Concepto de 2da quincena, pero estamos en 1ra
            return False
        if self.aplicar == '15' and date_from.day > 15:
            # Concepto de 1ra quincena, pero estamos en 2da
            return False

        # 3. Verificar fechas del concepto
        # El concepto debe haber iniciado antes o durante el período
        if self.date_start and self.date_start > date_to:
            return False
        # El concepto no debe haber terminado antes del período
        if self.date_end and self.date_end < date_from:
            return False

        return True


    def _no_apply(self, reason, period):
        """Retorna estructura cuando no se aplica el concepto"""
        return {
            'create_line': False,
            'values': {},
            'skip_info': {
                'reason': reason,
                'period': period
            },
            'formula': '',
            'detail_html': f'<div style="color: #dc3545;">{reason}</div>'
        }

    def _get_justified_absence_codes(self):
        """Retorna los códigos de ausencias justificadas"""
        return ['LEAVE90', 'LEAVE100', 'LEAVE110', 'LEAVE120']

    def _build_concept_html_log(self, periodo, aplicado, descripcion, rango_log, pasos, monto_final, formula):
        """Construye el HTML del log de cálculo"""
        pasos_html = ''.join([f'<li>{paso}</li>' for paso in pasos])
        rango_html = ''.join([f'<tr><td>{key}</td><td>{value}</td></tr>' for key, value in rango_log])
        
        return f"""
        <div style="font-family: system-ui; padding: 20px; background: #f8f9fa; border-radius: 8px;">
            <h4 style="color: #212529; margin-bottom: 10px;">{descripcion}</h4>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px;">
                <div>
                    <strong>Período:</strong> {periodo}<br>
                    <strong>Estado:</strong> {'<span style="color: #28a745;">Aplicado</span>' if aplicado else '<span style="color: #dc3545;">No aplicado</span>'}
                </div>
                <div>
                    <table style="width: 100%; border-collapse: collapse;">
                        {rango_html}
                    </table>
                </div>
            </div>
            <div style="background: white; padding: 15px; border-radius: 4px; margin-bottom: 15px;">
                <strong>Pasos del cálculo:</strong>
                <ol style="margin: 10px 0; padding-left: 20px;">
                    {pasos_html}
                </ol>
            </div>
            <div style="background: #e3f2fd; padding: 15px; border-radius: 4px; text-align: center;">
                <strong>Fórmula:</strong> {formula}<br>
                <strong style="font-size: 1.2em; color: #1976d2;">Monto Final: ${monto_final:,.2f}</strong>
            </div>
        </div>
        """

    # Métodos de acción
    def action_draft(self):
        """Pasar a borrador"""
        self.write({'state': 'draft'})

    def action_approve(self):
        """Aprobar concepto"""
        self.write({'state': 'done'})

    def action_cancel(self):
        """Cancelar concepto"""
        self.write({'state': 'cancel'})

    def action_force_double_payment(self):
        """Forzar pago doble"""
        self.ensure_one()
        if self.state != 'done':
            raise UserError(_('Solo se puede forzar pago doble en conceptos aprobados'))
            
        next_date = self._calculate_next_payment_date(fields.Date.today())
        if not next_date:
            raise UserError(_('No se puede determinar la próxima fecha de pago'))
            
        self.write({
            'force_double_payment': True,
            'double_payment_date': next_date
        })

    def action_cancel_double_payment(self):
        """Cancelar pago doble programado"""
        self.write({
            'force_double_payment': False,
            'double_payment_date': False
        })

    def apply_to_payslip(self, payslip):
        """Aplicar concepto a una nómina específica"""
        self.ensure_one()
        
        # Validar estado del concepto
        if self.state != 'done':
            return False

        # Obtener valores para la nómina
        values = self._get_payslip_values(payslip)
        if not values['amount']:
            return False

        # Crear línea de nómina
        line = self.env['hr.payslip.line'].create({
            'slip_id': payslip.id,
            'salary_rule_id': self.input_id.id,
            'contract_id': self.contract_id.id,
            'employee_id': payslip.employee_id.id,
            'concept_id': self.id,
            'amount': values['amount'],
            'total': values['amount'], 
            'quantity': 1.0,
            'rate': 100.0,
            **values
        })

        return line

    def _get_payslip_values(self, payslip):
        """Obtener valores para la línea de nómina"""
        self.ensure_one()
        values = {
            'name': self.input_id.name,
            'code': self.input_id.code,
            'sequence': self.sequence,
        }
        
        amount = self.get_amount_for_period(payslip.date_from, payslip.date_to)
        if self.amount_select == 'percentage':
            values['rate'] = self.amount
            values['amount'] = amount
        else:
            values['amount'] = amount
            
        return values

    def unlink(self):
        for record in self:
            lines = record._get_payslip_lines()
            if lines:
                raise ValidationError(_('No se puede eliminar una novedad que ha sido aplicada en nomina. '
                                    'Solo se puede cancelar para mantener el historico.'))
        return super().unlink()

    @api.ondelete(at_uninstall=False)
    def _unlink_if_no_lines(self):
        for record in self:
            lines = record._get_payslip_lines()
            if lines:
                raise ValidationError(_('No se puede eliminar una novedad que ha sido aplicada en nomina. '
                                    'Solo se puede cancelar para mantener el historico.'))

    # ==================== MÉTODOS DE ACCIÓN ====================

    def view_simulation(self):
        """Mostrar información de simulación del concepto"""
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Simulación de Concepto'),
                'message': self.simulation_text if self.simulation_text else _('Configure el concepto y calcule una nómina para ver la simulación'),
                'sticky': True,
                'type': 'info'
            }
        }

    def action_create_skip(self):
        """Crear un salto para este concepto"""
        self.ensure_one()

        if self.state != 'done':
            raise UserError(_('Solo se pueden crear saltos para conceptos aprobados'))

        if not self.allow_skips:
            raise UserError(_('Este concepto no permite crear saltos'))

        # Crear salto en borrador para el próximo período
        next_date = self.next_payment_date or fields.Date.today()

        skip = self.env['hr.contract.concept.skip'].create({
            'concept_id': self.id,
            'period_skip': next_date,
            'fortnight': self.aplicar if self.aplicar in ['15', '30'] else '15',
            'reason': _('Salto creado manualmente'),
            'state': 'draft',
        })

        return {
            'name': _('Salto de Concepto'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.contract.concept.skip',
            'res_id': skip.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def view_skips(self):
        """Ver todos los saltos de este concepto"""
        self.ensure_one()
        return {
            'name': _('Saltos - %s') % self.display_name,
            'type': 'ir.actions.act_window',
            'res_model': 'hr.contract.concept.skip',
            'domain': [('concept_id', '=', self.id)],
            'view_mode': 'list,form',
            'context': {'default_concept_id': self.id}
        }

    def view_payslip_lines(self):
        """Ver todas las líneas de nómina de este concepto"""
        self.ensure_one()
        return {
            'name': _('Líneas de Nómina - %s') % self.display_name,
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payslip.line',
            'domain': [('concept_id', '=', self.id)],
            'view_mode': 'list,form',
            'context': {
                'create': False,
                'delete': False,
            }
        }

    def action_close(self):
        """Cerrar el concepto"""
        self.ensure_one()

        if self.state != 'done':
            raise UserError(_('Solo se pueden cerrar conceptos aprobados'))

        if not self.close_ready:
            raise UserError(_('Este concepto no está listo para cerrar. Verifique que el saldo sea cero o cercano a cero.'))

        payslip_id = self.env.context.get('payslip_id')

        self.write({
            'state': 'closed',
            'closed_date': fields.Date.today(),
            'closed_payslip_id': payslip_id if payslip_id else False,
        })

        self.message_post(
            body=_('Concepto cerrado. Saldo final: $%s') % '{:,.2f}'.format(self.balance)
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Concepto Cerrado'),
                'message': _('El concepto ha sido cerrado exitosamente'),
                'type': 'success',
                'sticky': False,
            }
        }

    # =========================================================================
    # METODOS DE PROYECCION
    # =========================================================================

    def get_projected_amount(self, projection_type, date_from, date_to, localdict=None):
        """
        Calcula el monto proyectado del concepto segun el tipo de proyeccion.

        Args:
            projection_type: Tipo de proyeccion ('nomina', 'retencion', 'seguridad_social', 'prestaciones')
            date_from: Fecha inicio del periodo
            date_to: Fecha fin del periodo
            localdict: Diccionario con datos de nomina (opcional)

        Returns:
            float: Monto proyectado (0 si no aplica proyeccion)
        """
        self.ensure_one()

        # Verificar si aplica proyeccion para este tipo
        field_map = {
            'nomina': 'proyectar_nomina',
            'retencion': 'proyectar_retencion',
            'seguridad_social': 'proyectar_seguridad_social',
            'prestaciones': 'proyectar_prestaciones',
        }

        field_name = field_map.get(projection_type)
        if not field_name or not getattr(self, field_name, False):
            return 0.0

        # Obtener monto base del concepto
        if localdict:
            amount = self.get_computed_amount_for_payslip(
                localdict.get('slip'),
                date_from,
                date_to,
                localdict
            )
            if isinstance(amount, tuple):
                amount = amount[0] if amount else 0
        else:
            amount = self.get_amount_for_period(date_from, date_to)

        # Aplicar factor de proyeccion
        factor = self.factor_proyeccion or 1.0
        projected = amount * factor

        return projected

    @api.model
    def get_contract_projected_concepts(self, contract_id, projection_type, date_from, date_to, localdict=None):
        """
        Obtiene todos los conceptos proyectados de un contrato para un tipo especifico.

        Args:
            contract_id: ID del contrato
            projection_type: Tipo de proyeccion ('nomina', 'retencion', 'seguridad_social', 'prestaciones')
            date_from: Fecha inicio del periodo
            date_to: Fecha fin del periodo
            localdict: Diccionario con datos de nomina (opcional)

        Returns:
            dict: {
                'total': float,
                'concepts': [{'id': int, 'name': str, 'amount': float, 'projected': float}]
            }
        """
        field_map = {
            'nomina': 'proyectar_nomina',
            'retencion': 'proyectar_retencion',
            'seguridad_social': 'proyectar_seguridad_social',
            'prestaciones': 'proyectar_prestaciones',
        }

        field_name = field_map.get(projection_type)
        if not field_name:
            return {'total': 0, 'concepts': []}

        # Buscar conceptos con proyeccion habilitada
        domain = [
            ('contract_id', '=', contract_id),
            ('state', '=', 'done'),
            (field_name, '=', True),
        ]

        # Filtrar por fechas si aplica
        domain += [
            '|',
            ('date_start', '=', False),
            ('date_start', '<=', date_to),
        ]
        domain += [
            '|',
            ('date_end', '=', False),
            ('date_end', '>=', date_from),
        ]

        concepts = self.search(domain)

        result = {
            'total': 0.0,
            'concepts': [],
        }

        for concept in concepts:
            projected = concept.get_projected_amount(
                projection_type, date_from, date_to, localdict
            )
            if projected:
                result['concepts'].append({
                    'id': concept.id,
                    'name': concept.name or concept.input_id.name,
                    'code': concept.input_id.code if concept.input_id else '',
                    'amount': concept.amount,
                    'projected': projected,
                    'factor': concept.factor_proyeccion,
                })
                result['total'] += projected

        return result

    def get_projection_summary(self, date_from, date_to):
        """
        Genera un resumen de proyecciones para el concepto.

        Returns:
            dict: Resumen de proyecciones por tipo
        """
        self.ensure_one()
        summary = {}

        for ptype in ['nomina', 'retencion', 'seguridad_social', 'prestaciones']:
            field_name = f'proyectar_{ptype}'
            if getattr(self, field_name, False):
                projected = self.get_projected_amount(ptype, date_from, date_to)
                summary[ptype] = {
                    'active': True,
                    'amount': projected,
                    'factor': self.factor_proyeccion,
                }
            else:
                summary[ptype] = {'active': False, 'amount': 0, 'factor': 0}

        return summary

    # =========================================================================
    # METODOS DE CALCULO DE EMBARGOS - CST Art. 154
    # Llamados desde reglas salariales (hr.salary.rule)
    # Retornan tuple: (amount, quantity, rate, name, condition, data_result)
    # =========================================================================

    def _embargo001(self, localdict):
        """Primer embargo - Reutiliza logica generica"""
        return self._calculate_embargo_generic(localdict, 'EMBARGO001')

    def _embargo002(self, localdict):
        """Segundo embargo - Reutiliza logica generica"""
        return self._calculate_embargo_generic(localdict, 'EMBARGO002')

    def _embargo003(self, localdict):
        """Tercer embargo - Reutiliza logica generica"""
        return self._calculate_embargo_generic(localdict, 'EMBARGO003')

    def _embargo004(self, localdict):
        """Cuarto embargo - Reutiliza logica generica"""
        return self._calculate_embargo_generic(localdict, 'EMBARGO004')

    def _embargo005(self, localdict):
        """Quinto embargo - Reutiliza logica generica"""
        return self._calculate_embargo_generic(localdict, 'EMBARGO005')

    def _calculate_embargo_generic(self, localdict, rule_code):
        """
        Calcula el monto de embargo para la nomina segun ley colombiana CST Art. 154.

        Limites legales:
        - Embargo alimentario (ECA/cooperativas): hasta 50% del salario neto
        - Embargo general (O): 20% del excedente sobre SMMLV

        Args:
            localdict: Diccionario con datos de nomina (slip, employee, contract, categories, annual_parameters)
            rule_code: Codigo de la regla (EMBARGO001, EMBARGO002, etc.)

        Returns:
            tuple: (amount, quantity, rate, name, condition, data_result)
                   - amount: Monto negativo del embargo
                   - quantity: 1
                   - rate: Porcentaje aplicado
                   - name: Nombre descriptivo
                   - condition: False (siempre se aplica si llega aqui)
                   - data_result: dict con datos adicionales para el widget
        """
        slip = localdict['slip']
        employee = localdict['employee']
        contract = localdict['contract']
        categories = localdict.get('categories')
        annual_parameters = localdict.get('annual_parameters')
        date_from = slip.date_from
        date_to = slip.date_to

        # Validar que no exista ya en la nomina actual
        existing_line = slip.line_ids.filtered(lambda l: l.code == rule_code and l.total != 0)
        if existing_line:
            _logger.info(f"[EMBARGO] {rule_code} ya calculado en esta nomina")
            return (0, 1, 100, f'{rule_code} - Ya calculado', False, {'skip': True})

        # Validar que no exista en otras nominas de la misma quincena
        other_payslips = self.env['hr.payslip'].search([
            ('employee_id', '=', employee.id),
            ('date_from', '=', slip.date_from),
            ('date_to', '=', slip.date_to),
            ('state', 'in', ['done', 'paid']),
            ('id', '!=', slip.id)
        ])
        for other_slip in other_payslips:
            if other_slip.line_ids.filtered(lambda l: l.code == rule_code and l.total != 0):
                _logger.info(f"[EMBARGO] {rule_code} ya aplicado en otra nomina")
                return (0, 1, 100, f'{rule_code} - Ya aplicado en periodo', False, {'skip': True})

        # Buscar la regla de salario
        rule = self.env['hr.salary.rule'].search([('code', '=', rule_code)], limit=1)

        # Buscar conceptos aprobados para esta regla
        if rule:
            concepts = self.env['hr.contract.concepts'].search([
                ('contract_id', '=', contract.id),
                ('input_id', '=', rule.id),
                ('state', '=', 'done'),
                ('type_deduction', '=', 'E')
            ])
        else:
            concepts = self.env['hr.contract.concepts'].browse()

        if not concepts:
            _logger.info(f"[EMBARGO] {rule_code} - Sin concepto aprobado")
            return (0, 1, 100, f'{rule_code} - Sin concepto', False, {'skip': True})

        # Filtrar conceptos que aplican en esta quincena
        day = slip.date_from.day
        applicable_concepts = []
        for concept in concepts:
            aplicar = concept.aplicar or '0'
            if (day < 15 and aplicar == '30') or (day >= 15 and aplicar == '15'):
                continue
            applicable_concepts.append(concept)

        if not applicable_concepts:
            _logger.info(f"[EMBARGO] {rule_code} - Ningun embargo aplica en esta quincena")
            return (0, 1, 100, f'{rule_code} - No aplica', False, {'skip': True})

        _logger.info(f"[EMBARGO] Conceptos aplicables: {len(applicable_concepts)}")

        # Tomar el primer concepto para valores por defecto
        concept = applicable_concepts[0]
        tipo_emb = concept.type_emb or 'O'
        es_alimentario = (tipo_emb == 'ECA')

        # SMMLV
        smmlv = annual_parameters.smmlv_monthly if annual_parameters else 0.0

        # Construir pasos de calculo
        steps = []
        step = 1

        # =====================================================
        # CALCULO DE BASE SEGUN LEY COLOMBIANA CST Art. 154
        # =====================================================
        steps.append(f"{step}. Tipo de embargo: {'Alimentario/Cooperativa (50%)' if es_alimentario else 'General (20% excedente SMMLV)'}")
        step += 1

        # Acceder a los valores usando .dict (BrowsableObject pattern)
        cat_dict = categories.dict if hasattr(categories, 'dict') else {}
        rules_dict = {}
        result_rules = localdict.get('result_rules')
        if result_rules and hasattr(result_rules, 'dict'):
            rules_dict = result_rules.dict
        result_rules_co = localdict.get('result_rules_co')
        if result_rules_co and hasattr(result_rules_co, 'dict'):
            rules_dict.update(result_rules_co.dict)

        # Usar categorias/reglas configuradas en el concepto
        cat_codes_cfg = [c.code for c in concept.discount_categoria] if concept.discount_categoria else []
        rule_codes_cfg = [r.code for r in concept.discount_rule] if concept.discount_rule else []

        # Fallback a BASIC solo si no hay nada configurado
        if not cat_codes_cfg and not rule_codes_cfg:
            cat_codes_cfg = ['BASIC']

        # Calcular base bruta desde categorias configuradas
        base_bruta = 0.0
        for cat_code in cat_codes_cfg:
            cat_value = cat_dict.get(cat_code, 0)
            if isinstance(cat_value, dict):
                base_bruta += cat_value.get('total', 0)
            else:
                base_bruta += cat_value or 0

        # Agregar reglas configuradas
        for rule_c in rule_codes_cfg:
            rule_data = rules_dict.get(rule_c)
            if rule_data:
                if isinstance(rule_data, dict):
                    base_bruta += rule_data.get('total', 0)
                else:
                    base_bruta += getattr(rule_data, 'total', 0) if rule_data else 0

        base = base_bruta
        steps.append(f"{step}. Base de calculo (NETO): ${base:,.0f}")
        step += 1
        steps.append(f"{step}. SMMLV vigente: ${smmlv:,.0f}")
        step += 1

        # Obtener otros embargos activos
        otros_embargos_total = 0.0
        otros_embargos_alimentos = 0.0

        for line in slip.line_ids:
            if line.code and line.code.startswith('EMBARGO') and line.code != rule_code:
                line_total = abs(line.total) if line.total < 0 else line.total
                if line_total > 0:
                    otros_embargos_total += line_total
                    line_concept = self.env['hr.contract.concepts'].search([
                        ('contract_id', '=', contract.id),
                        ('input_id', '=', line.salary_rule_id.id)
                    ], limit=1)
                    if line_concept and line_concept.type_emb == 'ECA':
                        otros_embargos_alimentos += line_total

        if otros_embargos_total > 0:
            steps.append(f"{step}. Otros embargos activos: ${otros_embargos_total:,.0f}")
            step += 1

        # Calcular limites segun tipo de embargo
        if es_alimentario:
            limite_maximo = base * 0.5
            limite_disponible = limite_maximo - otros_embargos_alimentos
            steps.append(f"{step}. Limite legal (50%): ${base:,.0f} x 50% = ${limite_maximo:,.0f}")
        else:
            excedente = max(0.0, base - smmlv)
            limite_maximo = excedente * 0.2
            limite_disponible = limite_maximo - (otros_embargos_total - otros_embargos_alimentos)
            steps.append(f"{step}. Excedente sobre SMMLV: ${base:,.0f} - ${smmlv:,.0f} = ${excedente:,.0f}")
            step += 1
            steps.append(f"{step}. Limite legal (20%): ${excedente:,.0f} x 20% = ${limite_maximo:,.0f}")
        step += 1

        steps.append(f"{step}. Limite disponible: ${limite_disponible:,.0f}")
        step += 1

        if limite_disponible <= 0:
            _logger.info(f"[EMBARGO] {rule_code} - Sin limite disponible")
            return (0, 1, 100, f'{rule_code} - Sin limite', False, {'skip': True})

        # Calcular embargos
        total_embargo = 0.0
        limite_restante = limite_disponible
        names_list = []
        formula_parts = []

        for idx, concept in enumerate(applicable_concepts, 1):
            if limite_restante <= 0:
                break

            concept_name = concept.name or f'Concepto {concept.id}'
            amount_select = concept.amount_select or 'fix'
            amount = concept.amount or 0.0

            # Calcular valor para este concepto
            if amount_select == 'percentage':
                pct = amount
                if es_alimentario:
                    embargoable_raw = base * (pct / 100.0)
                else:
                    excedente = max(0.0, base - smmlv)
                    embargoable_raw = excedente * (pct / 100.0)
                tipo_calc = f'{pct}%'
            elif amount_select == 'fix':
                embargoable_raw = amount
                tipo_calc = f'Fijo ${amount:,.0f}'
            else:
                pct = amount / 100.0 if amount else 0.0
                embargoable_raw = base * (pct / 100.0)
                tipo_calc = f'{pct}%'

            # Ajustar al limite restante
            embargoable = min(embargoable_raw, limite_restante)

            if embargoable > 0:
                total_embargo += embargoable
                limite_restante -= embargoable
                names_list.append(concept_name)
                formula_parts.append(f"{concept_name}: {tipo_calc} = ${embargoable:,.0f}")
                steps.append(f"{step}. {concept_name}: {tipo_calc} = ${embargoable:,.0f}")
                step += 1
                _logger.info(f"[EMBARGO] Concepto {concept.id}: -{embargoable:,.2f}")

        if total_embargo <= 0:
            _logger.info(f"[EMBARGO] {rule_code} - Ningun embargo aplicado")
            return (0, 1, 100, f'{rule_code} - Sin embargo', False, {'skip': True})

        # Resultado final
        result_amt = -total_embargo  # Negativo porque es deduccion
        steps.append(f"{step}. TOTAL EMBARGO: -${total_embargo:,.0f}")

        # Construir nombre dinamico
        indicator = '1Q' if date_to.day <= 15 else '2Q'
        if len(names_list) == 1:
            name = f"EMBARGO - {names_list[0]} - {indicator} {date_to.month}/{date_to.year}"
        else:
            name = f"EMBARGOS ({len(names_list)}) - {indicator} {date_to.month}/{date_to.year}"

        formula = " + ".join(formula_parts) if formula_parts else f"${total_embargo:,.0f}"

        # Generar HTML con log detallado
        detail_html = self._build_concept_html_log(
            periodo=f"{indicator} {date_to.month}/{date_to.year}",
            aplicado=True,
            descripcion=f"Calculo de Embargo - {rule_code}",
            rango_log=[
                ('Base NETO', f"${base:,.0f}"),
                ('SMMLV', f"${smmlv:,.0f}"),
                ('Limite legal', f"${limite_maximo:,.0f}"),
                ('Tipo', 'Alimentario' if es_alimentario else 'General'),
            ],
            pasos=steps,
            monto_final=result_amt,
            formula=formula
        )

        # Calcular porcentaje aplicado para el rate
        pct = (total_embargo / base * 100) if base > 0 else 0.0

        _logger.info(f"[EMBARGO] {rule_code} - Retornando tuple: amount={result_amt}, rate={pct:.2f}%")

        # Estructura de datos adicionales para el widget
        data_result = {
            'base_calculo': base,
            'limite_legal': limite_maximo,
            'limite_disponible': limite_disponible,
            'total_embargo': total_embargo,
            'es_alimentario': es_alimentario,
            'conceptos_aplicados': len(names_list),
            'formula': formula,
            'detail_html': detail_html,
            'pasos': steps,
            'concept_id': concept.id if concept else None,
        }

        # Retornar tuple para regla salarial: (amount, quantity, rate, name, condition, data)
        return (result_amt, 1, pct, name, False, data_result)

    # =========================================================================
    # METODO DE CALCULO DE PRESTAMOS - type_deduction = 'P'
    # =========================================================================

    def get_prestamo_for_payslip(self, payslip, date_from, date_to, localdict):
        """
        Calcula el monto de prestamo para la nomina.

        Args:
            payslip: Objeto hr.payslip
            date_from: Fecha inicio del periodo
            date_to: Fecha fin del periodo
            localdict: Diccionario con datos de nomina

        Returns:
            dict: Estructura compatible con get_computed_amount_for_payslip
        """
        self.ensure_one()
        contract = localdict['contract']
        annual_params = localdict.get('annual_parameters')

        # Validar periodo
        if not self._should_apply_in_period(payslip, date_from, date_to, localdict):
            return self._no_apply(
                _('El prestamo no aplica en este periodo'),
                f"{date_from} - {date_to}"
            )

        # Construir pasos de calculo
        steps = []
        step = 1

        # Informacion del prestamo
        steps.append(f"{step}. Tipo: Prestamo empresa")
        step += 1

        if self.partner_id:
            steps.append(f"{step}. Entidad: {self.partner_id.name}")
            step += 1

        # Calcular monto base
        if self.amount_select == 'percentage':
            base_amt = contract.wage * (self.amount / 100)
            steps.append(f"{step}. Base: {self.amount}% de ${contract.wage:,.0f} = ${base_amt:,.0f}")
        else:
            base_amt = self.amount
            steps.append(f"{step}. Monto cuota fija: ${base_amt:,.0f}")
        step += 1

        # Modalidad de valor
        modal = dict(self._fields['modality_value'].selection).get(self.modality_value, 'Fijo')
        steps.append(f"{step}. Modalidad: {modal}")
        step += 1

        # Comportamiento mensual
        behavior = dict(self._fields['monthly_behavior'].selection).get(self.monthly_behavior, 'Igual')
        steps.append(f"{step}. Comportamiento mensual: {behavior}")
        step += 1

        # Calcular monto final segun modalidad
        if self.modality_value == 'fijo':
            if self.monthly_behavior == 'equal':
                amt = base_amt
                formula = f"${base_amt:,.0f}"
            elif self.monthly_behavior == 'divided':
                if self.aplicar == '0':
                    amt = base_amt / 2
                    formula = f"${base_amt:,.0f} / 2 = ${amt:,.0f}"
                else:
                    amt = base_amt
                    formula = f"${base_amt:,.0f}"
            else:  # proportional
                days_in_period = (date_to - date_from).days + 1
                days_in_month = calendar.monthrange(date_to.year, date_to.month)[1]
                amt = (base_amt * days_in_period) / days_in_month
                formula = f"(${base_amt:,.0f} x {days_in_period}) / {days_in_month} = ${amt:,.0f}"
        else:
            # Modalidad diaria
            worked_days = localdict.get('worked_days', {})
            wd100 = worked_days.get('WORK100')
            days = wd100.number_of_days if wd100 else (date_to - date_from).days + 1
            daily = base_amt / 30
            amt = daily * days
            formula = f"(${base_amt:,.0f} / 30) x {days:.0f} = ${amt:,.0f}"
            steps.append(f"{step}. Dias: {days:.0f}")
            step += 1

        steps.append(f"{step}. Calculo: {formula}")
        step += 1

        # Verificar saltos
        skip = self._get_active_skip(date_from, date_to)
        if skip:
            if skip.period_double:
                amt = amt * 2
                steps.append(f"{step}. Pago doble por salto: ${amt:,.0f}")
                step += 1
            else:
                return self._no_apply(
                    f'Prestamo saltado este periodo',
                    f"{date_from} - {date_to}"
                )

        # Aplicar signo (prestamo es deduccion)
        result_amt = round(amt, 2)
        is_deduction = self.input_id.dev_or_ded == 'deduccion' if self.input_id else True
        if is_deduction and result_amt > 0:
            result_amt = -result_amt

        steps.append(f"{step}. TOTAL CUOTA: ${result_amt:,.0f}")

        # Informacion de saldo
        if self.period == 'limited' and self.balance:
            steps.append(f"{step + 1}. Saldo pendiente: ${self.balance:,.0f}")
            steps.append(f"{step + 2}. Cuotas restantes: {self.remaining_installments}")

        # Construir nombre
        indicator = '1Q' if date_to.day <= 15 else '2Q'
        name = f"{self.input_id.name if self.input_id else 'PRESTAMO'} - {indicator} {date_to.month}/{date_to.year}"

        # Generar HTML
        detail_html = self._build_concept_html_log(
            periodo=f"{indicator} {date_to.month}/{date_to.year}",
            aplicado=True,
            descripcion=f"Calculo de Prestamo - {self.name or 'Prestamo'}",
            rango_log=[
                ('Monto cuota', f"${base_amt:,.0f}"),
                ('Modalidad', modal),
                ('Comportamiento', behavior),
                ('Saldo', f"${self.balance:,.0f}" if self.balance else 'N/A'),
            ],
            pasos=steps,
            monto_final=result_amt,
            formula=formula
        )

        # Actualizar estado
        self.write({
            'payslip_ids': [(4, payslip.id)]
        })

        _logger.info(f"[PRESTAMO] {self.name} - Retornando: amount={result_amt}")

        return {
            'create_line': True,
            'values': {
                'name': name,
                'code': self.input_id.code if self.input_id else 'PRESTAMO',
                'amount': result_amt,
                'quantity': 1,
                'rate': 100,
                'concept_id': self.id,
            },
            'skip_info': {},
            'formula': formula,
            'detail_html': detail_html,
            'prestamo_data': {
                'monto_cuota': base_amt,
                'saldo_pendiente': self.balance or 0,
                'cuotas_restantes': self.remaining_installments or 0,
                'total_pagado': self.total_paid or 0,
                'entidad': self.partner_id.name if self.partner_id else None,
            }
        }

    # =========================================================================
    # METODO DE CALCULO DE NOVEDADES DIRECTAS - Ahorros, Seguros, Libranzas, etc.
    # =========================================================================

    def get_novedad_for_payslip(self, payslip, date_from, date_to, localdict):
        """
        Calcula el monto de novedad directa para la nomina.
        Aplica para: Ahorros (A), Seguros (S), Libranzas (L), Retenciones (R), Otros (O)

        Args:
            payslip: Objeto hr.payslip
            date_from: Fecha inicio del periodo
            date_to: Fecha fin del periodo
            localdict: Diccionario con datos de nomina

        Returns:
            dict: Estructura compatible con get_computed_amount_for_payslip
        """
        self.ensure_one()
        contract = localdict['contract']
        annual_params = localdict.get('annual_parameters')

        # Validar periodo
        if not self._should_apply_in_period(payslip, date_from, date_to, localdict):
            return self._no_apply(
                _('La novedad no aplica en este periodo'),
                f"{date_from} - {date_to}"
            )

        # Tipo de deduccion
        tipo_ded_map = {
            'A': 'Ahorro',
            'S': 'Seguro',
            'L': 'Libranza',
            'R': 'Retencion',
            'O': 'Otros',
            'P': 'Prestamo',
            'E': 'Embargo',
        }
        tipo_nombre = tipo_ded_map.get(self.type_deduction, 'Novedad')

        # Construir pasos de calculo
        steps = []
        step = 1

        steps.append(f"{step}. Tipo: {tipo_nombre}")
        step += 1

        if self.partner_id:
            steps.append(f"{step}. Entidad: {self.partner_id.name}")
            step += 1

        if self.description:
            steps.append(f"{step}. Descripcion: {self.description}")
            step += 1

        # Calcular monto base
        if self.amount_select == 'percentage':
            # Obtener base segun categorias/reglas configuradas
            categories = localdict.get('categories')
            cat_dict = categories.dict if hasattr(categories, 'dict') else {}

            base_calculo = 0.0
            cat_codes_cfg = [c.code for c in self.discount_categoria] if self.discount_categoria else []
            rule_codes_cfg = [r.code for r in self.discount_rule] if self.discount_rule else []

            if not cat_codes_cfg and not rule_codes_cfg:
                # Fallback: usar salario del contrato
                base_calculo = contract.wage
                steps.append(f"{step}. Base (salario): ${base_calculo:,.0f}")
            else:
                for cat_code in cat_codes_cfg:
                    cat_value = cat_dict.get(cat_code, 0)
                    if isinstance(cat_value, dict):
                        base_calculo += cat_value.get('total', 0)
                    else:
                        base_calculo += cat_value or 0
                steps.append(f"{step}. Base calculada: ${base_calculo:,.0f}")
            step += 1

            base_amt = base_calculo * (self.amount / 100)
            steps.append(f"{step}. Porcentaje: {self.amount}% de ${base_calculo:,.0f} = ${base_amt:,.0f}")
        else:
            base_amt = self.amount
            steps.append(f"{step}. Monto fijo: ${base_amt:,.0f}")
        step += 1

        # Aplicar minimos y maximos
        if self.minimum_amount and base_amt < self.minimum_amount:
            base_amt = self.minimum_amount
            steps.append(f"{step}. Ajuste minimo: ${base_amt:,.0f}")
            step += 1
        if self.maximum_amount and base_amt > self.maximum_amount:
            base_amt = self.maximum_amount
            steps.append(f"{step}. Ajuste maximo: ${base_amt:,.0f}")
            step += 1

        # Modalidad de valor
        modal = dict(self._fields['modality_value'].selection).get(self.modality_value, 'Fijo')
        steps.append(f"{step}. Modalidad: {modal}")
        step += 1

        # Comportamiento mensual
        behavior = dict(self._fields['monthly_behavior'].selection).get(self.monthly_behavior, 'Igual')
        steps.append(f"{step}. Comportamiento mensual: {behavior}")
        step += 1

        # Calcular monto final segun modalidad
        if self.modality_value == 'fijo':
            if self.monthly_behavior == 'equal':
                amt = base_amt
                formula = f"${base_amt:,.0f}"
            elif self.monthly_behavior == 'divided':
                if self.aplicar == '0':
                    amt = base_amt / 2
                    formula = f"${base_amt:,.0f} / 2 = ${amt:,.0f}"
                else:
                    amt = base_amt
                    formula = f"${base_amt:,.0f}"
            else:  # proportional
                days_in_period = (date_to - date_from).days + 1
                days_in_month = calendar.monthrange(date_to.year, date_to.month)[1]
                amt = (base_amt * days_in_period) / days_in_month
                formula = f"(${base_amt:,.0f} x {days_in_period}) / {days_in_month} = ${amt:,.0f}"
        else:
            # Modalidad diaria
            worked_days = localdict.get('worked_days', {})
            wd100 = worked_days.get('WORK100')
            days = wd100.number_of_days if wd100 else (date_to - date_from).days + 1

            # Aplicar exclusiones si aplica
            if self.modality_value == 'diario_efectivo':
                excluded = 0
                if self.excluir_sabados:
                    excluded += localdict.get('sabado', 0)
                if self.excluir_domingos:
                    excluded += localdict.get('domingos', 0)
                if self.excluir_festivos:
                    excluded += localdict.get('festivos', 0)
                days = max(0, days - excluded)
                steps.append(f"{step}. Dias efectivos (excl. {excluded}): {days:.0f}")
                step += 1

            daily = base_amt / 30
            amt = daily * days
            formula = f"(${base_amt:,.0f} / 30) x {days:.0f} = ${amt:,.0f}"
            steps.append(f"{step}. Dias: {days:.0f}")
            step += 1

        steps.append(f"{step}. Calculo: {formula}")
        step += 1

        # Verificar saltos
        skip = self._get_active_skip(date_from, date_to)
        if skip:
            if skip.period_double:
                amt = amt * 2
                steps.append(f"{step}. Pago doble por salto: ${amt:,.0f}")
                step += 1
            else:
                return self._no_apply(
                    f'Novedad saltada este periodo',
                    f"{date_from} - {date_to}"
                )

        # Ajuste por distribucion diaria
        if self.adjust_by_daily_distribution and amt != 0:
            worked_days = localdict.get('worked_days', {})
            wd100 = worked_days.get('WORK100')
            if wd100:
                actual_days = wd100.number_of_days
                expected_days = 15
                if actual_days != expected_days and expected_days > 0:
                    factor = actual_days / expected_days
                    amt_before = amt
                    amt = amt * factor
                    steps.append(f"{step}. Ajuste distribucion: ${amt_before:,.0f} x ({actual_days}/{expected_days}) = ${amt:,.0f}")
                    step += 1

        # Aplicar signo segun tipo
        result_amt = round(amt, 2)
        is_deduction = self.input_id.dev_or_ded == 'deduccion' if self.input_id else False
        if is_deduction and result_amt > 0:
            result_amt = -result_amt
            formula += " x (-1)"

        steps.append(f"{step}. TOTAL: ${result_amt:,.0f}")

        # Construir nombre
        indicator = '1Q' if date_to.day <= 15 else '2Q'
        rule_name = self.input_id.name if self.input_id else tipo_nombre
        name = f"{rule_name} - {indicator} {date_to.month}/{date_to.year}"

        # Generar HTML
        detail_html = self._build_concept_html_log(
            periodo=f"{indicator} {date_to.month}/{date_to.year}",
            aplicado=True,
            descripcion=f"Calculo de {tipo_nombre} - {self.name or rule_name}",
            rango_log=[
                ('Tipo', tipo_nombre),
                ('Monto base', f"${base_amt:,.0f}"),
                ('Modalidad', modal),
                ('Comportamiento', behavior),
                ('Entidad', self.partner_id.name if self.partner_id else 'N/A'),
            ],
            pasos=steps,
            monto_final=result_amt,
            formula=formula
        )

        # Actualizar estado
        self.write({
            'payslip_ids': [(4, payslip.id)]
        })

        _logger.info(f"[NOVEDAD] {self.name} - Tipo: {tipo_nombre} - Retornando: amount={result_amt}")

        return {
            'create_line': True,
            'values': {
                'name': name,
                'code': self.input_id.code if self.input_id else 'NOVEDAD',
                'amount': result_amt,
                'quantity': 1,
                'rate': 100,
                'concept_id': self.id,
            },
            'skip_info': {},
            'formula': formula,
            'detail_html': detail_html,
            'novedad_data': {
                'tipo': self.type_deduction,
                'tipo_nombre': tipo_nombre,
                'monto_base': base_amt,
                'modalidad': self.modality_value,
                'comportamiento': self.monthly_behavior,
                'entidad': self.partner_id.name if self.partner_id else None,
                'es_deduccion': is_deduction,
            }
        }

    # =========================================================================
    # METODO UNIFICADO - Selecciona el metodo correcto segun type_deduction
    # =========================================================================

    def get_concept_for_payslip(self, payslip, date_from, date_to, localdict):
        """
        Metodo unificado que selecciona el calculo correcto segun el tipo de deduccion.

        NOTA: Los embargos (type_deduction='E') se calculan desde reglas salariales
        usando los metodos _embargo001() a _embargo005() y _calculate_embargo_generic().
        Este metodo solo maneja prestamos y novedades directas.

        Args:
            payslip: Objeto hr.payslip
            date_from: Fecha inicio del periodo
            date_to: Fecha fin del periodo
            localdict: Diccionario con datos de nomina

        Returns:
            dict: Estructura con create_line, values, skip_info, formula, detail_html
        """
        self.ensure_one()

        # Seleccionar metodo segun tipo
        if self.type_deduction == 'E':
            # Embargo - NO se calcula aqui, se llama desde regla salarial
            # Los metodos _embargo001() a _embargo005() retornan tuple
            _logger.warning(f"[CONCEPT] Embargo {self.id} debe llamarse desde regla salarial, no desde get_concept_for_payslip")
            return self._no_apply(
                'Los embargos se calculan desde reglas salariales',
                f"{date_from} - {date_to}"
            )
        elif self.type_deduction == 'P':
            # Prestamo empresa
            return self.get_prestamo_for_payslip(payslip, date_from, date_to, localdict)
        else:
            # Otros tipos: Ahorro, Seguro, Libranza, Retencion, Otros
            return self.get_novedad_for_payslip(payslip, date_from, date_to, localdict)
