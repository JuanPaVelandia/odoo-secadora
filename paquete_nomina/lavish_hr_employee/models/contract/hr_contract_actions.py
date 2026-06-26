# -*- coding: utf-8 -*-

import base64
import logging
import zipfile
import io
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class ContractActions(models.Model):
    """Modelo maestro para gestionar acciones de contrato"""
    _name = 'contract.actions'
    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin']
    _description = "Acciones de Contrato"
    _order = "date_application desc, id desc"
    _check_company_auto = True

    # ================================================================
    # CAMPOS BÁSICOS
    # ================================================================
    name = fields.Char(
        string='Referencia', 
        required=True, 
        copy=False, 
        readonly=True, 
        default='Nuevo',
        tracking=True
    )
    
    action_type = fields.Selection([
        ('salary_modification', 'Modificación Salarial'),
        ('contract_extension', 'Prórroga de Contrato'),
        ('pre_notice', 'Preaviso de Terminación'),
    ], string='Tipo de Acción', required=True, tracking=True)
    
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('in_progress', 'En Proceso'),
        ('done', 'Completado'),
        ('cancelled', 'Cancelado')
    ], string='Estado', default='draft', tracking=True, copy=False)
    
    company_id = fields.Many2one(
        'res.company', 
        string="Compañía", 
        default=lambda self: self.env.company,
        required=True
    )
    
    date_application = fields.Date(
        string="Fecha de Aplicación", 
        required=True, 
        default=fields.Date.today,
        tracking=True
    )

    # ================================================================
    # CONFIGURACIONES ESPECÍFICAS POR TIPO
    # ================================================================
    
    # Para modificaciones salariales
    salary_increase_type = fields.Selection([
        ('percentage', 'Porcentaje'),
        ('fixed_amount', 'Monto Fijo'),
        ('individual', 'Individual')
    ], string='Tipo de Aumento')
    
    salary_percentage = fields.Float(string='Porcentaje (%)', digits=(5, 2))
    salary_fixed_amount = fields.Float(string='Monto Fijo', digits=(16, 2))
    
    # Para prórrogas
    extension_months = fields.Integer(string='Meses de Prórroga', default=12)
    extension_days = fields.Integer(string='Días Adicionales', default=0)

    # Para preaviso
    notice_days = fields.Integer(string='Días de Preaviso', default=15)

    # ================================================================
    # FILTROS PARA CARGA MASIVA
    # ================================================================
    department_ids = fields.Many2many(
        'hr.department',
        'contract_actions_hr_department_rel',
        'contract_actions_id', 'hr_department_id',
        string='Departamentos',
        help="Filtro por departamentos para carga masiva"
    )

    job_ids = fields.Many2many('hr.job', 'contract_actions_hr_job_rel',
                               'contract_actions_id', 'hr_job_id',
                               string='Cargos')
    
    contract_type_filter = fields.Selection([
        ('obra', 'Obra o Labor'),
        ('fijo', 'Término Fijo'),
        ('indefinido', 'Indefinido'),
        ('aprendizaje', 'Aprendizaje'),
        ('temporal', 'Temporal')
    ], string='Filtro por Tipo')

    # ================================================================
    # CAMPOS PARA AGREGAR CONTRATOS MANUALMENTE
    # ================================================================
    additional_contract_ids = fields.Many2many(
        'hr.contract',
        'contract_actions_additional_rel',
        'contract_actions_id', 'hr_contract_id',
        string='Contratos Adicionales',
        domain=[('state', '=', 'open')]
    )

    additional_employee_ids = fields.Many2many(
        'hr.employee',
        'contract_actions_employee_rel',
        'contract_actions_id', 'hr_employee_id',
        string='Empleados Adicionales'
    )

    # ================================================================
    # LÍNEAS Y ESTADÍSTICAS
    # ================================================================
    action_lines = fields.One2many(
        'contract.actions.line', 
        'action_id', 
        string='Líneas de Acción'
    )
    
    total_contracts = fields.Integer(
        string='Total', 
        compute='_compute_totals', 
        store=True
    )
    
    processed_contracts = fields.Integer(
        string='Procesados', 
        compute='_compute_totals', 
        store=True
    )
    
    failed_contracts = fields.Integer(
        string='Fallidos', 
        compute='_compute_totals', 
        store=True
    )

    # ================================================================
    # CAMPOS ADICIONALES
    # ================================================================
    description = fields.Text(string='Descripción')
    attachment_ids = fields.Many2many('ir.attachment', 'contract_actions_ir_attachment_rel',
                                      'contract_actions_id', 'ir_attachment_id',
                                      string='Adjuntos')

    # ================================================================
    # COMPUTE METHODS
    # ================================================================
    @api.depends('action_lines.state')
    def _compute_totals(self):
        for record in self:
            lines = record.action_lines
            record.total_contracts = len(lines)
            record.processed_contracts = len(lines.filtered(lambda x: x.state == 'done'))
            record.failed_contracts = len(lines.filtered(lambda x: x.state == 'failed'))

    # ================================================================
    # CRUD OVERRIDES
    # ================================================================
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                sequence = self.env['ir.sequence'].next_by_code('contract.actions') or 'Nuevo'
                vals['name'] = sequence
        return super().create(vals_list)

    def write(self, vals):
        if 'state' in vals and vals['state'] in ['done', 'cancelled']:
            for record in self:
                if record.action_lines.filtered(lambda l: l.state == 'draft'):
                    raise UserError(_("No se puede cambiar el estado mientras hay líneas sin procesar"))
        return super().write(vals)

    # ================================================================
    # BUSINESS METHODS
    # ================================================================
    def action_load_contracts(self):
        """Cargar contratos según filtros"""
        self.ensure_one()
        
        if self.state != 'draft':
            raise UserError(_("Solo se pueden cargar contratos en estado borrador"))
        
        domain = self._build_contract_domain()
        contracts = self.env['hr.contract'].search(domain)
        
        if not contracts:
            raise UserError(_("No se encontraron contratos con los filtros aplicados"))
        
        # Limpiar líneas existentes
        self.action_lines.unlink()
        
        # Crear nuevas líneas
        lines_vals = []
        for contract in contracts:
            lines_vals.append(self._prepare_action_line_vals(contract))
        
        self.env['contract.actions.line'].create(lines_vals)
        
        return self._show_notification(
            _('Contratos Cargados'),
            _('Se cargaron {} contratos exitosamente').format(len(contracts)),
            'success'
        )

    def action_add_additional_contracts(self):
        """Agregar contratos adicionales"""
        self.ensure_one()
        
        if not self.additional_contract_ids:
            raise UserError(_("Debe seleccionar al menos un contrato"))
        
        existing_contracts = self.action_lines.mapped('contract_id')
        new_contracts = self.additional_contract_ids.filtered(lambda c: c not in existing_contracts)
        
        if not new_contracts:
            raise UserError(_("Todos los contratos ya están incluidos"))
        
        # Crear líneas para contratos nuevos
        lines_vals = []
        for contract in new_contracts:
            lines_vals.append(self._prepare_action_line_vals(contract))
        
        self.env['contract.actions.line'].create(lines_vals)
        self.additional_contract_ids = False
        
        return self._show_notification(
            _('Contratos Agregados'),
            _('Se agregaron {} contratos').format(len(new_contracts)),
            'success'
        )

    def action_add_additional_employees(self):
        """Agregar empleados (sus contratos activos)"""
        self.ensure_one()
        
        if not self.additional_employee_ids:
            raise UserError(_("Debe seleccionar al menos un empleado"))
        
        contracts_added = 0
        employees_without_contract = []
        
        for employee in self.additional_employee_ids:
            contract = self.env['hr.contract'].search([
                ('employee_id', '=', employee.id),
                ('state', '=', 'open')
            ], limit=1)
            
            if contract and contract not in self.action_lines.mapped('contract_id'):
                vals = self._prepare_action_line_vals(contract)
                self.env['contract.actions.line'].create(vals)
                contracts_added += 1
            elif not contract:
                employees_without_contract.append(employee.name)
        
        self.additional_employee_ids = False
        
        message = _('Se agregaron {} contratos').format(contracts_added)
        if employees_without_contract:
            message += _('. Empleados sin contrato: {}').format(', '.join(employees_without_contract))
        
        return self._show_notification(_('Empleados Procesados'), message, 'success')

    def action_clear_lines(self):
        """Limpiar todas las líneas"""
        self.ensure_one()
        
        if self.state != 'draft':
            raise UserError(_("Solo se pueden limpiar líneas en borrador"))
        
        lines_count = len(self.action_lines)
        self.action_lines.unlink()
        
        return self._show_notification(
            _('Líneas Limpiadas'),
            _('Se eliminaron {} líneas').format(lines_count),
            'success'
        )

    def action_process_all(self):
        """Procesar todas las líneas"""
        self.ensure_one()
        
        if self.state != 'draft':
            raise UserError(_("Solo se pueden procesar acciones en borrador"))
        
        draft_lines = self.action_lines.filtered(lambda l: l.state == 'draft')
        if not draft_lines:
            raise UserError(_("No hay líneas para procesar"))
        
        self.state = 'in_progress'
        
        success_count = 0
        error_count = 0
        
        for line in draft_lines:
            try:
                line.action_execute()
                success_count += 1
            except Exception as e:
                line.write({
                    'state': 'failed',
                    'error_message': str(e),
                    'processing_date': fields.Datetime.now()
                })
                error_count += 1
        
        # Actualizar estado final
        if all(line.state in ['done', 'failed'] for line in self.action_lines):
            self.state = 'done'
        
        message = _('Procesadas {} líneas exitosamente').format(success_count)
        if error_count:
            message += _(', {} con errores').format(error_count)
        
        return self._show_notification(
            _('Procesamiento Completado'),
            message,
            'warning' if error_count else 'success'
        )

    def action_select_all(self):
        """Seleccionar todas las líneas"""
        self.ensure_one()
        self.action_lines.write({'selected_for_processing': True})
        return self._show_notification(_('Líneas Seleccionadas'), _('Todas las líneas seleccionadas'), 'success')

    def action_deselect_all(self):
        """Deseleccionar todas las líneas"""
        self.ensure_one()
        self.action_lines.write({'selected_for_processing': False})
        return self._show_notification(_('Líneas Deseleccionadas'), _('Todas las líneas deseleccionadas'), 'info')

    def action_print_reports(self):
        """Imprimir reportes - comprimir si son múltiples"""
        self.ensure_one()
        
        done_lines = self.action_lines.filtered(lambda l: l.state == 'done')
        if not done_lines:
            raise UserError(_("No hay líneas procesadas para imprimir"))
        
        # Mapeo de reportes por tipo
        report_mapping = {
            'salary_modification': 'lavish_hr_payroll.report_hr_contract_salary_increase',
            'pre_notice': 'lavish_hr_payroll.report_hr_contract_preaviso',
            'contract_extension': 'lavish_hr_payroll.report_contract_extension'
        }
        
        report_ref = report_mapping.get(self.action_type)
        if not report_ref:
            raise UserError(_("No hay reporte disponible para este tipo de acción"))
        
        # Obtener registros para imprimir
        records = self._get_print_records(done_lines)
        
        if len(records) == 1:
            # Un solo reporte - sin comprimir
            return self.env.ref(report_ref).report_action(records)
        else:
            # Múltiples reportes - comprimir en ZIP
            return self._generate_compressed_reports(records, report_ref)

    # ================================================================
    # HELPER METHODS
    # ================================================================
    def _build_contract_domain(self):
        """Construir dominio para búsqueda de contratos"""
        domain = [
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'open')
        ]
        
        if self.department_ids:
            domain.append(('department_id', 'in', self.department_ids.ids))
        if self.job_ids:
            domain.append(('job_id', 'in', self.job_ids.ids))
        if self.contract_type_filter:
            domain.append(('contract_type', '=', self.contract_type_filter))
        
        # Filtros específicos por tipo
        if self.action_type == 'contract_extension':
            domain.extend([
                ('contract_type', 'in', ['fijo', 'aprendizaje']),
                ('date_end', '!=', False)
            ])
        elif self.action_type == 'pre_notice':
            date_limit = fields.Date.today() + timedelta(days=60)
            domain.extend([
                ('date_end', '<=', date_limit),
                ('date_end', '!=', False)
            ])
        
        return domain

    def _prepare_action_line_vals(self, contract):
        """Preparar valores para línea de acción"""
        vals = {
            'action_id': self.id,
            'contract_id': contract.id,
            'current_wage': contract.wage,
            'new_wage': self._calculate_new_wage(contract),
            'current_job_id': contract.job_id.id if contract.job_id else False,
            'new_job_id': contract.job_id.id if contract.job_id else False,
        }
        
        # Configuración específica por tipo
        if self.action_type == 'contract_extension' and contract.date_end:
            vals.update({
                'current_end_date': contract.date_end,
                'new_end_date': contract.date_end + relativedelta(
                    months=self.extension_months, 
                    days=self.extension_days
                ),
            })
        elif self.action_type == 'pre_notice' and contract.date_end:
            vals.update({
                'termination_date': contract.date_end,
                'notice_date': contract.date_end - timedelta(days=self.notice_days),
            })

        return vals

    def _calculate_new_wage(self, contract):
        """Calcular nuevo salario"""
        if self.action_type != 'salary_modification':
            return contract.wage
        
        if self.salary_increase_type == 'percentage' and self.salary_percentage:
            return contract.wage * (1 + self.salary_percentage / 100)
        elif self.salary_increase_type == 'fixed_amount' and self.salary_fixed_amount:
            return contract.wage + self.salary_fixed_amount
        
        return contract.wage

    def _get_print_records(self, lines):
        """Obtener registros para imprimir según tipo de acción"""
        if self.action_type == 'salary_modification':
            return lines.mapped('modification_id').filtered(lambda m: m)
        elif self.action_type == 'pre_notice':
            return lines.mapped('contract_id')
        elif self.action_type == 'contract_extension':
            return lines.mapped('modification_id').filtered(lambda m: m)
        return self.env[lines._name]

    def _generate_compressed_reports(self, records, report_ref):
        """Generar ZIP con múltiples reportes"""
        report = self.env.ref(report_ref)
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for record in records:
                # Generar PDF individual
                pdf_content, _ = report._render_qweb_pdf([record.id])
                
                # Nombre del archivo
                if hasattr(record, 'employee_id') and record.employee_id:
                    filename = f"{record.employee_id.name}_{record.id}.pdf"
                else:
                    filename = f"Reporte_{record.id}.pdf"
                
                # Limpiar nombre de archivo
                filename = filename.replace(' ', '_').replace('/', '_')
                zip_file.writestr(filename, pdf_content)
        
        zip_buffer.seek(0)
        zip_content = base64.b64encode(zip_buffer.read()).decode('utf-8')
        
        # Crear adjunto
        attachment = self.env['ir.attachment'].create({
            'name': f"Reportes_{self.action_type}_{self.name}.zip",
            'type': 'binary',
            'datas': zip_content,
            'res_model': self._name,
            'res_id': self.id,
        })
        
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    def _show_notification(self, title, message, notification_type='info'):
        """Mostrar notificación"""
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title,
                'message': message,
                'type': notification_type,
                'sticky': False,
            }
        }

    # ================================================================
    # CONSTRAINTS
    # ================================================================
    @api.constrains('salary_percentage')
    def _check_salary_percentage(self):
        for record in self:
            if record.salary_percentage and not (0 <= record.salary_percentage <= 100):
                raise ValidationError(_("El porcentaje debe estar entre 0% y 100%"))

    @api.constrains('extension_months', 'extension_days')
    def _check_extension_duration(self):
        for record in self:
            if (record.action_type == 'contract_extension' and 
                record.extension_months <= 0 and record.extension_days <= 0):
                raise ValidationError(_("La duración de prórroga debe ser mayor a 0"))

    @api.constrains('notice_days')
    def _check_notice_days(self):
        for record in self:
            if record.action_type == 'pre_notice' and record.notice_days <= 0:
                raise ValidationError(_("Los días de preaviso deben ser mayor a 0"))


