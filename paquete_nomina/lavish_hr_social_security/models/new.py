import math
import logging
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from decimal import Decimal
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

import base64
import io
import xlsxwriter
import math
import calendar
_logger = logging.getLogger(__name__)

def days360(start_date, end_date, method_eu=True):
    """Compute number of days between two dates regarding all months
    as 30-day months"""

    start_day = start_date.day
    start_month = start_date.month
    start_year = start_date.year
    end_day = end_date.day
    end_month = end_date.month
    end_year = end_date.year

    if (
            start_day == 31 or
            (
                method_eu is False and
                start_month == 2 and (
                    start_day == 29 or (
                        start_day == 28 and
                        calendar.isleap(start_year) is False
                    )
                )
            )
    ):
        start_day = 30

    if end_day == 31:
        if method_eu is False and start_day != 30:
            end_day = 1

            if end_month == 12:
                end_year += 1
                end_month = 1
            else:
                end_month += 1
        else:
            end_day = 30
    if end_month == 2 and end_day in (28, 29):
        end_day = 30

    return (
        end_day + end_month * 30 + end_year * 360 -
        start_day - start_month * 30 - start_year * 360 + 1
    )
class HrPayrollSocialSecurity(models.Model):
    _inherit = "hr.payroll.social.security"

    def _iniciar_log(self, step_name):
        """Inicia un log para un paso o proceso dado."""
        return {"step": step_name, "details": []}

    def _agregar_log(self, log, message, data=None):
        """Agrega un mensaje y datos opcionales al log."""
        if data is None:
            data = {}
        log["details"].append({"message": message, "data": data})
        return log

    def registrar_log_computo(self, log):
        """Registra el log de cómputo (en este ejemplo se escribe en el log del sistema)."""
        _logger.error("Log de cómputo: %s", log)
        return log

    def _get_period_dates(self):
        """Calcula la fecha de inicio y fin del período según el año y mes de la instancia."""
        start_date = date(int(self.year), int(self.month), 1)
        end_date = start_date + relativedelta(months=1, days=-1)
        return start_date, end_date

    def _obtener_parametros_anuales(self):
        annual_params = self.env["hr.annual.parameters"].search([("year", "=", self.year)], limit=1)
        if not annual_params:
            raise UserError(_("No se encontraron parámetros anuales para el año %s") % self.year)
        return annual_params

    def _limpiar_registros_previos(self, employee_id):
        if not employee_id:
            self.env["hr.errors.social.security"].search([
                ("executing_social_security_id", "=", self.id)
            ]).unlink()
            self.env["hr.executing.social.security"].search([
                ("executing_social_security_id", "=", self.id)
            ]).unlink()
        else:
            self.env["hr.errors.social.security"].search([
                ("executing_social_security_id", "=", self.id),
                ("employee_id", "=", employee_id)
            ]).unlink()
            self.env["hr.executing.social.security"].search([
                ("executing_social_security_id", "=", self.id),
                ("employee_id", "=", employee_id)
            ]).unlink()

    def _obtener_configuracion_seguridad_social(self):
        """Obtiene la configuración de seguridad social para cada proceso."""
        procesos = [
            "ss_empresa_salud", "ss_empresa_pension", "ss_empresa_arp",
            "ss_empresa_caja", "ss_empresa_sena", "ss_empresa_icbf"
        ]
        config_rules = {}
        for proc in procesos:
            config = self.env["hr.closing.configuration.header"].search([("process", "=", proc)], limit=1)
            if config:
                main_lines = {}
                for line in config.main_line_ids.filtered(lambda l: l.active):
                    key = (
                        line.contributor_type_id.id if line.contributor_type_id else False,
                        line.contributor_subtype_id.id if line.contributor_subtype_id else False
                    )
                    main_lines[key] = line
                leave_by_code = {}
                for line in config.leave_line_ids.filtered(lambda l: l.active):
                    if line.leave_type:
                        leave_by_code.setdefault(line.leave_type, []).append(line)
                    if line.code_leave:
                        for c in [x.strip() for x in line.code_leave.split(",")]:
                            leave_by_code.setdefault(c, []).append(line)
                config_rules[proc] = {
                    "config": config,
                    "main_lines": main_lines,
                    "leave_lines": leave_by_code
                }
        return config_rules

    def executing_social_security(self, employee_id=None):
        """
        Función principal para ejecutar el cálculo de seguridad social.
        Adaptada para mantener la lógica del primer archivo.
        """
        self.ensure_one()
        if self.state == 'accounting':
            raise ValidationError(_('No puede recalcular una seguridad social en estado contabilizado.'))
        date_start, date_end = self._get_period_dates()
        annual_params = self._obtener_parametros_anuales()
        self._limpiar_registros_previos(employee_id)
        config_rules = self._obtener_configuracion_seguridad_social()
        domain = []
        if employee_id:
            domain.append(('id', '=', employee_id))
            
        query = """
            SELECT DISTINCT e.id, e.name
            FROM hr_payslip p
            JOIN hr_employee e ON p.employee_id = e.id
            WHERE 
                p.state in ('done','paid')
                AND p.company_id = %s
                AND (
                    (p.date_from >= %s AND p.date_from <= %s)
                    OR (p.date_to >= %s AND p.date_to <= %s)
                )
            ORDER BY e.name
        """
        self.env.cr.execute(query, (self.company_id.id, date_start, date_end, date_start, date_end))
        employee_ids = [row[0] for row in self.env.cr.fetchall()]
        
        if domain:
            employees = self.env['hr.employee'].browse(employee_ids).filtered_domain(domain)
        else:
            employees = self.env['hr.employee'].browse(employee_ids)
        
        # Procesar cada empleado
        for employee in employees:
            self._procesar_empleado(employee, date_start, date_end, annual_params, config_rules)

        # Actualizar ausencias como no provisionales
        self._actualizar_ausencias_provisionales(date_start, date_end)

        self.state = 'done'
        return True

    def _actualizar_ausencias_provisionales(self, date_start, date_end):
        """Actualiza las ausencias para marcarlas como no provisionales
        despues de liquidar la seguridad social"""
        leaves = self.env['hr.leave'].search([
            ('state', '=', 'validate'),
            ('ibc_ss_provisional', '=', True),
            '|', '|',
            '&', ('date_from', '<=', date_end), ('date_to', '>=', date_start),
            '&', ('date_from', '>=', date_start), ('date_from', '<=', date_end),
            '&', ('date_to', '>=', date_start), ('date_to', '<=', date_end)
        ])
        if leaves:
            leaves.write({'ibc_ss_provisional': False})

    def _agregar_error(self, employee, desc):
        self.env["hr.errors.social.security"].create({
            "executing_social_security_id": self.id,
            "employee_id": employee.id,
            "description": desc
        })

    def _get_wage_in_date(self, process_date, contract):
        wage_in_date = contract.wage
        for change in sorted(contract.change_wage_ids, key=lambda x: x.date_start):
            if process_date >= change.date_start:
                wage_in_date = change.wage
        return wage_in_date

    def _validar_datos_empleado(self, employee):
        if not employee.tipo_coti_id:
            return self._agregar_error(employee, _(f"El empleado {employee.name} no tiene configurado el tipo de cotizante"))
        if not employee.subtipo_coti_id:
            return self._agregar_error(employee, _(f"El empleado {employee.name} no tiene configurado el subtipo de cotizante"))
        if not employee.work_contact_id.city_id:
            return self._agregar_error(employee, _(f"El empleado {employee.name} no tiene configurada la ciudad"))
        if not employee.work_contact_id.vat_co:
            return self._agregar_error(employee, _(f"El empleado {employee.name} no tiene configurado el documento de identidad"))

        obj_parameterization_contributors = self.env['hr.parameterization.of.contributors'].search(
            [('type_of_contributor', '=', employee.tipo_coti_id.id),
            ('contributor_subtype', '=', employee.subtipo_coti_id.id)], limit=1)

        if not obj_parameterization_contributors:
            return self._agregar_error(employee,
                _(f"No existe parametrización para el tipo/subtipo de cotizante del empleado {employee.name}."))

        entities_config = employee.social_security_entities
        entities_missing = []
        entities_missing_codes = []

        # Validar EPS
        if obj_parameterization_contributors.liquidates_eps_company or obj_parameterization_contributors.liquidated_eps_employee:
            eps_entities = entities_config.filtered(lambda e: e.contrib_id.type_entities == 'eps')
            if not eps_entities:
                entities_missing.append('EPS')
            elif len(eps_entities) > 1:
                return self._agregar_error(employee,
                    _(f"El empleado {employee.name} tiene más de una entidad EPS asignada."))
            elif not eps_entities[0].partner_id.code_pila_eps:
                entities_missing_codes.append('EPS')

        # Validar Pensión
        if obj_parameterization_contributors.liquidated_company_pension or obj_parameterization_contributors.liquidate_employee_pension or obj_parameterization_contributors.liquidates_solidarity_fund:
            pension_entities = entities_config.filtered(lambda e: e.contrib_id.type_entities == 'pension')
            if not pension_entities:
                entities_missing.append('Pensión')
            elif len(pension_entities) > 1:
                return self._agregar_error(employee,
                    _(f"El empleado {employee.name} tiene más de una entidad Pensión asignada."))
            elif not pension_entities[0].partner_id.code_pila_eps:
                entities_missing_codes.append('Pensión')

        # Validar ARL/ARP
        if obj_parameterization_contributors.liquidated_arl:
            risk_entities = entities_config.filtered(lambda e: e.contrib_id.type_entities == 'riesgo')
            if not risk_entities:
                entities_missing.append('ARL')
            elif len(risk_entities) > 1:
                return self._agregar_error(employee,
                    _(f"El empleado {employee.name} tiene más de una entidad ARL asignada."))
            elif not risk_entities[0].partner_id.code_pila_eps:
                entities_missing_codes.append('ARL')


        # Validar Caja de Compensación
        if obj_parameterization_contributors.liquidated_compensation_fund:
            fund_entities = entities_config.filtered(lambda e: e.contrib_id.type_entities == 'caja')
            if not fund_entities:
                entities_missing.append('Caja de Compensación')
            elif len(fund_entities) > 1:
                return self._agregar_error(employee,
                    _(f"El empleado {employee.name} tiene más de una entidad Caja de compensación asignada."))
            elif not fund_entities[0].partner_id.code_pila_ccf:
                entities_missing_codes.append('Caja de Compensación')
            elif not fund_entities[0].partner_id.partner_id.city_id:
                entities_missing_codes.append('Caja de Compensación NO TIENE CIUDAD')
        if entities_missing:
            return self._agregar_error(employee,
                _(f"El empleado {employee.name} no tiene configuradas las siguientes entidades: {', '.join(entities_missing)}"))

        if entities_missing_codes:
            return self._agregar_error(employee,
                _(f"Las siguientes entidades del empleado {employee.name} no tienen código configurado: {', '.join(entities_missing_codes)}"))


    def _obtener_contratos_empleado(self, employee, start_date, end_date):
        """Obtiene los contratos activos del empleado en el período."""
        return self.env["hr.contract"].search([
            ("employee_id", "=", employee.id),
            "|",
            "&", ("date_start", "<=", end_date), 
            "|", ("date_end", ">=", start_date), ("date_end", "=", False),
            "&", ("date_start", ">=", start_date), ("date_start", "<=", end_date)
        ])

    def _obtener_parametros_contribucion(self, employee):
        return self.env["hr.parameterization.of.contributors"].search([
            ("type_of_contributor", "=", employee.tipo_coti_id.id),
            ("contributor_subtype", "=", employee.subtipo_coti_id.id)
        ], limit=1)

    def _procesar_empleado(self, employee, date_start, date_end, annual_params, config_rules):
        """
        Procesa un empleado, adaptado del primer archivo.
        """
        self._validar_datos_empleado(employee)
        contracts = self._obtener_contratos_empleado(employee, date_start, date_end)
        if not contracts:
            self._agregar_error(employee, _("No hay contratos activos en el periodo"))
            return
        
        entidades = self._obtener_entidades_empleado(employee)
        contrib_param = self._obtener_parametros_contribucion(employee)
        if not contrib_param:
            self._agregar_error(employee, _("No se encontraron parámetros de contribución para el tipo y subtipo de cotizante"))
            return
        
        for contract in contracts:
            self._procesar_contrato(employee, contract, date_start, date_end, annual_params, config_rules, contrib_param, entidades)

    def _obtener_nominas_contrato(self, contract, start_date, end_date):
        """Obtiene las nóminas del contrato en el período."""
        return self.env["hr.payslip"].search([
            ("contract_id", "=", contract.id),
            ("state", "in", ["done", "paid"]),
            "|",
            "&", ("date_from", ">=", start_date), ("date_from", "<=", end_date),
            "&", ("date_to", ">=", start_date), ("date_to", "<=", end_date)
        ])

    def _procesar_contrato(self, employee, contract, date_start, date_end, annual_params, config_rules, contrib_param, entidades):
        """
        Procesa un contrato calculando primero el IBC global.
        Aplica correctamente la Ley 1393 segun configuracion include_absences_1393.
        """
        wage_actual = self._get_wage_in_date(date_end, contract)
        if wage_actual <= 0:
            self._agregar_error(employee, f"Sueldo inválido en {contract.name}")
            return

        payslips = self._obtener_nominas_contrato(contract, date_start, date_end)
        if not payslips:
            self._agregar_error(employee, f"No hay nóminas para {contract.name}")
            return

        payslip_lines = self._obtener_lineas_nomina_optimizado(payslips.ids)
        es_aprendiz = bool(contract.contract_type == "aprendizaje")
        ausencias = self.calcular_ausencias(employee, contract, date_start, date_end)

        # Ajustar fechas según contrato
        if contract.date_start and contract.date_start > date_start:
            date_start_calc = contract.date_start
        else:
            date_start_calc = date_start

        if contract.date_end and contract.date_end < date_end:
            date_end_calc = contract.date_end
        else:
            date_end_calc = date_end

        dias_periodo = days360(start_date=date_start_calc,end_date=date_end_calc)
        ausencias["dias_trabajados"] = dias_periodo - ausencias.get("dias_ausencias", 0)

        if ausencias["dias_trabajados"] <= 0 and ausencias["dias_ausencias"] <= 0:
            self._agregar_error(employee, f"No hay días trabajados ni ausencias en {contract.name}")
            return

        # Obtener configuracion Ley 1393 de la empresa
        company = contract.company_id or self.env.company
        try:
            include_absences_1393 = company.include_absences_1393 if 'include_absences_1393' in company._fields and company.include_absences_1393 else False
        except (AttributeError, KeyError):
            include_absences_1393 = False

        # Construcción de líneas para el cómputo (lines_pila)
        lines_pila = []
        base_salarial = 0.0
        base_no_salarial = 0.0
        base = 0.0

        # Categorias de ausencias en nomina
        category_ausencias = ['INCAPACIDAD', 'LICENCIA_NO_REMUNERADA', 'LICENCIA_REMUNERADA',
                              'LICENCIA_MATERNIDAD', 'VACACIONES', 'ACCIDENTE_TRABAJO']

        for line in payslip_lines['base_ss']:
            total_abs = abs(line['total'])
            # Excluir ausencias de la base salarial (se procesan aparte con tipo PILA)
            if line['category_code'] in category_ausencias:
                continue
            elif line['category_code'] == 'DEV_NO_SALARIAL':
                base_no_salarial += total_abs
            else:
                base_salarial += total_abs
                base += total_abs

        # Preparar lineas PILA de ausencias usando el campo novelty de hr.leave.type
        ausencias_pila = []
        valor_ausencias_pila = 0.0

        # Tipos PILA (novelty) que NO participan en limite 40% segun UGPP:
        # sln: Suspension temporal del contrato
        # ige: Incapacidad EPS
        # irl: Incapacidad ARL
        # lma: Licencia de Maternidad
        # lpa: Licencia de Paternidad
        # vco, vdi, vre: Vacaciones (compensadas, disfrutadas, retiro)
        novelty_excluidos_40 = ['sln', 'ige', 'irl', 'lma', 'lpa', 'vco', 'vdi', 'vre']

        # Mapeo de novelty a tipo interno PILA
        novelty_to_pila = {
            'sln': 'NO_PAY',
            'ige': 'SICKNESS',
            'irl': 'AT_EP',
            'lma': 'MAT_LIC',
            'lpa': 'MAT_LIC',
            'vco': 'VAC',
            'vdi': 'VAC',
            'vre': 'VAC',
            'lr': 'PAY',
            'lnr': 'NO_PAY',
            'lt': 'PAY',
            'p': None,  # Permisos no se envian en PILA
        }

        for ausencia in ausencias.get("ausencias", []):
            leave_id = ausencia.get("id")
            dias = ausencia.get("dias", 0)
            valor = ausencia.get("valor", 0)

            # Obtener el novelty del tipo de ausencia directamente
            leave = self.env['hr.leave'].browse(leave_id) if leave_id else None
            novelty = leave.holiday_status_id.novelty if leave and leave.holiday_status_id else None

            if not novelty or novelty == 'p':
                continue

            tipo_pila = novelty_to_pila.get(novelty, 'PAY')
            excluido_40 = novelty in novelty_excluidos_40

            ausencias_pila.append({
                'id': leave_id,
                'novelty': novelty,
                'tipo_pila': tipo_pila,
                'valor': valor,
                'dias': dias,
                'fecha_inicio': ausencia.get("fecha_inicio"),
                'fecha_fin': ausencia.get("fecha_fin"),
                'excluido_40': excluido_40,
                'ibc_detalle_html': ausencia.get("ibc_detalle_html", ""),
            })
            valor_ausencias_pila += valor

        # Aplicar Ley 1393 segun configuracion include_absences_1393
        # Solo se usa para calcular el exceso de no salariales (limite 40%).
        # Las ausencias NO se incluyen en ibc_calculado (línea MAIN): contribuyen
        # al IBC global mediante sus propias líneas PILA, evitando doble conteo.
        if include_absences_1393:
            base_for_40_limit = base_salarial + valor_ausencias_pila
        else:
            valor_ausencias_incluidas = sum(a['valor'] for a in ausencias_pila if not a['excluido_40'])
            base_for_40_limit = base_salarial + valor_ausencias_incluidas

        # Calcular limite 40% sobre (base_for_40_limit + no_salarial)
        total_for_limit = base_for_40_limit + base_no_salarial
        limite_no_salarial = total_for_limit * (annual_params.value_porc_statute_1395 / 100)

        # Calcular exceso de no salariales sobre el limite 40%
        exceso_no_salarial = max(0, base_no_salarial - limite_no_salarial)

        # IBC base = SOLO base salarial + exceso de no salariales.
        # Las ausencias contribuyen al IBC global mediante sus propias líneas PILA.
        ibc_calculado = base_salarial + exceso_no_salarial

        if exceso_no_salarial > 0:
            _logger.info("Ley 1393 - Empleado: %s, Exceso no salarial: %s, include_absences: %s",
                        employee.name, exceso_no_salarial, include_absences_1393)

        # Aplicar factor salario integral (70%)
        if contract.modality_salary == 'integral':
            ibc_calculado *= (annual_params.porc_integral_salary / 100)

        # Usar ibc_calculado como base para linea MAIN
        base = ibc_calculado
        if base_salarial > 0 and ausencias["dias_trabajados"] > 0:
            lines_pila.append((None, 'MAIN', base, ausencias["dias_trabajados"], None, None, base, ''))

        # Agregar lineas PILA por cada ausencia
        for aus in ausencias_pila:
            lines_pila.append((aus['id'], aus['tipo_pila'], aus['valor'], aus['dias'],
                              aus['fecha_inicio'], aus['fecha_fin'], aus['valor'],
                              aus.get('ibc_detalle_html', '')))
        sum_ibc = sum([lp[2] for lp in lines_pila])
        total_dias = sum([lp[3] for lp in lines_pila])
        tipo_cotizante = employee.tipo_coti_id.code if employee.tipo_coti_id else None
        ibc_global = self._set_limits_ibc(sum_ibc, annual_params.smmlv_monthly, tipo_cotizante, total_dias)
        
        # Vacaciones pagadas en dinero
        vac_money = 0.0
        for line in payslip_lines['all']:
            if line['rule_code'] in ('VACATIONS_MONEY', 'VACCONTRATO'):
                vac_money += abs(line['total'])
        
        # Configurar parámetros para el cálculo
        politics = {
            'eps_rate_employee': annual_params.value_porc_health_employee / 100,
            'eps_rate_employer': annual_params.value_porc_health_company / 100,
            'pen_rate_employee': annual_params.value_porc_pension_employee / 100,
            'pen_rate_employer': annual_params.value_porc_pension_company / 100,
            'pay_ccf_mat_pat': True,
            'smmlv': annual_params.smmlv_monthly
        }
        
        data = {
            'cr': self.env.cr,
            'is_liq': self.date_end >= (contract.retirement_date or contract.date_end) if (contract.retirement_date  or contract.date_end)  else False,
            'smmlv': annual_params.smmlv_monthly,
            'vac_money': vac_money,
            'f_type': employee.tipo_coti_id.code,
            'f_subtype': employee.subtipo_coti_id.code,
            'class': contract.contract_type,
            'apr': contract.contract_type == 'aprendizaje',
            'apr_lec': contract.contract_type == 'aprendizaje' and employee.tipo_coti_id.code == '12',
            'int': contract.modality_salary == 'integral',
            'date_start': contract.date_start,
            'settlement_date': contract.retirement_date,
            'period': self,
            'apply_ret': contract.state in ['close','finished'],
            'arl_rate': contract.risk_id.percent or 0,
        }
        data.update(politics)
        data['retired'] = data['apr'] or data['f_subtype'] not in ['00', False]
        
        # Procesar cada línea PILA
        for lp in lines_pila:
            new_line = {
                'document_type_contributor': employee.work_contact_id.l10n_latam_identification_type_id.dian_code,
                'document_contributor': employee.work_contact_id.vat_co,
                'type_contributor': employee.tipo_coti_id.code,
                'subtype_contributor': employee.subtipo_coti_id.code or '00',
                'foreign': 'X' if employee.extranjero else ' ',
                'colombian_abroad': 'X' if employee.residente else ' ',
                'municipality_city': employee.work_contact_id.city_id.code,
                'department': employee.work_contact_id.state_id.code,
                'first_last_name': employee.work_contact_id.first_lastname,
                'second_last_name': employee.work_contact_id.second_lastname,
                'first_name': employee.work_contact_id.first_name,
                'second_name': employee.work_contact_id.second_name,
                'executing_social_security_id': self.id,
                'employee_id': employee.id,
                'contract_id': contract.id,
                'global_ibc': ibc_global, 
                'nSueldo': wage_actual if wage_actual >= data['smmlv'] else data['smmlv'],
                'cExonerado1607': False,  
            }
            self._set_indicators(lp, new_line, data)
            
            self._set_quotation(lp, new_line, data, ibc_global)
            
            new_line['cExonerado1607'] = ibc_global < 10 * data['smmlv'] and not data['int'] and not data['apr']
            
            self._set_contribution_afp_eps(lp, new_line, data)
            self._set_contribution_arl_para(lp, new_line, data)
            
            self._set_dates(lp, new_line)
            
            new_line = self._round_fields(new_line)
            
            for campo_entidad, valor_entidad in entidades.items():
                if campo_entidad in new_line:
                    new_line[campo_entidad] = valor_entidad
                else:
                    new_line[campo_entidad] = valor_entidad
                    
            if payslips:
                new_line['dFechaInicioIGE'] = lp[4]
                new_line['dFechaFinIGE'] = lp[5]

            new_line['payslip_ids'] = [(6, 0, payslips.ids)]

            # Agregar detalle HTML del calculo IBC si existe
            if len(lp) > 7 and lp[7]:
                new_line['compute'] = lp[7]
            
            line_obj = self.env['hr.executing.social.security'].create(new_line)
            
            if new_line.get('main', False):
                self._update_main_line_totals(line_obj, payslips, new_line)

    def _round_fields(self, vals):
        """
        Redondea campos monetarios.
        """
        fields_to_round = [
            'nValorPensionEmpresa', 'nValorPensionEmpleado', 'nAporteVoluntarioPension',
            'nValorPensionTotal', 'nValorFondoSolidaridad', 'nValorFondoSubsistencia',
            'nValorSaludEmpresa', 'nValorSaludEmpleado', 'nValorSaludTotal',
            'nValorARP', 'nValorCajaCom', 'nValorSENA', 'nValorICBF'
        ]
        for field in fields_to_round:
            if field in vals and vals[field]:
                vals[field] = math.ceil(vals[field] / 100) * 100
        return vals

    def _update_main_line_totals(self, line, payslips, vals):
        nomina_health = 0
        nomina_pension = 0
        nomina_fondos = 0
        
        for payslip in payslips:
            for line_id in payslip.line_ids:
                if line_id.code == 'SSOCIAL001':
                    nomina_health += abs(line_id.total)
                elif line_id.code == 'SSOCIAL002':
                    nomina_pension += abs(line_id.total)
                elif line_id.code == 'SSOCIAL003':
                    nomina_fondos += abs(line_id.total)
                elif line_id.code == 'SSOCIAL004':
                    nomina_fondos += abs(line_id.total)
        
        line.write({
            'nValorSaludEmpleadoNomina': nomina_health,
            'nValorPensionEmpleadoNomina': nomina_pension,
            'nDiferenciaSalud': vals.get('nValorSaludEmpleado', 0) - nomina_health,
            'nDiferenciaPension': (vals.get('nValorPensionEmpleado', 0) + 
                                  vals.get('nValorFondoSolidaridad', 0) + 
                                  vals.get('nValorFondoSubsistencia', 0)) - (nomina_pension + nomina_fondos)
        })

    def _set_limits_ibc(self, ibc, valor_minimo, tipo_cotizante=None, dias=None):
        """Establece limites de IBC con logica especial para cotizante 51 (tiempo parcial).

        Para cotizante 51, el IBC minimo se calcula por semanas segun Resolucion 2388 de 2016:
        - 1-7 dias: SMMLV/4 (1 semana)
        - 8-14 dias: SMMLV/4 * 2 (2 semanas)
        - 15-21 dias: SMMLV/4 * 3 (3 semanas)
        - 22-30 dias: SMMLV (4 semanas)
        """
        annual_params = self._obtener_parametros_anuales()
        valor_maximo = 25 * annual_params.smmlv_monthly

        # Logica especial cotizante 51 (Trabajador tiempo parcial)
        if tipo_cotizante == '51' and dias:
            smmlv = annual_params.smmlv_monthly
            dias_redondeados = round(dias)
            if dias_redondeados >= 1 and dias_redondeados <= 7:
                valor_minimo = smmlv / 4
            elif dias_redondeados >= 8 and dias_redondeados <= 14:
                valor_minimo = (smmlv / 4) * 2
            elif dias_redondeados >= 15 and dias_redondeados <= 21:
                valor_minimo = (smmlv / 4) * 3
            elif dias_redondeados >= 22 and dias_redondeados <= 30:
                valor_minimo = smmlv

        if ibc > valor_maximo:
            return valor_maximo
        elif ibc < valor_minimo:
            return valor_minimo
        else:
            return ibc

    def _obtener_entidades_empleado(self, employee):
        """Obtiene las entidades de seguridad social del empleado.
        
        Args:
            employee: objeto hr.employee
            
        Returns:
            dict: Diccionario con los IDs de terceros y códigos de entidades
        """
        entidades = {
            "TerceroEPS": False,
            "TerceroPension": False,
            "TerceroFondoSolidaridad": False,
            "TerceroCajaCom": False,
            "TerceroARP": False,
            "TerceroSENA": False,
            "TerceroICBF": False,
            "eps_code": None,
            "afp_code": None,
            "ccf_code": None,
            "arl_code": None,
        }
        
        for entity in employee.social_security_entities:
            if entity.contrib_id.type_entities == 'eps':
                entidades["TerceroEPS"] = entity.partner_id.id
                entidades["eps_code"] = entity.partner_id.code_pila_eps
            elif entity.contrib_id.type_entities == 'pension':
                entidades["TerceroPension"] = entity.partner_id.id
                entidades["afp_code"] = entity.partner_id.code_pila_eps
            elif entity.contrib_id.type_entities == 'solidaridad':
                entidades["TerceroFondoSolidaridad"] = entity.partner_id.id
            elif entity.contrib_id.type_entities == 'caja':
                entidades["TerceroCajaCom"] = entity.partner_id.id
                entidades["ccf_code"] = entity.partner_id.code_pila_ccf
            elif entity.contrib_id.type_entities == 'riesgo':
                entidades["TerceroARP"] = entity.partner_id.id
                entidades["arl_code"] = entity.partner_id.code_pila_eps
        
        if not entidades["TerceroFondoSolidaridad"] and entidades["TerceroPension"]:
            entidades["TerceroFondoSolidaridad"] = entidades["TerceroPension"]
        
        sena = self.env["hr.contribution.register"].search([("type_entities", "=", "sena")], limit=1)
        if sena:
            sena_entity = self.env["hr.employee.entities"].search([("types_entities", "in", [sena.id])], limit=1)
            if sena_entity and sena_entity.partner_id:
                entidades["TerceroSENA"] = sena_entity.id
        
        icbf = self.env["hr.contribution.register"].search([("type_entities", "=", "icbf")], limit=1)
        if icbf:
            icbf_entity = self.env["hr.employee.entities"].search([("types_entities", "in", [icbf.id])], limit=1)
            if icbf_entity and icbf_entity.partner_id:
                entidades["TerceroICBF"] = icbf_entity.id
                
        return entidades

    def _obtener_lineas_nomina_optimizado(self, payslip_ids):
        if not payslip_ids:
            return {
                'all': [],
                'base_ss': [],
                'no_salarial': [],
                'ausencias': set(),
                'totales': {
                    'base_salarial': 0,
                    'base_no_salarial': 0,
                    'nomina_salud': 0,
                    'nomina_pension': 0,
                    'nomina_solidaridad': 0,
                    'nomina_subsistencia': 0
                }
            }
        
        payslip_lines = self.env['hr.payslip.line'].search([
            ('slip_id', 'in', payslip_ids)
        ])
        
        payslip_lines.mapped('salary_rule_id')
        payslip_lines.mapped('category_id')
        
        salary_rules = {rule.id: rule for rule in payslip_lines.mapped('salary_rule_id')}
        categories = {cat.id: cat for cat in payslip_lines.mapped('category_id')}
        
        parent_categories = self.env['hr.salary.rule.category'].browse(
            [cat.parent_id.id for cat in categories.values() if cat.parent_id]
        )
        parent_categories_dict = {cat.id: cat for cat in parent_categories}
        
        config_ss = self._obtener_configuracion_seguridad_social()
        codigos_ausencia = set()
        for proc, rules in config_ss.items():
            if "leave_lines" in rules:
                for code in rules["leave_lines"].keys():
                    codigos_ausencia.add(code)
        
        categorized_lines = {
            'all': [],
            'base_ss': [],
            'no_salarial': [],
            'ausencias': set(),
            'totales': {
                'base_salarial': 0,
                'base_no_salarial': 0,
                'nomina_salud': 0,
                'nomina_pension': 0,
                'nomina_solidaridad': 0,
                'nomina_subsistencia': 0
            }
        }
        
        for line in payslip_lines:
            rule = salary_rules.get(line.salary_rule_id.id)
            category = categories.get(line.category_id.id)
            parent_category_code = parent_categories_dict.get(category.parent_id.id).code if category.parent_id and category.parent_id.id in parent_categories_dict else False
            
            if rule.code in ["PERMISO", "VACACIONES_MONEY"]:
                continue
            
            line_data = {
                'id': line.id,
                'slip_id': line.slip_id.id,
                'salary_rule_id': line.salary_rule_id.id,
                'category_id': line.category_id.id,
                'total': line.total,
                'rule_code': rule.code,
                'base_seguridad_social': rule.base_seguridad_social,
                'base_parafiscales': rule.base_parafiscales,
                'category_code': category.code,
                'category_code_parent': parent_category_code
            }
            
            categorized_lines['all'].append(line_data)
            
            if category.code == 'DEV_NO_SALARIAL' or parent_category_code == 'DEV_NO_SALARIAL':
                categorized_lines['no_salarial'].append(line_data)
                categorized_lines['totales']['base_no_salarial'] += abs(line.total)
            elif rule.base_seguridad_social:
                categorized_lines['base_ss'].append(line_data)
                categorized_lines['totales']['base_salarial'] += abs(line.total)
            
            if rule.code in codigos_ausencia:
                categorized_lines['ausencias'].add(line.id)
            
            if rule.code == 'SSOCIAL001':
                categorized_lines['totales']['nomina_salud'] += abs(line.total)
            elif rule.code == 'SSOCIAL002':
                categorized_lines['totales']['nomina_pension'] += abs(line.total)
            elif rule.code == 'SSOCIAL003':
                categorized_lines['totales']['nomina_solidaridad'] += abs(line.total)
            elif rule.code == 'SSOCIAL004':
                categorized_lines['totales']['nomina_subsistencia'] += abs(line.total)
        return categorized_lines
    
    def _get_worked_days_sum(self, date_from, date_to,contract):
        worked_days_records = self.env['hr.payslip.worked_days'].search([
            ('payslip_id.contract_id', '=', contract.id),
            ('payslip_id.date_from', '>=', date_from),
            ('payslip_id.date_to', '<=', date_to),
            ('code', '=', 'WORK100'),
            ('payslip_id.struct_id.process', 'not in', ['vacaciones', 'prima', 'cesantias',]),
        ])
        total_days = sum(worked_days.number_of_days for worked_days in worked_days_records)
        return total_days


    def _get_ibc_last_month(self, date_to, contract):
        """
        Obtiene el IBC del mes anterior considerando las reglas de seguridad social
        y aplicando correctamente la Ley 1393 segun configuracion include_absences_1393.
        """
        from_date = (date_to.replace(day=1) - relativedelta(months=1))
        to_date = (date_to.replace(day=1) - relativedelta(days=1))
        annual_parameters = self.env['hr.annual.parameters'].search([
            ('year', '=', date_to.year)
        ], limit=1)
        if not annual_parameters:
            raise UserError(_(
                'No se encontraron parámetros anuales para el año %s.'
            ) % date_to.year)

        # Obtener configuracion Ley 1393 de la empresa
        company = contract.company_id or self.env.company
        try:
            include_absences_1393 = company.include_absences_1393 if 'include_absences_1393' in company._fields and company.include_absences_1393 else False
        except (AttributeError, KeyError):
            include_absences_1393 = False

        payslip_lines = self.env['hr.payslip.line'].search([
            ('slip_id.state', 'in', ['done', 'paid']),
            ('slip_id.contract_id', '=', contract.id),
            ('slip_id.date_from', '<=', to_date),
            ('slip_id.date_to', '>=', from_date),
        ])

        # Tipos PILA (novelty) que NO participan en limite 40% segun UGPP
        novelty_excluidos_40 = ['sln', 'ige', 'irl', 'lma', 'lpa', 'vco', 'vdi', 'vre']

        lines_by_type = {
            'base_ss': [],
            'no_salarial': [],
            'ausencias_excluidas': [],  # novelty excluido del 40%
            'ausencias_incluidas': [],  # novelty incluido en el 40% (lr, lt)
        }

        for line in payslip_lines:
            cat_code = line.salary_rule_id.category_id.code
            parent_code = line.salary_rule_id.category_id.parent_id.code if line.salary_rule_id.category_id.parent_id else None

            # Verificar si la linea tiene leave_id para obtener el novelty
            novelty = None
            try:
                if 'leave_id' in line._fields and line.leave_id and line.leave_id.holiday_status_id:
                    novelty = line.leave_id.holiday_status_id.novelty
            except (AttributeError, KeyError):
                pass

            # Clasificar por tipo usando novelty
            if novelty:
                if novelty in novelty_excluidos_40:
                    lines_by_type['ausencias_excluidas'].append(line)
                else:
                    lines_by_type['ausencias_incluidas'].append(line)
            elif cat_code == 'DEV_NO_SALARIAL' or parent_code == 'DEV_NO_SALARIAL':
                lines_by_type['no_salarial'].append(line)
            elif line.salary_rule_id.base_seguridad_social:
                lines_by_type['base_ss'].append(line)

        # Calcular totales
        value_base_ss = sum(abs(line.total) for line in lines_by_type['base_ss'])
        value_no_salarial = sum(abs(line.total) for line in lines_by_type['no_salarial'])
        value_ausencias_excluidas = sum(abs(line.total) for line in lines_by_type['ausencias_excluidas'])
        value_ausencias_incluidas = sum(abs(line.total) for line in lines_by_type['ausencias_incluidas'])

        # Aplicar Ley 1393 segun configuracion
        if include_absences_1393:
            # Todas las ausencias participan en el calculo del 40%
            base_for_40 = value_base_ss + value_ausencias_excluidas + value_ausencias_incluidas
        else:
            # UGPP: ausencias excluidas NO participan en el limite 40%
            # Solo ausencias incluidas (lr, lt) participan
            base_for_40 = value_base_ss + value_ausencias_incluidas

        # Calcular limite 40%
        total_for_limit = base_for_40 + value_no_salarial
        statute_value = total_for_limit * (annual_parameters.value_porc_statute_1395 / 100)
        exceso_no_salarial = max(0, value_no_salarial - statute_value)

        # IBC = base_for_40 + exceso de no salariales
        ibc = base_for_40 + exceso_no_salarial

        # Si UGPP: sumar ausencias excluidas directamente al IBC (no pasaron por limite 40%)
        if not include_absences_1393:
            ibc += value_ausencias_excluidas

        # Obtener nominas unicas para el detalle
        payslips = self.env['hr.payslip'].browse(list(set(line.slip_id.id for line in payslip_lines)))
        nominas_detalle = []
        for slip in payslips:
            nominas_detalle.append({
                'id': slip.id,
                'number': slip.number or f"ID:{slip.id}",
                'date_from': slip.date_from,
                'date_to': slip.date_to,
                'wage': slip.contract_id.wage if slip.contract_id else 0,
            })

        # Calcular promedio de salarios
        salarios = [n['wage'] for n in nominas_detalle if n['wage'] > 0]
        promedio_salario = sum(salarios) / len(salarios) if salarios else contract.wage

        calculo_detalle = {
            'periodo': {'desde': from_date, 'hasta': to_date},
            'valores': {
                'base_seguridad_social': value_base_ss,
                'no_salarial': value_no_salarial,
                'ausencias_excluidas': value_ausencias_excluidas,
                'ausencias_incluidas': value_ausencias_incluidas,
                'total': total_for_limit
            },
            'ley_1393': {
                'include_absences': include_absences_1393,
                'base_for_40': base_for_40,
                'porcentaje': annual_parameters.value_porc_statute_1395,
                'limite': statute_value,
                'exceso': exceso_no_salarial
            },
            'ibc_final': ibc,
            'nominas': nominas_detalle,
            'promedio_salario': promedio_salario,
        }

        ibc_final = ibc if ibc else contract.wage
        if (contract.fecha_ibc and
            from_date.year == contract.fecha_ibc.year and
            from_date.month == contract.fecha_ibc.month):
            ibc_final = contract.u_ibc

        # Retornar diccionario con valor y detalles
        return {
            'value': ibc_final,
            'detalle': calculo_detalle,
            'html': self._generar_html_ibc_detalle(calculo_detalle, ibc_final)
        }

    def _generar_html_ibc_detalle(self, detalle, ibc_final):
        """Genera HTML con el detalle del calculo IBC para seguridad social."""
        periodo = detalle.get('periodo', {})
        valores = detalle.get('valores', {})
        ley_1393 = detalle.get('ley_1393', {})
        nominas = detalle.get('nominas', [])
        promedio = detalle.get('promedio_salario', 0)

        # Tabla de nominas
        nominas_html = ""
        if nominas:
            nominas_html = """
            <table class='table table-sm table-bordered mb-2'>
                <thead class='table-light'>
                    <tr>
                        <th>Nomina</th>
                        <th>Periodo</th>
                        <th class='text-end'>Salario</th>
                    </tr>
                </thead>
                <tbody>
            """
            for n in nominas:
                date_from = n['date_from'].strftime('%d/%m') if n['date_from'] else 'N/A'
                date_to = n['date_to'].strftime('%d/%m/%Y') if n['date_to'] else 'N/A'
                nominas_html += f"""
                    <tr>
                        <td><code>{n['number']}</code></td>
                        <td>{date_from} - {date_to}</td>
                        <td class='text-end'>${n['wage']:,.2f}</td>
                    </tr>
                """
            nominas_html += """
                </tbody>
            </table>
            """

        desde = periodo.get('desde')
        hasta = periodo.get('hasta')
        periodo_str = f"{desde.strftime('%d/%m/%Y')} - {hasta.strftime('%d/%m/%Y')}" if desde and hasta else 'N/A'

        html = f"""
        <div class="card">
            <div class="card-header bg-info text-white py-2">
                <strong>Detalle Calculo IBC - Mes Anterior</strong>
            </div>
            <div class="card-body py-2">
                <div class="mb-2">
                    <small class="text-muted">Periodo:</small> <strong>{periodo_str}</strong>
                </div>

                {nominas_html}

                <table class="table table-sm table-borderless mb-2">
                    <tr>
                        <td class="text-muted" style="width:50%">Base Seguridad Social:</td>
                        <td class="text-end">${valores.get('base_seguridad_social', 0):,.2f}</td>
                    </tr>
                    <tr>
                        <td class="text-muted">No Salarial:</td>
                        <td class="text-end">${valores.get('no_salarial', 0):,.2f}</td>
                    </tr>
                    <tr>
                        <td class="text-muted">Ausencias Excluidas:</td>
                        <td class="text-end">${valores.get('ausencias_excluidas', 0):,.2f}</td>
                    </tr>
                    <tr>
                        <td class="text-muted">Ausencias Incluidas:</td>
                        <td class="text-end">${valores.get('ausencias_incluidas', 0):,.2f}</td>
                    </tr>
                </table>

                <div class="alert alert-secondary py-1 mb-2">
                    <small>
                        <strong>Ley 1393:</strong> Limite {ley_1393.get('porcentaje', 40)}% = ${ley_1393.get('limite', 0):,.2f}
                        | Exceso: ${ley_1393.get('exceso', 0):,.2f}
                    </small>
                </div>

                <div class="row">
                    <div class="col-6">
                        <small class="text-muted">Promedio Salario:</small><br/>
                        <strong>${promedio:,.2f}</strong>
                    </div>
                    <div class="col-6 text-end">
                        <small class="text-muted">IBC Final:</small><br/>
                        <strong class="text-primary fs-5">${ibc_final:,.2f}</strong>
                    </div>
                </div>
            </div>
        </div>
        """
        return html

    def calcular_ausencias(self, employee, contract, start_date, end_date, days_payslip=None):
        from datetime import datetime
        import calendar
        
        if days_payslip is None:
            days_payslip = self._get_worked_days_sum(start_date, end_date, contract)
        
        result = {
            "ausencias": [],
            "dias_trabajados": days_payslip,
            "dias_ausencias": 0,
            "tipos_ausencia": {
                "incapacidad_eps": 0,
                "licencia_no_remunerada": 0,
                "licencia_remunerada": 0,
                "maternidad": 0,
                "vacaciones": 0,
                "incapacidad_arl": 0,
                "licencia_no_pagada": 0,
                "permiso": 0
            },
            "valor_total_ausencias": 0,
            "valor_confirmado": True
        }
        
        #if contract.contract_type == "aprendizaje":
        #    return result
        
        tipo_ausencia_map = {
            "EGA": "incapacidad_eps", "EGH": "incapacidad_eps",
            "LICENCIA_NO_REMUNERADA": "licencia_no_remunerada", "INAS_INJU": "licencia_no_remunerada",
            "SANCION": "licencia_no_remunerada", "SUSP_CONTRATO": "licencia_no_remunerada", "DNR": "licencia_no_remunerada",
            "LICENCIA_REMUNERADA": "licencia_remunerada", "LUTO": "licencia_remunerada", "REP_VACACIONES": "licencia_remunerada",
            "MAT": "maternidad", "PAT": "maternidad",
            "VACDISFRUTADAS": "vacaciones",
            "LICENCIA_NO_PAGADA": "licencia_no_pagada",
            "PERMISO": "permiso",
            "EP": "incapacidad_arl", "AT": "incapacidad_arl",
            "sln": "licencia_no_remunerada",
            "ige": "incapacidad_eps",
            "irl": "incapacidad_arl",
            "lma": "maternidad",
            "lpa": "maternidad",
            "vco": "vacaciones",
            "vdi": "vacaciones",
            "vre": "vacaciones",
            "lr": "licencia_remunerada",
            "lnr": "licencia_no_remunerada",
            "lt": "licencia_remunerada"
        }
        
        dias_del_mes = calendar.monthrange(end_date.year, end_date.month)[1]
        es_mes_31_dias = dias_del_mes == 31
        es_febrero = end_date.month == 2
        
        ausencias_dict = {}
        
        leave_domain = [
            ('employee_id', '=', employee.id),
            ('holiday_status_id.novelty','!=','p'),
            ('state', '=', 'validate'),
            '|', '|',
                '&', ('date_from', '<=', end_date), ('date_to', '>=', start_date),
                '&', ('date_from', '>=', start_date), ('date_from', '<=', end_date),
                '&', ('date_to', '>=', start_date), ('date_to', '<=', end_date)
        ]
        
        all_leaves = self.env['hr.leave'].search(leave_domain)
        
        for leave in all_leaves:
            ausencias_dict[leave.id] = {
                'leave': leave,
                'es_del_contrato': leave.contract_id.id == contract.id if leave.contract_id else False,
                'is_vacation_money': leave.is_vacation_money if 'is_vacation_money' in leave._fields and leave.is_vacation_money else False,
                'leave_lines': [],
                'payslip_lines': []
            }
        
        if all_leaves:
            leave_line_domain = [
                ('leave_id', 'in', all_leaves.ids),
                ('date', '>=', start_date),
                ('date', '<=', end_date)
            ]
            leave_lines = self.env['hr.leave.line'].search(leave_line_domain)
            
            for line in leave_lines:
                leave_id = line.leave_id.id
                if leave_id in ausencias_dict:
                    ausencias_dict[leave_id]['leave_lines'].append(line)
        
        payslip_domain = [
            ('employee_id', '=', employee.id),
            ('state', 'in', ['done', 'paid']),
            ('date_from', '<=', end_date),
            ('date_to', '>=', start_date)
        ]
        
        payslips = self.env['hr.payslip'].search(payslip_domain)
        
        if payslips:
            payslip_line_domain = [
                ('slip_id', 'in', payslips.ids),
                ('leave_id', '!=', False)
            ]
            
            payslip_lines = self.env['hr.payslip.line'].search(payslip_line_domain)
            
            for line in payslip_lines:
                leave_id = line.leave_id.id
                if leave_id not in ausencias_dict:
                    ausencias_dict[leave_id] = {
                        'leave': line.leave_id,
                        'liquidar_con_base': line.salary_rule_id.liquidar_con_base,
                        'es_del_contrato': line.leave_id.contract_id.id == contract.id if line.leave_id.contract_id else False,
                        'is_vacation_money': line.leave_id.is_vacation_money if 'is_vacation_money' in line.leave_id._fields and line.leave_id.is_vacation_money else False,
                        'leave_lines': [],
                        'payslip_lines': []
                    }
                ausencias_dict[leave_id]['payslip_lines'].append(line)
        

        
        ausencias_con_contrato = sum(1 for info in ausencias_dict.values() if info['es_del_contrato'] and not info['is_vacation_money'])
        
        ausencias_procesadas = []
        
        ausencias_a_procesar = {k: v for k, v in ausencias_dict.items() 
                            if (ausencias_con_contrato == 0 or (v['es_del_contrato'] and not v['is_vacation_money']))}
        
        for leave_id, info in ausencias_a_procesar.items():
            leave = info['leave']
            
            dt_from = max(fields.Datetime.from_string(leave.date_from), datetime.combine(start_date, datetime.min.time()))
            dt_to = min(fields.Datetime.from_string(leave.date_to), datetime.combine(end_date, datetime.max.time()))
            dt_from = dt_from.date() if isinstance(dt_from, datetime) else dt_from
            dt_to = dt_to.date() if isinstance(dt_to, datetime) else dt_to
            
            if dt_to.day == 31:
                dt_to = dt_to.replace(day=30)
            
            days = (dt_to - dt_from).days + 1
            
            tipo = tipo_ausencia_map.get(leave.holiday_status_id.code, None)
            if not tipo:
                try:
                    if 'novelty' in leave.holiday_status_id._fields:
                        tipo = tipo_ausencia_map.get(leave.holiday_status_id.novelty, "desconocido")
                except (AttributeError, KeyError):
                    pass
            if not tipo:
                tipo = "desconocido"
            if not tipo:
                tipo = "desconocido"
            
            valor_aus = 0
            valor_confirmado = False
            fuente = "ninguna"
            use_ibc_calculation = False
            if leave.holiday_status_id.eps_arl_input_id.liquidar_con_base:
                use_ibc_calculation = True
            ibc_detalle_html = ""
            ibc_value = 0
            if use_ibc_calculation:
                # Usar ibc_ss_value del leave si esta definido y no es provisional
                try:
                    if 'ibc_ss_value' in leave._fields and leave.ibc_ss_value > 0:
                        ibc_value = leave.ibc_ss_value
                        fuente_origin = leave.ibc_ss_origin if 'ibc_ss_origin' in leave._fields else 'ibc'
                        fuente = f"ibc_ausencia_{fuente_origin or 'ibc'}"
                        valor_confirmado = not (leave.ibc_ss_provisional if 'ibc_ss_provisional' in leave._fields else True)
                except (AttributeError, KeyError):
                    pass
                else:
                    ibc_resultado = self._get_ibc_last_month(end_date, contract)
                    ibc_value = ibc_resultado['value']
                    ibc_detalle_html = ibc_resultado.get('html', '')
                    fuente = "ibc_mes_anterior"
                    valor_confirmado = True

                # Actualizar ibc_pila en la ausencia si es diferente
                if leave and ibc_value > 0 and (not leave.ibc_pila or leave.ibc_pila != ibc_value):
                    try:
                        leave.write({'ibc_pila': ibc_value})
                    except Exception as e:
                        _logger.warning(f"No se pudo actualizar ibc_pila en leave {leave.id}: {e}")

                daily_rate = ibc_value / 30
                valor_aus = daily_rate * days
            elif info['leave_lines'] and use_ibc_calculation == False:
                dias_lineas = sum(line.days_payslip for line in info['leave_lines']) or 1
                valor_lineas = sum(line.amount for line in info['leave_lines'])
                valor_aus = (valor_lineas / dias_lineas) * days
                valor_confirmado = True
                fuente = "lineas_ausencia"
            elif info['payslip_lines'] and use_ibc_calculation == False:
                valor_aus = sum(line.total for line in info['payslip_lines'])
                valor_confirmado = True
                fuente = "lineas_nomina"
            else:
                salario_diario = contract.wage / 30 if contract else 0
                valor_aus = salario_diario * days
                fuente = "estimado"
            
            ausencia_procesada = {
                "id": leave_id,
                "holiday_status_id": leave.holiday_status_id.id,
                "tipo": tipo,
                "codigo": leave.holiday_status_id.code,
                "fecha_inicio": dt_from,
                "fecha_fin": dt_to,
                "dias": days,
                "valor": valor_aus,
                "valor_confirmado": valor_confirmado,
                "cruza_mes": False,
                "fuente": fuente,
                "es_del_contrato": info['es_del_contrato'],
                "ibc_ss_origin": leave.ibc_ss_origin if 'ibc_ss_origin' in leave._fields else None,
                "ibc_ss_provisional": leave.ibc_ss_provisional if 'ibc_ss_provisional' in leave._fields else True,
                "ibc_detalle_html": ibc_detalle_html,
            }
            
            ausencias_procesadas.append(ausencia_procesada)
        
        ausencias_procesadas.sort(key=lambda a: a["fecha_inicio"])
        
        ultima_fecha = None
        dias_efectivos_ausencia = 0
        ausencia_cruza_fin_mes = False
        ausencia_cubre_todo_febrero = False
        
        for ausencia in ausencias_procesadas:
            leave = self.env['hr.leave'].browse(ausencia["id"])
            fecha_fin_original = fields.Datetime.from_string(leave.date_to).date()
            
            if fecha_fin_original.month > end_date.month or fecha_fin_original.year > end_date.year:
                ausencia["cruza_mes"] = True
                ausencia_cruza_fin_mes = True
            
            if ultima_fecha and ausencia["fecha_inicio"] <= ultima_fecha:
                dias_ajustados = (ausencia["fecha_fin"] - max(ausencia["fecha_inicio"], ultima_fecha)).days + 1
                ausencia["dias"] = max(0, dias_ajustados)
            
            if not ultima_fecha or ausencia["fecha_fin"] > ultima_fecha:
                ultima_fecha = ausencia["fecha_fin"]
            
            if es_febrero and ausencia["fecha_inicio"].day == 1 and ausencia["fecha_fin"].day == dias_del_mes:
                ausencia_cubre_todo_febrero = True
                ausencia["cubre_todo_febrero"] = True
            else:
                ausencia["cubre_todo_febrero"] = False
            
            result["ausencias"].append(ausencia)
            if ausencia["tipo"] in result["tipos_ausencia"]:
                result["tipos_ausencia"][ausencia["tipo"]] += ausencia["dias"]
            
            dias_efectivos_ausencia += ausencia["dias"]
            
            if ausencia["dias"] > 0:
                result["valor_total_ausencias"] += (ausencia["valor"]/ausencia["dias"]) * ausencia["dias"]
        
        if es_mes_31_dias and ausencias_procesadas and ultima_fecha and ultima_fecha.day == 30:
            for ausencia in result["ausencias"]:
                if ausencia["fecha_fin"] == ultima_fecha and ausencia["cruza_mes"]:
                    valor_diario = (ausencia["valor"]/ausencia["dias"]) if ausencia["dias"] > 0 else 0
                    ausencia["dias"] += 1
                    ausencia["valor"] = ausencia["dias"] * valor_diario
                    dias_efectivos_ausencia += 1
        
        if es_febrero and ausencia_cruza_fin_mes:
            dias_faltantes = 30 - dias_del_mes
            for ausencia in result["ausencias"]:
                if ausencia["cruza_mes"]:
                    valor_diario = (ausencia["valor"]/ausencia["dias"]) if ausencia["dias"] > 0 else 0
                    ausencia["dias"] += dias_faltantes
                    ausencia["valor"] = ausencia["dias"] * valor_diario
                    dias_efectivos_ausencia += dias_faltantes
        
        if es_febrero and ausencia_cubre_todo_febrero:
            dias_faltantes = 30 - dias_del_mes
            for ausencia in result["ausencias"]:
                if ausencia.get("cubre_todo_febrero", False):
                    valor_diario = (ausencia["valor"]/ausencia["dias"]) if ausencia["dias"] > 0 else 0
                    ausencia["dias"] += dias_faltantes
                    ausencia["valor"] = ausencia["dias"] * valor_diario
                    dias_efectivos_ausencia += dias_faltantes
                    if ausencia["tipo"] in result["tipos_ausencia"]:
                        result["tipos_ausencia"][ausencia["tipo"]] += dias_faltantes
        
        result["dias_ausencias"] = dias_efectivos_ausencia
        result["dias_trabajados"] = days_payslip - dias_efectivos_ausencia
        
        if contract.date_start and contract.date_start > start_date:
            dias_no_contratados = (contract.date_start - start_date).days
            result["dias_trabajados"] = days_payslip - dias_no_contratados - dias_efectivos_ausencia
        
        if result["dias_trabajados"] < 0:
            result["dias_trabajados"] = 0
        
        return result

    def _determinar_tipo_ausencia(self, code):
        if code in ["EGA", "EGH",]:
            return "incapacidad_eps"
        if code in ["LICENCIA_NO_REMUNERADA", "INAS_INJU", "SANCION", "SUSP_CONTRATO", "DNR"]:
            return "licencia_no_remunerada"
        if code in ["LICENCIA_REMUNERADA", "LUTO", "REP_VACACIONES"]:
            return "licencia_remunerada"
        if code in ["MAT", "PAT"]:
            return "maternidad"
        if code == "VACDISFRUTADAS":
            return "vacaciones"
        if code == "LICENCIA_NO_PAGADA":
            return "licencia_no_pagada"
        if code == "PERMISO":
            return "permiso"
        if code in ["EP", "AT"]:
            return "incapacidad_arl"
        return "desconocido"

    def _set_indicators(self, lp, new_line, data):
        new_line['leave_id'] = lp[0]
        new_line['main'] = (lp[1] == 'MAIN')
        new_line['ret'] = 'X' if data['apply_ret'] and data['is_liq'] else ' '
        data['apply_ret'] = False

        if lp[1] == 'VAC':
            new_line['vac_lr'] = 'X'
            new_line['nDiasVacaciones'] = lp[3]
        elif lp[1] == 'PAY':
            new_line['vac_lr'] = 'L'
            new_line['nDiasLicenciaRenumerada'] = lp[3]
        elif lp[1] == 'NO_PAY':
            new_line['sln'] = True
            new_line['nDiasLicencia'] = lp[3]
        elif lp[1] == 'SICKNESS':
            new_line['ige'] = True
            new_line['nDiasIncapacidadEPS'] = lp[3]
        elif lp[1] in ('MAT_LIC', 'PAT_LIC'):
            new_line['lma'] = True
            new_line['nDiasMaternidad'] = lp[3]
        elif lp[1] == 'AT_EP':
            new_line['irl'] = lp[3]
            new_line['nDiasIncapacidadARP'] = lp[3]
        else:
            new_line['vac_lr'] = ' '

        new_line['k_start'] = data['date_start'] if new_line.get('ing', ' ') == 'X' else None
        new_line['k_end'] = data['settlement_date'] if new_line.get('ret', ' ') == 'X' else None
        # Validar que las fechas existan antes de comparar
        period_date_start = data['period'].date_start
        contract_date_start = data['date_start']
        if period_date_start and contract_date_start:
            new_line['nIngreso'] = (period_date_start.month == contract_date_start.month and
                                    period_date_start.year == contract_date_start.year)
        else:
            new_line['nIngreso'] = False
        new_line['nRetiro'] = True if new_line.get('ret', ' ') == 'X' else False

        if not new_line.get('ing', False):
            # Validar que las fechas del periodo existan antes de ejecutar query
            if period_date_start and data['period'].date_end:
                query = """
                SELECT date_start FROM hr_contract_change_wage
                WHERE contract_id = %s AND
                date_start BETWEEN %s AND %s
                ORDER by date_start DESC LIMIT 1"""
                data['cr'].execute(query, (new_line['contract_id'], period_date_start, data['period'].date_end))
                vsp = data['cr'].fetchall()
                new_line['vsp'] = bool(vsp)
                new_line['vsp_start'] = vsp[0][0] if vsp else None
            else:
                new_line['vsp'] = False
                new_line['vsp_start'] = None
        else:
            new_line['vsp'] = False
            new_line['vsp_start'] = None

        new_line['vst'] = False
        if new_line.get('main', False) and not data.get('apr', False):
            query = """
            SELECT SUM(pl.total)
            FROM hr_payslip_line pl
            JOIN hr_salary_rule sr ON pl.salary_rule_id = sr.id
            JOIN hr_salary_rule_category sc ON sr.category_id = sc.id
            WHERE pl.slip_id IN (
                SELECT id FROM hr_payslip 
                WHERE contract_id = %s AND date_from >= %s AND date_to <= %s
            ) AND sc.code != 'BASIC' AND sr.base_seguridad_social = true
            """
            data['cr'].execute(query, (new_line['contract_id'], data['period'].date_start, data['period'].date_end))
            vst_total = data['cr'].fetchone()
            if vst_total and vst_total[0] and vst_total[0] > 0:
                new_line['vst'] = True

        new_line['cAVP'] = data.get('cAVP', False)
        new_line['nAporteVoluntarioPension'] = data.get('nAporteVoluntarioPension', 0)
        if new_line.get('cAVP', False):
            if 'cAVP' in data:
                del data['cAVP']
            if 'nAporteVoluntarioPension' in data:
                del data['nAporteVoluntarioPension']
        if new_line.get('main', False):
            new_line['nDiasLiquidados'] = lp[3]
            new_line['nNumeroHorasLaboradas'] = lp[3] * (230/30)
        return new_line

    def _verificar_exoneracion_ley_1607(self, employee, contract, ibc, annual_params):
        ibc_dec = self._calc_decimal(ibc)
        smmlv = self._calc_decimal(annual_params.smmlv_monthly)
        threshold = smmlv * Decimal("10") if employee.company_id.exonerated_law_1607 else smmlv * Decimal("12")
        return ibc_dec < threshold
    
    def _set_quotation(self, lp, new_line, data, global_ibc):
        """
        Establece las cuotas para cada concepto basado en el IBC global.
        """
        if data.get('int', False):
            new_line['wage_type'] = 'X'
        elif new_line.get('vst', False):
            new_line['wage_type'] = 'V'
        elif data.get('apr', False):
            new_line['wage_type'] = ' '
        else:
            new_line['wage_type'] = 'F'
                
        ibc_base = self._set_limits_ibc(lp[2], data['smmlv'] / 30 * lp[3], data.get('f_type'), lp[3])
        new_line['nValorBaseSalud'] = ibc_base
        
        if (data.get('apr', False) or (data.get('f_type', '') == '01' and 
            data.get('f_subtype', '') in ['01', '03', '06', '04'])) and lp[1] == 'MAIN':
            new_line['nValorBaseFondoPension'] = 0
        else:
            new_line['nValorBaseFondoPension'] = ibc_base
            
        new_line['nValorBaseARP'] = 0 if data.get('f_type', '') == '12' else ibc_base
        
        new_line['nValorBaseCajaCom'] = 0 if data.get('apr', False) else (lp[6] + data.get('vac_money', 0))
        
        exonerado = global_ibc < 10 * data['smmlv'] and not data['int'] and not data['apr']
        new_line['cExonerado1607'] = exonerado
        
        new_line['nValorBaseSENA'] = 0 if exonerado else new_line['nValorBaseCajaCom'] - data.get('vac_money', 0)
        new_line['nValorBaseICBF'] = 0 if exonerado else new_line['nValorBaseCajaCom'] - data.get('vac_money', 0)
        
        if 'vac_money' in data:
            del data['vac_money']
            
        return new_line
    
    def _set_contribution_afp_eps(self, lp, new_line, data):
        if data.get('retired', False) or data.get('apr', False):
            new_line['nPorcAportePensionEmpresa'] = 0
            new_line['nPorcAportePensionEmpleado'] = 0
            new_line['nPorcFondoSolidaridad'] = 0
            new_line['nValorFondoSolidaridad'] = 0
            new_line['nValorFondoSubsistencia'] = 0
        elif new_line.get('sln', False):
            new_line['nPorcAportePensionEmpresa'] = data.get('pen_rate_employer', 0) * 100
            new_line['nPorcAportePensionEmpleado'] = 0
            new_line['nPorcFondoSolidaridad'] = 0
            new_line['nValorFondoSolidaridad'] = 0
            new_line['nValorFondoSubsistencia'] = 0
        else:
            new_line['nPorcAportePensionEmpresa'] = data.get('pen_rate_employer', 0) * 100
            new_line['nPorcAportePensionEmpleado'] = data.get('pen_rate_employee', 0) * 100
            if new_line.get('global_ibc', 0)  >= 4 * data.get('smmlv', 0):
                ratio = new_line['nValorBaseFondoPension'] / data['smmlv']
                if ratio < 16:
                    new_line['nPorcFondoSolidaridad'] = 1.0
                elif ratio < 17:
                    new_line['nPorcFondoSolidaridad'] = 1.2
                elif ratio < 18:
                    new_line['nPorcFondoSolidaridad'] = 1.4
                elif ratio < 19:
                    new_line['nPorcFondoSolidaridad'] = 1.6
                elif ratio < 20:
                    new_line['nPorcFondoSolidaridad'] = 1.8
                else:
                    new_line['nPorcFondoSolidaridad'] = 2.0
                new_line['nValorFondoSolidaridad'] = new_line['nValorBaseFondoPension'] * 0.005
                #if new_line['nPorcFondoSolidaridad'] > 1.0:
                fondo_subsistencia = new_line['nPorcFondoSolidaridad'] / 100 - 0.005
                new_line['nValorFondoSubsistencia'] = new_line['nValorBaseFondoPension'] * fondo_subsistencia
                #else:
                #   new_line['nValorFondoSubsistencia'] = 0
            else:
                new_line['nPorcFondoSolidaridad'] = 0
                new_line['nValorFondoSolidaridad'] = 0
                new_line['nValorFondoSubsistencia'] = 0
        new_line['nValorPensionEmpresa'] = new_line.get('nValorBaseFondoPension', 0) * new_line.get('nPorcAportePensionEmpresa', 0) / 100
        new_line['nValorPensionEmpleado'] = new_line.get('nValorBaseFondoPension', 0) * new_line.get('nPorcAportePensionEmpleado', 0) / 100
        new_line['nValorPensionTotal'] = new_line.get('nValorPensionEmpresa', 0) + new_line.get('nValorPensionEmpleado', 0) + new_line.get('nAporteVoluntarioPension', 0)
        if new_line.get('global_ibc', 0) >= 10 * data.get('smmlv', 0) or data.get('int', False) or data.get('apr', False):
            new_line['nPorcAporteSaludEmpresa'] = data.get('eps_rate_employer', 0) * 100
            new_line['nPorcAporteSaludEmpleado'] = data.get('eps_rate_employee', 0) * 100
        elif new_line.get('sln', False):
            new_line['nPorcAporteSaludEmpresa'] = 0
            new_line['nPorcAporteSaludEmpleado'] = 0
        else:
            if new_line.get('cExonerado1607', False):
                new_line['nPorcAporteSaludEmpresa'] = 0
            else:
                new_line['nPorcAporteSaludEmpresa'] = data.get('eps_rate_employer', 0) * 100
            new_line['nPorcAporteSaludEmpleado'] = data.get('eps_rate_employee', 0) * 100
        new_line['nValorSaludEmpresa'] = new_line.get('nValorBaseSalud', 0) * new_line.get('nPorcAporteSaludEmpresa', 0) / 100
        new_line['nValorSaludEmpleado'] = new_line.get('nValorBaseSalud', 0) * new_line.get('nPorcAporteSaludEmpleado', 0) / 100
        new_line['nValorSaludTotal'] = new_line.get('nValorSaludEmpresa', 0) + new_line.get('nValorSaludEmpleado', 0)
        return new_line

    def _set_contribution_arl_para(self, lp, new_line, data):
        pay_arl = new_line.get('main', False) and data.get('f_type', '') != '12'
        if pay_arl:
            new_line['nPorcAporteARP'] = data.get('arl_rate', 0)
        else:
            new_line['nPorcAporteARP'] = 0
        new_line['nValorARP'] = new_line.get('nValorBaseARP', 0) * new_line.get('nPorcAporteARP', 0) / 100
        pay_ccf = new_line.get('main', False)
        pay_ccf |= data.get('pay_ccf_mat_pat', False) and new_line.get('lma', False)
        pay_ccf |= (lp[1] == 'VAC' or lp[1] == 'PAY')
        pay_ccf |= not new_line.get('main', False) and new_line.get('ret', ' ') == 'X'
        pay_ccf &= not data.get('apr', False)
        new_line['nPorcAporteCajaCom'] = 4.0 if pay_ccf else 0
        new_line['nValorCajaCom'] = new_line.get('nValorBaseCajaCom', 0) * new_line.get('nPorcAporteCajaCom', 0) / 100
        if not new_line.get('cExonerado1607', False):
            pay_para = new_line.get('global_ibc', 0) >= 10 * data.get('smmlv', 0)
            pay_para |= data.get('int', False)
            pay_para &= not new_line.get('sln', False)
            pay_para &= new_line.get('main', False)
            new_line['nPorcAporteSENA'] = 2.0 if pay_para else 0
            new_line['nPorcAporteICBF'] = 3.0 if pay_para else 0
        else:
            new_line['nPorcAporteSENA'] = 0
            new_line['nPorcAporteICBF'] = 0
        new_line['nValorSENA'] = new_line.get('nValorBaseSENA', 0) * new_line.get('nPorcAporteSENA', 0) / 100
        new_line['nValorICBF'] = new_line.get('nValorBaseICBF', 0) * new_line.get('nPorcAporteICBF', 0) / 100
        return new_line

    def _set_dates(self, lp, new_line):
        if lp[1] == 'NO_PAY':
            new_line['dFechaInicioSLN'] = lp[4]
            new_line['dFechaFinSLN'] = lp[5]
        elif lp[1] == 'SICKNESS':
            new_line['dFechaInicioIGE'] = lp[4]
            new_line['dFechaFinIGE'] = lp[5]
        elif lp[1] in ('MAT_LIC', 'PAT_LIC'):
            new_line['dFechaInicioLMA'] = lp[4]
            new_line['dFechaFinLMA'] = lp[5]
        elif lp[1] == 'VAC':
            new_line['dFechaInicioVACLR'] = lp[4]
            new_line['dFechaFinVACLR'] = lp[5]
        elif lp[1] == 'AT_EP':
            new_line['dFechaInicioIRL'] = lp[4]
            new_line['dFechaFinIRL'] = lp[5]
        return new_line

    @staticmethod
    def round_100(valor):
        """Redondea al 100 más cercano por arriba."""
        return math.ceil(valor / 100) * 100
