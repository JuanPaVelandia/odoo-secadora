# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class HrAnnualParametersCopyWizard(models.TransientModel):
    """
    Wizard para copiar parámetros del año anterior y actualizar valores clave.
    Similar al patrón de configuración de POS.
    """
    _name = 'hr.annual.parameters.copy.wizard'
    _description = 'Copiar Parámetros Anuales'

    # Año origen y destino
    source_year = fields.Integer(
        string='Año Origen',
        required=True,
        default=lambda self: fields.Date.today().year - 1
    )
    target_year = fields.Integer(
        string='Año Destino',
        required=True,
        default=lambda self: fields.Date.today().year
    )

    source_parameters_id = fields.Many2one(
        'hr.annual.parameters',
        string='Parámetros Origen',
        compute='_compute_source_parameters',
        store=True
    )

    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company
    )

    # Valores actuales (del año origen)
    current_smmlv = fields.Float(
        string='SMMLV Actual',
        compute='_compute_current_values',
        store=True
    )
    current_uvt = fields.Float(
        string='UVT Actual',
        compute='_compute_current_values',
        store=True
    )
    current_aux_transporte = fields.Float(
        string='Aux. Transporte Actual',
        compute='_compute_current_values',
        store=True
    )

    # Nuevos valores
    new_smmlv = fields.Float(
        string='Nuevo SMMLV',
        required=True,
        help='Salario Mínimo Mensual Legal Vigente para el nuevo año'
    )
    new_uvt = fields.Float(
        string='Nuevo UVT',
        required=True,
        help='Unidad de Valor Tributario para el nuevo año'
    )
    new_aux_transporte = fields.Float(
        string='Nuevo Aux. Transporte',
        required=True,
        help='Auxilio de Transporte mensual para el nuevo año'
    )

    # Incrementos calculados
    increment_smmlv = fields.Float(
        string='Incremento SMMLV (%)',
        compute='_compute_increments',
        store=True
    )
    increment_uvt = fields.Float(
        string='Incremento UVT (%)',
        compute='_compute_increments',
        store=True
    )
    ipc_increment = fields.Float(
        string='IPC (%)',
        help='Índice de Precios al Consumidor - Se usará para ajustar topes y valores'
    )

    # Opciones de copia
    copy_social_security = fields.Boolean(
        string='Copiar config. Seguridad Social',
        default=True
    )
    copy_provisions = fields.Boolean(
        string='Copiar config. Provisiones',
        default=True
    )
    copy_working_hours = fields.Boolean(
        string='Copiar config. Horas Laborales',
        default=True
    )
    copy_options = fields.Boolean(
        string='Copiar opciones de nómina',
        default=True
    )

    # Estado
    state = fields.Selection([
        ('draft', 'Configurar'),
        ('preview', 'Vista Previa'),
        ('done', 'Completado')
    ], default='draft', string='Estado')

    @api.depends('source_year', 'company_id')
    def _compute_source_parameters(self):
        for wizard in self:
            wizard.source_parameters_id = self.env['hr.annual.parameters'].get_for_year(
                wizard.source_year,
                company_id=wizard.company_id.id,
                raise_if_not_found=False,
            )

    @api.depends('source_parameters_id')
    def _compute_current_values(self):
        for wizard in self:
            if wizard.source_parameters_id:
                wizard.current_smmlv = wizard.source_parameters_id.smmlv_monthly
                wizard.current_uvt = wizard.source_parameters_id.value_uvt
                wizard.current_aux_transporte = wizard.source_parameters_id.transportation_assistance_monthly
            else:
                wizard.current_smmlv = 0
                wizard.current_uvt = 0
                wizard.current_aux_transporte = 0

    @api.depends('current_smmlv', 'new_smmlv', 'current_uvt', 'new_uvt')
    def _compute_increments(self):
        for wizard in self:
            if wizard.current_smmlv and wizard.new_smmlv:
                wizard.increment_smmlv = ((wizard.new_smmlv / wizard.current_smmlv) - 1) * 100
            else:
                wizard.increment_smmlv = 0

            if wizard.current_uvt and wizard.new_uvt:
                wizard.increment_uvt = ((wizard.new_uvt / wizard.current_uvt) - 1) * 100
            else:
                wizard.increment_uvt = 0

    @api.onchange('source_year')
    def _onchange_source_year(self):
        """Actualiza el año destino cuando cambia el origen"""
        if self.source_year:
            self.target_year = self.source_year + 1

    @api.onchange('source_parameters_id')
    def _onchange_source_parameters(self):
        """Pre-llena los nuevos valores con los actuales"""
        if self.source_parameters_id:
            self.new_smmlv = self.source_parameters_id.smmlv_monthly
            self.new_uvt = self.source_parameters_id.value_uvt
            self.new_aux_transporte = self.source_parameters_id.transportation_assistance_monthly

    def action_preview(self):
        """Muestra vista previa de los cambios"""
        self.ensure_one()

        if not self.source_parameters_id:
            raise UserError(_('No se encontraron parámetros para el año %s en la compañía %s') % (
                self.source_year, self.company_id.name))

        # Verificar si ya existe para el año destino
        existing = self.env['hr.annual.parameters'].get_for_year(
            self.target_year,
            company_id=self.company_id.id,
            raise_if_not_found=False,
        )

        if existing:
            raise UserError(_('Ya existen parámetros para el año %s. Edítelos directamente.') % self.target_year)

        self.state = 'preview'
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_back(self):
        """Volver al paso anterior"""
        self.state = 'draft'
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_copy_parameters(self):
        """Copia los parámetros al nuevo año"""
        self.ensure_one()

        if not self.source_parameters_id:
            raise UserError(_('No hay parámetros origen para copiar'))

        source = self.source_parameters_id

        # Preparar valores base
        vals = {
            'year': self.target_year,
            'company_ids': [(6, 0, [self.company_id.id])],
            # Valores actualizados
            'smmlv_monthly': self.new_smmlv,
            'value_uvt': self.new_uvt,
            'transportation_assistance_monthly': self.new_aux_transporte,
            # Incrementos
            'value_porc_increment_smlv': self.increment_smmlv,
            'value_porc_ipc': self.ipc_increment or self.increment_uvt,
        }

        # Copiar porcentajes de salario integral
        vals['porc_integral_salary'] = source.porc_integral_salary

        # Copiar configuración de seguridad social
        if self.copy_social_security:
            vals.update({
                'value_porc_health_company': source.value_porc_health_company,
                'value_porc_health_employee': source.value_porc_health_employee,
                'value_porc_health_employee_foreign': source.value_porc_health_employee_foreign,
                'value_porc_pension_company': source.value_porc_pension_company,
                'value_porc_pension_employee': source.value_porc_pension_employee,
                'value_porc_compensation_box_company': source.value_porc_compensation_box_company,
                'value_porc_sena_company': source.value_porc_sena_company,
                'value_porc_icbf_company': source.value_porc_icbf_company,
            })

        # Copiar configuración de provisiones
        if self.copy_provisions:
            vals.update({
                'value_porc_provision_bonus': source.value_porc_provision_bonus,
                'value_porc_provision_cesantias': source.value_porc_provision_cesantias,
                'value_porc_provision_intcesantias': source.value_porc_provision_intcesantias,
                'value_porc_provision_vacation': source.value_porc_provision_vacation,
                'simple_provisions': source.simple_provisions,
                'severance_pay_calculation': source.severance_pay_calculation,
            })

        # Copiar configuración de horas
        if self.copy_working_hours:
            vals.update({
                'hours_daily': source.hours_daily,
                'hours_weekly': source.hours_weekly,
                'hours_fortnightly': source.hours_fortnightly,
                'hours_monthly': source.hours_monthly,
            })

        # Copiar opciones de nómina
        if self.copy_options:
            vals.update({
                'rtf_projection': source.rtf_projection,
                'ded_round': source.ded_round,
                'rtf_round': source.rtf_round,
                'aux_apr_lectiva': source.aux_apr_lectiva,
                'aux_apr_prod': source.aux_apr_prod,
                'fragment_vac': source.fragment_vac,
                'prv_vac_cpt': source.prv_vac_cpt,
                'aux_prst': source.aux_prst,
                'aus_prev': source.aus_prev,
                'positive_net': source.positive_net,
                'nonprofit': source.nonprofit,
                'prst_wo_susp': source.prst_wo_susp,
                'accounting_method': source.accounting_method,
                'default_accounting_date': source.default_accounting_date,
                'overtime_calculation_method': source.overtime_calculation_method,
                'complete_february_to_30': source.complete_february_to_30,
                'month_change_policy': source.month_change_policy,
                'apply_day_31': source.apply_day_31,
                'store_payroll_history': source.store_payroll_history,
                'ibc_history_months': source.ibc_history_months,
                'weight_contribution_calculations': source.weight_contribution_calculations,
            })

        # Copiar valores tributarios (tope retención)
        vals['value_top_source_retention'] = source.value_top_source_retention

        # Copiar ley 1395
        vals['value_porc_statute_1395'] = source.value_porc_statute_1395

        # Crear nuevo registro
        new_params = self.env['hr.annual.parameters'].create(vals)

        # Copiar horas laborales si aplica
        if self.copy_working_hours and source.working_hours_ids:
            for wh in source.working_hours_ids:
                self.env['hr.company.working.hours'].create({
                    'company_id': self.company_id.id,
                    'year': self.target_year,
                    'month': wh.month,
                    'max_hours_per_week': wh.max_hours_per_week,
                    'hours_to_pay': wh.hours_to_pay,
                    'effective_date': wh.effective_date.replace(year=self.target_year),
                    'notes': wh.notes,
                    'annual_parameter_id': new_params.id,
                    'lunch_duration_hours': wh.lunch_duration_hours,
                    'lunch_start_time': wh.lunch_start_time,
                    'works_saturday': wh.works_saturday,
                    'work_start_time': wh.work_start_time,
                })

        self.state = 'done'

        # Abrir el nuevo registro
        return {
            'type': 'ir.actions.act_window',
            'name': _('Parámetros %s') % self.target_year,
            'res_model': 'hr.annual.parameters',
            'res_id': new_params.id,
            'view_mode': 'form',
            'target': 'current',
        }
