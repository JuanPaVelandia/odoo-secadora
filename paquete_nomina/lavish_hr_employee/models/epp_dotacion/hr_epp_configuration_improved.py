# -*- coding: utf-8 -*-
"""
MEJORAS AL SISTEMA EPP/DOTACIÓN/EXÁMENES MÉDICOS

Cambios principales:
1. Separación clara de 3 tipos de configuración
2. Integración con ciclos de nómina
3. Creación desde plantillas (individual o masivo)
4. Vencimientos y recordatorios automatizados
5. Control de proveedores y acuerdos
"""

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from dateutil.relativedelta import relativedelta
from datetime import date, timedelta

class HrEppConfiguration(models.Model):
    """
    Configuración mejorada para EPP/Dotación/Exámenes

    MEJORAS:
    - Tipo más específico con validaciones
    - Integración con ciclos de nómina
    - Plantillas reutilizables
    - Control de vencimientos
    - Acuerdos con proveedores
    """
    _inherit = 'hr.epp.configuration'

    # ========================================================================
    # MEJORA 1: TIPO MÁS ESPECÍFICO
    # ========================================================================

    config_subtype = fields.Selection([
        ('basic_epp', 'EPP Básico'),
        ('specialized_epp', 'EPP Especializado'),
        ('office_clothing', 'Dotación Oficina'),
        ('industrial_clothing', 'Dotación Industrial'),
        ('medical_ingress', 'Examen de Ingreso'),
        ('medical_periodic', 'Examen Periódico'),
        ('medical_retirement', 'Examen de Retiro'),
        ('medical_special', 'Examen Especial'),
    ], string='Subtipo Específico',
       help='Clasificación detallada para control y reportes')

    # ========================================================================
    # MEJORA 2: INTEGRACIÓN CON NÓMINA
    # ========================================================================

    sync_with_payroll = fields.Boolean(
        'Sincronizar con Ciclos de Nómina',
        default=False,
        help='Genera automáticamente según los periodos de nómina'
    )

    payroll_period_type = fields.Selection([
        ('monthly', 'Mensual'),
        ('biweekly', 'Quincenal'),
    ], string='Tipo de Periodo',
       help='Tipo de periodo de nómina para sincronización')

    generate_on_period = fields.Selection([
        ('first', 'Primera Quincena/Principio de Mes'),
        ('second', 'Segunda Quincena/Fin de Mes'),
        ('both', 'Ambos Periodos'),
    ], string='Generar en Periodo',
       default='first',
       help='En qué periodo del ciclo de nómina generar')

    payroll_month_day = fields.Integer(
        'Día del Mes',
        default=1,
        help='Día específico del mes para generar (1-28)'
    )

    # ========================================================================
    # MEJORA 3: PLANTILLAS Y CREACIÓN RÁPIDA
    # ========================================================================

    is_template = fields.Boolean(
        'Es Plantilla',
        default=False,
        help='Marcar como plantilla reutilizable'
    )

    template_id = fields.Many2one(
        'hr.epp.configuration',
        string='Basado en Plantilla',
        domain=[('is_template', '=', True)],
        help='Plantilla base para copiar configuración'
    )

    quick_create_mode = fields.Selection([
        ('single', 'Solicitud Individual'),
        ('batch', 'Lote Masivo'),
    ], string='Modo de Creación',
       default='batch',
       help='Cómo se generan las solicitudes desde esta config')

    # ========================================================================
    # MEJORA 4: VENCIMIENTOS Y RECORDATORIOS
    # ========================================================================

    has_expiry = fields.Boolean(
        'Tiene Vencimiento',
        compute='_compute_has_expiry',
        store=True,
        help='EPP/Dotación no vence, Exámenes sí'
    )

    validity_months = fields.Integer(
        'Vigencia (meses)',
        default=12,
        help='Meses de vigencia para exámenes médicos'
    )

    alert_before_days = fields.Integer(
        'Alertar con Días de Anticipación',
        default=30,
        help='Días antes del vencimiento para alertar'
    )

    alert_responsible_ids = fields.Many2many(
        'res.users',
        'hr_epp_config_alert_users_rel',
        'config_id',
        'user_id',
        string='Responsables de Alertas',
        help='Usuarios que recibirán alertas de vencimiento'
    )

    auto_renew = fields.Boolean(
        'Renovación Automática',
        default=False,
        help='Crear automáticamente nueva solicitud antes del vencimiento'
    )

    # ========================================================================
    # MEJORA 5: PROVEEDORES Y ACUERDOS
    # ========================================================================

    # Campo corregido: partner_id en lugar de proveedor_id
    default_provider_id = fields.Many2one(
        'res.partner',
        string='Proveedor Principal',
        domain=[('supplier_rank', '>', 0)],
        help='Proveedor predeterminado para esta configuración'
    )

    provider_agreement_ids = fields.One2many(
        'hr.epp.provider.agreement',
        'configuration_id',
        string='Acuerdos con Proveedores'
    )

    has_active_agreement = fields.Boolean(
        'Tiene Acuerdo Vigente',
        compute='_compute_has_active_agreement',
        store=True
    )

    current_agreement_id = fields.Many2one(
        'hr.epp.provider.agreement',
        string='Acuerdo Actual',
        compute='_compute_current_agreement',
        store=True
    )

    # ========================================================================
    # MEJORA 6: CONTROL POR TIPO
    # ========================================================================

    requires_medical_approval = fields.Boolean(
        'Requiere Aprobación Médica',
        compute='_compute_type_requirements',
        store=True
    )

    requires_stock_control = fields.Boolean(
        'Requiere Control de Stock',
        compute='_compute_type_requirements',
        store=True
    )

    requires_signature = fields.Boolean(
        'Requiere Firma',
        default=True
    )

    # ========================================================================
    # COMPUTES
    # ========================================================================

    @api.depends('type')
    def _compute_has_expiry(self):
        """Solo exámenes médicos tienen vencimiento"""
        for record in self:
            record.has_expiry = record.type not in ('epp', 'dotacion')

    @api.depends('type', 'config_subtype')
    def _compute_type_requirements(self):
        """Requisitos según tipo"""
        for record in self:
            # EPP especializado requiere aprobación médica
            record.requires_medical_approval = record.config_subtype in [
                'specialized_epp',
                'medical_ingress',
                'medical_periodic',
                'medical_retirement',
                'medical_special'
            ]

            # Solo EPP y Dotación requieren control de stock
            record.requires_stock_control = record.type in ('epp', 'dotacion')

    @api.depends('provider_agreement_ids.state', 'provider_agreement_ids.date_end')
    def _compute_has_active_agreement(self):
        """Verifica si hay acuerdo vigente"""
        today = fields.Date.today()
        for record in self:
            active_agreements = record.provider_agreement_ids.filtered(
                lambda a: a.state == 'active' and
                         (not a.date_end or a.date_end >= today)
            )
            record.has_active_agreement = bool(active_agreements)

    @api.depends('provider_agreement_ids.state', 'provider_agreement_ids.date_end')
    def _compute_current_agreement(self):
        """Obtiene el acuerdo actual vigente"""
        today = fields.Date.today()
        for record in self:
            active = record.provider_agreement_ids.filtered(
                lambda a: a.state == 'active' and
                         (not a.date_end or a.date_end >= today)
            ).sorted('date_start', reverse=True)
            record.current_agreement_id = active[0] if active else False

    # ========================================================================
    # MÉTODOS MEJORADOS
    # ========================================================================

    @api.model
    def cron_generate_epp_requests_improved(self):
        """
        Cron mejorado para generar solicitudes

        MEJORAS:
        - Sincronización con ciclos de nómina
        - Respeta configuración de periodo
        - Control por tipo
        """
        today = fields.Date.today()

        configs = self.search([
            ('generate_automatically', '=', True),
            ('active', '=', True)
        ])

        for config in configs:
            should_generate = False

            if config.sync_with_payroll:
                # Generar según ciclo de nómina
                should_generate = self._check_payroll_cycle(config, today)
            else:
                # Generación tradicional por frecuencia
                if not config.last_generation_date:
                    should_generate = True
                else:
                    next_date = config.last_generation_date + relativedelta(
                        months=config.frequency
                    )
                    should_generate = today >= next_date

            if should_generate:
                self._generate_from_config(config)

    def _check_payroll_cycle(self, config, today):
        """Verifica si debe generar según ciclo de nómina"""
        if not config.payroll_period_type:
            return False

        if config.payroll_period_type == 'monthly':
            # Mensual: verificar día del mes
            if config.generate_on_period == 'first':
                return today.day == config.payroll_month_day
            elif config.generate_on_period == 'second':
                # Último día del mes
                last_day = (today.replace(day=1) + relativedelta(months=1) - timedelta(days=1)).day
                return today.day == last_day
            else:  # both
                return today.day == config.payroll_month_day or today.day == 15

        elif config.payroll_period_type == 'biweekly':
            # Quincenal: día 15 y último día
            if config.generate_on_period == 'first':
                return today.day == 1
            elif config.generate_on_period == 'second':
                return today.day == 15
            else:  # both
                last_day = (today.replace(day=1) + relativedelta(months=1) - timedelta(days=1)).day
                return today.day in (15, last_day)

        return False

    def _generate_from_config(self, config):
        """Genera solicitudes desde configuración"""
        # Filtrar empleados
        domain = [('company_id', '=', config.company_id.id)]
        if config.department_ids:
            domain.append(('department_id', 'in', config.department_ids.ids))
        if config.job_ids:
            domain.append(('job_id', 'in', config.job_ids.ids))

        employees = self.env['hr.employee'].search(domain)

        if config.quick_create_mode == 'single':
            # Crear solicitudes individuales
            for employee in employees:
                self._create_individual_request(config, employee)
        else:
            # Crear lote masivo
            self._create_batch_request(config, employees)

        config.last_generation_date = fields.Date.today()

    def _create_individual_request(self, config, employee):
        """Crea solicitud individual"""
        request = self.env['hr.epp.request'].create({
            'employee_id': employee.id,
            'type': config.type,
            'configuration_id': config.id,
            'state': 'draft',
        })

        # Agregar líneas del kit
        for line in config.kit_line_ids:
            size = self._get_employee_size(employee, line.item_type)
            self.env['hr.epp.request.line'].create({
                'request_id': request.id,
                'item_type': line.item_type,
                'product_id': line.product_id.id if line.product_id else False,
                'name': line.name,
                'quantity': line.quantity,
                'size': size,
            })

        return request

    def _create_batch_request(self, config, employees):
        """Crea lote masivo"""
        batch = self.env['hr.epp.batch'].create({
            'batch_type': config.type,
            'company_id': config.company_id.id,
            'use_stock_location': config.use_stock_location,
            'default_location_id': config.location_id.id if config.location_id else False,
        })

        for employee in employees:
            self._create_individual_request(config, employee)

        return batch

    def _get_employee_size(self, employee, item_type):
        """Obtiene talla del empleado"""
        if item_type == 'shirt':
            return employee.shirt_size or 'M'
        elif item_type == 'pants':
            return employee.pants_size or '32'
        elif item_type in ('shoes', 'boots'):
            return employee.shoe_size or '40'
        return False

    # ========================================================================
    # ACCIONES
    # ========================================================================

    def action_create_from_template(self):
        """Crear nueva configuración desde plantilla"""
        self.ensure_one()

        if not self.is_template:
            raise UserError(_('Esta configuración no es una plantilla'))

        # Copiar configuración
        new_config = self.copy({
            'name': _('%s (Copia)') % self.name,
            'is_template': False,
            'template_id': self.id,
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'hr.epp.configuration',
            'res_id': new_config.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_create_quick_request(self):
        """Crear solicitud rápida (individual)"""
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': _('Crear Solicitud Individual'),
            'res_model': 'wizard.epp.quick.create',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_configuration_id': self.id,
                'default_type': self.type,
            }
        }

    def action_create_batch(self):
        """Crear lote masivo"""
        self.ensure_one()

        batch = self.env['hr.epp.batch'].create({
            'batch_type': self.type,
            'company_id': self.company_id.id,
            'use_stock_location': self.use_stock_location,
            'default_location_id': self.location_id.id if self.location_id else False,
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'hr.epp.batch',
            'res_id': batch.id,
            'view_mode': 'form',
            'target': 'current',
        }


class HrEppProviderAgreement(models.Model):
    """
    NUEVO MODELO: Acuerdos con Proveedores

    Controla acuerdos comerciales con proveedores de EPP/Dotación/Exámenes
    """
    _name = 'hr.epp.provider.agreement'
    _description = 'Acuerdo con Proveedor'
    _order = 'date_start desc'

    name = fields.Char('Referencia', required=True, default='Nuevo')

    configuration_id = fields.Many2one(
        'hr.epp.configuration',
        string='Configuración',
        required=True,
        ondelete='cascade'
    )

    provider_id = fields.Many2one(
        'res.partner',
        string='Proveedor',
        required=True,
        domain=[('supplier_rank', '>', 0)]
    )

    date_start = fields.Date('Fecha Inicio', required=True, default=fields.Date.today)
    date_end = fields.Date('Fecha Fin')

    state = fields.Selection([
        ('draft', 'Borrador'),
        ('active', 'Activo'),
        ('expired', 'Vencido'),
        ('cancelled', 'Cancelado'),
    ], string='Estado', default='draft', required=True)

    # Términos del acuerdo
    discount_percentage = fields.Float('% Descuento', digits=(5, 2))
    fixed_price = fields.Monetary('Precio Fijo', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)

    payment_terms_id = fields.Many2one('account.payment.term', string='Términos de Pago')
    delivery_days = fields.Integer('Días de Entrega', default=7)

    minimum_quantity = fields.Integer('Cantidad Mínima')
    maximum_quantity = fields.Integer('Cantidad Máxima')

    notes = fields.Text('Observaciones')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'hr.epp.provider.agreement'
                ) or 'AGR/001'
        return super().create(vals_list)

    def action_activate(self):
        """Activar acuerdo"""
        self.write({'state': 'active'})

    def action_cancel(self):
        """Cancelar acuerdo"""
        self.write({'state': 'cancelled'})