class ContractActionsLine(models.Model):
    """Líneas de acción de contrato"""
    _name = 'contract.actions.line'
    _description = "Línea de Acción de Contrato"
    _order = "priority desc, employee_id"
    _check_company_auto = True

    # ================================================================
    # CAMPOS RELACIONALES BÁSICOS
    # ================================================================
    action_id = fields.Many2one('contract.actions', string='Acción', ondelete='cascade', required=True)
    contract_id = fields.Many2one('hr.contract', string='Contrato', required=True, domain=[('state', '=', 'open')])
    employee_id = fields.Many2one(related='contract_id.employee_id', string='Empleado', store=True)
    company_id = fields.Many2one(related='contract_id.company_id', string='Compañía', store=True)

    # ================================================================
    # CAMPOS DE CONTROL
    # ================================================================
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('done', 'Procesado'),
        ('failed', 'Fallido')
    ], string='Estado', default='draft', copy=False)
    
    selected_for_processing = fields.Boolean(string='Seleccionar', default=True)
    priority = fields.Selection([
        ('low', 'Baja'),
        ('normal', 'Normal'),
        ('high', 'Alta'),
        ('urgent', 'Urgente')
    ], string='Prioridad', default='normal')
    
    error_message = fields.Text(string='Error')
    processing_date = fields.Datetime(string='Procesado')

    # ================================================================
    # CAMPOS INFORMATIVOS (SIN RELATED INNECESARIOS)
    # ================================================================
    employee_identification = fields.Char(related='employee_id.identification_id', string='ID', store=True)
    current_department_id = fields.Many2one(related='contract_id.department_id', string='Departamento', store=True)

    # ================================================================
    # CAMPOS PARA MODIFICACIÓN SALARIAL
    # ================================================================
    current_wage = fields.Float(string='Salario Actual', digits=(16, 2))
    new_wage = fields.Float(string='Nuevo Salario', digits=(16, 2))
    wage_difference = fields.Float(string='Diferencia', compute='_compute_wage_difference', store=True, digits=(16, 2))
    wage_percentage = fields.Float(string='% Incremento', compute='_compute_wage_difference', store=True, digits=(5, 2))
    current_job_id = fields.Many2one('hr.job', string='Cargo Actual')
    new_job_id = fields.Many2one('hr.job', string='Nuevo Cargo')

    # ================================================================
    # CAMPOS PARA PRÓRROGA
    # ================================================================
    current_end_date = fields.Date(string='Fecha Fin Actual')
    new_end_date = fields.Date(string='Nueva Fecha Fin')
    extension_duration = fields.Char(string='Duración', compute='_compute_extension_duration')

    # ================================================================
    # CAMPOS PARA PREAVISO
    # ================================================================
    termination_date = fields.Date(string='Fecha Terminación')
    notice_date = fields.Date(string='Fecha Preaviso')
    termination_reason = fields.Selection([
        ('con_justa_causa', 'Con Justa Causa'),
        ('sin_justa_causa', 'Sin Justa Causa'),
        ('pension', 'Pensión'),
        ('mutual_acuerdo', 'Mutuo Acuerdo'),
        ('renuncia', 'Renuncia'),
        ('vencimiento', 'Vencimiento')
    ], string='Motivo')

    # ================================================================
    # REFERENCIAS A REGISTROS CREADOS
    # ================================================================
    modification_id = fields.Many2one('hr.contractual.modifications', string='Modificación Creada')

    # ================================================================
    # COMPUTE METHODS
    # ================================================================
    @api.depends('current_wage', 'new_wage')
    def _compute_wage_difference(self):
        for record in self:
            if record.current_wage and record.new_wage:
                record.wage_difference = record.new_wage - record.current_wage
                record.wage_percentage = (record.wage_difference / record.current_wage * 100) if record.current_wage else 0.0
            else:
                record.wage_difference = 0.0
                record.wage_percentage = 0.0

    @api.depends('current_end_date', 'new_end_date')
    def _compute_extension_duration(self):
        for record in self:
            if record.current_end_date and record.new_end_date:
                delta = relativedelta(record.new_end_date, record.current_end_date)
                parts = []
                if delta.years:
                    parts.append(f"{delta.years}a")
                if delta.months:
                    parts.append(f"{delta.months}m")
                if delta.days:
                    parts.append(f"{delta.days}d")
                record.extension_duration = ' '.join(parts) if parts else '0d'
            else:
                record.extension_duration = ''

    # ================================================================
    # BUSINESS METHODS
    # ================================================================
    def action_execute(self):
        """Ejecutar la acción"""
        self.ensure_one()
        
        if self.state != 'draft':
            raise UserError(_("Solo se pueden ejecutar líneas en borrador"))
        
        action_type = self.action_id.action_type
        
        try:
            if action_type == 'salary_modification':
                self._execute_salary_modification()
            elif action_type == 'contract_extension':
                self._execute_contract_extension()
            elif action_type == 'pre_notice':
                self._execute_pre_notice()
            
            self.write({
                'state': 'done',
                'processing_date': fields.Datetime.now()
            })
            
        except Exception as e:
            self.write({
                'state': 'failed',
                'error_message': str(e),
                'processing_date': fields.Datetime.now()
            })
            raise

    def action_execute_selected(self):
        """Ejecutar líneas seleccionadas"""
        selected_lines = self.filtered(lambda l: l.selected_for_processing and l.state == 'draft')
        
        if not selected_lines:
            raise UserError(_("No hay líneas seleccionadas"))
        
        success_count = 0
        error_count = 0
        
        for line in selected_lines:
            try:
                line.action_execute()
                success_count += 1
            except Exception:  # noqa: BLE001 – error de línea individual se contabiliza, no detiene el lote
                _logger.warning("Error ejecutando acción de línea %s", line, exc_info=True)
                error_count += 1
        
        message = _("Procesadas {} líneas exitosamente").format(success_count)
        if error_count:
            message += _(", {} con errores").format(error_count)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Procesamiento Completado'),
                'message': message,
                'type': 'warning' if error_count else 'success',
            }
        }

    def action_reset_to_draft(self):
        """Resetear a borrador"""
        self.write({
            'state': 'draft',
            'error_message': False,
            'processing_date': False
        })

    def action_print_individual_report(self):
        """Imprimir reporte individual"""
        self.ensure_one()

        if self.state != 'done':
            raise UserError(_("Solo se pueden imprimir reportes procesados"))

        action_type = self.action_id.action_type

        if action_type == 'salary_modification' and self.modification_id:
            return self.env.ref('lavish_hr_payroll.report_hr_contract_salary_increase').report_action(self.modification_id)
        elif action_type == 'pre_notice':
            return self.env.ref('lavish_hr_payroll.report_hr_contract_preaviso').report_action(self.contract_id)
        elif action_type == 'contract_extension' and self.modification_id:
            return self.env.ref('lavish_hr_payroll.report_contract_extension').report_action(self.modification_id)
        else:
            raise UserError(_("No hay reporte disponible"))

    # ================================================================
    # PRIVATE METHODS
    # ================================================================
    def _execute_salary_modification(self):
        """Ejecutar modificación salarial"""
        modification_vals = {
            'contract_id': self.contract_id.id,
            'date': self.action_id.date_application,
            'description': f'Modificación desde: {self.action_id.name}',
            'wage': self.new_wage,
            'job_id': self.new_job_id.id if self.new_job_id else self.current_job_id.id,
            'old_wage': self.current_wage,
            'old_job_id': self.current_job_id.id if self.current_job_id else False,
            'reason': 'batch_processing',
        }
        
        modification = self.env['hr.contractual.modifications'].create(modification_vals)
        
        # Actualizar contrato
        contract_vals = {'wage': self.new_wage}
        if self.new_job_id and self.new_job_id != self.current_job_id:
            contract_vals['job_id'] = self.new_job_id.id
        
        self.contract_id.write(contract_vals)
        self.modification_id = modification.id

    def _execute_contract_extension(self):
        """Ejecutar prórroga"""
        modification_vals = {
            'contract_id': self.contract_id.id,
            'date': self.new_end_date,
            'description': f'Prórroga desde: {self.action_id.name}',
            'prorroga': True,
            'date_from': self.current_end_date + timedelta(days=1),
            'date_to': self.new_end_date,
            'wage': self.contract_id.wage,
            'job_id': self.contract_id.job_id.id if self.contract_id.job_id else False,
        }
        
        modification = self.env['hr.contractual.modifications'].create(modification_vals)
        self.contract_id.write({'date_end': self.new_end_date})
        self.modification_id = modification.id

    def _execute_pre_notice(self):
        """Ejecutar preaviso"""
        # Crear registro de preaviso
        prenotice_vals = {
            'contract_id': self.contract_id.id,
            'prenotice_type': self.termination_reason,
            'termination_date': self.termination_date,
            'notice_date': self.notice_date,
            'company_id': self.company_id.id,
        }
        
        # Aquí se crearía el registro de preaviso si existe el modelo
        # prenotice = self.env['contract.prenotice'].create(prenotice_vals)

    # ================================================================
    # CONSTRAINTS
    # ================================================================
    @api.constrains('new_wage')
    def _check_new_wage(self):
        for record in self:
            if (record.action_id.action_type == 'salary_modification' and 
                record.new_wage and record.new_wage <= 0):
                raise ValidationError(_("El nuevo salario debe ser mayor a 0"))

    @api.constrains('new_end_date', 'current_end_date')
    def _check_extension_dates(self):
        for record in self:
            if (record.action_id.action_type == 'contract_extension' and 
                record.new_end_date and record.current_end_date and 
                record.new_end_date <= record.current_end_date):
                raise ValidationError(_("La nueva fecha debe ser posterior a la actual"))

