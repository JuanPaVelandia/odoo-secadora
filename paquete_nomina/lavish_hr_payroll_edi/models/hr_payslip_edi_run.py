# -*- coding: utf-8 -*-
"""
Lotes de Nómina Electrónica DIAN.
"""
import logging
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class HrPayslipEdiRun(models.Model):
    _name = 'hr.payslip.edi.run'
    _description = 'Lote de Nómina Electrónica'
    _order = 'date_end desc'

    name = fields.Char(string='Nombre', required=True)
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('verify', 'Verificación'),
        ('close', 'Cerrado'),
    ], string='Estado', default='draft', index=True, copy=False)

    date_start = fields.Date(
        string='Fecha Inicio', required=True,
        default=lambda self: fields.Date.to_string(date.today().replace(day=1))
    )
    date_end = fields.Date(
        string='Fecha Fin', required=True,
        default=lambda self: fields.Date.to_string(
            (datetime.now() + relativedelta(months=+1, day=1, days=-1)).date()
        )
    )
    fecha_vencimiento = fields.Date(string='Fecha de Vencimiento')

    company_id = fields.Many2one(
        'res.company', string='Compañía',
        required=True, default=lambda self: self.env.company
    )
    credit_note = fields.Boolean(
        string='Notas de Ajuste',
        help='Si está marcado, las nóminas generadas serán notas de ajuste'
    )
    provision_mode = fields.Selection([
        ('include', 'Incluir Provisiones'),
        ('exclude', 'Excluir Provisiones'),
        ('only', 'Solo Provisiones'),
    ], string='Modo Provisiones', default='include',
        help='Controla cómo se manejan las provisiones de prestaciones '
             'en las nóminas electrónicas de este lote.'
    )
    use_external_accumulated = fields.Boolean(
        string='Incluir Acumulados Externos',
        default=False,
        help='Cuando está activo, la consolidación de las nóminas del lote '
             'busca en Acumulados de Nómina registros de "Carga Inicial" '
             'para restar provisiones reportadas en un sistema anterior. '
             'Se propaga a cada nómina electrónica del lote.'
    )
    es_ajuste_electronico = fields.Boolean(
        string='Ajuste Electrónico',
        default=False,
        help='Marca este lote como un ajuste para envío de nómina electrónica. '
             'Permite forzar las nóminas a estado "Hecho" sin pasar por el flujo normal.'
    )
    payslip_run_source_id = fields.Many2one(
        'hr.payslip.run',
        string='Lote de Nómina Origen',
        help='Lote de nómina regular asociado (ej: consolidación). '
             'Al generar nóminas electrónicas, se buscarán las nóminas de este lote.',
    )

    slip_ids = fields.One2many(
        'hr.payslip.edi', 'payslip_run_id',
        string='Nóminas Electrónicas'
    )
    payslip_count = fields.Integer(
        string='Cantidad',
        compute='_compute_payslip_count'
    )
    employee_summary_ids = fields.One2many(
        'hr.payslip.edi.employee.summary', 'run_id',
        string='Resumen por Empleado',
        compute='_compute_employee_summary'
    )
    certificate_expiry_warning = fields.Char(
        string='Alerta Certificado',
        compute='_compute_certificate_expiry_warning'
    )

    @api.depends('company_id')
    def _compute_certificate_expiry_warning(self):
        today = date.today()
        for rec in self:
            expiry = rec.company_id.certificate_expiry_payroll
            if expiry and expiry <= today + timedelta(days=30):
                days_left = (expiry - today).days
                if days_left <= 0:
                    rec.certificate_expiry_warning = _(
                        'CERTIFICADO VENCIDO desde %s. No podrá enviar documentos a DIAN.'
                    ) % expiry
                else:
                    rec.certificate_expiry_warning = _(
                        'El certificado digital vence en %d días (%s). Renuévelo pronto.'
                    ) % (days_left, expiry)
            else:
                rec.certificate_expiry_warning = False

    @api.depends('slip_ids')
    def _compute_payslip_count(self):
        for run in self:
            run.payslip_count = len(run.slip_ids)

    @api.depends('slip_ids', 'slip_ids.state', 'slip_ids.state_dian',
                 'slip_ids.total_devengos', 'slip_ids.total_deducciones', 'slip_ids.total_paid')
    def _compute_employee_summary(self):
        """Calcula resumen agrupado por empleado."""
        for run in self:
            # Limpiar resúmenes anteriores
            run.employee_summary_ids = [(5, 0, 0)]

            if not run.slip_ids:
                continue

            # Agrupar por empleado
            employee_data = {}
            for slip in run.slip_ids.filtered(lambda s: s.state != 'cancel'):
                emp_id = slip.employee_id.id
                if emp_id not in employee_data:
                    employee_data[emp_id] = {
                        'employee_id': emp_id,
                        'run_id': run.id,
                        'payslip_count': 0,
                        'done_count': 0,
                        'dian_ok_count': 0,
                        'dian_error_count': 0,
                        'dian_pending_count': 0,
                        'total_devengados': 0.0,
                        'total_deducciones': 0.0,
                        'total_neto': 0.0,
                    }

                data = employee_data[emp_id]
                data['payslip_count'] += 1
                data['total_devengados'] += slip.total_devengos or 0
                data['total_deducciones'] += slip.total_deducciones or 0
                data['total_neto'] += slip.total_paid or 0

                if slip.state == 'done':
                    data['done_count'] += 1
                    if slip.state_dian == 'exitoso':
                        data['dian_ok_count'] += 1
                    elif slip.state_dian in ('rechazado', 'error'):
                        data['dian_error_count'] += 1
                    else:
                        data['dian_pending_count'] += 1

            # Crear registros de resumen
            summaries = []
            for emp_id, data in employee_data.items():
                summaries.append((0, 0, data))

            run.employee_summary_ids = summaries

    # ================================================================
    # CAMPOS PARA STEPPER (paso a paso)
    # ================================================================

    # Contadores por estado
    slip_draft_count = fields.Integer(
        string='Nóminas Borrador',
        compute='_compute_slip_counts'
    )
    slip_verify_count = fields.Integer(
        string='Nóminas en Verificación',
        compute='_compute_slip_counts'
    )
    slip_done_count = fields.Integer(
        string='Nóminas Hechas',
        compute='_compute_slip_counts'
    )
    slip_cancel_count = fields.Integer(
        string='Nóminas Canceladas',
        compute='_compute_slip_counts'
    )

    # Contadores DIAN
    slip_dian_pending_count = fields.Integer(
        string='Pendientes DIAN',
        compute='_compute_slip_counts'
    )
    slip_dian_success_count = fields.Integer(
        string='Exitosos DIAN',
        compute='_compute_slip_counts'
    )
    slip_dian_error_count = fields.Integer(
        string='Errores DIAN',
        compute='_compute_slip_counts'
    )

    # Estados de cada paso
    step1_ready = fields.Boolean(
        string='Paso 1 Listo',
        compute='_compute_step_status',
        help='Indica si hay nóminas generadas'
    )
    step2_ready = fields.Boolean(
        string='Paso 2 Listo',
        compute='_compute_step_status',
        help='Indica si las líneas están consolidadas'
    )
    step3_ready = fields.Boolean(
        string='Paso 3 Listo',
        compute='_compute_step_status',
        help='Indica si las nóminas están confirmadas'
    )
    step4_ready = fields.Boolean(
        string='Paso 4 Listo',
        compute='_compute_step_status',
        help='Indica si todas las nóminas fueron validadas en DIAN'
    )

    # Texto de estado para cada paso
    step1_status = fields.Char(
        string='Estado Paso 1',
        compute='_compute_step_status'
    )
    step2_status = fields.Char(
        string='Estado Paso 2',
        compute='_compute_step_status'
    )
    step3_status = fields.Char(
        string='Estado Paso 3',
        compute='_compute_step_status'
    )
    step4_status = fields.Char(
        string='Estado Paso 4',
        compute='_compute_step_status'
    )

    @api.depends('slip_ids', 'slip_ids.state', 'slip_ids.state_dian')
    def _compute_slip_counts(self):
        for run in self:
            slips = run.slip_ids
            run.slip_draft_count = len(slips.filtered(lambda s: s.state == 'draft'))
            run.slip_verify_count = len(slips.filtered(lambda s: s.state == 'verify'))
            run.slip_done_count = len(slips.filtered(lambda s: s.state == 'done'))
            run.slip_cancel_count = len(slips.filtered(lambda s: s.state == 'cancel'))

            # DIAN
            done_slips = slips.filtered(lambda s: s.state == 'done')
            run.slip_dian_pending_count = len(done_slips.filtered(
                lambda s: s.state_dian in ('por_notificar', 'por_validar')
            ))
            run.slip_dian_success_count = len(done_slips.filtered(
                lambda s: s.state_dian == 'exitoso'
            ))
            run.slip_dian_error_count = len(done_slips.filtered(
                lambda s: s.state_dian in ('rechazado', 'error')
            ))

    @api.depends('slip_ids', 'slip_ids.state', 'slip_ids.state_dian',
                 'slip_ids.line_ids', 'state')
    def _compute_step_status(self):
        for run in self:
            total = len(run.slip_ids)
            active_slips = run.slip_ids.filtered(lambda s: s.state != 'cancel')
            total_active = len(active_slips)

            # Paso 1: Generar Nóminas
            run.step1_ready = total > 0
            if total == 0:
                run.step1_status = "Sin nóminas"
            else:
                run.step1_status = f"{total} nóminas generadas"

            # Paso 2: Consolidar Líneas
            slips_with_lines = active_slips.filtered(
                lambda s: s.line_ids
            )
            run.step2_ready = total_active > 0 and len(slips_with_lines) == total_active
            if total_active == 0:
                run.step2_status = "Sin nóminas activas"
            elif len(slips_with_lines) == 0:
                run.step2_status = "Pendiente consolidar"
            elif len(slips_with_lines) < total_active:
                run.step2_status = f"{len(slips_with_lines)}/{total_active} consolidadas"
            else:
                run.step2_status = "Todas consolidadas"

            # Paso 3: Confirmar (estado done)
            done_slips = run.slip_ids.filtered(lambda s: s.state == 'done')
            run.step3_ready = total_active > 0 and len(done_slips) == total_active
            if total_active == 0:
                run.step3_status = "Sin nóminas activas"
            elif len(done_slips) == 0:
                run.step3_status = "Pendiente confirmar"
            elif len(done_slips) < total_active:
                run.step3_status = f"{len(done_slips)}/{total_active} confirmadas"
            else:
                run.step3_status = "Todas confirmadas"

            # Paso 4: Validar DIAN
            success_slips = done_slips.filtered(lambda s: s.state_dian == 'exitoso')
            run.step4_ready = len(done_slips) > 0 and len(success_slips) == len(done_slips)
            if len(done_slips) == 0:
                run.step4_status = "Sin nóminas para validar"
            elif len(success_slips) == 0:
                pending = len(done_slips.filtered(
                    lambda s: s.state_dian in ('por_notificar', 'por_validar')
                ))
                errors = len(done_slips.filtered(
                    lambda s: s.state_dian in ('rechazado', 'error')
                ))
                if errors > 0:
                    run.step4_status = f"{errors} con errores, {pending} pendientes"
                else:
                    run.step4_status = f"{pending} pendientes DIAN"
            elif len(success_slips) < len(done_slips):
                run.step4_status = f"{len(success_slips)}/{len(done_slips)} validadas DIAN"
            else:
                run.step4_status = "Todas validadas DIAN"

    # ================================================================
    # ACCIONES DE ESTADO
    # ================================================================

    def action_draft(self):
        return self.write({'state': 'draft'})

    def action_verify(self):
        return self.write({'state': 'verify'})

    def action_close(self):
        if not self._are_payslips_ready():
            raise UserError(_('Todas las nóminas deben estar en estado Hecho o Cancelado.'))
        return self.write({'state': 'close'})

    def _are_payslips_ready(self):
        return all(slip.state in ['done', 'cancel'] for slip in self.slip_ids)

    # ================================================================
    # ACCIONES DE LOTE
    # ================================================================

    def action_validate(self):
        """Consolida las líneas de todas las nóminas del lote."""
        for run in self:
            for slip in run.slip_ids.filtered(lambda s: s.state != 'cancel'):
                slip.get_payslip_period()
                slip.update_total()

    def action_confirm(self):
        """Confirma el lote de nóminas."""
        for run in self:
            slips_to_confirm = run.slip_ids.filtered(lambda s: s.state == 'draft')
            if not slips_to_confirm:
                raise UserError(_('No hay nóminas en borrador para confirmar.'))
            slips_to_confirm.write({'state': 'verify'})
            run.write({'state': 'close'})

    def action_done_all(self):
        """Confirma todas las nóminas del lote (draft/verify → done)."""
        for run in self:
            slips_to_confirm = run.slip_ids.filtered(
                lambda s: s.state in ('draft', 'verify')
            )
            if not slips_to_confirm:
                raise UserError(_('No hay nóminas pendientes de confirmar.'))
            slips_to_confirm.write({'state': 'done'})

    def action_force_done(self):
        """Fuerza todas las nóminas del lote a estado 'Hecho' (ajuste electrónico)."""
        for run in self:
            if not run.es_ajuste_electronico:
                raise UserError(_(
                    'Solo puede forzar estado en lotes marcados como Ajuste Electrónico.'
                ))
            slips_to_force = run.slip_ids.filtered(lambda s: s.state not in ('done', 'cancel'))
            if not slips_to_force:
                raise UserError(_('No hay nóminas pendientes de forzar a estado Hecho.'))

            slips_to_force.write({
                'state': 'done',
                'state_dian': 'por_notificar',
            })
            _logger.info(
                "Lote %s: forzadas %d nóminas a estado 'done' (ajuste electrónico)",
                run.name, len(slips_to_force)
            )
            run.message_post(
                body=_(
                    '<strong>Ajuste Electrónico:</strong> %d nóminas forzadas a estado Hecho '
                    'para envío electrónico.'
                ) % len(slips_to_force),
                message_type='comment',
                subtype_xmlid='mail.mt_note',
            )

    def validar_dian(self):
        """Envía a DIAN las nóminas electrónicas del lote."""
        for run in self:
            slips_to_validate = run.slip_ids.filtered(
                lambda s: s.state == 'done' and s.state_dian in ('por_notificar', 'rechazado', 'error')
            )
            if not slips_to_validate:
                raise UserError(_('No hay nóminas listas para validar en DIAN.'))
            # Resetear rechazadas/error para permitir reenvío
            slips_retry = slips_to_validate.filtered(lambda s: s.state_dian in ('rechazado', 'error'))
            if slips_retry:
                slips_retry.write({
                    'state_dian': 'por_notificar',
                    'resend': True,
                    'name_xml': False,
                })

            # Validar datos faltantes antes de enviar
            warnings = run._check_missing_data(slips_to_validate)
            if warnings:
                return run._show_warnings_wizard(warnings, slips_to_validate)

            errors_summary = []
            success_count = 0

            for slip in slips_to_validate:
                try:
                    slip.action_send_dian()
                    success_count += 1
                except Exception as e:
                    error_msg = str(e)
                    _logger.error("Error enviando nómina %s (%s): %s",
                                  slip.number, slip.employee_id.name, error_msg)
                    # Registrar como nota en el documento
                    slip.message_post(
                        body=_('<strong>Error al enviar a DIAN:</strong><br/>%s') % error_msg,
                        message_type='comment',
                        subtype_xmlid='mail.mt_note',
                    )
                    slip.write({
                        'state_dian': 'error',
                        'response_message_dian': (slip.response_message_dian or '') +
                            f"\n[Lote] Error: {error_msg}",
                    })
                    errors_summary.append(f"{slip.employee_id.name} ({slip.number}): {error_msg}")

            # Mostrar resumen al final
            if errors_summary:
                msg_body = _(
                    '<strong>Resumen envío DIAN:</strong><br/>'
                    'Exitosos: %d / %d<br/><br/>'
                    '<strong>Errores:</strong><br/>%s'
                ) % (success_count, len(slips_to_validate),
                     '<br/>'.join(errors_summary))
                run.message_post(
                    body=msg_body,
                    message_type='comment',
                    subtype_xmlid='mail.mt_note',
                )
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Envío DIAN con errores'),
                        'message': _('%d exitosos, %d con errores. Revise las notas del lote.') % (
                            success_count, len(errors_summary)),
                        'type': 'warning',
                        'sticky': True,
                    }
                }

    def _check_missing_data(self, slips):
        """
        Verifica datos faltantes en las nóminas del lote.
        Retorna lista de advertencias agrupadas por tipo.
        """
        warnings = {
            'company': [],
            'employee': [],
            'contract': [],
            'payslip': [],
        }

        # Validar empresa (solo una vez)
        company = self.company_id
        generator = self.env['nomina.xml.generator']
        company_errors = generator.validate_company_config(company)
        if company_errors:
            warnings['company'] = company_errors

        # Validar cada nómina
        for slip in slips:
            employee = slip.employee_id
            contract = slip.contract_id

            # Validar empleado
            emp_errors = generator.validate_employee_data(employee)
            if emp_errors:
                for err in emp_errors:
                    warnings['employee'].append(f"{employee.name}: {err}")

            # Validar contrato
            contract_errors = generator.validate_contract_data(contract)
            if contract_errors:
                for err in contract_errors:
                    warnings['contract'].append(f"{employee.name}: {err}")

            # Validar nómina
            payslip_errors = generator.validate_payslip_data(slip)
            if payslip_errors:
                for err in payslip_errors:
                    warnings['payslip'].append(f"{slip.name or employee.name}: {err}")

            # Validaciones adicionales específicas
            if not slip.line_ids:
                warnings['payslip'].append(
                    f"{slip.name or employee.name}: No tiene líneas de nómina"
                )

            # Verificar totales
            if slip.total_devengos <= 0:
                warnings['payslip'].append(
                    f"{slip.name or employee.name}: Total devengados es cero o negativo"
                )

        # Filtrar categorías vacías
        return {k: v for k, v in warnings.items() if v}

    def _show_warnings_wizard(self, warnings, slips_to_validate):
        """Muestra wizard con advertencias antes de continuar."""
        warning_text = []

        if warnings.get('company'):
            warning_text.append("=== EMPRESA ===")
            warning_text.extend(warnings['company'])
            warning_text.append("")

        if warnings.get('employee'):
            warning_text.append("=== EMPLEADOS ===")
            warning_text.extend(warnings['employee'])
            warning_text.append("")

        if warnings.get('contract'):
            warning_text.append("=== CONTRATOS ===")
            warning_text.extend(warnings['contract'])
            warning_text.append("")

        if warnings.get('payslip'):
            warning_text.append("=== NÓMINAS ===")
            warning_text.extend(warnings['payslip'])

        # Contar errores críticos vs advertencias
        total_errors = sum(len(v) for v in warnings.values())

        return {
            'type': 'ir.actions.act_window',
            'name': _('Advertencias de Datos Faltantes'),
            'res_model': 'hr.payslip.edi.run.warning.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_run_id': self.id,
                'default_warning_text': '\n'.join(warning_text),
                'default_slip_ids': [(6, 0, slips_to_validate.ids)],
                'default_error_count': total_errors,
            },
        }

    def action_force_validar_dian(self):
        """Fuerza el envío a DIAN ignorando advertencias."""
        for run in self:
            slips_to_validate = run.slip_ids.filtered(
                lambda s: s.state == 'done' and s.state_dian == 'por_notificar'
            )
            errors_summary = []
            success_count = 0

            for slip in slips_to_validate:
                try:
                    slip.action_send_dian()
                    success_count += 1
                except Exception as e:
                    error_msg = str(e)
                    _logger.error("Error enviando nómina %s (%s): %s",
                                  slip.number, slip.employee_id.name, error_msg)
                    slip.message_post(
                        body=_('<strong>Error al enviar a DIAN:</strong><br/>%s') % error_msg,
                        message_type='comment',
                        subtype_xmlid='mail.mt_note',
                    )
                    slip.write({
                        'state_dian': 'error',
                        'response_message_dian': (slip.response_message_dian or '') +
                            f"\n[Lote Forzado] Error: {error_msg}",
                    })
                    errors_summary.append(f"{slip.employee_id.name} ({slip.number}): {error_msg}")

            if errors_summary:
                msg_body = _(
                    '<strong>Resumen envío forzado DIAN:</strong><br/>'
                    'Exitosos: %d / %d<br/><br/>'
                    '<strong>Errores:</strong><br/>%s'
                ) % (success_count, len(slips_to_validate),
                     '<br/>'.join(errors_summary))
                run.message_post(
                    body=msg_body,
                    message_type='comment',
                    subtype_xmlid='mail.mt_note',
                )
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Envío forzado con errores'),
                        'message': _('%d exitosos, %d con errores. Revise las notas.') % (
                            success_count, len(errors_summary)),
                        'type': 'warning',
                        'sticky': True,
                    }
                }

    def restart_full_batch(self):
        """Reinicia el lote completo."""
        for run in self:
            for slip in run.slip_ids:
                slip.action_cancel()
                slip.unlink()
            run.write({'state': 'draft'})

    # ================================================================
    # SMART BUTTONS
    # ================================================================

    def action_open_payslips(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Nóminas Electrónicas'),
            'res_model': 'hr.payslip.edi',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.slip_ids.ids)],
        }

    def action_open_generate_wizard(self):
        """Abre el wizard para generar nóminas electrónicas."""
        self.ensure_one()
        # Si hay lote origen, usar sus fechas
        if self.payslip_run_source_id:
            df = self.payslip_run_source_id.date_start
            dt = self.payslip_run_source_id.date_end
        else:
            df = self.date_start
            dt = self.date_end
        return {
            'type': 'ir.actions.act_window',
            'name': _('Generar Nóminas Electrónicas'),
            'res_model': 'hr.payslip.edi.employees',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_payslip_run_id': self.id,
                'default_date_from': df,
                'default_date_to': dt,
            },
        }

    # ================================================================
    # ENVÍO SELECTIVO DIAN
    # ================================================================

    def action_open_selective_dian(self):
        """Abre wizard para envío selectivo de documentos a DIAN."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Envío Selectivo DIAN'),
            'res_model': 'hr.payslip.edi.selective.dian',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_run_id': self.id,
            },
        }

    # ================================================================
    # AJUSTES MASIVOS (FASE 3)
    # ================================================================

    def action_create_batch_adjustments(self):
        """Abre wizard de ajuste masivo con los exitosos del lote preseleccionados."""
        self.ensure_one()
        exitosos = self.slip_ids.filtered(
            lambda s: s.state_dian == 'exitoso' and not s.credit_note
        )
        if not exitosos:
            raise UserError(_('No hay documentos exitosos en este lote para ajustar.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Crear Ajustes Masivos'),
            'res_model': 'hr.payslip.edi.batch.adjustment',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_source_ids': [(6, 0, exitosos.ids)],
                'default_new_run_name': _('Ajustes - %s') % self.name,
            },
        }

    def action_detect_adjustments_needed(self):
        """Detecta documentos del lote que podrían necesitar ajuste."""
        self.ensure_one()
        EdiModel = self.env['hr.payslip.edi']
        candidates = EdiModel.detect_adjustment_candidates(
            domain=[('payslip_run_id', '=', self.id)]
        )
        if not candidates:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sin ajustes necesarios'),
                    'message': _('No se detectaron documentos que requieran ajuste en este lote.'),
                    'type': 'info',
                    'sticky': False,
                }
            }

        candidate_ids = [c['edi_id'] for c in candidates]

        # Postear razones en el chatter del lote
        reasons_text = []
        for c in candidates:
            edi = EdiModel.browse(c['edi_id'])
            reasons_text.append(
                '<b>%s</b> (%s): %s' % (
                    edi.employee_id.name, edi.number,
                    '; '.join(c['reasons'])
                )
            )
        self.message_post(
            body=_(
                '<strong>Documentos que podrían necesitar ajuste:</strong><br/>%s'
            ) % '<br/>'.join(reasons_text),
            message_type='comment',
            subtype_xmlid='mail.mt_note',
        )

        return {
            'type': 'ir.actions.act_window',
            'name': _('Crear Ajustes Masivos'),
            'res_model': 'hr.payslip.edi.batch.adjustment',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_source_ids': [(6, 0, candidate_ids)],
                'default_new_run_name': _('Ajustes Detectados - %s') % self.name,
            },
        }

    # ================================================================
    # CONSTRAINTS
    # ================================================================

    def unlink(self):
        if any(run.state != 'draft' for run in self):
            raise UserError(_('Solo puede eliminar lotes en estado borrador.'))
        if any(slip.state not in ('draft', 'cancel') for slip in self.mapped('slip_ids')):
            raise UserError(_('Solo puede eliminar lotes con nóminas en borrador o canceladas.'))
        return super().unlink()
