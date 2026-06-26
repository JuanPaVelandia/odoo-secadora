# -*- coding: utf-8 -*-
import base64
import logging

from dateutil.relativedelta import relativedelta
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

class HrPayslipRun(models.Model):
    _inherit = 'hr.payslip.run'

    # v19 core usa Ready/Done/Paid/Cancelled (3 estados + cancel). ColombiaChef
    # v18 tenía Nuevo/Confirmado/Listo/Pagado (4 estados). Añadimos '02b_done'
    # como estado intermedio entre Confirmado y Pagado y renombramos las labels.
    # Usamos selection_add para evitar warning "use selection_add instead";
    # entradas con keys existentes solo relabel; '02b_done' es nueva con
    # ondelete='set default' para v19 compliance.
    state = fields.Selection(
        selection_add=[
            ('01_ready', 'Nuevo'),
            ('02_close', 'Confirmado'),
            ('02b_done', 'Listo'),
            ('03_paid', 'Pagado'),
            ('04_cancel', 'Cancelado'),
        ],
        ondelete={'02b_done': 'set default'},
    )

    def action_confirm(self):
        """v18 UX: 'Confirmar' = computar (slips quedan draft con lineas), NO valida.
        El lote pasa a '02_close' (Confirmado) via _compute_state al detectar
        slips con line_ids. Para validar y crear asiento contable, el usuario
        debe usar 'Marcar como Listo' (action_set_done).
        """
        draft_slips = self.slip_ids.filtered(lambda s: s.state == 'draft')
        if draft_slips:
            draft_slips.compute_sheet()

    def action_set_done(self):
        """Transicion v18 'done' (Listo): valida los slips computados y crea
        el asiento contable. action_payslip_done() en hr.payslip lleva los slips
        de 'draft' a 'validated', con _compute_state recalculando run a '02b_done'.
        """
        validatable = self.slip_ids.filtered(lambda s: s.state == 'draft' and s.line_ids)
        # v19: hr.payslip.name es required. Slips antiguos creados antes del fix
        # de compute_slip pueden tener name vacio -> default seguro antes de validar.
        for slip in validatable:
            if not slip.name:
                contract_name = slip.contract_id.name if slip.contract_id else slip.employee_id.name
                slip.name = f"Nomina de {contract_name or 'sin contrato'}"
        if validatable:
            validatable.action_payslip_done()

    def action_back_to_close(self):
        """Regresa de Listo a Confirmado por si se necesita revisión adicional."""
        return self.write({'state': '02_close'})

    @api.depends("slip_ids.state")
    def _compute_state(self):
        """Fidelidad v18 estricta:
            01_ready (Nuevo):     manual, hasta que se haga clic en Verificar
            02_close (Confirmado): manual via assign_status_verify (Verificar)
            02b_done (Listo):     slips validados (action_validate crea asientos)
            03_paid  (Pagado):    slips pagados
            04_cancel (Cancelado): todos los slips cancelados

        Transicion 01_ready -> 02_close es MANUAL en v18 (boton 'Verificar').
        Por eso este compute preserva 01_ready/02_close cuando los slips no
        fuerzan una promocion a Listo/Pagado/Cancelado.
        """
        for run in self:
            slips = run.slip_ids
            states = slips.mapped('state')
            if slips and all(s == 'cancel' for s in states):
                run.state = '04_cancel'
            elif any(s == 'paid' for s in states):
                run.state = '03_paid'
            elif any(s == 'validated' for s in states):
                run.state = '02b_done'
            elif run.state in ('01_ready', '02_close'):
                # preservar estado manual (Nuevo o Confirmado) cuando los
                # slips estan draft/sin slips. v18 requiere accion explicita
                # para Nuevo -> Confirmado (Verificar).
                pass
            else:
                run.state = '01_ready'

    period_id = fields.Many2one(
        'hr.period',
        string='Periodo de Nomina',
        domain="[('closed', '=', False)]"
    )
    @api.model
    def _get_default_structure(self):
        return self.env['hr.payroll.structure'].search([('process','=','nomina')],limit=1)

    time_process = fields.Char(string='Tiempo ejecución')
    observations = fields.Text('Observaciones')
    definitive_plan = fields.Boolean(string='Plano definitivo generado')
    hr_payslip_line_ids = fields.One2many('hr.payslip.line', 'run_id')
    move_line_ids = fields.One2many('account.move.line', 'run_id')
    date_liquidacion = fields.Date('Fecha liquidación de contrato')
    date_prima = fields.Date('Fecha liquidación de prima')
    date_cesantias = fields.Date('Fecha liquidación de cesantías')
    pay_cesantias_in_payroll = fields.Boolean('¿Liquidar Interese de cesantia en nómina?')
    pay_primas_in_payroll = fields.Boolean('¿Liquidar Primas en nómina?')
    structure_id = fields.Many2one('hr.payroll.structure', string='Tipo de nomina', default=_get_default_structure)
    struct_process = fields.Selection(related='structure_id.process', string='Proceso', store=True)
    method_schedule_pay  = fields.Selection([('bi-weekly', 'Quincenal'),
                                            ('monthly', 'Mensual'),
                                            ('other', 'Ambos')], 'Frecuencia de Pago', default='other')
    analytic_account_ids = fields.Many2many('account.analytic.account', string='Cuentas analíticas')
    state_contract = fields.Selection([('open','En Proceso'),('finished','Finalizado Por Liquidar')], string='Estado Contrato', default='open')
    settle_payroll_concepts = fields.Boolean('Liquida conceptos de nómina', default=True)
    novelties_payroll_concepts = fields.Boolean('Liquida conceptos de novedades', default=True)
    prima_run_reverse_id = fields.Many2one('hr.payslip.run', string='Lote de prima a ajustar')
    account_move_count = fields.Integer(compute='_compute_account_move_count')
    number = fields.Char(string='Número', readonly=True, copy=False)
    email_state = fields.Selection([
        ('draft', 'Pendiente'),
        ('sending', 'En Proceso'),
        ('sent', 'Enviado'),
        ('failed', 'Con Errores')
    ], string='Estado de Envío', default='draft', tracking=True)
    email_count = fields.Integer(string='Total Emails', compute='_compute_email_stats')
    email_sent = fields.Integer(string='Enviados', compute='_compute_email_stats')
    email_failed = fields.Integer(string='Fallidos', compute='_compute_email_stats')
    failed_payslips = fields.Text(string='Nóminas Fallidas', compute='_compute_email_stats')
    sequence_prefix = fields.Char(compute='_compute_sequence_prefix', store=True)
    is_credit_note = fields.Boolean('Nota de Crédito', default=False)
    employee_count = fields.Integer(compute='_compute_employee_count', string='Número de Empleados')
    payslip_count = fields.Integer(compute='_compute_payslip_count', string='Número de Nóminas')
    contract_count = fields.Integer(compute='_compute_counts')
    leave_count = fields.Integer(compute='_compute_counts')
    confirmed_payslip_count = fields.Integer(compute='_compute_counts')
    draft_payslip_count = fields.Integer(compute='_compute_counts')
    paid_payslip_count = fields.Integer(compute='_compute_counts')
    novelty_count = fields.Integer(compute='_compute_counts', string='Novedades')
    total_basic = fields.Monetary(compute='_compute_totals', string='Total Básico', currency_field='currency_id')
    total_transport = fields.Monetary(compute='_compute_totals', string='Total Auxilio Transporte', currency_field='currency_id')
    total_earnings = fields.Monetary(compute='_compute_totals', string='Total Devengos', currency_field='currency_id')
    total_deductions = fields.Monetary(compute='_compute_totals', string='Total Deducciones', currency_field='currency_id')
    total_net = fields.Monetary(compute='_compute_totals', string='Total Neto', currency_field='currency_id')
    total_social_security = fields.Monetary(compute='_compute_totals', string='Total Seguridad Social', currency_field='currency_id')
    total_parafiscales = fields.Monetary(compute='_compute_totals', string='Total Parafiscales', currency_field='currency_id')
    total_provisions = fields.Monetary(compute='_compute_totals', string='Total Provisiones', currency_field='currency_id')
    total_other_earnings = fields.Monetary(compute='_compute_totals', string='Otros Devengos', currency_field='currency_id')
    total_other_deductions = fields.Monetary(compute='_compute_totals', string='Otras Deducciones', currency_field='currency_id')
    total_company_contributions = fields.Monetary(compute='_compute_totals', string='Aportes Empresa', currency_field='currency_id')
    total_overtime = fields.Monetary(compute='_compute_totals', string='Total Horas Extra', currency_field='currency_id')
    total_absences = fields.Monetary(compute='_compute_totals', string='Total Ausencias', currency_field='currency_id')
    total_loans = fields.Monetary(compute='_compute_totals', string='Total Préstamos', currency_field='currency_id')
    total_health = fields.Monetary(compute='_compute_totals', string='Total Salud', currency_field='currency_id')
    total_pension = fields.Monetary(compute='_compute_totals', string='Total Pensión', currency_field='currency_id')
    total_arl = fields.Monetary(compute='_compute_totals', string='Total ARL', currency_field='currency_id')
    total_retention = fields.Monetary(compute='_compute_totals', string='Total Retención', currency_field='currency_id')
    total_prima = fields.Monetary(compute='_compute_totals', string='Total Prima', currency_field='currency_id')
    total_cesantias = fields.Monetary(compute='_compute_totals', string='Total Cesantías', currency_field='currency_id')
    total_vacaciones = fields.Monetary(compute='_compute_totals', string='Total Vacaciones', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', string='Moneda')
    lines_summary_html = fields.Html(compute='_compute_lines_summary_html', string='Resumen de Líneas', sanitize=False)
    novelties_summary_html = fields.Html(compute='_compute_novelties_summary_html', string='Resumen de Novedades', sanitize=False)
    payslips_summary_html = fields.Html(compute='_compute_payslips_summary_html', string='Resumen de Nóminas', sanitize=False)
    department_summary_html = fields.Html(compute='_compute_department_summary_html', string='Resumen por Departamento', sanitize=False)
    summary_widget = fields.Binary(string='Resumen', compute='_compute_summary_widget', store=True)

    # Campo para mostrar historial de cambios salariales de todos los contratos del lote
    batch_change_wage_ids = fields.Many2many(
        'hr.contract.change.wage',
        compute='_compute_batch_change_wage_ids',
        string='Cambios Salariales del Lote',
        help='Historial de cambios salariales de todos los contratos incluidos en este lote'
    )

    @api.depends('slip_ids', 'slip_ids.contract_id', 'slip_ids.contract_id.change_wage_ids')
    def _compute_batch_change_wage_ids(self):
        for run in self:
            contracts = run.slip_ids.mapped('contract_id')
            run.batch_change_wage_ids = contracts.mapped('change_wage_ids')

    @api.depends('slip_ids', 'slip_ids.line_ids', 'slip_ids.line_ids.total', 'slip_ids.state',
                 'slip_ids.net_wage', 'slip_ids.employee_id')
    def _compute_summary_widget(self):
        import hashlib
        import json
        for record in self:
            # Para registros nuevos (NewId no es JSON serializable) usa id=0.
            record_id = record.id if isinstance(record.id, int) else 0
            data = {
                'id': record_id,
                'count': len(record.slip_ids),
                'net': sum(record.slip_ids.mapped('net_wage') or [0]),
                'states': ','.join(record.slip_ids.mapped('state') or []),
                'ts': fields.Datetime.now().isoformat() if record.slip_ids else ''
            }
            json_data = json.dumps(data, sort_keys=True)
            hash_value = hashlib.md5(json_data.encode()).hexdigest()
            record.summary_widget = hash_value.encode('utf-8')
    vacation_count = fields.Html(
        'Alerta de Vacaciones', 
        compute='_compute_warning_messages',
        sanitize=False,
        help='Muestra conteo de vacaciones pendientes y contratos por liquidar'
    )
    
    contract_state_warning = fields.Html(
        'Alerta de Contratos',
        compute='_compute_warning_messages',
        sanitize=False,
        help='Alerta sobre el estado de los contratos seleccionados'
    )
    liquidate_contract = fields.Boolean(
        '¿Liquidar Contratos?',
        default=False,
        help='Generar liquidación para contratos terminados'
    )
    liquidate_vacations = fields.Boolean(
        '¿Liquidar Vacaciones en Nómina?',
        default=False,
        help='Incluir liquidación de vacaciones en la nómina'
    )
    liquidation_structure_id = fields.Many2one(
        'hr.payroll.structure',
        string='Estructura de Liquidación',
        domain="[('process', '=', 'contrato')]",
        help='Estructura a usar para la liquidación de contratos'
    )

    @api.onchange('liquidate_contract')
    def _onchange_liquidate_contract(self):
        if self.liquidate_contract and not self.liquidation_structure_id:
            default_structure = self.env['hr.payroll.structure'].search(
                [('process', '=', 'contrato')], limit=1)
            self.liquidation_structure_id = default_structure


    def _compute_warning_messages(self):
        for run in self:
            vacation_count = []
            
            contracts = self.env['hr.contract'].search([('state', 'in', ('finished','close','open'))])

            if contracts:
                employee_ids = contracts.mapped('employee_id').ids
                
                base_domain = [
                    ('employee_id', 'in', employee_ids),
                    ('state', '=', 'validate'),
                    '|',
                        '&', ('request_date_from', '<=', run.date_start), ('request_date_to', '>=', run.date_start),
                        '&', ('request_date_from', '<=', run.date_end), ('request_date_to', '>=', run.date_start)
                ]

                time_leaves = self.env['hr.leave'].search(base_domain + [
                    ('holiday_status_id.is_vacation', '=', True),
                    ('holiday_status_id.is_vacation_money', '=', False),
                ])

                money_leaves = self.env['hr.leave'].search(base_domain + [
                    ('holiday_status_id.is_vacation_money', '=', True),
                ])

                unpaid_time_leaves = time_leaves.filtered(
                    lambda l: any(
                        line.state == 'validated' and line.state != 'paid' and
                        (line.date >= run.date_start and line.date <= run.date_end)
                        for line in l.line_ids
                    )
                )

                unpaid_money_leaves = money_leaves.filtered(
                    lambda l: any(
                        line.state == 'validated' and line.state != 'paid' and
                        (line.date >= run.date_start and line.date <= run.date_end)
                        for line in l.line_ids
                    )
                )

                base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
                action_id = self.env.ref('hr_holidays.hr_leave_action_action_approve_department').id
                menu_id = self.env.ref('hr_holidays.menu_hr_holidays_root').id

                if unpaid_time_leaves:
                    leave_ids = ','.join(map(str, unpaid_time_leaves.ids))
                    time_url = f"{base_url}/web#action={action_id}&menu_id={menu_id}&view_type=list&model=hr.leave&domain=[('id', 'in', [{leave_ids}])]"
                    vacation_count.append(
                        f"⚠️ <a href='{time_url}' target='_blank'>{len(unpaid_time_leaves)} Vacaciones en tiempo pendientes</a>"
                    )

                if unpaid_money_leaves:
                    money_ids = ','.join(map(str, unpaid_money_leaves.ids))
                    money_url = f"{base_url}/web#action={action_id}&menu_id={menu_id}&view_type=list&model=hr.leave&domain=[('id', 'in', [{money_ids}])]"
                    vacation_count.append(
                        f"💰 <a href='{money_url}' target='_blank'>{len(unpaid_money_leaves)} Vacaciones en dinero pendientes</a>"
                    )

                contracts_without_liquidation = contracts.filtered(
                    lambda c: (c.state in ['finished', 'close'] and not c.retirement_date) or 
                            (c.state == 'open' and c.date_end and c.date_end <= run.date_end)
                ).filtered(
                    lambda c: not self.env['hr.payslip'].search([
                        ('employee_id', '=', c.employee_id.id),
                        ('struct_id.process', '=', 'liquidacion'),
                        ('state', 'in', ['done', 'paid']),
                        ('date_from', '<=', c.date_end or run.date_end),
                        ('date_to', '>=', c.date_end or run.date_end),
                    ])
                )

                if contracts_without_liquidation:
                    contract_action = self.env.ref('hr_contract.action_hr_contract').id
                    contract_menu = {}
                    contract_ids = ','.join(map(str, contracts_without_liquidation.ids))
                    contract_url = f"{base_url}/web#action={contract_action}&menu_id={contract_menu}&view_type=list&model=hr.contract&domain=[('id', 'in', [{contract_ids}])]"
                    
                    vacation_count.append(
                        f"🔔 <a href='{contract_url}' target='_blank'>{len(contracts_without_liquidation)} Contratos pendientes por liquidar</a>"
                    )

            run.vacation_count = Markup("<br/>".join(vacation_count)) if vacation_count else False
            run.contract_state_warning = Markup(
                "⚠️ Se encontraron registros que requieren atención. "
                "Haga clic en los enlaces arriba para revisar."
            ) if vacation_count else False

    @api.depends('slip_ids', 'slip_ids.line_ids', 'slip_ids.line_ids.total')
    def _compute_totals(self):
        for record in self:
            lines = record.slip_ids.mapped('line_ids')
            record.total_basic = sum(lines.filtered(lambda l: l.category_code == 'BASIC').mapped('total'))
            record.total_transport = sum(lines.filtered(lambda l: l.category_code == 'AUX' or l.code in ('AUXTRANS', 'AUXTRANSPORTE', 'AUX_TRANSPORTE', 'TRANS001', 'AUX000', 'AUX00C')).mapped('total'))

            # v19 fix DEDUCCIONES=$0:
            # En v18 las categorías de deducción (SSOCIAL, RET, etc.) caian dentro del
            # rango DED por configuración heredada. En v19, _AFECTA_TOTALES_DED_CATS
            # solo incluye 'DED' literal -> afecta_totales_effective='ninguno' para
            # Salud/Pension/Retencion -> total_deductions queda en 0.
            #
            # Heuristica robusta: las lineas de deduccion tienen total<0, las de devengo
            # total>0. Excluimos las lineas sentinel (TOTALDEV/TOTALDED/NET) para no
            # double-counting. Si el sumatorio directo es 0, fallback a sentinels.
            totaldev_lines = lines.filtered(lambda l: l.category_code == 'TOTALDEV' or l.code == 'TOTALDEV')
            totalded_lines = lines.filtered(lambda l: l.category_code == 'TOTALDED' or l.code == 'TOTALDED')
            net_lines = lines.filtered(lambda l: l.category_code in ('NET', 'NETO') or l.code in ('NET', 'NETO'))
            sentinel_codes = ('TOTALDEV', 'TOTALDED', 'NET', 'NETO')
            real_lines = lines.filtered(
                lambda l: l.category_code not in sentinel_codes and l.code not in sentinel_codes
            )

            # Preferimos afecta_totales_effective si esta correctamente seteado;
            # si no, caemos a clasificacion por signo.
            earnings_by_flag = sum(real_lines.filtered(lambda l: l.afecta_totales_effective == 'devengo').mapped('total'))
            deductions_by_flag = sum(real_lines.filtered(lambda l: l.afecta_totales_effective == 'deduccion').mapped('total'))
            earnings_by_sign = sum(real_lines.filtered(lambda l: l.total > 0).mapped('total'))
            deductions_by_sign = sum(real_lines.filtered(lambda l: l.total < 0).mapped('total'))

            record.total_earnings = earnings_by_flag or earnings_by_sign or sum(totaldev_lines.mapped('total'))
            record.total_deductions = deductions_by_flag or deductions_by_sign or sum(totalded_lines.mapped('total'))
            record.total_net = sum(net_lines.mapped('total')) if net_lines else (record.total_earnings + record.total_deductions)
            record.total_social_security = sum(lines.filtered(lambda l: l.category_code in ('SSOCIAL', 'SS', 'SS_EMP')).mapped('total'))
            record.total_parafiscales = sum(lines.filtered(lambda l: l.category_code in ('PARF', 'PARAFISCALES')).mapped('total'))
            record.total_provisions = sum(lines.filtered(lambda l: l.category_code == 'PROV').mapped('total'))
            record.total_other_earnings = sum(lines.filtered(
                lambda l: l.afecta_totales_effective == 'devengo' and l.category_code not in ('BASIC', 'HEYREC', 'AUS')
            ).mapped('total'))
            record.total_other_deductions = sum(lines.filtered(
                lambda l: l.afecta_totales_effective == 'deduccion' and l.category_code not in ('SSOCIAL', 'SS', 'SS_EMP', 'PARF')
            ).mapped('total'))
            record.total_company_contributions = sum(lines.filtered(lambda l: l.category_code in ('COMP', 'CONTRIBUCION')).mapped('total'))
            record.total_overtime = sum(lines.filtered(lambda l: l.category_code in ('HEYREC', 'HE') or l.object_type == 'overtime').mapped('total'))
            record.total_absences = sum(lines.filtered(lambda l: l.category_code in ('AUS', 'AUSENCIA') or l.object_type in ('absence', 'leave')).mapped('total'))
            record.total_loans = sum(lines.filtered(lambda l: l.object_type == 'loan').mapped('total'))
            # Salud: SSOCIAL001 o código que contenga EPS/SALUD
            record.total_health = sum(lines.filtered(lambda l: l.code == 'SSOCIAL001' or 'EPS' in (l.code or '') or 'SALUD' in (l.code or '').upper()).mapped('total'))
            # Pensión: SSOCIAL002, SSOCIAL003, SSOCIAL004 o código que contenga PENSION
            record.total_pension = sum(lines.filtered(lambda l: l.code in ('SSOCIAL002', 'SSOCIAL003', 'SSOCIAL004') or 'PENSION' in (l.code or '').upper()).mapped('total'))
            record.total_arl = sum(lines.filtered(lambda l: 'ARL' in (l.code or '').upper()).mapped('total'))
            # Retención: categoría RET o código con RETEFUENTE/RTEFTE
            record.total_retention = sum(lines.filtered(lambda l: l.category_code in ('RET', 'RETEFUENTE') or 'RTEFTE' in (l.code or '').upper() or 'RETEFUENTE' in (l.code or '').upper()).mapped('total'))
            record.total_prima = sum(lines.filtered(lambda l: l.object_type == 'prima').mapped('total'))
            record.total_cesantias = sum(lines.filtered(lambda l: l.object_type in ('cesantias', 'int_cesantias')).mapped('total'))
            record.total_vacaciones = sum(lines.filtered(lambda l: l.object_type == 'vacation').mapped('total'))

    @api.depends('slip_ids', 'slip_ids.line_ids', 'total_earnings', 'total_deductions', 'total_net',
                 'total_basic', 'total_transport', 'total_overtime', 'total_health', 'total_pension',
                 'total_provisions', 'total_social_security', 'total_parafiscales', 'total_arl',
                 'total_prima', 'total_cesantias', 'total_vacaciones', 'total_company_contributions',
                 'employee_count', 'payslip_count')
    def _compute_lines_summary_html(self):
        for record in self:
            currency = record.currency_id or self.env.company.currency_id
            symbol = currency.symbol or '$'

            # Calcular provisiones empresa
            # Códigos típicos: PRV_PRIM, PRV_CES, PRV_ICES, PRV_VAC
            lines = record.slip_ids.mapped('line_ids')
            prov_lines = lines.filtered(lambda l: (l.category_code or '') == 'PROV')

            # Prima: códigos que contengan PRIM (PRV_PRIM, PRIMA, etc.)
            prima_emp = sum(prov_lines.filtered(lambda l: 'PRIM' in (l.code or '').upper()).mapped('total'))

            # Cesantías: códigos que contengan CES pero NO ICES (PRV_CES, CESANTIAS, etc.)
            cesantias_emp = sum(prov_lines.filtered(lambda l: 'CES' in (l.code or '').upper() and 'ICES' not in (l.code or '').upper()).mapped('total'))

            # Intereses Cesantías: códigos que contengan ICES o (INT + CES) (PRV_ICES, INT_CES, etc.)
            int_cesantias_emp = sum(prov_lines.filtered(lambda l: 'ICES' in (l.code or '').upper() or ('INT' in (l.code or '').upper() and 'CES' in (l.code or '').upper())).mapped('total'))

            # Vacaciones: códigos que contengan VAC (PRV_VAC, VACACIONES, etc.)
            vacaciones_emp = sum(prov_lines.filtered(lambda l: 'VAC' in (l.code or '').upper()).mapped('total'))

            # Seguridad social empresa - buscar en múltiples categorías
            # Busca categorías SSOCIAL_EMP, SS_EMP, COMP, CONTRIBUCION o códigos con sufijo _EMP
            emp_categories = ('SSOCIAL_EMP', 'SS_EMP', 'COMP', 'CONTRIBUCION', 'APORTES_EMP')

            # Salud empresa: categorías de empresa o códigos con SALUD_EMP, EPS_EMP
            salud_emp = sum(lines.filtered(lambda l:
                (l.category_code in emp_categories and ('SALUD' in (l.code or '').upper() or 'EPS' in (l.code or '').upper())) or
                ('SALUD_EMP' in (l.code or '').upper() or 'EPS_EMP' in (l.code or '').upper())
            ).mapped('total'))

            # Pensión empresa: categorías de empresa o códigos con PENSION_EMP
            pension_emp = sum(lines.filtered(lambda l:
                (l.category_code in emp_categories and 'PENSION' in (l.code or '').upper()) or
                'PENSION_EMP' in (l.code or '').upper() or 'AFP_EMP' in (l.code or '').upper()
            ).mapped('total'))

            # ARL: cualquier línea con ARL en el código
            arl_emp = sum(lines.filtered(lambda l: 'ARL' in (l.code or '').upper()).mapped('total'))

            # Parafiscales
            sena = sum(lines.filtered(lambda l: 'SENA' in (l.code or '').upper()).mapped('total'))
            icbf = sum(lines.filtered(lambda l: 'ICBF' in (l.code or '').upper()).mapped('total'))
            ccf = sum(lines.filtered(lambda l: 'CCF' in (l.code or '').upper() or 'CAJA' in (l.code or '').upper()).mapped('total'))

            html = f"""
            <div style="padding: 15px;">
                <!-- Fila Principal: Neto, Devengos, Deducciones -->
                <div class="row" style="background: #3949AB; border-radius: 10px; padding: 20px; margin-bottom: 15px; color: white;">
                    <div class="col-md-4 text-center" style="border-right: 1px solid rgba(255,255,255,0.3);">
                        <div style="font-size: 13px; opacity: 0.9;">TOTAL NETO A PAGAR</div>
                        <div style="font-size: 28px; font-weight: bold;">{symbol} {record.total_net:,.0f}</div>
                        <div style="font-size: 11px; opacity: 0.8;">{record.employee_count} empleados | {record.payslip_count} nóminas</div>
                    </div>
                    <div class="col-md-4 text-center" style="border-right: 1px solid rgba(255,255,255,0.3);">
                        <div style="font-size: 13px; opacity: 0.9;"><i class="fa fa-plus-circle"></i> DEVENGOS</div>
                        <div style="font-size: 22px; font-weight: bold; color: #90EE90;">{symbol} {record.total_earnings:,.0f}</div>
                        <div style="font-size: 10px; opacity: 0.8;">
                            Básico: {symbol} {record.total_basic:,.0f} | Aux. Trans: {symbol} {record.total_transport:,.0f} | H. Extra: {symbol} {record.total_overtime:,.0f}
                        </div>
                    </div>
                    <div class="col-md-4 text-center">
                        <div style="font-size: 13px; opacity: 0.9;"><i class="fa fa-minus-circle"></i> DEDUCCIONES</div>
                        <div style="font-size: 22px; font-weight: bold; color: #FFB6C1;">{symbol} {record.total_deductions:,.0f}</div>
                        <div style="font-size: 10px; opacity: 0.8;">
                            Salud: {symbol} {record.total_health:,.0f} | Pensión: {symbol} {record.total_pension:,.0f} | Ret: {symbol} {record.total_retention:,.0f}
                        </div>
                    </div>
                </div>

                <!-- Fila Secundaria: Provisiones y Seguridad Social Empresa -->
                <div class="row">
                    <!-- Provisiones -->
                    <div class="col-md-6">
                        <div style="background: #E8EAF6; border-radius: 8px; padding: 15px; height: 100%;">
                            <div style="font-size: 13px; font-weight: bold; color: #3949AB; margin-bottom: 10px;">
                                <i class="fa fa-calendar-check-o"></i> PROVISIONES
                            </div>
                            <div class="row" style="font-size: 11px; color: #424242;">
                                <div class="col-6">
                                    <div><strong>Prima:</strong> {symbol} {prima_emp:,.0f}</div>
                                    <div><strong>Cesantías:</strong> {symbol} {cesantias_emp:,.0f}</div>
                                </div>
                                <div class="col-6">
                                    <div><strong>Int. Cesantías:</strong> {symbol} {int_cesantias_emp:,.0f}</div>
                                    <div><strong>Vacaciones:</strong> {symbol} {vacaciones_emp:,.0f}</div>
                                </div>
                            </div>
                            <div style="font-size: 14px; font-weight: bold; color: #3949AB; margin-top: 8px; text-align: right;">
                                Total: {symbol} {record.total_provisions:,.0f}
                            </div>
                        </div>
                    </div>

                    <!-- Seguridad Social y Parafiscales Empresa -->
                    <div class="col-md-6">
                        <div style="background: #FFF3E0; border-radius: 8px; padding: 15px; height: 100%;">
                            <div style="font-size: 13px; font-weight: bold; color: #E65100; margin-bottom: 10px;">
                                <i class="fa fa-building"></i> APORTES EMPRESA
                            </div>
                            <div class="row" style="font-size: 11px; color: #424242;">
                                <div class="col-6">
                                    <div><strong>Salud Emp:</strong> {symbol} {salud_emp:,.0f}</div>
                                    <div><strong>Pensión Emp:</strong> {symbol} {pension_emp:,.0f}</div>
                                    <div><strong>ARL:</strong> {symbol} {arl_emp:,.0f}</div>
                                </div>
                                <div class="col-6">
                                    <div><strong>SENA:</strong> {symbol} {sena:,.0f}</div>
                                    <div><strong>ICBF:</strong> {symbol} {icbf:,.0f}</div>
                                    <div><strong>CCF:</strong> {symbol} {ccf:,.0f}</div>
                                </div>
                            </div>
                            <div style="font-size: 14px; font-weight: bold; color: #E65100; margin-top: 8px; text-align: right;">
                                Total: {symbol} {record.total_company_contributions + record.total_parafiscales:,.0f}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            """
            record.lines_summary_html = html

    @api.depends('novelty_count')
    def _compute_novelties_summary_html(self):
        for record in self:
            record.novelties_summary_html = f"<p>Total novedades: {record.novelty_count}</p>"

    @api.depends('slip_ids', 'slip_ids.state')
    def _compute_payslips_summary_html(self):
        for record in self:
            draft = len(record.slip_ids.filtered(lambda s: s.state == 'draft'))
            verify = len(record.slip_ids.filtered(lambda s: s.state == 'draft'))
            done = len(record.slip_ids.filtered(lambda s: s.state == 'validated'))
            paid = len(record.slip_ids.filtered(lambda s: s.state == 'paid'))
            html = f"<p>Borrador: {draft} | Verificar: {verify} | Confirmado: {done} | Pagado: {paid}</p>"
            record.payslips_summary_html = html

    @api.depends('slip_ids', 'slip_ids.employee_id', 'slip_ids.line_ids')
    def _compute_department_summary_html(self):
        for record in self:
            record.department_summary_html = "<p>Ver pestaña Resumen Detallado</p>"

    @api.depends('slip_ids', 'slip_ids.state', 'slip_ids.paid', 'slip_ids.leave_ids')
    def _compute_counts(self):
        for record in self:
            record.contract_count = len(record.slip_ids.mapped('contract_id'))
            leaves = record.slip_ids.mapped('leave_ids.leave_id').filtered(lambda l: l.state == 'validate')
            record.leave_count = len(leaves)
            record.confirmed_payslip_count = len(record.slip_ids.filtered(lambda x: x.state == 'validated'))
            record.draft_payslip_count = len(record.slip_ids.filtered(lambda x: x.state == 'draft'))
            record.paid_payslip_count = len(record.slip_ids.filtered(lambda x: x.state == ('paid')))
            # Contar novedades de los empleados del lote
            employee_ids = record.slip_ids.mapped('employee_id').ids
            record.novelty_count = self.env['hr.novelties.different.concepts'].search_count([
                ('employee_id', 'in', employee_ids)
            ]) if employee_ids else 0

    def get_summary_data(self):
        """Devuelve datos estructurados para el widget de resumen."""
        self.ensure_one()

        # Agrupar por departamento
        departments_data = {}
        totals = {
            'basic': 0, 'earnings': 0, 'deductions': 0, 'net': 0,
            'health': 0, 'pension': 0, 'retention': 0, 'transport': 0
        }
        categories_data = {}
        employee_ids = self.slip_ids.mapped('employee_id').ids

        # Obtener novedades relacionadas
        novelties = []
        if employee_ids:
            # Novedades por conceptos
            novelties_records = self.env['hr.novelties.different.concepts'].search([
                ('employee_id', 'in', employee_ids),
                ('state', 'in', ['approved', 'draft'])
            ], limit=50)
            for nov in novelties_records:
                novelties.append({
                    'id': nov.id,
                    'type': 'novelty',
                    'type_name': 'Novedad',
                    'icon': 'fa-pencil-square-o',
                    'color': '#3b82f6',
                    'employee': nov.employee_id.name,
                    'employee_id': nov.employee_id.id,
                    'description': nov.salary_rule_id.name if nov.salary_rule_id else nov.name,
                    'amount': nov.amount,
                    'state': nov.state,
                    'date': str(nov.date) if nov.date else '',
                })

            # Préstamos activos
            loans = self.env['hr.loan'].search([
                ('employee_id', 'in', employee_ids),
                ('state', '=', 'active')
            ], limit=20)
            for loan in loans:
                novelties.append({
                    'id': loan.id,
                    'type': 'loan',
                    'type_name': 'Préstamo',
                    'icon': 'fa-money',
                    'color': '#f59e0b',
                    'employee': loan.employee_id.name,
                    'employee_id': loan.employee_id.id,
                    'description': loan.name or 'Préstamo',
                    'amount': loan.loan_amount,
                    'balance': loan.balance_amount if hasattr(loan, 'balance_amount') else 0,
                    'state': loan.state,
                    'date': str(loan.date) if hasattr(loan, 'date') and loan.date else '',
                })

            # Horas extra
            if hasattr(self.env, 'hr.overtime'):
                try:
                    overtimes = self.env['hr.overtime'].search([
                        ('employee_id', 'in', employee_ids),
                        ('state', 'in', ['validated', 'approved'])
                    ], limit=30)
                    for ot in overtimes:
                        novelties.append({
                            'id': ot.id,
                            'type': 'overtime',
                            'type_name': 'Hora Extra',
                            'icon': 'fa-clock-o',
                            'color': '#10b981',
                            'employee': ot.employee_id.name,
                            'employee_id': ot.employee_id.id,
                            'description': ot.type_overtime_id.name if hasattr(ot, 'type_overtime_id') and ot.type_overtime_id else 'Hora Extra',
                            'hours': ot.number_of_hours if hasattr(ot, 'number_of_hours') else 0,
                            'amount': ot.total if hasattr(ot, 'total') else 0,
                            'state': ot.state,
                            'date': str(ot.date) if hasattr(ot, 'date') and ot.date else '',
                        })
                except Exception:  # noqa: BLE001 – datos de dashboard opcionales, fallo no crítico
                    _logger.warning("Error obteniendo datos de horas extras para dashboard del lote %s", self.name, exc_info=True)

            # Ausencias/Vacaciones
            leaves = self.env['hr.leave'].search([
                ('employee_id', 'in', employee_ids),
                ('state', '=', 'validate')
            ], limit=30)
            for leave in leaves:
                novelties.append({
                    'id': leave.id,
                    'type': 'leave',
                    'type_name': leave.holiday_status_id.name if leave.holiday_status_id else 'Ausencia',
                    'icon': 'fa-calendar-minus-o',
                    'color': '#ef4444',
                    'employee': leave.employee_id.name,
                    'employee_id': leave.employee_id.id,
                    'description': leave.holiday_status_id.name if leave.holiday_status_id else 'Ausencia',
                    'days': leave.number_of_days if hasattr(leave, 'number_of_days') else 0,
                    'amount': leave.payroll_value if hasattr(leave, 'payroll_value') else 0,
                    'state': leave.state,
                    'date': str(leave.date_from) if leave.date_from else '',
                })

        for slip in self.slip_ids:
            dept = slip.employee_id.department_id
            dept_id = dept.id if dept else 0
            dept_name = dept.name if dept else 'Sin Departamento'

            if dept_id not in departments_data:
                departments_data[dept_id] = {
                    'id': dept_id,
                    'name': dept_name,
                    'employees': [],
                    'total_basic': 0,
                    'total_earnings': 0,
                    'total_deductions': 0,
                    'total_net': 0,
                }

            # Obtener totales directamente de las líneas TOTALDEV, TOTALDED, NET
            lines = slip.line_ids
            emp_basic = sum(lines.filtered(lambda l: l.category_code == 'BASIC').mapped('total'))

            # Usar líneas de totales directamente
            totaldev_line = lines.filtered(lambda l: l.category_code == 'TOTALDEV' or l.code == 'TOTALDEV')
            totalded_line = lines.filtered(lambda l: l.category_code == 'TOTALDED' or l.code == 'TOTALDED')
            net_line = lines.filtered(lambda l: l.category_code in ('NET', 'NETO') or l.code in ('NET', 'NETO'))

            emp_earnings = totaldev_line[0].total if totaldev_line else sum(
                lines.filtered(lambda l: l.afecta_totales_effective == 'devengo').mapped('total')
            )
            emp_deductions = totalded_line[0].total if totalded_line else sum(
                lines.filtered(lambda l: l.afecta_totales_effective == 'deduccion').mapped('total')
            )
            emp_net = net_line[0].total if net_line else (emp_earnings - abs(emp_deductions))

            # Seguridad social
            emp_health = sum(lines.filtered(lambda l: 'SALUD' in (l.code or '')).mapped('total'))
            emp_pension = sum(lines.filtered(lambda l: 'PENSION' in (l.code or '')).mapped('total'))
            emp_retention = sum(lines.filtered(lambda l: 'RET' in (l.code or '')).mapped('total'))

            departments_data[dept_id]['employees'].append({
                'id': slip.employee_id.id,
                'name': slip.employee_id.name,
                'identification': slip.employee_id.identification_id or '',
                'payslip_id': slip.id,
                'state': slip.state,
                'basic': emp_basic,
                'earnings': emp_earnings,
                'deductions': emp_deductions,
                'net': emp_net,
            })

            # Acumular totales del departamento
            departments_data[dept_id]['total_basic'] += emp_basic
            departments_data[dept_id]['total_earnings'] += emp_earnings
            departments_data[dept_id]['total_deductions'] += emp_deductions
            departments_data[dept_id]['total_net'] += emp_net

            # Acumular totales generales
            totals['basic'] += emp_basic
            totals['earnings'] += emp_earnings
            totals['deductions'] += emp_deductions
            totals['net'] += emp_net
            totals['health'] += emp_health
            totals['pension'] += emp_pension
            totals['retention'] += emp_retention

            # Agrupar por categoría
            for line in lines.filtered(lambda l: l.category_code not in ('TOTALDEV', 'TOTALDED', 'NET', 'NETO', 'GROSS')):
                cat_code = line.category_code or 'OTROS'
                cat_name = line.category_id.name if line.category_id else 'Otros'
                if cat_code not in categories_data:
                    categories_data[cat_code] = {
                        'code': cat_code,
                        'name': cat_name,
                        'type': line.dev_or_ded or 'devengo',
                        'total': 0,
                    }
                categories_data[cat_code]['total'] += line.total

        # Ordenar categorías por total
        categories_list = sorted(categories_data.values(), key=lambda x: abs(x['total']), reverse=True)[:8]

        # Agrupar novedades por tipo
        novelties_by_type = {}
        for nov in novelties:
            nov_type = nov['type']
            if nov_type not in novelties_by_type:
                novelties_by_type[nov_type] = {
                    'type': nov_type,
                    'type_name': nov['type_name'],
                    'icon': nov['icon'],
                    'color': nov['color'],
                    'items': [],
                    'total': 0,
                    'count': 0,
                }
            novelties_by_type[nov_type]['items'].append(nov)
            novelties_by_type[nov_type]['total'] += nov.get('amount', 0)
            novelties_by_type[nov_type]['count'] += 1

        return {
            'departments': list(departments_data.values()),
            'totals': totals,
            'categories': categories_list,
            'novelties': list(novelties_by_type.values()),
        }

    def action_view_contracts(self):
        return {
            'name': 'Contratos',
            'view_mode': 'list,form',
            'res_model': 'hr.contract',
            'type': 'ir.actions.act_window',
            'domain': [('id', 'in', self.slip_ids.mapped('contract_id').ids)],
        }

    def action_view_leaves(self):
        return {
            'name': 'Incapacidades',
            'view_mode': 'list,form',
            'res_model': 'hr.leave',
            'type': 'ir.actions.act_window',
            'domain': [('id', 'in', self.slip_ids.mapped('leave_ids.leave_id').filtered(lambda l: l.state == 'validate').ids)],
        }

    def _get_lavish_payslip_views(self):
        """Devuelve el par (list, form) para hr.payslip usando el list view propio
        sin js_class custom v19 (que causa lista en blanco)."""
        list_view = self.env.ref('lavish_hr_payroll.view_hr_payslip_tree_lavish', raise_if_not_found=False)
        return [
            (list_view.id if list_view else False, 'list'),
            (False, 'form'),
        ]

    def action_view_confirmed_payslips(self):
        return {
            'name': 'Nóminas Confirmadas',
            'views': self._get_lavish_payslip_views(),
            'res_model': 'hr.payslip',
            'type': 'ir.actions.act_window',
            'domain': [('id', 'in', self.slip_ids.filtered(lambda x: x.state == 'validated').ids)],
            'context': {},
        }

    def action_view_draft_payslips(self):
        return {
            'name': 'Nóminas en Borrador',
            'views': self._get_lavish_payslip_views(),
            'res_model': 'hr.payslip',
            'type': 'ir.actions.act_window',
            'domain': [('id', 'in', self.slip_ids.filtered(lambda x: x.state == 'draft').ids)],
            'context': {},
        }

    def action_view_paid_payslips(self):
        return {
            'name': 'Nóminas Pagadas',
            'views': self._get_lavish_payslip_views(),
            'res_model': 'hr.payslip',
            'type': 'ir.actions.act_window',
            'domain': [('id', 'in', self.slip_ids.filtered(lambda x: x.state == ('paid')).ids)],
            'context': {},
        }
    def _compute_employee_count(self):
        for record in self:
            record.employee_count = len(record.slip_ids.mapped('employee_id'))

    def _compute_payslip_count(self):
        for record in self:
            record.payslip_count = len(record.slip_ids)

    def action_view_employees(self):
        self.ensure_one()
        return {
            'name': 'Empleados',
            'view_mode': 'list,form',
            'res_model': 'hr.employee',
            'type': 'ir.actions.act_window',
            'domain': [('id', 'in', self.slip_ids.mapped('employee_id').ids)],
        }

    def action_view_payslips(self):
        self.ensure_one()
        return {
            'name': 'Recibos de nomina del lote',
            'views': self._get_lavish_payslip_views(),
            'res_model': 'hr.payslip',
            'type': 'ir.actions.act_window',
            'domain': [('id', 'in', self.slip_ids.ids)],
            'context': {},
        }

    def action_open_payslips(self):
        """Evita la list view enterprise con payrun card, que deja la pantalla
        desordenada/en blanco cuando falla el JS del encabezado.
        """
        self.ensure_one()
        return self.action_view_payslips()

    def action_view_novelties(self):
        """Vista de novedades del lote."""
        self.ensure_one()
        employee_ids = self.slip_ids.mapped('employee_id').ids
        return {
            'name': 'Novedades',
            'type': 'ir.actions.act_window',
            'res_model': 'hr.novelties.different.concepts',
            'view_mode': 'list,form',
            'domain': [('employee_id', 'in', employee_ids)],
        }

    def action_create_novelty(self):
        """Crear nueva novedad para empleados del lote."""
        self.ensure_one()
        employee_ids = self.slip_ids.mapped('employee_id').ids
        return {
            'name': 'Nueva Novedad',
            'type': 'ir.actions.act_window',
            'res_model': 'hr.novelties.different.concepts',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_date': self.date_start,
                'default_employee_ids': [(6, 0, [])],
                'employee_ids_domain': employee_ids,
            }
        }

    def action_view_loans(self):
        """Vista de préstamos de empleados del lote."""
        self.ensure_one()
        employee_ids = self.slip_ids.mapped('employee_id').ids
        return {
            'name': 'Préstamos',
            'type': 'ir.actions.act_window',
            'res_model': 'hr.loan',
            'view_mode': 'list,form',
            'domain': [('employee_id', 'in', employee_ids)],
        }

    def action_create_loan(self):
        """Crear nuevo préstamo."""
        self.ensure_one()
        return {
            'name': 'Nuevo Préstamo',
            'type': 'ir.actions.act_window',
            'res_model': 'hr.loan',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_date': self.date_start,
            }
        }

    def action_view_overtimes(self):
        """Vista de horas extra de empleados del lote."""
        self.ensure_one()
        employee_ids = self.slip_ids.mapped('employee_id').ids
        return {
            'name': 'Horas Extra',
            'type': 'ir.actions.act_window',
            'res_model': 'hr.overtime',
            'view_mode': 'list,form',
            'domain': [('employee_id', 'in', employee_ids)],
        }

    def action_create_overtime(self):
        """Crear nueva hora extra."""
        self.ensure_one()
        return {
            'name': 'Nueva Hora Extra',
            'type': 'ir.actions.act_window',
            'res_model': 'hr.overtime',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_date': self.date_start,
            }
        }

    def action_view_leaves(self):
        """Vista de ausencias de empleados del lote."""
        self.ensure_one()
        employee_ids = self.slip_ids.mapped('employee_id').ids
        return {
            'name': 'Ausencias',
            'type': 'ir.actions.act_window',
            'res_model': 'hr.leave',
            'view_mode': 'list,form',
            'domain': [('employee_id', 'in', employee_ids)],
        }

    def action_create_leave(self):
        """Crear nueva ausencia."""
        self.ensure_one()
        return {
            'name': 'Nueva Ausencia',
            'type': 'ir.actions.act_window',
            'res_model': 'hr.leave',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_request_date_from': self.date_start,
                'default_request_date_to': self.date_end,
            }
        }

    def action_view_payslip_lines(self):
        """Vista de líneas agrupada por departamento y empleado."""
        self.ensure_one()
        return {
            'name': 'Líneas de Nómina',
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payslip.line',
            'view_mode': 'list,pivot,graph,form',
            'domain': [('slip_id', 'in', self.slip_ids.ids)],
            'context': {
                'search_default_group_department': 1,
                'search_default_group_employee': 1,
            }
        }

    def action_open_summary_modal(self):
        """Abre el resumen detallado en una ventana modal/flotante."""
        self.ensure_one()
        return {
            'name': f'Resumen - {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payslip.run',
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': self.env.ref('lavish_hr_payroll.view_hr_payslip_run_summary_modal').id,
            'target': 'new',
            'context': {'form_view_initial_mode': 'readonly'},
        }

    def get_payslips_detail(self):
        """Devuelve datos detallados de las nóminas para el widget PayslipRunSummary."""
        self.ensure_one()
        payslips_data = []
        totals = {'basic': 0, 'earnings': 0, 'deductions': 0, 'net': 0}

        for slip in self.slip_ids:
            lines = slip.line_ids

            # Obtener totales directamente de las líneas TOTALDEV, TOTALDED, NET
            totaldev_line = lines.filtered(lambda l: l.category_code == 'TOTALDEV' or l.code == 'TOTALDEV')
            totalded_line = lines.filtered(lambda l: l.category_code == 'TOTALDED' or l.code == 'TOTALDED')
            net_line = lines.filtered(lambda l: l.category_code in ('NET', 'NETO') or l.code in ('NET', 'NETO'))

            emp_gross = totaldev_line[0].total if totaldev_line else sum(
                lines.filtered(lambda l: l.afecta_totales_effective == 'devengo').mapped('total')
            )
            emp_deductions = abs(totalded_line[0].total) if totalded_line else abs(sum(
                lines.filtered(lambda l: l.afecta_totales_effective == 'deduccion').mapped('total')
            ))
            emp_net = net_line[0].total if net_line else (emp_gross - emp_deductions)

            # Agrupar líneas por categoría/tipo
            def get_line_data(line):
                return {
                    'id': line.id,
                    'code': line.code or '',
                    'name': line.name or '',
                    'total': line.total,
                    'quantity': line.quantity or 0,
                    'rate': line.rate or 0,
                    'amount': line.amount or 0,
                    'rule_id': line.salary_rule_id.id if line.salary_rule_id else False,
                    'rule_name': line.salary_rule_id.name if line.salary_rule_id else '',
                    'category': line.category_id.name if line.category_id else '',
                    'category_code': line.category_code or '',
                    'object_type': line.object_type or '',
                }

            # Líneas de devengos agrupadas
            basic_lines = []
            transport_lines = []
            overtime_lines = []
            absence_lines = []
            non_salary_earnings = []  # Devengos no salariales
            ibd_ibc_lines = []  # IBD/IBC del período
            ibc_previous_lines = []  # IBC de períodos anteriores
            other_earnings = []

            # Categorías a excluir de devengos normales (totales y provisiones)
            exclude_cats = ('PROV', 'TOTALDEV', 'TOTALDED', 'NET', 'GROSS', 'COMP')
            exclude_codes = ('PRV_', 'TOTALDEV', 'TOTALDED', 'NET', 'GROSS')

            for line in lines.filtered(lambda l: l.afecta_totales_effective == 'devengo' and l.total != 0):
                line_data = get_line_data(line)
                obj_type = line.object_type or ''
                cat_code = line.category_code or ''
                code = (line.code or '').upper()
                seq = line.sequence or 0

                # Saltar provisiones, totales y contribuciones empresa
                if cat_code in exclude_cats or any(code.startswith(ec) for ec in exclude_codes):
                    continue

                # Básico (seq 1-10)
                if cat_code == 'BASIC':
                    basic_lines.append(line_data)
                # Auxilio de transporte / Conectividad
                elif cat_code == 'AUX' or 'TRANS' in code or 'CONECT' in code:
                    transport_lines.append(line_data)
                # Horas extras y recargos
                elif obj_type in ('overtime', 'he') or cat_code in ('HEYREC', 'HE'):
                    overtime_lines.append(line_data)
                # Ausencias, vacaciones, incapacidades, licencias (NO provisiones de vacaciones)
                elif (obj_type in ('absence', 'leave', 'vacation') or
                      cat_code in ('AUS', 'AUSENCIA', 'VACACIONES', 'INCAPACIDAD',
                                   'LICENCIA_REMUNERADA', 'LICENCIA_MATERNIDAD',
                                   'ACCIDENTE_TRABAJO', 'LICENCIA_NO_REMUNERADA') or
                      ('VAC' in code and 'PRV' not in code) or 'INCAP' in code or 'LICENCIA' in code or
                      'MAT' in code or 'PAT' in code):
                    absence_lines.append(line_data)
                # Devengos no salariales (bonos, auxilios no salariales, etc.)
                elif (cat_code == 'DEV_NO_SALARIAL' or
                      'BONO' in code or 'AUX11' in code or 'AUX12' in code or
                      'DEV116' in code or 'BONNS' in code):
                    non_salary_earnings.append(line_data)
                # IBD/IBC del período actual
                elif ('IBD' in code or code == 'IBC') and 'PRV' not in code and 'ANT' not in code:
                    ibd_ibc_lines.append(line_data)
                # IBC de períodos anteriores (IBC_ANT, IBC_ANTERIOR, etc.)
                elif ('IBC' in code and ('ANT' in code or 'PREV' in code or 'HIST' in code)):
                    ibc_previous_lines.append(line_data)
                else:
                    other_earnings.append(line_data)

            # Líneas de prestaciones sociales (seq 301-400)
            benefits_lines = []
            for line in lines.filtered(lambda l: l.category_code in ('PRESTACIONES_SOCIALES', 'PRIMA') and l.total != 0 and 'PRV' not in (l.code or '').upper()):
                benefits_lines.append(get_line_data(line))

            # Líneas de provisiones (seq 401-500) - SEPARADAS
            provision_lines = []
            for line in lines.filtered(lambda l: (l.category_code == 'PROV' or 'PRV_' in (l.code or '').upper()) and l.total != 0):
                provision_lines.append(get_line_data(line))

            # Líneas de deducciones agrupadas por tipo
            health_lines = []
            pension_lines = []
            solidarity_lines = []
            retention_lines = []
            loan_lines = []
            other_deductions = []

            for line in lines.filtered(lambda l: l.afecta_totales_effective == 'deduccion' and l.total != 0):
                line_data = get_line_data(line)
                obj_type = line.object_type or ''
                cat_code = line.category_code or ''
                code = (line.code or '').upper()

                # Salud (EPS) - SSOCIAL001
                if code == 'SSOCIAL001' or 'EPS' in code or 'SALUD' in code:
                    health_lines.append(line_data)
                # Pensión - SSOCIAL002
                elif code == 'SSOCIAL002' or 'PENSION' in code or 'AFP' in code:
                    pension_lines.append(line_data)
                # Fondo Solidaridad/Subsistencia - SSOCIAL003, SSOCIAL004
                elif code in ('SSOCIAL003', 'SSOCIAL004') or 'FSP' in code or 'SOLIDAR' in code or 'SUBSIST' in code:
                    solidarity_lines.append(line_data)
                # Retención en la Fuente - RT_MET_01, RET_PRIMA, RTF_INDEM
                elif (cat_code in ('RET', 'RETEFUENTE', 'DEDUCCIONES') and
                      ('RTEFTE' in code or 'RETEFUENTE' in code or 'RT_' in code or 'RET_' in code or 'RTF_' in code)):
                    retention_lines.append(line_data)
                # Préstamos - P01 y similares
                elif obj_type == 'loan' or 'PREST' in code or code.startswith('P0'):
                    loan_lines.append(line_data)
                else:
                    other_deductions.append(line_data)

            # Novedades del empleado
            novelties = []
            employee_novelties = self.env['hr.novelties.different.concepts'].search([
                ('employee_id', '=', slip.employee_id.id),
                ('state', 'in', ['approved', 'draft']),
            ], limit=10)
            for nov in employee_novelties:
                novelties.append({
                    'id': nov.id,
                    'concept': nov.salary_rule_id.name if nov.salary_rule_id else nov.name,
                    'amount': nov.amount,
                    'date': str(nov.date) if nov.date else '',
                })

            # Horas extra del período
            overtime_records = []
            try:
                ot_records = self.env['hr.overtime'].search([
                    ('employee_id', '=', slip.employee_id.id),
                    ('date', '>=', slip.date_from),
                    ('date', '<=', slip.date_to),
                    ('state', 'in', ['validated', 'approved', 'done']),
                ], limit=20)
                for ot in ot_records:
                    overtime_records.append({
                        'id': ot.id,
                        'type': ot.type_overtime_id.name if hasattr(ot, 'type_overtime_id') and ot.type_overtime_id else 'Hora Extra',
                        'hours': ot.number_of_hours if hasattr(ot, 'number_of_hours') else 0,
                        'date': str(ot.date) if hasattr(ot, 'date') and ot.date else '',
                        'amount': ot.total if hasattr(ot, 'total') else 0,
                    })
            except Exception:  # noqa: BLE001 – datos de horas extras opcionales por nómina
                _logger.warning("Error obteniendo horas extras para nómina %s", slip.name, exc_info=True)

            # Ausencias del período
            leave_records = []
            try:
                leaves = self.env['hr.leave'].search([
                    ('employee_id', '=', slip.employee_id.id),
                    ('date_from', '<=', slip.date_to),
                    ('date_to', '>=', slip.date_from),
                    ('state', '=', 'validate'),
                ], limit=20)
                for leave in leaves:
                    leave_records.append({
                        'id': leave.id,
                        'type': leave.holiday_status_id.name if leave.holiday_status_id else 'Ausencia',
                        'days': leave.number_of_days if hasattr(leave, 'number_of_days') else 0,
                        'date_from': str(leave.date_from.date()) if leave.date_from else '',
                        'date_to': str(leave.date_to.date()) if leave.date_to else '',
                    })
            except Exception:  # noqa: BLE001 – datos de ausencias opcionales por nómina
                _logger.warning("Error obteniendo ausencias para nómina %s", slip.name, exc_info=True)

            payslips_data.append({
                'id': slip.id,
                'employee_id': slip.employee_id.id,
                'employee_name': slip.employee_id.name or '',
                'identification': slip.employee_id.identification_id or '',
                'department': slip.employee_id.department_id.name if slip.employee_id.department_id else '',
                'state': slip.state,
                'gross': emp_gross,
                'deductions': emp_deductions,
                'net': emp_net,
                # Líneas de devengos agrupadas
                'basic_lines': basic_lines,
                'transport_lines': transport_lines,
                'overtime_lines': overtime_lines,
                'absence_lines': absence_lines,
                'non_salary_earnings': non_salary_earnings,
                'ibd_ibc_lines': ibd_ibc_lines,
                'ibc_previous_lines': ibc_previous_lines,
                'other_earnings': other_earnings,
                # Líneas de prestaciones y provisiones
                'provision_lines': provision_lines,
                'benefits_lines': benefits_lines,
                # Líneas de deducciones agrupadas
                'health_lines': health_lines,
                'pension_lines': pension_lines,
                'solidarity_lines': solidarity_lines,
                'retention_lines': retention_lines,
                'loan_lines': loan_lines,
                'other_deductions': other_deductions,
                # Registros relacionados
                'overtime_records': overtime_records,
                'leave_records': leave_records,
                'novelties': novelties,
                'novelty_count': len(novelties),
                'overtime_count': len(overtime_records),
                'leave_count': len(leave_records),
            })

            # Acumular totales
            totals['earnings'] += emp_gross
            totals['deductions'] += emp_deductions
            totals['net'] += emp_net

        return {
            'payslips': payslips_data,
            'totals': totals,
        }

    def action_view_details(self):
        return {
            'name': 'Detalles',
            'view_mode': 'form',
            'res_model': 'hr.payslip.run',
            'type': 'ir.actions.act_window',
            'res_id': self.id,
        }

    def action_compute_all_payslips(self):
        """Computa todas las nóminas del lote usando el contexto optimizado."""
        self.ensure_one()
        return self.action_compute_all_payslips_optimized()

    def action_compute_all_payslips_optimized(self, chunk_size=50, use_context=True):
        """
        Computa todas las nóminas del lote de forma OPTIMIZADA.

        Parámetros configurables:
        - chunk_size: Tamaño de chunks para commits intermedios (default 50)
        - use_context: Si usar servicios optimizados (default True)

        Usa:
        - Servicios modulares para procesamiento
        - Procesamiento en chunks para evitar transacciones largas
        """
        import time

        self.ensure_one()
        start_time = time.time()

        payslips = self.slip_ids.filtered(lambda s: s.state in ('draft', 'verify'))
        total = len(payslips)
        processed = 0
        errors = 0

        for i, payslip in enumerate(payslips, 1):
            try:
                payslip.compute_sheet()
                processed += 1
            except Exception as e:
                errors += 1
                _logger.error("Error computando nómina %s: %s", payslip.name, e)

            if i % chunk_size == 0:
                self.env.cr.commit()
                _logger.info("Procesadas %d/%d nóminas", i, total)

        self.env.cr.commit()
        elapsed = time.time() - start_time

        # Guardar tiempo de ejecución
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        self.time_process = f"{mins}m {secs}s ({processed} nóminas)"

        self.invalidate_recordset()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_compute_all_payslips_legacy(self):
        """Computa todas las nóminas del lote (método legacy sin optimización)."""
        self.ensure_one()
        payslips_to_compute = self.slip_ids.filtered(lambda s: s.state in ('draft', 'verify'))
        total = len(payslips_to_compute)

        for i, payslip in enumerate(payslips_to_compute, 1):
            try:
                payslip.compute_sheet()
                if i % 50 == 0:
                    self.env.cr.commit()
                    _logger.info(f"Procesadas {i}/{total} nóminas")
            except Exception as e:
                _logger.error(f"Error computando nómina {payslip.name}: {e}")

        self.invalidate_recordset()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_post_account_moves(self):
        """Publica los asientos contables de las nóminas."""
        self.ensure_one()
        moves_to_post = self.slip_ids.mapped('move_id').filtered(lambda m: m.state == 'draft')

        if not moves_to_post:
            raise UserError(_("No hay asientos en borrador para publicar."))

        moves_to_post.action_post()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_draft_account_moves(self):
        """Revierte asientos contables a borrador."""
        self.ensure_one()
        moves_to_draft = self.slip_ids.mapped('move_id').filtered(lambda m: m.state == 'posted')

        if not moves_to_draft:
            raise UserError(_("No hay asientos publicados para revertir."))

        for move in moves_to_draft:
            if move.payment_state != 'not_paid':
                raise UserError(_("No se puede revertir el asiento %s porque tiene pagos conciliados.") % move.name)

        moves_to_draft.button_draft()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_recompute_totals(self):
        """Recalcula los totales del lote."""
        self.ensure_one()
        self.env.flush_all()
        self.invalidate_recordset()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    @api.depends('slip_ids.mail_state')
    def _compute_email_stats(self):
        for record in self:
            all_slips = record.slip_ids
            sent_slips = all_slips.filtered(lambda s: s.mail_state == 'sent')
            failed_slips = all_slips.filtered(lambda s: s.mail_state == 'failed')
            
            record.email_count = len(all_slips)
            record.email_sent = len(sent_slips)
            record.email_failed = len(failed_slips)
            
            if failed_slips:
                failed_details = []
                for slip in failed_slips:
                    failed_details.append(f"{slip.employee_id.name}: {slip.mail_error_msg or 'Error desconocido'}")
                record.failed_payslips = "\n".join(failed_details)
            else:
                record.failed_payslips = False
    def action_send_payslip_emails(self):
        self.ensure_one()
        if not self.slip_ids:
            raise UserError(_("No hay nóminas para enviar."))
        self.email_state = 'sending'
        try:
            template = self.env.ref('lavish_hr_payroll.email_template_payslip_smart')
            if not template:
                raise UserError(_("No se encontró la plantilla de correo."))

            batch_size = 50
            payslips = self.slip_ids.filtered(lambda s: s.mail_state != 'sent')
            total = len(payslips)
            
            _logger.info(f"Iniciando envío masivo de {total} comprobantes de nómina del lote {self.name}")
            
            for i in range(0, total, batch_size):
                batch = payslips[i:i + batch_size]
                self._process_payslip_batch(batch, template)
                self.env.cr.commit() 
                _logger.info(f"Procesado lote {i//batch_size + 1} de {(total-1)//batch_size + 1}")

        except Exception as e:
            self.email_state = 'failed'
            _logger.error(f"Error en el proceso de envío masivo: {str(e)}")
            raise UserError(_(f"Error en el proceso de envío: {str(e)}"))

        finally:
            # Actualizar estado final
            failed_count = len(self.slip_ids.filtered(lambda s: s.mail_state == 'failed'))
            if failed_count:
                self.email_state = 'failed'
            else:
                self.email_state = 'sent'
            
            # Crear mensaje en el chatter
            sent_count = len(self.slip_ids.filtered(lambda s: s.mail_state == 'sent'))
            self.message_post(
                body=f"""<b>Proceso de envío completado</b><br/>
                        - Total procesados: {total}<br/>
                        - Enviados exitosamente: {sent_count}<br/>
                        - Fallidos: {failed_count}<br/>
                        {f'<br/><b>⚠️ Algunos comprobantes no pudieron ser enviados.</b>' if failed_count else ''}""",
                message_type='notification'
            )

    def _process_payslip_batch(self, payslips, template):
        for payslip in payslips:
            try:
                if not (payslip.employee_id.work_email or payslip.employee_id.personal_email):
                    raise UserError(_(f"El empleado {payslip.employee_id.name} no tiene configurado un correo electrónico."))

                report = payslip.struct_id.report_id
                if not report:
                    raise UserError(_(f"La estructura de nómina {payslip.struct_id.name} no tiene un reporte configurado."))

                pdf_content, dummy = self.env['ir.actions.report']._render_qweb_pdf(report, payslip.id)
                
                attachment_name = f"Comprobante_nomina_{payslip.employee_id.work_contact_id.vat or 'SIN-ID'}_{payslip.number or 'SIN-NUM'}.pdf"
                attachment = self.env['ir.attachment'].create({
                    'name': attachment_name,
                    'type': 'binary',
                    'datas': base64.b64encode(pdf_content),
                    'res_model': 'hr.payslip',
                    'res_id': payslip.id,
                })

                # Enviar correo
                with self.env.cr.savepoint():
                    template.with_context(
                        force_send=True,
                        payslip_run=self.id,
                        lang=payslip.employee_id.lang 
                    ).send_mail(
                        payslip.id,
                        force_send=True,
                        email_values={
                            'attachment_ids': [(4, attachment.id)],
                            'auto_delete': False
                        },
                        raise_exception=True
                    )

                    # Actualizar estado de la nómina
                    payslip.write({
                        'mail_state': 'sent',
                        'mail_sent_date': fields.Datetime.now(),
                        'mail_error_msg': False
                    })
                    
                    _logger.info(f"Correo enviado exitosamente para {payslip.employee_id.name}")

            except Exception as e:
                error_msg = str(e)
                _logger.error(f"Error enviando nómina {payslip.name} de {payslip.employee_id.name}: {error_msg}")
                payslip.write({
                    'mail_state': 'failed',
                    'mail_error_msg': error_msg
                })



    @api.depends('structure_id', 'structure_id.process', 'is_credit_note')
    def _compute_sequence_prefix(self):
        for run in self:
            if run.structure_id and run.structure_id.process:
                prefix_map = {
                    'nomina': 'NOM' if not run.is_credit_note else 'RNOM',
                    'vacaciones': 'VAC' if not run.is_credit_note else 'RVAC',
                    'prima': 'PRI' if not run.is_credit_note else 'RPRI',
                    'cesantias': 'CES' if not run.is_credit_note else 'RCES',
                    'contrato': 'LIQ' if not run.is_credit_note else 'RLIQ',
                    'intereses_cesantias': 'INT' if not run.is_credit_note else 'RINT',
                    'otro': 'OTR' if not run.is_credit_note else 'ROTR'
                }
                run.sequence_prefix = prefix_map.get(run.structure_id.process, 'OTR')
            else:
                run.sequence_prefix = 'OTR'

    def _get_next_number(self):
        """Obtener siguiente número según estructura de nómina."""
        last_record = self.search([
            ('company_id', '=', self.env.company.id),
            ('structure_id', '=', self.structure_id.id),
            ('sequence_prefix', '=', self.sequence_prefix)
        ], order='number desc', limit=1)

        if last_record and last_record.number:
            try:
                base_number = last_record.number.split('/')[-1]
                next_number = int(base_number) + 1
            except (ValueError, IndexError):
                next_number = 1
        else:
            next_number = 1

        year = str(fields.Date.today().year)
        return f"{self.sequence_prefix}/{year}/{str(next_number).zfill(3)}"

    def _get_period_name(self, date):
        """Obtener nombre del período."""
        MESES = {
            1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril',
            5: 'Mayo', 6: 'Junio', 7: 'Julio', 8: 'Agosto',
            9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'
        }
        return f"{MESES.get(date.month, '')} {date.year}"

    @api.onchange('structure_id', 'date_start', 'is_credit_note')
    def _onchange_structure_and_date(self):
        if self.structure_id and self.date_start:
            period_name = self._get_period_name(self.date_start)
            prefix = "Reversión de " if self.is_credit_note else ""
            self.name = f"{prefix}{self.structure_id.name} - {period_name}"
            self._compute_sequence_prefix()  # Recalcular el prefijo
            self.number = self._get_next_number()
            if self.structure_id.process == 'nomina':
                self.date_end = (self.date_start + relativedelta(months=1, day=1, days=-1))
            elif self.structure_id.process in ['prima', 'cesantias', 'intereses_cesantias']:
                self.date_end = self.date_start
            else:
                self.date_end = (self.date_start + relativedelta(months=1, day=1, days=-1))
    @api.model_create_multi
    def create(self, vals_list):
        PayrollStructure = self.env['hr.payroll.structure']
        
        for vals in vals_list:
            if vals.get('structure_id'):
                # Create a temporary record for computations
                temp_record = self.new(vals)
                temp_record._compute_sequence_prefix()

                # Set number if not provided
                if not vals.get('number'):
                    vals['number'] = temp_record._get_next_number()
                
                # Set name if date_start exists and name not provided
                if vals.get('date_start') and not vals.get('name'):
                    structure = PayrollStructure.browse(vals['structure_id'])
                    date_start = fields.Date.from_string(vals['date_start'])
                    period_name = self._get_period_name(date_start)
                    
                    # Handle credit note prefix
                    prefix = "Reversión de " if vals.get('is_credit_note') else ""
                    vals['name'] = f"{prefix}{structure.name} - {period_name}"

        runs = super().create(vals_list)

        # Asignar periodo a las nóminas si existe
        for run in runs:
            if run.period_id:
                for slip in run.slip_ids:
                    slip.write({
                        'period_id': run.period_id.id,
                        'date_from': run.period_id.date_start,
                        'date_to': run.period_id.date_end,
                    })

        return runs

    def write(self, vals):
        """Override write para sincronizar cambios de periodo con las nominas."""
        # Detectar cambio de estado a 'close' para recalcular seguridad social
        state_changed_to_close = 'state' in vals and vals.get('state') == 'close'

        res = super().write(vals)

        if 'period_id' in vals:
            for record in self:
                if record.period_id:
                    for slip in record.slip_ids:
                        slip.write({
                            'period_id': record.period_id.id,
                            'date_from': record.period_id.date_start,
                            'date_to': record.period_id.date_end,
                        })

        # Si el lote se cerró, recalcular seguridad social del período
        if state_changed_to_close:
            for record in self:
                record._recompute_social_security()

        return res

    def action_auto_generate_payslips(self):
        """Genera recibos para TODOS los empleados elegibles del periodo
        sin pedir seleccion en wizard (comportamiento estilo v18).

        Reemplaza el flujo v19 enterprise que abre lista de hr.version y exige
        que el usuario seleccione. Usamos _get_valid_version_ids() sin filtros
        para obtener todos los validos del periodo/estructura del lote.
        """
        self.ensure_one()
        version_ids = self._get_valid_version_ids()
        if not version_ids:
            raise UserError(_(
                "No hay empleados elegibles para el periodo %s - %s con la "
                "estructura seleccionada."
            ) % (self.date_start, self.date_end))
        return self.generate_payslips(version_ids=version_ids)

    def generate_payslips(self, version_ids=None, employee_ids=None):
        """Override para asegurar que el periodo se asigne correctamente.

        v19 enterprise pasa kwargs `version_ids` (hr.version) y `employee_ids`.
        Aceptamos ambos y los reenviamos al super.
        """
        res = super().generate_payslips(version_ids=version_ids, employee_ids=employee_ids)

        if self.period_id:
            # Asegurar que todas las nominas generadas tengan el periodo correcto
            for slip in self.slip_ids:
                if not slip.period_id:
                    slip.write({
                        'period_id': self.period_id.id,
                        'date_from': self.period_id.date_start,
                        'date_to': self.period_id.date_end,
                    })

        return res

    def _recompute_social_security(self):
        """
        Recalcula la seguridad social del período cuando se cierra/publica el lote.

        Este método:
        1. Identifica los períodos (año/mes) afectados por las nóminas del lote
        2. Busca los registros de seguridad social correspondientes
        3. Re-ejecuta el cálculo COMPLETO de seguridad social para actualizar los valores

        Solo recalcula si el registro está en estado 'draft' o 'done'.
        No modifica registros en estado 'accounting' (ya contabilizados).
        """
        self.ensure_one()

        # Obtener las nóminas confirmadas del lote
        confirmed_payslips = self.slip_ids.filtered(lambda s: s.state in ('validated', 'paid'))

        if not confirmed_payslips:
            return

        # Identificar los períodos únicos de las nóminas
        SocialSecurity = self.env['hr.payroll.social.security']
        periods = set()

        for slip in confirmed_payslips:
            if slip.date_from:
                periods.add((slip.date_from.year, slip.date_from.month, slip.company_id.id))

        # Para cada período, buscar y recalcular la seguridad social
        for year, month, company_id in periods:
            ss_record = SocialSecurity.search([
                ('year', '=', year),
                ('month', '=', str(month)),
                ('company_id', '=', company_id)
            ], limit=1)

            is_new_record = not ss_record

            if is_new_record:
                # Si no existe, crear el registro
                ss_record = SocialSecurity.create({
                    'year': year,
                    'month': str(month),
                    'company_id': company_id,
                    'state': 'draft',
                })

            # Solo recalcular si no está contabilizado
            if ss_record.state != 'accounting':
                try:
                    # Re-ejecutar el cálculo COMPLETO para este período (todos los empleados)
                    ss_record.executing_social_security()

                    # Generar mensaje en el chatter
                    employee_count = len(confirmed_payslips.mapped('employee_id'))
                    ss_record.message_post(
                        body=f"Seguridad social recalculada automáticamente al publicar el lote '{self.name}'. "
                             f"Se procesaron {employee_count} empleado(s) del período {month}/{year}.",
                        subject="Recálculo Automático por Publicación de Lote"
                    )

                    # Si el recálculo fue exitoso y el estado es draft, pasarlo a done
                    if ss_record.state == 'draft':
                        ss_record.write({'state': 'done'})

                except Exception as e:
                    # Generar mensaje de error en el chatter
                    error_msg = f"Error al recalcular seguridad social para período {month}/{year} del lote {self.name}: {str(e)}"

                    ss_record.message_post(
                        body=error_msg,
                        subject="Error en Recálculo de Seguridad Social",
                        message_type='notification',
                        subtype_xmlid='mail.mt_note'
                    )

                    # Log de error
                    _logger.error(error_msg)

    def action_reverse_payslip_run(self):
        """Crear una reversión del lote de nómina."""
        self.ensure_one()
        if self.state != '02_close':
            raise UserError(_("Solo se pueden revertir lotes cerrados."))

        reversed_run = self.copy({
            'is_credit_note': True,
            'date_start': fields.Date.today(),
            'date_end': fields.Date.today(),
            'number': False, 
            'name': False, 
        })
        
        for slip in self.slip_ids:
            slip.copy({
                'payslip_run_id': reversed_run.id,
                'credit_note': True,
                'name': False,
            })

        action = {
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'hr.payslip.run',
            'res_id': reversed_run.id,
        }
        return action

    def compute_sheet(self):
        # v19: hr.payslip ya no tiene estado 'verify', solo 'draft'/'validated'/'paid'/'cancel'.
        for rec in self:
            for line in rec.slip_ids:
                if line.state == 'draft':
                    line.compute_sheet()

    def compute_sheet_2(self):
        # v19: hr.payslip ya no tiene estado 'verify'.
        for rec in self:
            for line in rec.slip_ids:
                if line.state == 'draft':
                    line.compute_sheet_2()

    def action_payslip_done_2(self):
        # v19: 'done' -> 'validated', 'verify' no existe.
        for rec in self:
            for line in rec.slip_ids:
                if line.state in ('draft', 'validated'):
                    line.action_payslip_done_2()


    def assign_status_verify(self):
        # v18 'Verificar': Nuevo -> Confirmado. En v19 mapeamos a 01_ready -> 02_close.
        # Requiere slips computados (con line_ids) igual que en v18.
        for record in self:
            if not record.slip_ids:
                raise ValidationError(_("No existen nóminas asociadas a este lote, no es posible pasar a estado verificar."))
            uncomputed = record.slip_ids.filtered(lambda s: s.state == 'draft' and not s.line_ids)
            if uncomputed:
                raise ValidationError(_(
                    "Hay %d recibo(s) sin computar. Use 'Computar Nóminas' antes de verificar."
                ) % len(uncomputed))
            record.write({'state': '02_close'})

    def action_validate(self):
        settings_batch_account = self._get_batch_account_setting()
        slips_original = self.mapped('slip_ids').filtered(lambda slip: slip.state != 'cancel')
        if settings_batch_account == '1': 
            slips = slips_original.filtered(lambda x: len(x.move_id) == 0 or x.move_id == False)[0:200]
        else:
            slips = slips_original
        slips.action_payslip_done()
        # v19: ya no existe action_close() en hr.payslip.run; el estado del lote
        # se recomputa automáticamente vía _compute_state cuando todos los
        # payslips quedan en 'done'. Se setea explícitamente como respaldo.
        if len(slips_original.filtered(lambda x: len(x.move_id) == 0 or x.move_id == False)) == 0:
            self.write({'state': '02_close'})

    def _get_batch_account_setting(self):
        param = self.env['ir.config_parameter'].sudo().get_param(
            'lavish_hr_payroll.module_hr_payroll_batch_account'
        )
        if param in ('0', '1'):
            return param
        try:
            params = self.env['hr.annual.parameters'].get_for_year(
                fields.Date.today().year,
                company_id=self.env.company.id,
                raise_if_not_found=False
            )
            if params and params.accounting_method:
                return '1' if params.accounting_method == 'employee' else '0'
        except Exception:  # noqa: BLE001 – falla no crítica, se retorna valor por defecto
            _logger.warning("Error al obtener método contable de parámetros anuales, usando valor por defecto '1'", exc_info=True)
        return '1'

    def restart_payroll_batch(self):
        self.ensure_one()

        has_reconciled = self.slip_ids.filtered(
            lambda s: s.move_id and s.move_id.state == 'posted'
                      and s.move_id.payment_state != 'not_paid'
        )
        if has_reconciled:
            raise UserError(_(
                'No se puede reiniciar el lote.\n\n'
                'Existen %d recibo(s) con asientos contables que tienen pagos '
                'conciliados. Cancela los pagos antes de continuar.'
            ) % len(has_reconciled))

        for payslip in self.slip_ids:
            move = payslip.move_id
            if move:
                if move.state == 'posted':
                    move.button_draft()
                if move.state in ('draft', 'cancel'):
                    move.button_cancel()
                    move.unlink()

        self.mapped('slip_ids').action_payslip_cancel()
        self.mapped('slip_ids').unlink()
        # v19: hr.payslip.run state Selection ('01_ready','02_close','02b_done','03_paid','04_cancel')
        return self.write({'state': '01_ready', 'observations': False, 'time_process': False})

    def restart_payroll_account_batch(self):
        """
        Reversa la contabilización del lote: elimina asientos contables
        y revierte los recibos a estado 'verify'.
        Maneja correctamente asientos en estado publicado (draft previo).
        """
        self.ensure_one()

        for payslip in self.slip_ids:
            move = payslip.move_id
            if move:
                if move.state == 'posted':
                    if move.payment_state != 'not_paid':
                        raise UserError(_(
                            'No se puede reversar la contabilización.\n\n'
                            'El asiento %s del recibo %s tiene pagos conciliados. '
                            'Cancela el pago antes de continuar.'
                        ) % (move.name, payslip.name))
                    move.button_draft()
                if move.state in ('draft', 'cancel'):
                    move.button_cancel()
                    move.unlink()
            self.env['hr.vacation'].search([('payslip', '=', payslip.id)]).unlink()
            self.env['hr.history.prima'].search([('payslip', '=', payslip.id)]).unlink()
            self.env['hr.history.cesantias'].search([('payslip', '=', payslip.id)]).unlink()
            payslip.write({'state': 'draft'})  # v19: state Selection es draft/validated/paid/cancel
        # hr.payslip.run en v19: 'verify' -> '01_ready'
        return self.write({'state': '01_ready'})

    def restart_full_payroll_batch(self):
        for payslip in self.slip_ids:
            payslip.mapped('move_id').unlink() 
            self.env['hr.vacation'].search([('payslip', '=', payslip.id)]).unlink()
            self.env['hr.history.prima'].search([('payslip', '=', payslip.id)]).unlink()
            self.env['hr.history.cesantias'].search([('payslip', '=', payslip.id)]).unlink()
            payslip.write({'state': 'draft'})  # v19: state Selection es draft/validated/paid/cancel
            payslip.action_payslip_cancel()
            payslip.unlink()
        # hr.payslip.run en v19: 'draft' -> '01_ready'
        return self.write({'state': '01_ready'})

    def _compute_account_move_count(self):
        for payslip_run in self:
            payslip_run.account_move_count = len(self.slip_ids.mapped('move_id'))

    def action_open_account_move(self):
        self.ensure_one()
        views = [(self.env.ref('account.view_move_tree').id, 'list'),
                 (self.env.ref('account.view_move_form').id, 'form')]
        return {
            'name': _('Account Move'),
            'view_mode': 'list,form',
            'res_model': 'account.move',
            'view_id': False,
            'views': views,
            'type': 'ir.actions.act_window',
            'domain': [['id', 'in', self.slip_ids.mapped('move_id').ids]],
        }

    def action_regenerate_accounting_entries(self):
        """
        Regenera los asientos contables del lote de nómina
        1. Verifica que el lote esté en estado cerrado
        2. Elimina los asientos contables existentes
        3. Crea nuevos asientos contables
        """
        self.ensure_one()
        
        # Verificar que el lote esté en estado cerrado
        # if self.state != 'close':
        #     raise UserError(_('Solo se pueden regenerar asientos contables de lotes cerrados.'))

        # Obtener todas las nóminas del lote en estado validado o pagado
        payslips = self.slip_ids.filtered(lambda x: x.state in ['done', 'paid'])
        
        if not payslips:
            raise UserError(_('No hay nóminas validadas o pagadas en este lote.'))

        # Crear un registro de actividad para el seguimiento
        self.activity_schedule(
            'mail.mail_activity_data_todo',
            note=f'Iniciada regeneración de asientos contables por {self.env.user.name}',
            user_id=self.env.user.id
        )

        # Variables para seguimiento
        processed_ok = []
        failed_payslips = []
        error_messages = []

        # Procesar cada nómina individualmente
        for payslip in payslips:
            try:
                if payslip.move_id:
                    if payslip.move_id.state == 'posted':
                        payslip.move_id.button_draft()
                    payslip.move_id.button_cancel()
                    payslip.move_id.unlink()
                payslip._action_create_account_move()
                processed_ok.append(payslip)
            except Exception as e:
                error_detail = f'Error en nómina {payslip.number} - {payslip.employee_id.name}: {str(e)}'
                failed_payslips.append(payslip)
                error_messages.append(error_detail)
                continue

        # Construir mensaje para el chatter
        message_body = []
        message_body.append(_('Resumen de regeneración de asientos contables:'))
        message_body.append(_('- Nóminas procesadas exitosamente: %s') % len(processed_ok))
        
        if processed_ok:
            message_body.append(_('\nProcesadas correctamente:'))
            for slip in processed_ok:
                message_body.append(f'✓ {slip.number} - {slip.employee_id.name}')

        if failed_payslips:
            message_body.append(_('\nNóminas con errores: %s') % len(failed_payslips))
            message_body.append(_('Detalle de errores:'))
            for error in error_messages:
                message_body.append(f'❌ {error}')

        message_body.append(_('\nProceso realizado por: %s') % self.env.user.name)

        self.message_post(body='<br/>'.join(message_body))
        if failed_payslips:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Regeneración Completada con Advertencias'),
                    'message': _('Proceso completado. Algunas nóminas presentaron errores. Revise el chatter para más detalles.'),
                    'type': 'warning',
                    'sticky': True,
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Regeneración Completada'),
                    'message': _('Todos los asientos contables han sido regenerados exitosamente.'),
                    'type': 'success',
                    'sticky': False,
                }
            }

    def action_draft(self):
        """v18 'Establecer como borrador': regresa el lote a Nuevo limpiando
        asientos, lineas calculadas y dejando los slips en draft sin lineas.
        Asi _compute_state ve 'draft sin line_ids' y vuelve a '01_ready'.
        """
        self.ensure_one()

        has_reconciled = self.slip_ids.filtered(
            lambda s: s.move_id and s.move_id.state == 'posted'
                      and s.move_id.payment_state != 'not_paid'
        )
        if has_reconciled:
            raise UserError(_(
                'No se puede restablecer el lote a borrador.\n\n'
                'Existen %d recibo(s) con asientos contables que tienen pagos '
                'conciliados. Cancela los pagos antes de continuar.'
            ) % len(has_reconciled))

        for payslip in self.slip_ids:
            move = payslip.move_id
            if move:
                if move.state == 'posted':
                    move.button_draft()
                if move.state in ('draft', 'cancel'):
                    move.button_cancel()
                    move.unlink()

        # Limpiar lineas calculadas y dias trabajados para que _compute_state
        # detecte slips draft sin line_ids -> '01_ready' (Nuevo).
        self.slip_ids.mapped('line_ids').unlink()
        self.slip_ids.mapped('worked_days_line_ids').unlink()
        return super().action_draft()