# ================================================================
# MODELO SIMPLE PARA PREAVISO
# ================================================================
class ContractPrenotice(models.Model):
    """Modelo simple para preaviso"""
    _name = 'contract.prenotice'
    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin']
    _description = "Preaviso de Contrato"
    _order = "termination_date desc"
    _check_company_auto = True

    name = fields.Char(string='Referencia', default='Nuevo', copy=False)
    contract_id = fields.Many2one('hr.contract', string='Contrato', required=True)
    employee_id = fields.Many2one(related='contract_id.employee_id', string='Empleado', store=True)
    company_id = fields.Many2one(related='contract_id.company_id', string='Compañía', store=True)
    
    prenotice_type = fields.Selection([
        ('pension', 'Pensión de Vejez'),
        ('con_justa_causa', 'Con Justa Causa'),
        ('abandono', 'Abandono de Puesto'),
        ('vencimiento', 'Vencimiento de Término')
    ], string='Tipo de Preaviso', required=True)
    
    termination_date = fields.Date(string='Fecha de Terminación', required=True)
    notice_date = fields.Date(string='Fecha de Preaviso', required=True)
    
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('sent', 'Enviado'),
        ('confirmed', 'Confirmado')
    ], string='Estado', default='draft')
    
    notes = fields.Text(string='Observaciones')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                sequence = self.env['ir.sequence'].next_by_code('contract.prenotice') or 'Nuevo'
                vals['name'] = sequence
        return super().create(vals_list)