class HrPayslipEmployees(models.TransientModel):
    _name = 'hr.payslip.employees'
    _description = 'Generate Payslips Wizard (Lavish Compat)'

    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
    department_id = fields.Many2one('hr.department', string='Department')
    date_start = fields.Date(string='Date From', required=True, default=lambda self: self.env.context.get('default_date_start') or fields.Date.today())
    date_end = fields.Date(string='Date To', required=True, default=lambda self: self.env.context.get('default_date_end') or fields.Date.today())
    period_id = fields.Many2one('hr.period', string='Periodo')
    employee_ids = fields.Many2many(
        'hr.employee',
        'lavish_hr_payslip_employees_rel',
        'wizard_id',
        'employee_id',
        string='Employees',
        compute='_compute_employee_ids',
        store=False,
        readonly=False,
    )

    # Campo temporal para compatibilidad con vista obsoleta (se eliminará en próxima actualización)
    test_mode = fields.Selection([
        ('none', 'Deshabilitado'),
        ('services', 'Test Servicios'),
        ('compare', 'Comparar')
    ], string='Modo Test', default='none')
    write_to_db = fields.Boolean('Escribir a BD', default=False)

    @api.model
    def _get_default_structure(self):
        return self.env['hr.payroll.structure'].search([('process','=','nomina')],limit=1)
    
    @api.model
    def _get_default_liquidate_contract(self):
        if self.env.context.get('active_model') == 'hr.payslip.run' and self.env.context.get('active_id'):
            payslip_run = self.env['hr.payslip.run'].browse(self.env.context['active_id'])
            return payslip_run.liquidate_contract
        return False

    @api.model
    def _get_default_pay_vacations(self):
        if self.env.context.get('active_model') == 'hr.payslip.run' and self.env.context.get('active_id'):
            payslip_run = self.env['hr.payslip.run'].browse(self.env.context['active_id'])
            return payslip_run.liquidate_vacations
        return False

    date_liquidacion = fields.Date('Fecha liquidación de contrato')
    date_prima = fields.Date('Fecha liquidación de prima')
    date_cesantias = fields.Date('Fecha liquidación de cesantías')
    pay_cesantias_in_payroll = fields.Boolean('¿Liquidar Interese de cesantia en nómina?')
    pay_primas_in_payroll = fields.Boolean('¿Liquidar Primas en nómina?')
    liquidate_contract = fields.Boolean(
        '¿Liquidar Contratos?',
        default=_get_default_liquidate_contract,
        help='Generar liquidación para contratos terminados'
    )
    structure_id = fields.Many2one('hr.payroll.structure', string='Salary Structure', default=_get_default_structure)
    struct_process = fields.Selection(related='structure_id.process', string='Proceso', store=True)
    method_schedule_pay  = fields.Selection([('bi-weekly', 'Quincenal'),
                                          ('monthly', 'Mensual'),
                                          ('other', 'Ambos')], 'Frecuencia de Pago', default='other')
    analytic_account_ids = fields.Many2many('account.analytic.account', string='Cuentas analíticas')
    state_contract = fields.Selection([('open','En Proceso'),('finished','Finalizado Por Liquidar')], string='Estado Contrato', default='open')
    settle_payroll_concepts = fields.Boolean('Liquida conceptos de nómina', default=True)
    novelties_payroll_concepts = fields.Boolean('Liquida conceptos de novedades', default=True)
    prima_run_reverse_id = fields.Many2one('hr.payslip.run', string='Lote de prima a ajustar')
    pay_vacations_in_payroll = fields.Boolean(
        'Liquida Vacaciones de nómina',
        default=_get_default_pay_vacations,
        help='Activar para incluir liquidación de vacaciones en la nómina'
    )

    vacation_count = fields.Text(
        'Alerta de Vacaciones',
        compute='_compute_vacation_warnings',
        help='Conteo de vacaciones pendientes y contratos por liquidar'
    )

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        context = self.env.context
        
        if context.get('active_model') == 'hr.payslip.run' and context.get('active_ids'):
            payslip_run = self.env['hr.payslip.run'].browse(context.get('active_ids'))
            if payslip_run.liquidate_contract:
                res.update({
                    'liquidate_contract': True,
                })
            res['pay_vacations_in_payroll'] = payslip_run.liquidate_vacations
        
        return res

    def _compute_vacation_warnings(self):
        for wizard in self:
            warnings = []
            contracts = self.env['hr.contract'].search([('state', 'in', ('finished','close','open'))])
            if contracts.employee_id:
                date_start = fields.Date.to_date(self.env.context.get('default_date_start'))
                date_end = fields.Date.to_date(self.env.context.get('default_date_end'))
                employee_ids = contracts.employee_id.ids

                base_domain = [
                    ('employee_id', 'in', employee_ids),
                    ('state', '=', 'validate'),
                    '|',
                        '&', ('request_date_from', '<=', date_start), ('request_date_to', '>=', date_start),
                        '&', ('request_date_from', '<=', date_end), ('request_date_to', '>=', date_start)
                ]

                time_count = self.env['hr.leave'].search_count(
                    base_domain + [
                        ('holiday_status_id.is_vacation', '=', True),
                        ('holiday_status_id.is_vacation_money', '=', False),
                    ]
                )

                money_count = self.env['hr.leave'].search_count(
                    base_domain + [
                        ('holiday_status_id.is_vacation_money', '=', True),
                    ]
                )

                contract_count = self.env['hr.contract'].search_count([
                    ('employee_id', 'in', employee_ids),
                    ('state', 'in', ['finished', 'close']),
                    '|',
                        ('retirement_date', '=', False),
                        ('retirement_date', '=', None),
                    '|',
                        '&', ('date_start', '<=', date_end), ('date_end', '>=', date_start),
                        '&', ('date_start', '<=', date_end), ('date_end', '=', False)
                ])
                if time_count > 0:
                    warnings.append(f"⚠️ {time_count} Vacaciones en tiempo")
                if money_count > 0:
                    warnings.append(f"💰 {money_count} Vacaciones en dinero")
                if contract_count > 0:
                    warnings.append(f"🔔 {contract_count} Contratos por liquidar")
            wizard.vacation_count = " | ".join(warnings) if warnings else False

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'employee_ids' in fields_list and res.get('employee_ids'):
            self._compute_vacation_warnings()
        return res
    
    def _get_available_contracts_domain(self):
        domain = [('contract_id.state', '=', self.state_contract or 'open'), ('company_id', '=', self.env.company.id)]
        if self.method_schedule_pay and self.method_schedule_pay != 'other':
            domain.append(('contract_id.method_schedule_pay','=',self.method_schedule_pay))
        if len(self.analytic_account_ids) > 0:
            domain.append(('contract_id.employee_id.analytic_account_id', 'in', self.analytic_account_ids.ids))
        if self.prima_run_reverse_id:
            employee_ids = self.env['hr.payslip'].search([('payslip_run_id', '=', self.prima_run_reverse_id.id)]).employee_id.ids
            domain.append(('id','in',employee_ids))
        if self.structure_id.process in ('cesantia','prima'):
            domain.append(('contract_id.modality_salary','!=','integral'))
            domain.append(('contract_id.employee_id.tipo_coti_id.code','not in', ['12', '19']))
        return domain

    @api.depends('structure_id','department_id','method_schedule_pay','analytic_account_ids','state_contract','prima_run_reverse_id')
    def _compute_employee_ids(self):
        for wizard in self:
            wizard._compute_vacation_warnings()
            domain = wizard._get_available_contracts_domain()
            if wizard.department_id:
                domain.append(('department_id', 'child_of', self.department_id.id))
            wizard.employee_ids = self.env['hr.employee'].search(domain)

    def _check_undefined_slots(self, work_entries, payslip_run):
        """
        Check if a time slot in the contract's calendar is not covered by a work entry
        """
        calendar_is_not_covered = self.env['hr.contract']
        work_entries_by_contract = defaultdict(lambda: self.env['hr.work.entry'])
        for work_entry in work_entries:
            work_entries_by_contract[work_entry.contract_id] |= work_entry

        for contract, work_entries in work_entries_by_contract.items():
            calendar_start = pytz.utc.localize(datetime.combine(max(contract.date_start, payslip_run.date_start), datetime.min.time()))
            calendar_end = pytz.utc.localize(datetime.combine(min(contract.date_end or date.max, payslip_run.date_end), datetime.max.time()))
            outside = contract.resource_calendar_id._attendance_intervals_batch(calendar_start, calendar_end)[False] - work_entries._to_intervals()
            if outside:
                calendar_is_not_covered |= contract
        return calendar_is_not_covered

    def _filter_contracts(self, contracts):
        return contracts

    def compute_sheet(self):
        self.ensure_one()
        if not self.env.context.get('active_id'):
            from_date = fields.Date.to_date(self.env.context.get('default_date_start'))
            end_date = fields.Date.to_date(self.env.context.get('default_date_end'))
            today = fields.date.today()
            first_day = today + relativedelta(day=1)
            last_day = today + relativedelta(day=31)
            if from_date == first_day and end_date == last_day:
                batch_name = from_date.strftime('%B %Y')
            else:
                batch_name = _('From %s to %s', format_date(self.env, from_date), format_date(self.env, end_date))
            payslip_run = self.env['hr.payslip.run'].create({
                'name': batch_name,
                'date_start': from_date,
                'date_end': end_date,
            })
        else:
            payslip_run = self.env['hr.payslip.run'].browse(self.env.context.get('active_id'))

        employees = self.with_context(active_test=False).employee_ids
        if not employees:
            raise UserError(_("You must select employee(s) to generate payslip(s)."))

        #Prevent a payslip_run from having multiple payslips for the same employee
        employees -= payslip_run.slip_ids.employee_id
        success_result = {
                'type': 'ir.actions.act_window',
                'res_model': 'hr.payslip.run',
                'views': [[False, 'form']],
                'res_id': payslip_run.id,
            }
        #try:
        payslips = self.env['hr.payslip']
        Payslip = self.env['hr.payslip']

        if self.structure_id.process == 'contrato':
            contracts = employees._get_contracts(payslip_run.date_start, payslip_run.date_end, states=['open', 'finished'])
        else:
            contracts = employees._get_contracts(payslip_run.date_start, payslip_run.date_end, states=['open']) 

        default_values = Payslip.default_get(Payslip.fields_get())
        payslips_vals = []
        for contract in self._filter_contracts(contracts):
            structure = self.structure_id
            if self.liquidate_contract and contract.state in ['finished', 'close']:
                structure = payslip_run.liquidation_structure_id
            values = dict(default_values, **{
                'name': _('New Payslip'),
                'employee_id': contract.employee_id.id,
                'payslip_run_id': payslip_run.id,
                'date_from': payslip_run.date_start,
                'date_to': payslip_run.date_end,
                'date_liquidacion': self.date_liquidacion,
                'date_prima': self.date_prima,
                'date_cesantias': self.date_cesantias,
                'pay_cesantias_in_payroll': self.pay_cesantias_in_payroll,
                'pay_vacations_in_payroll': self.pay_vacations_in_payroll,
                'pay_primas_in_payroll': self.pay_primas_in_payroll,
                'contract_id': contract.id,
                'struct_id': structure.id, #self.structure_id.id or contract.structure_type_id.default_struct_id.id,
            })
            payslips_vals.append(values)
        payslips = Payslip.with_context(tracking_disable=True).create(payslips_vals)
        payslips.compute_slip()
        # v18 UX: "Generar" solo computa, NO valida (no genera asiento contable).
        # Los slips quedan en 'draft' con line_ids ya computados; _compute_state
        # detectara las lineas computadas y movera run a '02_close' (Confirmado).
        # Para crear el asiento contable, el usuario debe presionar
        # "Marcar como Listo" / "Validate" (action_payslip_done).
        return success_result

    def clean_employees(self):   
        self.employee_ids = [(5,0,0)]
        return {
            'context': self.env.context,
            'view_mode': 'form',
            'res_model': 'hr.payslip.employees',
            'res_id': self.id,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }
    @api.onchange('period_id')
    def _onchange_period_id(self):
        """Actualiza las fechas del lote segun el periodo seleccionado."""
        if self.period_id and (not self.date_start or not self.date_end or
                               self.date_start.year != self.period_id.date_start.year or
                               self.date_end.year != self.period_id.date_end.year):
            self.date_start = self.period_id.date_start
            self.date_end = self.period_id.date_end

    @api.onchange('date_start', 'date_end')
    def _onchange_dates(self):
        """Busca automaticamente el periodo correspondiente a las fechas."""
        if not self._context.get('skip_period_search'):
            if self.date_start:
                company_id = self.company_id.id or self.env.company.id
                if self.date_end:
                    days_diff = (self.date_end - self.date_start).days + 1
                    if days_diff <= 7:
                        schedule_pay = 'weekly'
                    elif days_diff <= 15:
                        schedule_pay = 'bi-monthly'
                    elif days_diff <= 31:
                        schedule_pay = 'monthly'
                    else:
                        schedule_pay = 'monthly'
                else:
                    schedule_pay = 'monthly'

                period = self.env['hr.period'].get_period(
                    self.date_start, self.date_end, schedule_pay, company_id)

                if period and self.period_id != period:
                    self.with_context(skip_period_search=True).period_id = period.id