# ================================================================
# WIZARD PARA CREAR ACCIONES DE CONTRATO
# ================================================================
class ContractActionWizard(models.TransientModel):
    """Wizard para crear acciones de contrato desde empleado o contrato"""
    _name = 'contract.action.wizard'
    _description = "Asistente de Acciones de Contrato"

    # ================================================================
    # CAMPOS DEL WIZARD
    # ================================================================
    wizard_type = fields.Selection([
        ('single', 'Contrato Individual'),
        ('employee', 'Empleado Individual')
    ], string='Tipo', default='single', required=True)
    
    # Campos para identificar origen
    contract_id = fields.Many2one('hr.contract', string='Contrato')
    employee_id = fields.Many2one('hr.employee', string='Empleado')
    
    # Configuración de la acción
    action_type = fields.Selection([
        ('salary_modification', 'Modificación Salarial'),
        ('contract_extension', 'Prórroga de Contrato'),
        ('pre_notice', 'Preaviso de Terminación'),
    ], string='Tipo de Acción', required=True)

    action_name = fields.Char(string='Nombre de la Acción', required=True)
    date_application = fields.Date(string='Fecha de Aplicación', default=fields.Date.today, required=True)
    description = fields.Text(string='Descripción')

    # Configuración específica por tipo
    # Para modificaciones salariales
    salary_increase_type = fields.Selection([
        ('percentage', 'Porcentaje'),
        ('fixed_amount', 'Monto Fijo'),
        ('individual', 'Individual')
    ], string='Tipo de Aumento')

    salary_percentage = fields.Float(string='Porcentaje (%)')
    salary_fixed_amount = fields.Float(string='Monto Fijo')

    # Para prórrogas
    extension_months = fields.Integer(string='Meses de Prórroga', default=12)
    extension_days = fields.Integer(string='Días Adicionales', default=0)

    # Para preaviso
    notice_days = fields.Integer(string='Días de Preaviso', default=15)

    # ================================================================
    # BUSINESS METHODS
    # ================================================================
    def action_create_contract_action(self):
        """Crear acción de contrato"""
        self.ensure_one()
        
        # Validar que tenemos un contrato
        contract = self.contract_id
        if not contract and self.employee_id:
            contract = self.env['hr.contract'].search([
                ('employee_id', '=', self.employee_id.id),
                ('state', '=', 'open')
            ], limit=1)
        
        if not contract:
            raise UserError(_("No se encontró un contrato activo"))
        
        # Preparar valores para la acción
        action_vals = {
            'name': self.action_name,
            'action_type': self.action_type,
            'date_application': self.date_application,
            'description': self.description,
            'company_id': contract.company_id.id,
        }
        
        # Agregar configuración específica por tipo
        if self.action_type == 'salary_modification':
            action_vals.update({
                'salary_increase_type': self.salary_increase_type,
                'salary_percentage': self.salary_percentage,
                'salary_fixed_amount': self.salary_fixed_amount,
            })
        elif self.action_type == 'contract_extension':
            action_vals.update({
                'extension_months': self.extension_months,
                'extension_days': self.extension_days,
            })
        elif self.action_type == 'pre_notice':
            action_vals.update({
                'notice_days': self.notice_days,
            })
        
        # Crear la acción
        action = self.env['contract.actions'].create(action_vals)
        
        # Agregar el contrato específico
        action.additional_contract_ids = [(6, 0, [contract.id])]
        action.action_add_additional_contracts()
        
        # Redirigir a la acción creada
        return {
            'type': 'ir.actions.act_window',
            'name': _('Acción de Contrato Creada'),
            'res_model': 'contract.actions',
            'res_id': action.id,
            'view_mode': 'form',
            'target': 'current',
        }


# ================================================================
# EXTENSIONES COMPLETAS DE MODELOS EXISTENTES
# ================================================================
class HrContractExtended(models.Model):
    """Extensión completa del modelo de contrato con acciones y modificaciones"""
    _inherit = 'hr.contract'

    # ================================================================
    # RELACIONES ONE2MANY
    # ================================================================
    contract_actions_lines = fields.One2many(
        'contract.actions.line', 'contract_id',
        string='Líneas de Acción'
    )
    prenotice_ids = fields.One2many(
        'contract.prenotice', 'contract_id',
        string='Preavisos'
    )
    contractual_modifications_ids = fields.One2many(
        'hr.contractual.modifications', 'contract_id',
        string='Modificaciones Contractuales',
        help="Historial de modificaciones realizadas a este contrato"
    )

    # ================================================================
    # CAMPOS COMPUTADOS - ACCIONES
    # ================================================================
    contract_actions_count = fields.Integer(
        string='Acciones de Contrato',
        compute='_compute_contract_actions_count'
    )
    prenotice_count = fields.Integer(
        string='Preavisos',
        compute='_compute_prenotice_count'
    )
    last_action_date = fields.Date(
        string='Última Acción',
        compute='_compute_last_action_date'
    )

    # ================================================================
    # CAMPOS COMPUTADOS - MODIFICACIONES
    # ================================================================
    modifications_count = fields.Integer(
        string='Modificaciones',
        compute='_compute_modifications_count'
    )
    salary_modifications_count = fields.Integer(
        string='Modificaciones Salariales',
        compute='_compute_modifications_count'
    )
    extensions_count = fields.Integer(
        string='Prórrogas',
        compute='_compute_modifications_count'
    )
    last_modification_date = fields.Date(
        string='Última Modificación',
        compute='_compute_last_modification'
    )
    last_salary_change = fields.Float(
        string='Último Cambio Salarial',
        compute='_compute_last_modification',
        digits=(16, 2)
    )
    pending_modifications = fields.Integer(
        string='Modificaciones Pendientes',
        compute='_compute_modifications_count'
    )

    @api.depends('contract_actions_lines')
    def _compute_contract_actions_count(self):
        for record in self:
            record.contract_actions_count = len(record.contract_actions_lines)

    @api.depends('prenotice_ids')
    def _compute_prenotice_count(self):
        for record in self:
            record.prenotice_count = len(record.prenotice_ids)

    @api.depends('contract_actions_lines.processing_date')
    def _compute_last_action_date(self):
        for record in self:
            last_action = record.contract_actions_lines.filtered(
                lambda l: l.processing_date
            ).sorted('processing_date', reverse=True)
            record.last_action_date = last_action[0].processing_date.date() if last_action else False

    def action_view_contract_actions(self):
        """Ver acciones de contrato"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Acciones de Contrato'),
            'res_model': 'contract.actions.line',
            'domain': [('contract_id', '=', self.id)],
            'view_mode': 'tree,form',
            'target': 'current',
            'context': {'default_contract_id': self.id}
        }

    def action_view_prenotices(self):
        """Ver preavisos del contrato"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Preavisos de Contrato'),
            'res_model': 'contract.prenotice',
            'domain': [('contract_id', '=', self.id)],
            'view_mode': 'tree,form',
            'target': 'current',
            'context': {'default_contract_id': self.id}
        }

    def action_create_prenotice(self):
        """Crear preaviso para el contrato"""
        self.ensure_one()
        
        if not self.date_end:
            raise UserError(_("El contrato debe tener fecha de finalización para crear un preaviso"))
        
        # Calcular fecha de preaviso (30 días antes por defecto)
        from datetime import timedelta
        notice_date = self.date_end - timedelta(days=30)
        
        prenotice_vals = {
            'contract_id': self.id,
            'termination_date': self.date_end,
            'notice_date': notice_date,
            'prenotice_type': 'vencimiento',  # Por defecto
        }
        
        prenotice = self.env['contract.prenotice'].create(prenotice_vals)
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Preaviso Creado'),
            'res_model': 'contract.prenotice',
            'res_id': prenotice.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_contract_wizard(self):
        """Abrir wizard de acciones desde contrato"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Acciones de Contrato'),
            'res_model': 'contract.action.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_contract_id': self.id}
        }

    # ================================================================
    # COMPUTE METHODS - MODIFICACIONES
    # ================================================================
    @api.depends('contractual_modifications_ids')
    def _compute_modifications_count(self):
        """Calcular contadores de modificaciones"""
        for record in self:
            modifications = record.contractual_modifications_ids
            record.modifications_count = len(modifications)
            record.salary_modifications_count = len(modifications.filtered(lambda m: not m.prorroga))
            record.extensions_count = len(modifications.filtered(lambda m: m.prorroga))
            record.pending_modifications = len(modifications)

    @api.depends('contractual_modifications_ids.date', 'contractual_modifications_ids.wage')
    def _compute_last_modification(self):
        """Calcular información de la última modificación"""
        for record in self:
            last_modification = record.contractual_modifications_ids.sorted('date', reverse=True)
            if last_modification:
                record.last_modification_date = last_modification[0].date
                last_salary_mod = last_modification.filtered(lambda m: m.wage)
                record.last_salary_change = last_salary_mod[0].wage if last_salary_mod else 0.0
            else:
                record.last_modification_date = False
                record.last_salary_change = 0.0

    # ================================================================
    # BUSINESS METHODS - MODIFICACIONES
    # ================================================================
    def action_view_modifications(self):
        """Ver todas las modificaciones del contrato"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Modificaciones Contractuales'),
            'res_model': 'hr.contractual.modifications',
            'domain': [('contract_id', '=', self.id)],
            'view_mode': 'tree,form',
            'target': 'current',
            'context': {
                'default_contract_id': self.id,
                'search_default_group_applied': 1
            }
        }

    def action_view_salary_modifications(self):
        """Ver solo modificaciones salariales"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Modificaciones Salariales'),
            'res_model': 'hr.contractual.modifications',
            'domain': [('contract_id', '=', self.id), ('prorroga', '=', False)],
            'view_mode': 'tree,form',
            'target': 'current',
            'context': {
                'default_contract_id': self.id,
                'default_prorroga': False
            }
        }

    def action_view_extensions(self):
        """Ver solo prórrogas"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Prórrogas de Contrato'),
            'res_model': 'hr.contractual.modifications',
            'domain': [('contract_id', '=', self.id), ('prorroga', '=', True)],
            'view_mode': 'tree,form',
            'target': 'current',
            'context': {
                'default_contract_id': self.id,
                'default_prorroga': True
            }
        }

    def action_view_pending_modifications(self):
        """Ver modificaciones pendientes"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Modificaciones Pendientes'),
            'res_model': 'hr.contractual.modifications',
            'domain': [('contract_id', '=', self.id)],
            'view_mode': 'tree,form',
            'target': 'current',
            'context': {
                'default_contract_id': self.id,
                'search_default_not_applied': 1
            }
        }

    def action_create_salary_modification(self):
        """Crear nueva modificación salarial"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Nueva Modificación Salarial'),
            'res_model': 'hr.contractual.modifications',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_contract_id': self.id,
                'default_prorroga': False,
                'default_reason': 'salary_increase',
                'default_old_wage': self.wage,
                'default_old_job_id': self.job_id.id if self.job_id else False,
                'default_old_contract_type': self.contract_type,
                'default_old_method_schedule_pay': self.method_schedule_pay,
            }
        }

    def action_create_extension(self):
        """Crear nueva prórroga"""
        self.ensure_one()
        if not self.date_end:
            raise UserError(_("No se puede crear una prórroga para un contrato sin fecha de finalización"))
        last_extension = self.contractual_modifications_ids.filtered(
            lambda m: m.prorroga
        ).sorted('sequence', reverse=True)
        next_sequence = (last_extension[0].sequence + 1) if last_extension else 1
        return {
            'type': 'ir.actions.act_window',
            'name': _('Nueva Prórroga de Contrato'),
            'res_model': 'hr.contractual.modifications',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_contract_id': self.id,
                'default_prorroga': True,
                'default_reason': 'proroga',
                'default_sequence': next_sequence,
                'default_date_from': self.date_end,
                'default_wage': self.wage,
                'default_job_id': self.job_id.id if self.job_id else False,
                'default_contract_type': self.contract_type,
                'default_method_schedule_pay': self.method_schedule_pay,
            }
        }

    def action_apply_all_pending_modifications(self):
        """Aplicar todas las modificaciones pendientes"""
        self.ensure_one()
        pending_mods = self.contractual_modifications_ids.filtered(lambda m: not m.prorroga)
        if not pending_mods:
            raise UserError(_("No hay modificaciones pendientes para aplicar"))
        for modification in pending_mods.sorted('date'):
            modification.action_apply_modification()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Modificaciones Aplicadas'),
                'message': _('Se han aplicado %d modificaciones correctamente') % len(pending_mods),
                'type': 'success',
                'sticky': False,
            }
        }

    # ================================================================
    # OVERRIDE METHODS
    # ================================================================
    def write(self, vals):
        """Override write para crear modificación automática"""
        result = super().write(vals)
        # Si se está actualizando el salario directamente, crear modificación automática
        if 'wage' in vals and not self.env.context.get('skip_auto_modification'):
            for record in self:
                today_modification = record.contractual_modifications_ids.filtered(
                    lambda m: m.date == fields.Date.today() and not m.prorroga
                )
                if not today_modification:
                    self.env['hr.contractual.modifications'].create({
                        'date': vals.get('date_start', fields.Date.today()),
                        'contract_id': record.id,
                        'description': 'Modificación automática por cambio directo',
                        'wage': vals['wage'],
                    })
        return result

    # ================================================================
    # STATISTICS METHODS
    # ================================================================
    def get_salary_history(self):
        """Obtener historial salarial"""
        self.ensure_one()
        modifications = self.contractual_modifications_ids.filtered(
            lambda m: m.wage and m.prorroga
        ).sorted('date')
        history = []
        for mod in modifications:
            history.append({
                'date': mod.date,
                'wage': mod.wage,
                'old_wage': mod.old_wage,
                'difference': mod.difference,
                'percentage': mod.difference_percentage,
                'reason': mod.reason,
                'description': mod.description,
            })
        return history

    def get_extension_history(self):
        """Obtener historial de prórrogas"""
        self.ensure_one()
        extensions = self.contractual_modifications_ids.filtered(
            lambda m: m.prorroga
        ).sorted('date')
        history = []
        for ext in extensions:
            history.append({
                'sequence': ext.sequence,
                'date_from': ext.date_from,
                'date_to': ext.date_to,
                'duration': ext.extension_duration,
                'description': ext.description,
            })
        return history


class HrEmployeeExtended(models.Model):
    """Extensión del modelo de empleado"""
    _inherit = 'hr.employee'

    def action_contract_wizard(self):
        """Abrir wizard de acciones desde empleado"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Acciones de Contrato'),
            'res_model': 'contract.action.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_employee_id': self.id,
                'default_wizard_type': 'employee'
            }
        }


# ================================================================
# EXTENSIONES DEL MODELO DE PREAVISO
# ================================================================
class ContractPrenoticeExtended(models.Model):
    """Extensión del modelo de preaviso con métodos de negocio"""
    _inherit = 'contract.prenotice'

    def action_send_prenotice(self):
        """Enviar preaviso por email"""
        for record in self:
            if record.state != 'draft':
                raise UserError(_("Solo se pueden enviar preavisos en estado borrador"))
            
            # Enviar email
            template = self.env.ref('lavish_hr_employee.email_template_prenotice_sent', raise_if_not_found=False)
            if template and record.employee_id.work_email:
                template.send_mail(record.id)
            
            record.state = 'sent'
            
            # Crear actividad de seguimiento
            self.env['mail.activity'].create({
                'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id,
                'summary': f'Seguimiento preaviso - {record.employee_id.name}',
                'note': f'Verificar recepción del preaviso {record.name}',
                'res_id': record.id,
                'res_model_id': self.env.ref('lavish_hr_employee.model_contract_prenotice').id,
                'user_id': self.env.user.id,
                'date_deadline': fields.Date.today() + timedelta(days=3),
            })

    def action_confirm_prenotice(self):
        """Confirmar recepción del preaviso"""
        for record in self:
            if record.state != 'sent':
                raise UserError(_("Solo se pueden confirmar preavisos enviados"))
            
            record.state = 'confirmed'

    def action_cancel_prenotice(self):
        """Cancelar preaviso"""
        for record in self:
            if record.state == 'confirmed':
                raise UserError(_("No se pueden cancelar preavisos confirmados"))
            
            record.state = 'draft'

    def action_print_prenotice(self):
        """Imprimir carta de preaviso"""
        return self.env.ref('lavish_hr_employee.action_report_contract_prenotice').report_action(self)

