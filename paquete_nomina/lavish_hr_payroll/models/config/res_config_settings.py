# -*- coding: utf-8 -*-
"""
Configuracion de Nomina Colombia
================================
Extension de res.company y res.config.settings para nomina colombiana.

Modelos extraidos a archivos separados:
- hr_employee_salary_history.py: HrEmployeeSalaryHistory, HrSalaryChangeReason
- hr_employee_ibc_history.py: HrEmployeeIbcHistory
- services/setup/payroll_setup_service.py: PayrollSetupService
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class ResCompany(models.Model):
    _inherit = 'res.company'

    # =========================================================================
    # APROBACIONES
    # =========================================================================
    novelty_approval_required = fields.Boolean(
        'Requiere Aprobacion de Novedades',
        default=False,
        help='Si esta activo, las novedades requieren un proceso de aprobacion'
    )
    vacation_cutoff_day = fields.Integer(
        'Día de corte vacaciones',
        help='Día del mes para el corte de cálculo de vacaciones (1-31). '
             'Si no se define, no se aplica corte.'
    )
    vacation_cutoff_month = fields.Selection(
        [
            ('1', 'Enero'),
            ('2', 'Febrero'),
            ('3', 'Marzo'),
            ('4', 'Abril'),
            ('5', 'Mayo'),
            ('6', 'Junio'),
            ('7', 'Julio'),
            ('8', 'Agosto'),
            ('9', 'Septiembre'),
            ('10', 'Octubre'),
            ('11', 'Noviembre'),
            ('12', 'Diciembre'),
        ],
        string='Mes de corte vacaciones',
        help='Mes para el corte de cálculo de vacaciones. '
             'Si no se define, no se aplica corte.'
    )

    # =========================================================================
    # ACCIONES DE CONFIGURACION DESDE EMPRESA
    # =========================================================================
    def _get_payroll_settings_proxy(self):
        """Crea un res.config.settings temporal con la compañia activa."""
        self.ensure_one()
        return self.env['res.config.settings'].with_company(self).with_context(
            allowed_company_ids=[self.id],
            company_id=self.id,
        ).create({})

    def action_setup_salary_categories(self):
        """Configura categorias de reglas salariales desde la compañia."""
        self.ensure_one()
        return self._get_payroll_settings_proxy().action_setup_salary_categories()

    def action_setup_leave_types(self):
        """Configura tipos de ausencia desde la compañia."""
        self.ensure_one()
        return self._get_payroll_settings_proxy().action_setup_leave_types()

    def action_generate_salary_rules(self):
        """Genera reglas salariales completas desde la compañia."""
        self.ensure_one()
        return self._get_payroll_settings_proxy().action_generate_salary_rules()

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # =========================================================================
    # CONTABILIZACION
    # =========================================================================
    # NOTA: accounting_method y default_accounting_date estan definidos en
    # hr.annual.parameters (lavish_hr_employee) y se acceden via
    # nomina_accounting_method (related) en res_config_settings_nomina.py

    addref_work_address_account_moves = fields.Boolean(
        'Agregar ubicacion laboral en descripcion movimientos contables'
    )
    round_payroll = fields.Boolean(
        'NO redondear decimales en procesos de liquidacion'
    )

    # =========================================================================
    # VACACIONES, CESANTIAS, PRIMA
    # =========================================================================
    pay_vacations_in_payroll = fields.Boolean('Liquidar vacaciones en nomina?')
    pay_cesantias_in_payroll = fields.Boolean('Liquidar Intereses de cesantia en nomina?')
    pay_primas_in_payroll = fields.Boolean('Liquidar Primas en nomina?')
    vacation_cutoff_day = fields.Integer(
        related='company_id.vacation_cutoff_day',
        string='Día de corte vacaciones',
        readonly=False
    )
    vacation_cutoff_month = fields.Selection(
        related='company_id.vacation_cutoff_month',
        string='Mes de corte vacaciones',
        readonly=False
    )
    vacation_days_calculate_absences = fields.Char('Dias de vacaciones para calcular deducciones')
    cesantias_salary_take = fields.Boolean('Promediar salario ultimos 3 meses en cesantias')
    prima_salary_take = fields.Boolean('Promediar salario ultimos 6 meses en prima')

    # =========================================================================
    # CONDICIONES LEGALES PARA PROMEDIOS DE SUELDO
    # =========================================================================
    # PRIMA DE SERVICIOS (CST Art. 306-308)
    prima_periodo_meses = fields.Integer(
        'Meses periodo prima',
        default=6,
        help='Periodo del semestre para prima: 6 meses (Ene-Jun o Jul-Dic)'
    )
    prima_incluye_auxilio = fields.Boolean(
        'Prima incluye auxilio transporte',
        default=True,
        help='Incluir auxilio de transporte en base de prima si salario < 2 SMMLV'
    )
    prima_incluye_extras = fields.Boolean(
        'Prima incluye horas extras',
        default=True,
        help='Incluir promedio de horas extras en base de prima'
    )
    prima_meses_extras = fields.Integer(
        'Meses promedio extras para prima',
        default=3,
        help='Cantidad de meses para promediar horas extras en prima'
    )

    # CESANTIAS (CST Art. 249-258, Ley 50/1990)
    cesantias_periodo_meses = fields.Integer(
        'Meses periodo cesantias',
        default=12,
        help='Periodo anual para cesantias: 12 meses (Ene-Dic)'
    )
    cesantias_incluye_auxilio = fields.Boolean(
        'Cesantias incluye auxilio transporte',
        default=True,
        help='Incluir auxilio de transporte en base de cesantias si salario < 2 SMMLV'
    )
    cesantias_incluye_extras = fields.Boolean(
        'Cesantias incluye horas extras',
        default=True,
        help='Incluir promedio de horas extras en base de cesantias'
    )
    cesantias_meses_extras = fields.Integer(
        'Meses promedio extras para cesantias',
        default=3,
        help='Cantidad de meses para promediar horas extras en cesantias'
    )

    # INTERESES SOBRE CESANTIAS (Ley 52/1975, Ley 50/1990 Art. 99)
    intereses_tasa_anual = fields.Float(
        'Tasa anual intereses cesantias',
        default=12.0,
        help='Tasa de interes anual sobre cesantias: 12%'
    )

    # VACACIONES (CST Art. 186-192)
    vacaciones_periodo_meses = fields.Integer(
        'Meses periodo vacaciones',
        default=12,
        help='Periodo anual para vacaciones: 12 meses'
    )
    vacaciones_dias_por_ano = fields.Integer(
        'Dias vacaciones por año',
        default=15,
        help='Dias habiles de vacaciones por año trabajado: 15'
    )
    vacaciones_incluye_auxilio = fields.Boolean(
        'Vacaciones incluye auxilio transporte',
        default=False,
        help='NO incluir auxilio en vacaciones (Art. 192 CST)'
    )
    vacaciones_incluye_extras = fields.Boolean(
        'Vacaciones incluye horas extras',
        default=False,
        help='NO incluir extras en vacaciones (solo salario ordinario)'
    )

    # PROMEDIO PONDERADO - Cambios de salario
    promedio_detectar_cambios = fields.Boolean(
        'Detectar cambios de salario para promedio',
        default=True,
        help='Si hubo cambio de salario en el periodo, calcular promedio ponderado'
    )
    promedio_meses_cambio = fields.Integer(
        'Meses para detectar cambio salarial',
        default=3,
        help='Meses hacia atras para detectar si hubo cambio de salario'
    )

    # =========================================================================
    # CONSOLIDACIÓN DE PRESTACIONES SOCIALES
    # =========================================================================
    validar_consolidacion_estructura = fields.Boolean(
        'Validar estructura de consolidación al contabilizar',
        default=True,
        help=(
            'Valida la existencia de cuentas contables y reglas de consolidación antes de contabilizar.\n\n'
            'VALIDACIONES:\n'
            '→ Cuentas de provisión configuradas (ej: 2610, 2615)\n'
            '→ Cuentas de consolidación configuradas (ej: 2505, 2510)\n'
            '→ Reglas: CESANTIAS_CONS, INTCESANTIAS_CONS, VACACIONES_CONS\n\n'
            'IMPORTANTE:\n'
            'La consolidación garantiza el ajuste contable exacto comparando el saldo de la '
            'cuenta de provisión vs la cuenta de consolidación al cierre del período.\n\n'
            'Use el botón "Crear Estructura de Consolidación" para generar automáticamente '
            'las estructuras y reglas requeridas.'
        )
    )

    # Cuentas contables para Cesantías (PUC Colombia) - Multi-empresa
    cuenta_provision_cesantias_id = fields.Many2one(
        'account.account',
        string='Cuenta Provisión Cesantías',
        domain="[('company_id', '=', current_company_id)]",
        company_dependent=True,
        help='PUC 261005 - Provisión de cesantías (Pasivos estimados). '
             'Si no se configura, busca cuentas que inicien con 261005.'
    )
    cuenta_consolidacion_cesantias_id = fields.Many2one(
        'account.account',
        string='Cuenta Obligación Cesantías',
        domain="[('company_id', '=', current_company_id)]",
        company_dependent=True,
        help='PUC 2510 - Cesantías consolidadas (Obligaciones laborales). '
             'Si no se configura, busca cuentas que inicien con 2510.'
    )

    # Cuentas contables para Intereses de Cesantías
    cuenta_provision_intereses_id = fields.Many2one(
        'account.account',
        string='Cuenta Provisión Intereses',
        domain="[('company_id', '=', current_company_id)]",
        company_dependent=True,
        help='PUC 261010 - Provisión de intereses sobre cesantías. '
             'Si no se configura, busca cuentas que inicien con 261010.'
    )
    cuenta_consolidacion_intereses_id = fields.Many2one(
        'account.account',
        string='Cuenta Obligación Intereses',
        domain="[('company_id', '=', current_company_id)]",
        company_dependent=True,
        help='PUC 2515 - Intereses sobre cesantías (Obligaciones laborales). '
             'Si no se configura, busca cuentas que inicien con 2515.'
    )

    # Cuentas contables para Vacaciones
    cuenta_provision_vacaciones_id = fields.Many2one(
        'account.account',
        string='Cuenta Provisión Vacaciones',
        domain="[('company_id', '=', current_company_id)]",
        company_dependent=True,
        help='PUC 261015 - Provisión de vacaciones (Pasivos estimados). '
             'Si no se configura, busca cuentas que inicien con 261015.'
    )
    cuenta_consolidacion_vacaciones_id = fields.Many2one(
        'account.account',
        string='Cuenta Obligación Vacaciones',
        domain="[('company_id', '=', current_company_id)]",
        company_dependent=True,
        help='PUC 2525 - Vacaciones consolidadas (Obligaciones laborales). '
             'Si no se configura, busca cuentas que inicien con 2525.'
    )

    # Opción de integrar consolidación en liquidación
    integrar_consolidacion_liquidacion = fields.Boolean(
        'Integrar consolidación en liquidación de contrato',
        default=False,
        help=(
            'Si está activo, al liquidar un contrato:\n'
            '- Las cuentas de provisión (26XX) y obligación (25XX) quedarán en cero\n'
            '- Se ejecutará la regla GASTO_FESTIVO para ajustar diferencias\n'
            '- El saldo pendiente se trasladará al gasto del período\n\n'
            'Útil para: Cierre de año, liquidaciones de contrato, ajustes de festivos.'
        )
    )

    def action_crear_estructura_consolidacion(self):
        """
        Crea la estructura de consolidación y las reglas necesarias.

        IMPORTANTE: Solo crea si no existe, NUNCA actualiza reglas existentes
        para no dañar información configurada manualmente.

        Crea:
        - Estructura de consolidación para cesantías
        - Estructura de consolidación para vacaciones
        - Reglas de consolidación (CESANTIAS_CONS, INTCESANTIAS_CONS, VACACIONES_CONS)
        - Regla GASTO_FESTIVO para ajuste de provisión vs obligación
        - Líneas contables (salary_rule_accounting) con cuentas PUC
        """
        self.ensure_one()

        Structure = self.env['hr.payroll.structure']
        StructureType = self.env['hr.payroll.structure.type']
        SalaryRule = self.env['hr.salary.rule']
        RuleAccounting = self.env['hr.salary.rule.accounting']
        AccountAccount = self.env['account.account']

        # Configuración de conceptos consolidables (PUC Colombia)
        consolidacion_config = {
            'cesantias': {
                'codigo_regla': 'CESANTIAS_CONS',
                'codigo_provision': 'PRVCESANTIAS',
                'cuenta_provision': '261005',
                'cuenta_obligacion': '2510',
                'nombre': 'Consolidación Cesantías',
                'tipo_prestacion': 'cesantias',
                'estructura': 'cesantias',
            },
            'intereses': {
                'codigo_regla': 'INTCESANTIAS_CONS',
                'codigo_provision': 'PRVINTCESANTIAS',
                'cuenta_provision': '261010',
                'cuenta_obligacion': '2515',
                'nombre': 'Consolidación Intereses de Cesantías',
                'tipo_prestacion': 'intereses_cesantias',
                'estructura': 'cesantias',
            },
            'vacaciones': {
                'codigo_regla': 'VACACIONES_CONS',
                'codigo_provision': 'PRVVACACIONES',
                'cuenta_provision': '261015',
                'cuenta_obligacion': '2525',
                'nombre': 'Consolidación Vacaciones',
                'tipo_prestacion': 'vacaciones',
                'estructura': 'vacaciones',
            },
        }

        # Buscar o crear tipo de estructura para consolidación
        struct_type = StructureType.search([
            ('name', '=', 'Consolidación')
        ], limit=1)

        if not struct_type:
            default_work_entry = self.env['hr.work.entry.type'].search([
                ('code', '=', 'WORK100')
            ], limit=1)
            if not default_work_entry:
                default_work_entry = self.env['hr.work.entry.type'].search([], limit=1)

            struct_type = StructureType.create({
                'name': 'Consolidación',
                'wage_type': 'monthly',
                'default_work_entry_type_id': default_work_entry.id if default_work_entry else False,
            })

        # Crear estructuras de consolidación
        estructuras_creadas = []
        estructuras = {}

        # Estructura para Cesantías e Intereses
        struct_cesantias = Structure.search([
            ('process', '=', 'consolidacion'),
            ('name', 'ilike', 'Cesantías'),
        ], limit=1)

        if not struct_cesantias:
            struct_cesantias = Structure.create({
                'name': 'Consolidación Cesantías',
                'code': 'consolidacion_cesantias',
                'process': 'consolidacion',
                'type_id': struct_type.id,
            })
            estructuras_creadas.append(struct_cesantias.name)
        estructuras['cesantias'] = struct_cesantias

        # Estructura para Vacaciones
        struct_vacaciones = Structure.search([
            ('process', '=', 'consolidacion'),
            ('name', 'ilike', 'Vacaciones'),
        ], limit=1)

        if not struct_vacaciones:
            struct_vacaciones = Structure.create({
                'name': 'Consolidación Vacaciones',
                'code': 'consolidacion_vacaciones',
                'process': 'consolidacion',
                'type_id': struct_type.id,
            })
            estructuras_creadas.append(struct_vacaciones.name)
        estructuras['vacaciones'] = struct_vacaciones

        # Crear reglas de consolidación y sus líneas contables
        reglas_creadas = []
        cuentas_faltantes = []
        contabilidad_creada = []

        for concepto, config in consolidacion_config.items():
            codigo_regla = config['codigo_regla']

            rule = SalaryRule.search([('code', '=', codigo_regla)], limit=1)

            if not rule:
                estructura = estructuras.get(config['estructura'])
                rule = SalaryRule.create({
                    'name': config['nombre'],
                    'code': codigo_regla,
                    'struct_id': estructura.id if estructura else False,
                    'sequence': 10 if concepto != 'intereses' else 20,
                    'category_id': self.env.ref('hr_payroll.BASIC').id,
                    'amount_select': 'code',
                    'active': True,
                })
                reglas_creadas.append(rule.name)

            # Buscar cuentas PUC
            cuenta_prov = AccountAccount.search([
                ('code', '=like', f"{config['cuenta_provision']}%"),
                ('company_id', '=', self.env.company.id),
            ], limit=1)

            cuenta_oblig = AccountAccount.search([
                ('code', '=like', f"{config['cuenta_obligacion']}%"),
                ('company_id', '=', self.env.company.id),
            ], limit=1)

            if not cuenta_prov:
                cuentas_faltantes.append(f"{config['cuenta_provision']} (Provisión {concepto})")
            if not cuenta_oblig:
                cuentas_faltantes.append(f"{config['cuenta_obligacion']} (Obligación {concepto})")

            if rule and cuenta_prov and cuenta_oblig:
                existing_accounting = RuleAccounting.search([
                    ('salary_rule', '=', rule.id),
                ], limit=1)

                if not existing_accounting:
                    RuleAccounting.create({
                        'salary_rule': rule.id,
                        'debit_account': cuenta_oblig.id,
                        'credit_account': cuenta_prov.id,
                        'third_debit': 'empleado',
                        'third_credit': 'empleado',
                    })
                    contabilidad_creada.append(f"{codigo_regla}: D:{cuenta_oblig.code} C:{cuenta_prov.code}")

        # Crear regla GASTO_FESTIVO
        rule_gasto_festivo = SalaryRule.search([('code', '=', 'GASTO_FESTIVO')], limit=1)

        if not rule_gasto_festivo:
            rule_gasto_festivo = SalaryRule.create({
                'name': 'Gasto Festivo - Ajuste Provisión/Obligación',
                'code': 'GASTO_FESTIVO',
                'struct_id': struct_vacaciones.id if struct_vacaciones else False,
                'sequence': 100,
                'category_id': self.env.ref('hr_payroll.BASIC').id,
                'amount_select': 'code',
                'active': True,
            })
            reglas_creadas.append(rule_gasto_festivo.name)

            cuenta_prov_vac = AccountAccount.search([
                ('code', '=like', '261015%'),
                ('company_id', '=', self.env.company.id),
            ], limit=1)
            cuenta_oblig_vac = AccountAccount.search([
                ('code', '=like', '2525%'),
                ('company_id', '=', self.env.company.id),
            ], limit=1)

            if cuenta_prov_vac and cuenta_oblig_vac:
                RuleAccounting.create({
                    'salary_rule': rule_gasto_festivo.id,
                    'debit_account': cuenta_prov_vac.id,
                    'credit_account': cuenta_oblig_vac.id,
                    'third_debit': 'compañia',
                    'third_credit': 'empleado',
                })
                contabilidad_creada.append(f"GASTO_FESTIVO: D:{cuenta_prov_vac.code} C:{cuenta_oblig_vac.code}")

        # Construir mensaje de resultado
        mensaje = []
        if estructuras_creadas:
            mensaje.append(f"Estructuras creadas: {', '.join(estructuras_creadas)}")
        if reglas_creadas:
            mensaje.append(f"Reglas creadas: {', '.join(reglas_creadas)}")
        if contabilidad_creada:
            mensaje.append(f"Contabilidad creada: {', '.join(contabilidad_creada)}")
        if cuentas_faltantes:
            mensaje.append(
                f"ADVERTENCIA: Faltan cuentas PUC: {', '.join(cuentas_faltantes)}. "
                f"Créelas en el plan de cuentas."
            )

        if mensaje:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Consolidación de Prestaciones'),
                    'message': '\n'.join(mensaje),
                    'type': 'warning' if cuentas_faltantes else 'success',
                    'sticky': True,
                }
            }

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Consolidación'),
                'message': _('Estructura, reglas y contabilidad ya existen. No se realizaron cambios.'),
                'type': 'info',
                'sticky': False,
            }
        }

    # =========================================================================
    # CONFIGURACION DE TIPO COTIZANTE POR DEFECTO
    # =========================================================================
    tipo_cotizante_default_id = fields.Many2one(
        'hr.tipo.cotizante',
        string='Tipo Cotizante por Defecto',
        help='Tipo de cotizante que se asignara a nuevos empleados'
    )
    subtipo_cotizante_default_id = fields.Many2one(
        'hr.subtipo.cotizante',
        string='Subtipo Cotizante por Defecto',
        help='Subtipo de cotizante que se asignara a nuevos empleados'
    )

    prst_wo_susp = fields.Boolean(
        'No descontar suspensiones de prima',
        config_parameter='lavish_hr_payroll.prst_wo_susp'
    )

    # =========================================================================
    # AUXILIO DE TRANSPORTE - VALIDACION DISTANCIA
    # =========================================================================
    validate_distance_aux_transport = fields.Boolean(
        'Validar distancia para auxilio de transporte',
        config_parameter='lavish_hr_payroll.validate_distance_aux_transport',
        help='Si esta activo, no se pagara auxilio de transporte a empleados que vivan a menos de 1km del lugar de trabajo'
    )
    distance_threshold_km = fields.Float(
        'Distancia minima (km)',
        config_parameter='lavish_hr_payroll.distance_threshold_km',
        default=1.0,
        help='Distancia minima en kilometros para recibir auxilio de transporte. Por defecto 1km segun Decreto 1258/1959'
    )

    # =========================================================================
    # TIPO COTIZANTE POR DEFECTO
    # NOTA: No usar prefijo "default_" porque tiene significado especial en Odoo
    # =========================================================================
    nomina_tipo_cotizante_id = fields.Many2one(
        'hr.tipo.cotizante',
        string='Tipo Cotizante por Defecto (nomina)',
        help='Tipo de cotizante que se asignara a nuevos empleados'
    )
    nomina_subtipo_cotizante_id = fields.Many2one(
        'hr.subtipo.cotizante',
        string='Subtipo Cotizante por Defecto (nomina)',
        help='Subtipo de cotizante que se asignara a nuevos empleados'
    )

    # Alias para compatibilidad con vistas existentes en servidor
    nomina_default_tipo_cotizante_id = fields.Many2one(
        'hr.tipo.cotizante',
        string='Tipo Cotizante por Defecto (alias)',
        help='Alias de nomina_tipo_cotizante_id para compatibilidad'
    )
    nomina_default_subtipo_cotizante_id = fields.Many2one(
        'hr.subtipo.cotizante',
        string='Subtipo Cotizante por Defecto (alias)',
        help='Alias de nomina_subtipo_cotizante_id para compatibilidad'
    )

    # =========================================================================
    # ACCIONES - Usan PayrollSetupService
    # =========================================================================

    def action_setup_all_payroll(self):
        """
        Configura TODO el modulo de nomina en orden logico.
        Muestra progreso en vivo con notificaciones secuenciales.
        Crea o actualiza segun si ya existen los datos.
        """
        self.ensure_one()
        company = self.env.company

        # Definir pasos en orden logico
        steps = [
            ('tipos', 'Tipos de Cotizante', self._setup_tipos_cotizante),
            ('subtipos', 'Subtipos de Cotizante', self._setup_subtipos_cotizante),
            ('params', 'Parametrizaciones SS', self._setup_parametrizaciones),
            ('overtime', 'Tipos Horas Extras', self._setup_overtime_types),
            ('employees', 'Asignar Empleados', self._setup_assign_employees),
            ('sections', 'Secciones de Estructura', self._setup_structure_sections),
        ]

        results = []
        errors = []
        total_created = 0
        total_updated = 0

        for idx, (code, name, method) in enumerate(steps, 1):
            try:
                # Notificar inicio del paso
                self._notify_progress(f'[{idx}/{len(steps)}] {name}...', 'info')

                # Ejecutar paso
                result = method(company)
                created = result.get('created', 0)
                updated = result.get('updated', 0)
                total_created += created
                total_updated += updated

                # Notificar resultado del paso
                status = 'Creados' if created else 'Actualizados' if updated else 'Sin cambios'
                msg = f'{name}: {created} creados, {updated} actualizados'
                results.append(msg)

                self._notify_progress(f'OK: {name} ({created}+{updated})', 'success')

            except Exception as e:
                error_msg = f'{name}: {str(e)}'
                errors.append(error_msg)
                self._notify_progress(f'ERROR: {name}', 'danger')
                _logger.exception(f"Error en setup paso {code}")

        # Mensaje final
        final_msg = f'Configuracion completada para {company.name}\n'
        final_msg += f'Total: {total_created} creados, {total_updated} actualizados\n'
        if errors:
            final_msg += f'\nErrores ({len(errors)}):\n' + '\n'.join(errors)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Configuracion de Nomina'),
                'message': final_msg,
                'type': 'success' if not errors else 'warning',
                'sticky': True,
            }
        }

    def _notify_progress(self, message, notif_type='info'):
        """Envia notificacion de progreso al usuario"""
        self.env['bus.bus']._sendone(
            self.env.user.partner_id,
            'simple_notification',
            {
                'title': _('Configuracion Nomina'),
                'message': message,
                'type': notif_type,
                'sticky': False,
            }
        )
        # Commit para que la notificacion se envie inmediatamente
        self.env.cr.commit()

    def _normalize_name_case(self, name):
        """Pone la primera letra en mayuscula y el resto en minuscula."""
        if not name:
            return name
        normalized = str(name).strip()
        if not normalized:
            return normalized
        return normalized[:1].upper() + normalized[1:].lower()

    def _setup_tipos_cotizante(self, company):
        """Paso 1: Crear/actualizar tipos de cotizante"""
        service = self.env['hr.payroll.setup.service']
        TipoCotizante = self.env['hr.tipo.cotizante']

        created = updated = 0
        for data in service.get_tipos_cotizante_data():
            existing = TipoCotizante.search([('code', '=', data['code'])], limit=1)
            if existing:
                existing.write({k: v for k, v in data.items() if k != 'code'})
                updated += 1
            else:
                TipoCotizante.create(data)
                created += 1

        return {'created': created, 'updated': updated}

    def _setup_subtipos_cotizante(self, company):
        """Paso 2: Crear/actualizar subtipos de cotizante"""
        service = self.env['hr.payroll.setup.service']
        SubtipoCotizante = self.env['hr.subtipo.cotizante']

        created = updated = 0
        for data in service.get_subtipos_cotizante_data():
            existing = SubtipoCotizante.search([('code', '=', data['code'])], limit=1)
            if existing:
                existing.write({k: v for k, v in data.items() if k != 'code'})
                updated += 1
            else:
                SubtipoCotizante.create(data)
                created += 1

        return {'created': created, 'updated': updated}

    def _setup_parametrizaciones(self, company):
        """Paso 3: Crear/actualizar parametrizaciones SS"""
        service = self.env['hr.payroll.setup.service']
        TipoCotizante = self.env['hr.tipo.cotizante']
        SubtipoCotizante = self.env['hr.subtipo.cotizante']
        Param = self.env['hr.parameterization.of.contributors']

        tipos = {t.code: t for t in TipoCotizante.search([])}
        subtipos = {s.code: s for s in SubtipoCotizante.search([])}

        created = updated = 0
        for data in service.get_parametrizaciones_data():
            tipo = tipos.get(data['tipo'])
            subtipo = subtipos.get(data['subtipo'])
            if not tipo or not subtipo:
                continue

            existing = Param.search([
                ('type_of_contributor', '=', tipo.id),
                ('contributor_subtype', '=', subtipo.id)
            ], limit=1)

            vals = {
                'type_of_contributor': tipo.id,
                'contributor_subtype': subtipo.id,
                'liquidated_eps_employee': data['eps_emp'],
                'liquidate_employee_pension': data['pension_emp'],
                'liquidated_aux_transport': data['aux_transp'],
                'liquidates_solidarity_fund': data['fsp'],
                'liquidates_eps_company': data['eps_cia'],
                'liquidated_company_pension': data['pension_cia'],
                'liquidated_arl': data['arl'],
                'liquidated_sena': data['sena'],
                'liquidated_icbf': data['icbf'],
                'liquidated_compensation_fund': data['ccf'],
            }

            if existing:
                existing.write(vals)
                updated += 1
            else:
                Param.create(vals)
                created += 1

        return {'created': created, 'updated': updated}

    def _setup_overtime_types(self, company):
        """Paso 4: Crear/actualizar tipos de horas extras"""
        service = self.env['hr.payroll.setup.service']
        TypeOvertime = self.env['hr.type.overtime']
        SalaryRule = self.env['hr.salary.rule']

        created = updated = 0
        for data in service.get_overtime_types_data():
            rule = SalaryRule.search([('code', '=', data['rule_code'])], limit=1)
            if not rule:
                continue  # Saltar si no existe la regla

            existing = TypeOvertime.search([('type_overtime', '=', data['type_overtime'])], limit=1)

            vals = {
                'name': data['name'],
                'salary_rule': rule.id,
                'type_overtime': data['type_overtime'],
                'percentage': data['percentage'],
                'start_time': data['start_time'],
                'end_time': data['end_time'],
                'mon': data['mon'], 'tue': data['tue'], 'wed': data['wed'],
                'thu': data['thu'], 'fri': data['fri'], 'sat': data['sat'],
                'sun': data['sun'], 'contains_holidays': data['contains_holidays'],
            }

            if existing:
                existing.write(vals)
                updated += 1
            else:
                TypeOvertime.create(vals)
                created += 1

        return {'created': created, 'updated': updated}

    def _setup_assign_employees(self, company):
        """Paso 5: Asignar tipo cotizante a empleados sin configuracion"""
        TipoCotizante = self.env['hr.tipo.cotizante']
        SubtipoCotizante = self.env['hr.subtipo.cotizante']
        Employee = self.env['hr.employee']

        tipo = TipoCotizante.search([('code', '=', '01')], limit=1)
        subtipo = SubtipoCotizante.search([('code', '=', '00')], limit=1)

        if not tipo or not subtipo:
            return {'created': 0, 'updated': 0}

        employees = Employee.search([
            ('company_id', '=', company.id),
            ('active', '=', True),
            '|', ('tipo_coti_id', '=', False), ('subtipo_coti_id', '=', False)
        ])

        for emp in employees:
            emp.write({'tipo_coti_id': tipo.id, 'subtipo_coti_id': subtipo.id})

        return {'created': 0, 'updated': len(employees)}

    def _setup_structure_sections(self, company):
        """
        Paso 6: Crear secciones de estructura salarial con dependencias correctas.

        Flujo de ejecucion:
        - DEVENGOS (seq 10) -> TOTALDEV
        - DEDUCCIONES (seq 20) -> TOTALDED
        - IBD_SS (seq 15) -> TOTALDEV, TOTALDED (es general, afecta ambos totales)
        - TOTALDEV (seq 40) -> NET
        - TOTALDED (seq 50) -> NET
        - NET (seq 60) -> PROVISIONES
        - PROVISIONES (seq 70) -> fin
        """
        Structure = self.env['hr.payroll.structure']
        Section = self.env['hr.payroll.structure.section']

        # Buscar todas las estructuras (en Odoo 18 hr.payroll.structure no tiene company_id)
        structures = Structure.search([])

        created = updated = 0

        # Definicion de secciones con orden y dependencias
        SECTIONS_CONFIG = [
            {
                'type': 'devengos',
                'name': 'Ingresos',
                'sequence': 10,
                'color': 10,  # Verde
                'connects_to': ['totaldev'],
                'description': 'Salario base, auxilios, comisiones, horas extras, bonificaciones',
            },
            {
                'type': 'ibd_ss',
                'name': 'IBC Seguridad Social',
                'sequence': 15,
                'color': 11,  # Cyan
                'connects_to': ['totaldev', 'totalded'],
                'description': 'Ingreso Base de Cotizacion para aportes de seguridad social',
            },
            {
                'type': 'deducciones',
                'name': 'Descuentos',
                'sequence': 20,
                'color': 1,  # Rojo
                'connects_to': ['totalded'],
                'description': 'Aportes empleado (EPS, Pension), retenciones, prestamos, embargos',
            },
            {
                'type': 'totaldev',
                'name': 'Total Devengos',
                'sequence': 40,
                'color': 4,  # Azul claro
                'connects_to': ['net'],
                'depends_on': ['devengos', 'ibd_ss'],
                'description': 'Suma de todos los ingresos del empleado',
            },
            {
                'type': 'totalded',
                'name': 'Total Deducciones',
                'sequence': 50,
                'color': 9,  # Fucsia
                'connects_to': ['net'],
                'depends_on': ['deducciones', 'ibd_ss'],
                'description': 'Suma de todos los descuentos aplicados',
            },
            {
                'type': 'net',
                'name': 'Neto a Pagar',
                'sequence': 60,
                'color': 5,  # Morado
                'connects_to': ['provisiones'],
                'depends_on': ['totaldev', 'totalded'],
                'description': 'Total Devengos - Total Deducciones = Valor a consignar',
            },
            {
                'type': 'provisiones',
                'name': 'Provisiones',
                'sequence': 70,
                'color': 3,  # Amarillo
                'connects_to': [],
                'depends_on': ['net'],
                'description': 'Cesantias, Intereses Cesantias, Prima, Vacaciones',
            },
        ]

        for structure in structures:
            # Activar uso de secciones si no esta activo
            if not structure.use_sections:
                structure.use_sections = True

            existing_types = {s.section_type: s for s in structure.section_ids}
            sections_created = {}

            # Primera pasada: crear secciones
            for config in SECTIONS_CONFIG:
                section_type = config['type']

                if section_type in existing_types:
                    # Actualizar existente
                    section = existing_types[section_type]
                    section.write({
                        'name': config['name'],
                        'sequence': config['sequence'],
                        'color': config['color'],
                        'notes': config.get('description', ''),
                        'active': True,
                    })
                    sections_created[section_type] = section
                    updated += 1
                else:
                    # Crear nueva
                    section = Section.create({
                        'structure_id': structure.id,
                        'section_type': section_type,
                        'name': config['name'],
                        'sequence': config['sequence'],
                        'color': config['color'],
                        'notes': config.get('description', ''),
                        'active': True,
                    })
                    sections_created[section_type] = section
                    created += 1

            # Segunda pasada: establecer conexiones y dependencias
            for config in SECTIONS_CONFIG:
                section_type = config['type']
                section = sections_created.get(section_type)
                if not section:
                    continue

                # Establecer conexiones (flujo visual)
                connects_to = config.get('connects_to', [])
                if connects_to:
                    target_ids = [
                        sections_created[t].id
                        for t in connects_to
                        if t in sections_created
                    ]
                    if target_ids:
                        section.write({'connected_to_ids': [(6, 0, target_ids)]})

                # Establecer dependencias (orden de ejecucion)
                depends_on = config.get('depends_on', [])
                if depends_on:
                    dep_ids = [
                        sections_created[d].id
                        for d in depends_on
                        if d in sections_created
                    ]
                    if dep_ids:
                        section.write({'depends_on_sections': [(6, 0, dep_ids)]})

        return {'created': created, 'updated': updated}

    def action_setup_structure_sections(self):
        """Boton para configurar secciones de estructura salarial"""
        self.ensure_one()
        company = self.env.company

        result = self._setup_structure_sections(company)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Secciones de Estructura'),
                'message': _('Creadas: %s, Actualizadas: %s') % (result['created'], result['updated']),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_create_default_parameterization(self):
        """Crea todas las parametrizaciones de seguridad social"""
        service = self.env['hr.payroll.setup.service']
        result = service.create_default_parameterization()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Parametrizacion Completa'),
                'message': _('Tipos: %s, Subtipos: %s. Parametrizaciones creadas: %s, actualizadas: %s') % (
                    result['tipos'], result['subtipos'], result['created'], result['updated']),
                'type': 'success',
                'sticky': True,
            }
        }

    def action_assign_default_tipo_cotizante(self):
        """Asigna tipo cotizante por defecto a empleados"""
        service = self.env['hr.payroll.setup.service']
        result = service.assign_default_tipo_cotizante()
        if result['success']:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Empleados actualizados'),
                    'message': _('Se asigno tipo Dependiente / Sin Subtipo a %s empleados') % result['count'],
                    'type': 'success',
                    'sticky': False,
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': result['message'],
                    'type': 'danger',
                    'sticky': False,
                }
            }

    def action_create_default_overtime_types(self):
        """Crea los tipos de horas extras por defecto"""
        service = self.env['hr.payroll.setup.service']
        result = service.create_default_overtime_types()

        message = f'Tipos: {result["created"]} creados, {result["updated"]} actualizados'
        rules_created = result.get('rules_created', [])
        if rules_created:
            message += f'. Reglas HEYREC creadas: {", ".join(rules_created)}'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Tipos de Horas Extras'),
                'message': message,
                'type': 'success',
                'sticky': bool(rules_created),
            }
        }

    # =========================================================================
    # GET/SET VALUES
    # =========================================================================

    def set_values(self):
        super(ResConfigSettings, self).set_values()
        set_param = self.env['ir.config_parameter'].sudo().set_param
        set_param('lavish_hr_payroll.addref_work_address_account_moves', self.addref_work_address_account_moves)
        set_param('lavish_hr_payroll.round_payroll', self.round_payroll)
        set_param('lavish_hr_payroll.pay_vacations_in_payroll', self.pay_vacations_in_payroll)
        set_param('lavish_hr_payroll.pay_cesantias_in_payroll', self.pay_cesantias_in_payroll)
        set_param('lavish_hr_payroll.pay_primas_in_payroll', self.pay_primas_in_payroll)
        set_param('lavish_hr_payroll.vacation_days_calculate_absences', self.vacation_days_calculate_absences)
        set_param('lavish_hr_payroll.cesantias_salary_take', self.cesantias_salary_take)
        set_param('lavish_hr_payroll.prima_salary_take', self.prima_salary_take)
        # Condiciones legales promedios
        set_param('lavish_hr_payroll.prima_periodo_meses', self.prima_periodo_meses)
        set_param('lavish_hr_payroll.prima_incluye_auxilio', self.prima_incluye_auxilio)
        set_param('lavish_hr_payroll.prima_incluye_extras', self.prima_incluye_extras)
        set_param('lavish_hr_payroll.prima_meses_extras', self.prima_meses_extras)
        set_param('lavish_hr_payroll.cesantias_periodo_meses', self.cesantias_periodo_meses)
        set_param('lavish_hr_payroll.cesantias_incluye_auxilio', self.cesantias_incluye_auxilio)
        set_param('lavish_hr_payroll.cesantias_incluye_extras', self.cesantias_incluye_extras)
        set_param('lavish_hr_payroll.cesantias_meses_extras', self.cesantias_meses_extras)
        set_param('lavish_hr_payroll.intereses_tasa_anual', self.intereses_tasa_anual)
        set_param('lavish_hr_payroll.vacaciones_periodo_meses', self.vacaciones_periodo_meses)
        set_param('lavish_hr_payroll.vacaciones_dias_por_ano', self.vacaciones_dias_por_ano)
        set_param('lavish_hr_payroll.vacaciones_incluye_auxilio', self.vacaciones_incluye_auxilio)
        set_param('lavish_hr_payroll.vacaciones_incluye_extras', self.vacaciones_incluye_extras)
        set_param('lavish_hr_payroll.promedio_detectar_cambios', self.promedio_detectar_cambios)
        set_param('lavish_hr_payroll.promedio_meses_cambio', self.promedio_meses_cambio)

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        get_param = self.env['ir.config_parameter'].sudo().get_param
        res['addref_work_address_account_moves'] = get_param('lavish_hr_payroll.addref_work_address_account_moves')
        res['round_payroll'] = get_param('lavish_hr_payroll.round_payroll')
        res['pay_vacations_in_payroll'] = get_param('lavish_hr_payroll.pay_vacations_in_payroll')
        res['pay_cesantias_in_payroll'] = get_param('lavish_hr_payroll.pay_cesantias_in_payroll')
        res['pay_primas_in_payroll'] = get_param('lavish_hr_payroll.pay_primas_in_payroll')
        res['vacation_days_calculate_absences'] = get_param('lavish_hr_payroll.vacation_days_calculate_absences')
        res['cesantias_salary_take'] = get_param('lavish_hr_payroll.cesantias_salary_take')
        res['prima_salary_take'] = get_param('lavish_hr_payroll.prima_salary_take')
        # Condiciones legales promedios
        res['prima_periodo_meses'] = int(get_param('lavish_hr_payroll.prima_periodo_meses', 6))
        res['prima_incluye_auxilio'] = get_param('lavish_hr_payroll.prima_incluye_auxilio', True)
        res['prima_incluye_extras'] = get_param('lavish_hr_payroll.prima_incluye_extras', True)
        res['prima_meses_extras'] = int(get_param('lavish_hr_payroll.prima_meses_extras', 3))
        res['cesantias_periodo_meses'] = int(get_param('lavish_hr_payroll.cesantias_periodo_meses', 12))
        res['cesantias_incluye_auxilio'] = get_param('lavish_hr_payroll.cesantias_incluye_auxilio', True)
        res['cesantias_incluye_extras'] = get_param('lavish_hr_payroll.cesantias_incluye_extras', True)
        res['cesantias_meses_extras'] = int(get_param('lavish_hr_payroll.cesantias_meses_extras', 3))
        res['intereses_tasa_anual'] = float(get_param('lavish_hr_payroll.intereses_tasa_anual', 12.0))
        res['vacaciones_periodo_meses'] = int(get_param('lavish_hr_payroll.vacaciones_periodo_meses', 12))
        res['vacaciones_dias_por_ano'] = int(get_param('lavish_hr_payroll.vacaciones_dias_por_ano', 15))
        res['vacaciones_incluye_auxilio'] = get_param('lavish_hr_payroll.vacaciones_incluye_auxilio', False)
        res['vacaciones_incluye_extras'] = get_param('lavish_hr_payroll.vacaciones_incluye_extras', False)
        res['promedio_detectar_cambios'] = get_param('lavish_hr_payroll.promedio_detectar_cambios', True)
        res['promedio_meses_cambio'] = int(get_param('lavish_hr_payroll.promedio_meses_cambio', 3))
        return res

    def action_setup_salary_categories(self):
        """Botón para configurar categorías de reglas salariales desde la compañía"""
        self.ensure_one()

        self._handle_duplicate_categories()

        self._setup_salary_categories()

        self._setup_leave_types()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Éxito'),
                'message': _('Categorías de reglas salariales y tipos de ausencia configurados correctamente.'),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_setup_leave_types(self):
        """Botón para configurar tipos de ausencia y tipos de entrada de trabajo desde la compañía"""
        self.ensure_one()

        self._setup_leave_types()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Éxito'),
                'message': _('Tipos de ausencia y tipos de entrada de trabajo configurados correctamente.'),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_create_structures(self):
        """Boton para crear solo las estructuras salariales"""
        self.ensure_one()

        self._generate_all_structures()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Estructuras Creadas'),
                'message': _('Estructuras salariales (Nomina, Vacaciones, Prima, Cesantias, Contrato, Intereses) configuradas correctamente.'),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_create_salary_rules(self):
        """Boton para crear solo las reglas salariales"""
        self.ensure_one()

        self._generate_all_rules()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Reglas Creadas'),
                'message': _('Reglas salariales configuradas correctamente.'),
                'type': 'success',
                'sticky': False,
            }
        }

    def _handle_duplicate_categories(self):
        """
        Maneja categorías con códigos duplicados:
        1. Identifica códigos duplicados
        2. Para cada código, conserva una categoría y archiva las demás
        3. Mueve todas las reglas de las categorías archivadas a la categoría principal
        """
        all_categories = self.env['hr.salary.rule.category'].search([])
        codes = all_categories.mapped('code')
        
        duplicate_codes = []
        for code in set(codes):
            categories = self.env['hr.salary.rule.category'].search([('code', '=', code)])
            if len(categories) > 1:
                duplicate_codes.append(code)
        
        for code in duplicate_codes:
            categories = self.env['hr.salary.rule.category'].search([('code', '=', code)])
            
            active_categories = categories.filtered(lambda c: c.active)
            if active_categories:
                active_category = active_categories[0]
            else:
                active_category = categories[0]
                active_category.write({'active': True})
            
            for category in categories:
                if category.id != active_category.id:
                    rules = self.env['hr.salary.rule'].search([('category_id', '=', category.id)])
                    
                    if rules:
                        rules.write({'category_id': active_category.id})
                    
                    category.write({'active': False})
    
    def _setup_salary_categories(self):
        """
        Configura las categorías de reglas salariales con orden lógico:
        - Devengos: secuencias 1-200
        - Deducciones: secuencias 201-300
        - Prestaciones: secuencias 301-400
        - Provisiones: secuencias 401-500
        - Totales: secuencias 501-600
        - Otros: secuencias 601+
        """
 
        main_categories = [
            # DEVENGOS - PRINCIPALES (1-10)
            {'code': 'DEV_SALARIAL', 'name': 'DEVENGO SALARIAL', 'sequence': 1, 'active': True, 
             'description': 'El devengado corresponde a todos los conceptos por los que un empleado recibe una remuneración.', 
             'category_type': 'earnings', 'parent_id': False},
             
            {'code': 'DEV_NO_SALARIAL', 'name': 'DEVENGO NO SALARIAL', 'sequence': 100, 'active': True, 
             'description': 'No constituyen salario las sumas que ocasionalmente recibe el trabajador.', 
             'category_type': 'earnings_non_salary', 'parent_id': False},
             
            # DEDUCCIONES (201-300)
            {'code': 'DEDUCCIONES', 'name': 'DEDUCCIONES', 'sequence': 201, 'active': True, 
             'description': '<p>Las deducciones de nómina son aquellos descuentos al salario.</p>', 
             'category_type': 'deductions', 'parent_id': False},
             
            # PRESTACIONES (301-400)
            {'code': 'PRESTACIONES_SOCIALES', 'name': 'PRESTACIONES SOCIALES', 'sequence': 301, 'active': True, 
             'description': 'Prestación social es lo que debe el patrono al trabajador.', 
             'category_type': 'benefits', 'parent_id': False},
             
            # PROVISIONES (401-500)
            {'code': 'PROV', 'name': 'PROVISIONES DE NOMINA', 'sequence': 401, 'active': True, 
             'description': False, 'category_type': 'provisions', 'parent_id': False},
             
            # TOTALES (501-600)
            {'code': 'TOTALDEV', 'name': 'TOTAL DEVENGO', 'sequence': 501, 'active': True, 
             'description': False, 'category_type': 'totals', 'parent_id': False},
             
            {'code': 'TOTALDED', 'name': 'TOTAL DEDUCCIONES', 'sequence': 510, 'active': True, 
             'description': False, 'category_type': 'totals', 'parent_id': False},
             
            {'code': 'GROSS', 'name': 'BRUTO', 'sequence': 520, 'active': True, 
             'description': '<p><br></p>', 'category_type': 'totals', 'parent_id': False},
             
            {'code': 'NET', 'name': 'NETO', 'sequence': 530, 'active': True, 
             'description': False, 'category_type': 'totals', 'parent_id': False},
             
            # OTROS (601+)
            {'code': 'ALW', 'name': 'SUBSIDIO', 'sequence': 601, 'active': True, 
             'description': False, 'category_type': 'other', 'parent_id': False},
             
            {'code': 'COMP', 'name': 'CONTRIBUCIÓN DE LA EMPRESA', 'sequence': 610, 'active': True, 
             'description': False, 'category_type': 'other', 'parent_id': False},

            {'code': 'AUX', 'name': 'AUXILIO DE TRANSPORTE', 'sequence': 620, 'active': True, 
             'description': 'El auxilio de transporte es un pago que se realiza a los trabajadores que tienen un sueldo de hasta dos salarios mínimos mensuales.', 
             'category_type': 'earnings_non_salary', 'parent_id': False},
            
            {'code': 'AUS', 'name': 'AUSENCIA', 'sequence': 630, 'active': True, 
             'description': False, 'category_type': 'other', 'parent_id': False},
             
            {'code': 'COMISIONES', 'name': 'COMISIONES', 'sequence': 640, 'active': True, 
             'description': False, 'category_type': 'other', 'parent_id': False},
             
            {'code': 'BASE_SEC', 'name': 'BASE SEGURIDAD SOCIAL', 'sequence': 650, 'active': True, 
             'description': False, 'category_type': 'other', 'parent_id': False},
             
            {'code': 'BASE_OTROS', 'name': 'SUBTOTAL OTROS DEVENGOS', 'sequence': 660, 'active': True, 
             'description': False, 'category_type': 'other', 'parent_id': False},
             
            {'code': 'DIAS', 'name': 'DIAS VACA', 'sequence': 670, 'active': True, 
             'description': False, 'category_type': 'other', 'parent_id': False}
        ]
        
        created_categories = {}
        
        for cat_data in main_categories:
            category_type = cat_data.pop('category_type', 'other')
            parent_id = cat_data.pop('parent_id', False)
            normalized_name = self._normalize_name_case(cat_data['name'])
            
            existing_category = self.env['hr.salary.rule.category'].search([
                ('code', '=', cat_data['code']),
                ('active', '=', True)
            ], limit=1)
            
            if existing_category:
                update_vals = {
                    'name': normalized_name,
                    'sequence': cat_data['sequence'],
                    'active': cat_data['active'],
                    'category_type': category_type,
                    'group_payroll_voucher': True if cat_data['code'] not in ['NET', 'TOTALDEV', 'TOTALDED', 'GROSS'] else False,
                    
                }
                if parent_id:
                    update_vals['parent_id'] = existing_category or self.env['hr.salary.rule.category'].search([('code', '=',parent_id),], limit=1).id
                
                existing_category.write(update_vals)
                created_categories[cat_data['code']] = existing_category
            else:
                create_vals = {
                    'name': normalized_name,
                    'code': cat_data['code'],
                    'sequence': cat_data['sequence'],
                    'active': cat_data['active'],
                    'category_type': category_type,
                    'group_payroll_voucher': True if cat_data['code'] not in ['NET', 'TOTALDEV', 'TOTALDED', 'GROSS'] else False,
                    'note': cat_data['description'],
                }
                if parent_id:
                    create_vals['parent_id'] = self.env['hr.salary.rule.category'].search([('code', '=',parent_id),], limit=1).id
                
                new_category = self.env['hr.salary.rule.category'].create(create_vals)
                created_categories[cat_data['code']] = new_category
        
        subcategories = [
            {'code': 'BASIC', 'name': 'BÁSICO', 'sequence': 11, 'active': True, 
             'description': 'El sueldo base es la remuneración fija.', 
             'category_type': 'basic', 'parent_code': 'DEV_SALARIAL'},
             
            {'code': 'VACACIONES', 'name': 'VACACIONES', 'sequence': 21, 'active': True, 
             'description': '<p>El derecho a las vacaciones se adquiere al cumplirse el año de servicio.', 
             'category_type': 'earnings', 'parent_code': 'DEV_SALARIAL'},
            
            {'code': 'AUS', 'name': 'AUSENCIA', 'sequence': 630, 'active': True, 
             'description': False, 'category_type': 'earnings', 'parent_code': 'DEV_SALARIAL'},
             
            {'code': 'COMISIONES', 'name': 'COMISIONES', 'sequence': 640, 'active': True, 
             'description': False, 'category_type': 'earnings', 'parent_code': 'PRESTACIONES_SOCIALES'},
            
            {'code': 'INDEM', 'name': 'INDEMNIZACIONES', 'sequence': 150, 'active': True, 
             'description': False, 'category_type': 'o_rights', 'parent_code': 'DEV_SALARIAL'},
                       
            {'code': 'HEYREC', 'name': 'HORAS EXTRAS Y RECARGOS', 'sequence': 31, 'active': True, 
             'description': 'Pagos por trabajo extraordinario.', 
             'category_type': 'earnings', 'parent_code': 'DEV_SALARIAL'},
             
            {'code': 'INCAPACIDAD', 'name': 'INCAPACIDAD', 'sequence': 41, 'active': True, 
             'description': False, 'category_type': 'earnings', 'parent_code': 'DEV_SALARIAL'},
             
            {'code': 'LICENCIA_REMUNERADA', 'name': 'LICENCIA REMUNERADA', 'sequence': 51, 'active': True, 
             'description': False, 'category_type': 'earnings', 'parent_code': 'DEV_SALARIAL'},
             
            {'code': 'LICENCIA_MATERNIDAD', 'name': 'LICENCIA MATERNIDAD', 'sequence': 61, 'active': True, 
             'description': False, 'category_type': 'earnings', 'parent_code': 'DEV_SALARIAL'},
             
            {'code': 'ACCIDENTE_TRABAJO', 'name': 'ACCIDENTE TRABAJO', 'sequence': 71, 'active': True, 
             'description': False, 'category_type': 'earnings', 'parent_code': 'DEV_SALARIAL'},
             
            # AUX: Categoria sin parent para evitar doble conteo en TOTALDEV
            # Segun Ley 15/1959: "El valor del subsidio no se computara como factor de salario"
            {'code': 'AUX', 'name': 'AUXILIO DE TRANSPORTE', 'sequence': 120, 'active': True,
             'description': 'Auxilio de transporte. No hereda de DEV_NO_SALARIAL para evitar doble conteo.',
             'category_type': 'earnings_non_salary', 'parent_code': False},
             
            # AUSENCIA_NO_PAGO: Categoria sin parent para ausencias no remuneradas
            # NO suma a TOTALDEV porque no tiene parent_code
            {'code': 'AUSENCIA_NO_PAGO', 'name': 'AUSENCIA SIN PAGO', 'sequence': 140, 'active': True,
             'description': 'Ausencias no remuneradas (licencia no remunerada, suspensiones). No suma a TOTALDEV.',
             'category_type': 'non_taxed_earnings', 'parent_code': False},

            {'code': 'EM', 'name': 'EMBARGOS', 'sequence': 210, 'active': True, 
             'description': False, 'category_type': 'deductions', 'parent_code': 'DEDUCCIONES'},
             
            {'code': 'SSOCIAL', 'name': 'SEGURIDAD SOCIAL SS', 'sequence': 220, 'active': True, 
             'description': False, 'category_type': 'deductions', 'parent_code': 'DEDUCCIONES'},
             
            {'code': 'DESCUENTO_AFC', 'name': 'DESCUENTO AFC', 'sequence': 230, 'active': True, 
             'description': False, 'category_type': 'deductions', 'parent_code': 'DEDUCCIONES'},

            {'code': 'PRIMA', 'name': 'PRIMA LEGAL', 'sequence': 310, 'active': True, 
             'description': False, 'category_type': 'benefits', 'parent_code': 'PRESTACIONES_SOCIALES'},
        ]
        
        for cat_data in subcategories:
            parent_code = cat_data.pop('parent_code', False)
            category_type = cat_data.pop('category_type', 'other')
            normalized_name = self._normalize_name_case(cat_data['name'])
            
            parent_id = False
            if parent_code and parent_code in created_categories:
                parent_id = created_categories[parent_code].id
            
            active_category = self.env['hr.salary.rule.category'].search([
                ('code', '=', cat_data['code']),
                ('active', '=', True)
            ], limit=1)
            
            if active_category:
                active_category.write({
                    'name': normalized_name,
                    'sequence': cat_data['sequence'],
                    'category_type': category_type,
                    'parent_id': parent_id,
                    'group_payroll_voucher': True,
                    'note': cat_data['description'],
                })
            else:
                new_category = self.env['hr.salary.rule.category'].create({
                    'name': normalized_name,
                    'code': cat_data['code'],
                    'sequence': cat_data['sequence'],
                    'active': cat_data['active'],
                    'category_type': category_type,
                    'parent_id': parent_id,
                    'group_payroll_voucher': True,
                    'note': cat_data['description'],
                })
        
        return True

    def _setup_leave_types(self):
        """
        Configura los tipos de ausencia (hr.leave.type) y tipos de entrada de trabajo (hr.work.entry.type)
        usando diccionarios con control de actualización
        """

        # Definición de tipos de entrada de trabajo
        work_entry_types = [
            {
                'code': 'INCAPACIDAD001',
                'name': 'INCAPACIDAD EPS',
                'short_name': 'INCAP. EPS',
                'color': 5,
                'is_leave': True,
                'sequence': 5,
                'not_contribution_base': False,
                'deduct_deductions': 'law',
                'force_update': False,
            },
            # NOTA: INCAPACIDAD002 es solo regla salarial, no work entry type
            {
                'code': 'INCAPACIDAD007',
                'name': 'INCAPACIDAD EPS 50%',
                'short_name': 'INCAP. EPS 50%',
                'color': 5,
                'is_leave': True,
                'sequence': 7,
                'not_contribution_base': False,
                'deduct_deductions': 'law',
                'force_update': False,
            },
            {
                'code': 'EGH',
                'name': 'AUSENCIA POR ENFERMEDAD 66%',
                'short_name': 'ENF. 66%',
                'color': 5,
                'is_leave': True,
                'sequence': 8,
                'not_contribution_base': False,
                'deduct_deductions': 'law',
                'force_update': False,
            },
            {
                'code': 'AT',
                'name': 'ACCIDENTE DE TRABAJO',
                'short_name': 'ACC. TRABAJO',
                'color': 9,
                'is_leave': True,
                'sequence': 9,
                'not_contribution_base': False,
                'deduct_deductions': 'law',
                'force_update': False,
            },
            {
                'code': 'EP',
                'name': 'ENFERMEDAD PROFESIONAL',
                'short_name': 'ENF. PROF.',
                'color': 9,
                'is_leave': True,
                'sequence': 10,
                'not_contribution_base': False,
                'deduct_deductions': 'law',
                'force_update': False,
            },
            {
                'code': 'MAT',
                'name': 'LICENCIA DE MATERNIDAD',
                'short_name': 'MATERNIDAD',
                'color': 4,
                'is_leave': True,
                'sequence': 11,
                'not_contribution_base': False,
                'deduct_deductions': 'law',
                'force_update': False,
            },
            {
                'code': 'PAT',
                'name': 'LICENCIA DE PATERNIDAD',
                'short_name': 'PATERNIDAD',
                'color': 4,
                'is_leave': True,
                'sequence': 12,
                'not_contribution_base': False,
                'deduct_deductions': 'law',
                'force_update': False,
            },
            {
                'code': 'LICENCIA001',
                'name': 'LICENCIA REMUNERADA',
                'short_name': 'LIC. REM.',
                'color': 3,
                'is_leave': True,
                'sequence': 13,
                'not_contribution_base': False,
                'deduct_deductions': 'law',
                'force_update': False,
            },
            {
                'code': 'LUTO',
                'name': 'LUTO',
                'short_name': 'LUTO',
                'color': 8,
                'is_leave': True,
                'sequence': 14,
                'not_contribution_base': False,
                'deduct_deductions': 'law',
                'force_update': False,
            },
            {
                'code': 'LICENCIA_NO_REMUNERADA',
                'name': 'LICENCIA NO REMUNERADA',
                'short_name': 'LIC. NO REM.',
                'color': 6,
                'is_leave': True,
                'sequence': 16,
                'not_contribution_base': True,
                'deduct_deductions': 'all',
                'force_update': False,
            },
            {
                'code': 'INAS_INJU',
                'name': 'INASISTENCIA INJUSTIFICADA',
                'short_name': 'INAS. INJU.',
                'color': 1,
                'is_leave': True,
                'sequence': 17,
                'not_contribution_base': True,
                'deduct_deductions': 'all',
                'force_update': False,
            },
            {
                'code': 'INAS_INJU_D',
                'name': 'AUSENCIA INJUSTIFICADA DOMINICAL',
                'short_name': 'INAS. INJU. DOM.',
                'color': 1,
                'is_leave': True,
                'sequence': 18,
                'not_contribution_base': True,
                'deduct_deductions': 'all',
                'force_update': True,  # Esta es nueva, sí debe actualizarse
            },
            {
                'code': 'SUSP_CONTRATO',
                'name': 'SUSPENSIÓN DEL CONTRATO',
                'short_name': 'SUSP. CONTRATO',
                'color': 6,
                'is_leave': True,
                'sequence': 19,
                'not_contribution_base': True,
                'deduct_deductions': 'all',
                'force_update': False,
            },
            {
                'code': 'SANCION',
                'name': 'SANCION',
                'short_name': 'SANCIÓN',
                'color': 1,
                'is_leave': True,
                'sequence': 20,
                'not_contribution_base': True,
                'deduct_deductions': 'all',
                'force_update': False,
            },
            {
                'code': 'VACDISFRUTADAS',
                'name': 'VACACIONES DISFRUTADAS',
                'short_name': 'VAC. DISFR.',
                'color': 2,
                'is_leave': True,
                'sequence': 26,
                'not_contribution_base': False,
                'deduct_deductions': 'law',
                'force_update': False,
            },
            {
                'code': 'VACATIONS_MONEY',
                'name': 'VACACIONES EN DINERO',
                'short_name': 'VAC. DINERO',
                'color': 2,
                'is_leave': True,
                'sequence': 51,
                'not_contribution_base': False,
                'deduct_deductions': 'law',
                'force_update': False,
            },
        ]

        # Crear o actualizar tipos de entrada de trabajo
        for entry_data in work_entry_types:
            force_update = entry_data.pop('force_update', False)
            code = entry_data['code']

            # Buscar si ya existe
            existing_entry = self.env['hr.work.entry.type'].search([
                ('code', '=', code)
            ], limit=1)

            if existing_entry:
                if force_update:
                    # Actualizar solo si force_update está en True
                    existing_entry.write(entry_data)
            else:
                # Crear nuevo
                new_entry = self.env['hr.work.entry.type'].create(entry_data)

        # Definición de tipos de ausencia
        leave_types = [
            {
                'code': 'INCAPACIDAD001',
                'name': 'INCAPACIDAD EPS',
                'request_unit': 'day',
                'leave_validation_type': 'manager',
                'requires_allocation': 'no',
                'employee_requests': 'yes',
                'color': 5,
                'work_entry_type_code': 'INCAPACIDAD001',
                'unpaid_absences': False,
                'discounting_bonus_days': False,
                'sub_wd': True,
                'pay_transport_allowance': True,
                'apply_day_31': False,
                'discount_rest_day': False,
                'published_portal': True,
                'novelty': 'ige',
                'liquidacion_value': 'IBC',
                'force_update': False,
            },
            {
                'code': 'INCAPACIDAD007',
                'name': 'INCAPACIDAD EPS 50%',
                'request_unit': 'day',
                'leave_validation_type': 'manager',
                'requires_allocation': 'no',
                'employee_requests': 'yes',
                'color': 5,
                'work_entry_type_code': 'INCAPACIDAD007',
                'unpaid_absences': False,
                'discounting_bonus_days': False,
                'sub_wd': True,
                'pay_transport_allowance': True,
                'apply_day_31': False,
                'discount_rest_day': False,
                'published_portal': True,
                'novelty': 'ige',
                'liquidacion_value': 'IBC',
                'force_update': False,
            },
            {
                'code': 'EGH',
                'name': 'AUSENCIA POR ENFERMEDAD 66%',
                'request_unit': 'day',
                'leave_validation_type': 'manager',
                'requires_allocation': 'no',
                'employee_requests': 'yes',
                'color': 5,
                'work_entry_type_code': 'EGH',
                'unpaid_absences': False,
                'discounting_bonus_days': False,
                'sub_wd': True,
                'pay_transport_allowance': True,
                'apply_day_31': False,
                'discount_rest_day': False,
                'published_portal': True,
                'novelty': 'ige',
                'liquidacion_value': 'IBC',
                'force_update': False,
            },
            {
                'code': 'AT',
                'name': 'ACCIDENTE DE TRABAJO',
                'request_unit': 'day',
                'leave_validation_type': 'manager',
                'requires_allocation': 'no',
                'employee_requests': 'yes',
                'color': 9,
                'work_entry_type_code': 'AT',
                'unpaid_absences': False,
                'discounting_bonus_days': False,
                'sub_wd': True,
                'pay_transport_allowance': True,
                'apply_day_31': False,
                'discount_rest_day': False,
                'published_portal': True,
                'novelty': 'irl',
                'liquidacion_value': 'IBC',
                'force_update': False,
            },
            {
                'code': 'EP',
                'name': 'ENFERMEDAD PROFESIONAL',
                'request_unit': 'day',
                'leave_validation_type': 'manager',
                'requires_allocation': 'no',
                'employee_requests': 'yes',
                'color': 9,
                'work_entry_type_code': 'EP',
                'unpaid_absences': False,
                'discounting_bonus_days': False,
                'sub_wd': True,
                'pay_transport_allowance': True,
                'apply_day_31': False,
                'discount_rest_day': False,
                'published_portal': True,
                'novelty': 'irl',
                'liquidacion_value': 'IBC',
                'force_update': False,
            },
            {
                'code': 'MAT',
                'name': 'LICENCIA DE MATERNIDAD',
                'request_unit': 'day',
                'leave_validation_type': 'manager',
                'requires_allocation': 'no',
                'employee_requests': 'yes',
                'color': 4,
                'work_entry_type_code': 'MAT',
                'unpaid_absences': False,
                'discounting_bonus_days': False,
                'sub_wd': True,
                'pay_transport_allowance': True,
                'apply_day_31': False,
                'discount_rest_day': False,
                'published_portal': True,
                'novelty': 'lma',
                'liquidacion_value': 'IBC',
                'force_update': False,
            },
            {
                'code': 'PAT',
                'name': 'LICENCIA DE PATERNIDAD',
                'request_unit': 'day',
                'leave_validation_type': 'manager',
                'requires_allocation': 'no',
                'employee_requests': 'yes',
                'color': 4,
                'work_entry_type_code': 'PAT',
                'unpaid_absences': False,
                'discounting_bonus_days': False,
                'sub_wd': True,
                'pay_transport_allowance': True,
                'apply_day_31': False,
                'discount_rest_day': False,
                'published_portal': True,
                'novelty': 'lpa',
                'liquidacion_value': 'IBC',
                'force_update': False,
            },
            {
                'code': 'LICENCIA001',
                'name': 'LICENCIA REMUNERADA',
                'request_unit': 'day',
                'leave_validation_type': 'manager',
                'requires_allocation': 'no',
                'employee_requests': 'yes',
                'color': 3,
                'work_entry_type_code': 'LICENCIA001',
                'unpaid_absences': False,
                'discounting_bonus_days': False,
                'sub_wd': True,
                'pay_transport_allowance': True,
                'apply_day_31': False,
                'discount_rest_day': False,
                'published_portal': True,
                'novelty': 'lr',
                'liquidacion_value': 'WAGE',
                'force_update': False,
            },
            {
                'code': 'LUTO',
                'name': 'LUTO',
                'request_unit': 'day',
                'leave_validation_type': 'manager',
                'requires_allocation': 'no',
                'employee_requests': 'yes',
                'color': 8,
                'work_entry_type_code': 'LUTO',
                'unpaid_absences': False,
                'discounting_bonus_days': False,
                'sub_wd': True,
                'pay_transport_allowance': True,
                'apply_day_31': False,
                'discount_rest_day': False,
                'published_portal': True,
                'novelty': 'lt',
                'liquidacion_value': 'WAGE',
                'force_update': False,
            },
            {
                'code': 'LICENCIA_NO_REMUNERADA',
                'name': 'LICENCIA NO REMUNERADA',
                'request_unit': 'day',
                'leave_validation_type': 'no_validation',
                'requires_allocation': 'no',
                'employee_requests': 'yes',
                'color': 6,
                'work_entry_type_code': 'LICENCIA_NO_REMUNERADA',
                'unpaid_absences': True,
                'discounting_bonus_days': True,
                'sub_wd': True,
                'pay_transport_allowance': False,
                'apply_day_31': False,
                'discount_rest_day': False,
                'published_portal': True,
                'novelty': 'lnr',
                'liquidacion_value': 'WAGE',
                'force_update': False,
            },
            {
                'code': 'INAS_INJU',
                'name': 'INASISTENCIA INJUSTIFICADA',
                'request_unit': 'day',
                'leave_validation_type': 'no_validation',
                'requires_allocation': 'no',
                'employee_requests': 'yes',
                'color': 1,
                'work_entry_type_code': 'INAS_INJU',
                'unpaid_absences': True,
                'discounting_bonus_days': True,
                'sub_wd': True,
                'pay_transport_allowance': False,
                'apply_day_31': False,
                'discount_rest_day': False,
                'published_portal': False,
                'novelty': 'lnr',
                'liquidacion_value': 'WAGE',
                'force_update': False,
            },
            {
                'code': 'INAS_INJU_D',
                'name': 'AUSENCIA INJUSTIFICADA DOMINICAL',
                'request_unit': 'day',
                'leave_validation_type': 'no_validation',
                'requires_allocation': 'no',
                'employee_requests': 'yes',
                'color': 1,
                'work_entry_type_code': 'INAS_INJU_D',
                'unpaid_absences': True,
                'discounting_bonus_days': True,
                'sub_wd': True,
                'pay_transport_allowance': False,
                'apply_day_31': False,
                'discount_rest_day': True,
                'published_portal': False,
                'novelty': 'lnr',
                'liquidacion_value': 'WAGE',
                'force_update': True,  # Esta es nueva, sí debe actualizarse
            },
            {
                'code': 'SUSP_CONTRATO',
                'name': 'SUSPENSIÓN DEL CONTRATO',
                'request_unit': 'day',
                'leave_validation_type': 'no_validation',
                'requires_allocation': 'no',
                'employee_requests': 'yes',
                'color': 6,
                'work_entry_type_code': 'SUSP_CONTRATO',
                'unpaid_absences': True,
                'discounting_bonus_days': True,
                'sub_wd': True,
                'pay_transport_allowance': False,
                'apply_day_31': False,
                'discount_rest_day': False,
                'published_portal': False,
                'novelty': 'sln',
                'liquidacion_value': 'WAGE',
                'force_update': False,
            },
            {
                'code': 'SANCION',
                'name': 'SANCION',
                'request_unit': 'day',
                'leave_validation_type': 'no_validation',
                'requires_allocation': 'no',
                'employee_requests': 'no',
                'color': 1,
                'work_entry_type_code': 'SANCION',
                'unpaid_absences': True,
                'discounting_bonus_days': True,
                'sub_wd': True,
                'pay_transport_allowance': False,
                'apply_day_31': False,
                'discount_rest_day': False,
                'published_portal': False,
                'novelty': 'lnr',
                'liquidacion_value': 'WAGE',
                'force_update': False,
            },
            {
                'code': 'VACDISFRUTADAS',
                'name': 'VACACIONES DISFRUTADAS',
                'request_unit': 'day',
                'leave_validation_type': 'manager',
                'requires_allocation': 'yes',
                'employee_requests': 'yes',
                'color': 2,
                'work_entry_type_code': 'VACDISFRUTADAS',
                'unpaid_absences': False,
                'discounting_bonus_days': False,
                'sub_wd': True,
                'pay_transport_allowance': True,
                'apply_day_31': False,
                'discount_rest_day': False,
                'published_portal': True,
                'novelty': 'vdi',
                'liquidacion_value': 'WAGE',
                'is_vacation': True,
                'force_update': False,
            },
            {
                'code': 'VACATIONS_MONEY',
                'name': 'VACACIONES EN DINERO',
                'request_unit': 'day',
                'leave_validation_type': 'manager',
                'requires_allocation': 'yes',
                'employee_requests': 'yes',
                'color': 2,
                'work_entry_type_code': 'VACATIONS_MONEY',
                'unpaid_absences': False,
                'discounting_bonus_days': False,
                'sub_wd': False,
                'pay_transport_allowance': True,
                'apply_day_31': False,
                'discount_rest_day': False,
                'published_portal': True,
                'novelty': 'vco',
                'liquidacion_value': 'WAGE',
                'is_vacation_money': True,
                'force_update': False,
            },
        ]

        # Crear o actualizar tipos de ausencia
        for leave_data in leave_types:
            force_update = leave_data.pop('force_update', False)
            work_entry_code = leave_data.pop('work_entry_type_code', False)
            code = leave_data['code']

            # Buscar el work_entry_type_id
            if work_entry_code:
                work_entry = self.env['hr.work.entry.type'].search([
                    ('code', '=', work_entry_code)
                ], limit=1)
                if work_entry:
                    leave_data['work_entry_type_id'] = work_entry.id

            # Buscar si ya existe
            existing_leave = self.env['hr.leave.type'].search([
                ('code', '=', code)
            ], limit=1)

            if existing_leave:
                if force_update:
                    # Actualizar solo si force_update está en True
                    existing_leave.write(leave_data)
                else:
                    # Siempre actualizar campos críticos de comportamiento de días
                    # aunque force_update sea False
                    critical_fields = ['sub_wd', 'unpaid_absences', 'discounting_bonus_days',
                                       'pay_transport_allowance', 'discount_rest_day', 'novelty']
                    critical_update = {k: v for k, v in leave_data.items() if k in critical_fields}
                    if critical_update:
                        existing_leave.write(critical_update)
            else:
                # Crear nuevo
                new_leave = self.env['hr.leave.type'].create(leave_data)

        return True

    def _link_leave_types_to_rules(self):
        """
        Vincula los tipos de ausencia con sus reglas salariales correspondientes.
        Configura eps_arl_input_id, company_input_id y factores de reconocimiento.
        """
        SalaryRule = self.env['hr.salary.rule']
        LeaveType = self.env['hr.leave.type']

        # Mapeo de tipos de ausencia a reglas salariales
        # Formato: code -> {eps_arl_rule, company_rule, config}
        LEAVE_RULE_MAPPING = {
            # INCAPACIDADES EPS (primeros 2 dias empresa, resto EPS)
            # INCAPACIDAD EPS: Primeros 2 días empresa (100%), días 3-90 EPS (66.67%)
            'INCAPACIDAD001': {
                'eps_arl_rule': 'INCAPACIDAD001',      # Regla EPS (66.67%)
                'company_rule': 'INCAPACIDAD002',      # Regla empresa (100% primeros 2 días)
                'num_days_no_assume': 2,               # Primeros 2 días asume empresa
                'recognizing_factor_eps_arl': 66.67,   # 66.67% del IBC
                'recognizing_factor_company': 100.0,   # 100% los primeros 2 días
                'periods_calculations_ibl': 1,         # Último mes
            },
            # NOTA: INCAPACIDAD002 no es tipo de ausencia, es solo regla salarial
            # INCAPACIDAD EPS 50%: Días 91-180 (50% del IBC)
            'INCAPACIDAD007': {
                'eps_arl_rule': 'INCAPACIDAD007',
                'company_rule': False,
                'num_days_no_assume': 0,
                'recognizing_factor_eps_arl': 50.0,  # 50% del IBC (dia 91+)
                'recognizing_factor_company': 0,
                'periods_calculations_ibl': 1,
            },
            'EGH': {
                'eps_arl_rule': 'EGH',
                'company_rule': False,
                'num_days_no_assume': 0,
                'recognizing_factor_eps_arl': 66.67,
                'recognizing_factor_company': 0,
                'periods_calculations_ibl': 1,
            },
            # ACCIDENTE DE TRABAJO / ENFERMEDAD PROFESIONAL (100% ARL desde dia 1)
            'AT': {
                'eps_arl_rule': 'AT',
                'company_rule': False,
                'num_days_no_assume': 0,  # ARL asume desde dia 1
                'recognizing_factor_eps_arl': 100.0,  # 100% del IBC
                'recognizing_factor_company': 0,
                'periods_calculations_ibl': 1,
            },
            'EP': {
                'eps_arl_rule': 'EP',
                'company_rule': False,
                'num_days_no_assume': 0,
                'recognizing_factor_eps_arl': 100.0,
                'recognizing_factor_company': 0,
                'periods_calculations_ibl': 1,
            },
            # LICENCIA MATERNIDAD/PATERNIDAD (100% EPS)
            'MAT': {
                'eps_arl_rule': 'MAT',
                'company_rule': False,
                'num_days_no_assume': 0,
                'recognizing_factor_eps_arl': 100.0,
                'recognizing_factor_company': 0,
                'periods_calculations_ibl': 1,
            },
            'PAT': {
                'eps_arl_rule': 'PAT',
                'company_rule': False,
                'num_days_no_assume': 0,
                'recognizing_factor_eps_arl': 100.0,
                'recognizing_factor_company': 0,
                'periods_calculations_ibl': 1,
            },
            # LICENCIA REMUNERADA (100% empresa)
            'LICENCIA001': {
                'eps_arl_rule': False,
                'company_rule': 'LICENCIA001',
                'num_days_no_assume': 0,
                'recognizing_factor_eps_arl': 0,
                'recognizing_factor_company': 100.0,
                'periods_calculations_ibl': 1,
            },
            'LUTO': {
                'eps_arl_rule': False,
                'company_rule': 'LUTO',
                'num_days_no_assume': 0,
                'recognizing_factor_eps_arl': 0,
                'recognizing_factor_company': 100.0,
                'periods_calculations_ibl': 1,
            },
            # LICENCIA NO REMUNERADA / SUSPENSIONES (0% - no se paga)
            'LICENCIA_NO_REMUNERADA': {
                'eps_arl_rule': False,
                'company_rule': False,
                'num_days_no_assume': 0,
                'recognizing_factor_eps_arl': 0,
                'recognizing_factor_company': 0,
                'periods_calculations_ibl': 0,
            },
            'INAS_INJU': {
                'eps_arl_rule': False,
                'company_rule': 'INAS_INJU',
                'num_days_no_assume': 0,
                'recognizing_factor_eps_arl': 0,
                'recognizing_factor_company': 0,  # Descuento
                'periods_calculations_ibl': 0,
            },
            'INAS_INJU_D': {
                'eps_arl_rule': False,
                'company_rule': 'INAS_INJU_D',
                'num_days_no_assume': 0,
                'recognizing_factor_eps_arl': 0,
                'recognizing_factor_company': 0,
                'periods_calculations_ibl': 0,
            },
            'SUSP_CONTRATO': {
                'eps_arl_rule': False,
                'company_rule': 'SUSP_CONTRATO',
                'num_days_no_assume': 0,
                'recognizing_factor_eps_arl': 0,
                'recognizing_factor_company': 0,
                'periods_calculations_ibl': 0,
            },
            'SANCION': {
                'eps_arl_rule': False,
                'company_rule': 'SANCION',
                'num_days_no_assume': 0,
                'recognizing_factor_eps_arl': 0,
                'recognizing_factor_company': 0,
                'periods_calculations_ibl': 0,
            },
            # VACACIONES
            'VACDISFRUTADAS': {
                'eps_arl_rule': False,
                'company_rule': 'VACDISFRUTADAS',
                'num_days_no_assume': 0,
                'recognizing_factor_eps_arl': 0,
                'recognizing_factor_company': 100.0,
                'periods_calculations_ibl': 12,  # Ultimo ano
            },
            'VACATIONS_MONEY': {
                'eps_arl_rule': False,
                'company_rule': 'VACATIONS_MONEY',
                'num_days_no_assume': 0,
                'recognizing_factor_eps_arl': 0,
                'recognizing_factor_company': 100.0,
                'periods_calculations_ibl': 12,
            },
        }

        updated = 0
        for leave_code, config in LEAVE_RULE_MAPPING.items():
            leave_type = LeaveType.search([('code', '=', leave_code)], limit=1)
            if not leave_type:
                _logger.warning(f"Tipo de ausencia {leave_code} no encontrado")
                continue

            update_vals = {
                'num_days_no_assume': config.get('num_days_no_assume', 0),
                'recognizing_factor_eps_arl': config.get('recognizing_factor_eps_arl', 0),
                'recognizing_factor_company': config.get('recognizing_factor_company', 0),
                'periods_calculations_ibl': config.get('periods_calculations_ibl', 1),
            }

            # Buscar regla EPS/ARL
            eps_rule_code = config.get('eps_arl_rule')
            if eps_rule_code:
                eps_rule = SalaryRule.search([('code', '=', eps_rule_code)], limit=1)
                if eps_rule:
                    update_vals['eps_arl_input_id'] = eps_rule.id
                else:
                    _logger.warning(f"Regla EPS/ARL {eps_rule_code} no encontrada para {leave_code}")

            # Buscar regla Compania
            company_rule_code = config.get('company_rule')
            if company_rule_code:
                company_rule = SalaryRule.search([('code', '=', company_rule_code)], limit=1)
                if company_rule:
                    update_vals['company_input_id'] = company_rule.id
                else:
                    _logger.warning(f"Regla empresa {company_rule_code} no encontrada para {leave_code}")

            try:
                leave_type.write(update_vals)
                updated += 1
            except Exception as e:
                _logger.error(f"Error vinculando {leave_code}: {e}")

        return updated

    def action_generate_salary_rules(self):
        """Acción para generar reglas salariales desde la compañía"""
        self.ensure_one()
        # Primero crear categorias salariales (DEV_SALARIAL, DEV_NO_SALARIAL, etc.)
        self._setup_salary_categories()
        self._generate_all_structures()
        self._generate_all_rules()
        self._generate_overtime_types()
        # Vincular tipos de ausencia con reglas salariales
        self._link_leave_types_to_rules()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Éxito'),
                'message': _('Reglas salariales y tipos de ausencia configurados correctamente'),
                'type': 'success',
                'sticky': False,
            }
        }
    
    def _generate_lavish_code(self, process_code, sequence):
        """
        Genera un código lavish de 4 dígitos basado en el proceso y una secuencia
        """
        # Mapeo de códigos de proceso a prefijos
        process_prefix = {
            'nomina': '1',
            'vacaciones': '2',
            'prima': '3',
            'cesantias': '4',
            'contrato': '5',
            'intereses_cesantias': '6',
        }
        
        # Obtener el prefijo del proceso
        prefix = process_prefix.get(process_code, '9')
        
        # Generar un número de 3 dígitos para la secuencia
        sequence_num = str(sequence).zfill(3)
        
        # Combinar el prefijo y la secuencia
        return prefix + sequence_num
    
    def _get_or_create_structure_type(self):
        """
        Obtiene o crea el tipo de estructura salarial para Colombia
        """
        StructureType = self.env['hr.payroll.structure.type']

        # Buscar tipo existente
        structure_type = StructureType.search([
            '|',
            ('name', 'ilike', 'Colombia'),
            ('name', 'ilike', 'Empleado Colombia'),
        ], limit=1)

        if not structure_type:
            # Crear nuevo tipo de estructura
            structure_type = StructureType.create({
                'name': 'Empleado Colombia',
                'wage_type': 'monthly',
            })

        return structure_type

    def _create_or_update_structure(self, name, process_type, sequence, reference=False, structure_type=None):
        """
        Crea o actualiza una estructura salarial
        """
        existing_structure = self.env['hr.payroll.structure'].search([
            ('name', '=', name),
        ], limit=1)
        if not existing_structure:
            existing_structure = self.env['hr.payroll.structure'].search([
                ('process', '=', process_type),
            ], limit=1)

        # Obtener tipo de estructura si no se proporciona
        if not structure_type:
            structure_type = self._get_or_create_structure_type()

        structure_data = {
            'name': name,
            'process': process_type,
            'type_id': structure_type.id,
        }

        if existing_structure:
            existing_structure.write(structure_data)
            return existing_structure
        else:
            new_structure = self.env['hr.payroll.structure'].create(structure_data)
            return new_structure
    
    def _get_rule_properties(self, code, name, category_code, sequence, process_code='nomina', 
                            rule_type='concept', is_leave=False, dev_or_ded='devengo', 
                            is_recargo=False, modality_value='fijo', appears_on_payslip=True):
        """
        Obtiene propiedades base para una regla salarial
        """
        
        base_props = {
            'code': code,
            'name': self._normalize_name_case(name),
            'sequence': sequence,
            'active': True,
            'appears_on_payslip': appears_on_payslip,
            'process': process_code,
        }
        
        # Obtener la categoría por código
        category = self.env['hr.salary.rule.category'].search([
            ('code', '=', category_code),
            ('active', '=', True)
        ], limit=1)
        
        if not category:
            _logger.warning(f"Categoría {category_code} no encontrada para la regla {code}")
            return None
        
        structure = self.env['hr.payroll.structure'].search([
            ('process', '=', process_code),
        ], limit=1)
        
        if not structure:
            _logger.warning(f"Estructura para el proceso {process_code} no encontrada")
            return None
        
        base_props['struct_id'] = structure.id

        # Mapeo de categorias a tipos de concepto
        # type_concepts validos: sueldo, contrato, ley, novedad, prestacion, provision,
        #                        consolidacion, tributaria, seguridad_social, parafiscal
        TYPE_CONCEPTS_MAP = {
            # SUELDO / SALARIO
            'BASIC': 'sueldo',

            # POR LEY (ausencias legales)
            'INCAPACIDAD': 'ley',
            'LICENCIA_REMUNERADA': 'ley',
            'LICENCIA_NO_REMUNERADA': 'ley',
            'AUSENCIA_NO_PAGO': 'ley',
            'LICENCIA_MATERNIDAD': 'ley',
            'ACCIDENTE_TRABAJO': 'ley',
            'VACACIONES': 'ley',
            'AUX': 'ley',

            # PRESTACIONES SOCIALES
            'PRESTACIONES_SOCIALES': 'prestacion',
            'PRIMA': 'prestacion',
            'INDEM': 'prestacion',

            # PROVISIONES
            'PROV': 'provision',

            # TOTALIZADORES / CONSOLIDACIONES
            'TOTALDEV': 'consolidacion',
            'TOTALDED': 'consolidacion',
            'NET': 'consolidacion',
            'GROSS': 'consolidacion',
            'BASE_SEC': 'consolidacion',
            'BASE_OTROS': 'consolidacion',

            # DEDUCCIONES TRIBUTARIAS
            'INTVIV': 'tributaria',
            'AFC': 'tributaria',
            'MEDPRE': 'tributaria',
            'DEDDEP': 'tributaria',
            'DESCUENTO_AFC': 'tributaria',

            # SEGURIDAD SOCIAL
            'SSOCIAL': 'seguridad_social',

            # PARAFISCALES
            'COMP': 'parafiscal',

            # DEVENGOS SALARIALES Y NO SALARIALES (de contrato)
            'DEV_SALARIAL': 'contrato',
            'DEV_NO_SALARIAL': 'contrato',

            # NOVEDADES VARIABLES (horas extras, comisiones, embargos, deducciones)
            'HEYREC': 'novedad',
            'COMISIONES': 'novedad',
            'EM': 'novedad',
            'DEDUCCIONES': 'novedad',
            'SANCIONES': 'novedad',
        }

        # Determinar type_concepts segun proceso si no esta en el mapa
        if category_code in TYPE_CONCEPTS_MAP:
            type_concepts = TYPE_CONCEPTS_MAP[category_code]
        else:
            # Default: 'contrato' para proceso contrato, 'novedad' para otros
            type_concepts = 'contrato' if process_code == 'contrato' else 'novedad'

        if rule_type == 'concept':
            base_props.update({
                'category_id': category.id,
                'condition_select': 'none',
                'amount_select': 'concept',
                'type_concepts': type_concepts,
                'is_leave': is_leave,
                'dev_or_ded': dev_or_ded,
                'modality_value': modality_value,  # Default 'fijo', o 'diario' si se pasa explicitamente
                'is_recargo': is_recargo,
            })
            
            # ====================================================
            # CONFIGURACIÓN DE BASES PARA PRESTACIONES SOCIALES
            # ====================================================
            # Devengos salariales: Sí afectan bases (prima, cesantías, vacaciones, etc.)
            # Devengos no salariales: NO afectan bases (AUX transporte, bonos no salariales)
            # Deducciones: NO afectan bases
            # Prestaciones: NO afectan bases (ellas SON las prestaciones)
            # Totalizadores/NET: NO afectan bases

            if dev_or_ded == 'devengo':
                # SALARIO BÁSICO - Afecta todas las bases
                if category_code == 'BASIC':
                    base_props.update({
                        'base_prima': True,
                        'base_cesantias': True,
                        'base_vacaciones': True,
                        'base_seguridad_social': True,
                        'base_parafiscales': True,
                    })
                # DEVENGOS SALARIALES (bonificaciones, comisiones, retroactivos)
                elif category_code in ['DEV_SALARIAL', 'COMISIONES']:
                    base_props.update({
                        'base_prima': True,
                        'base_cesantias': True,
                        'base_vacaciones': True,
                        'base_seguridad_social': True,
                        'base_parafiscales': True,
                    })
                # HORAS EXTRAS Y RECARGOS - Afectan bases (son salario)
                elif category_code == 'HEYREC':
                    base_props.update({
                        'base_prima': True,
                        'base_cesantias': True,
                        'base_vacaciones': True,
                        'base_seguridad_social': True,
                        'base_parafiscales': True,
                    })
                # INCAPACIDADES - Solo base seguridad social (IBC)
                elif category_code == 'INCAPACIDAD':
                    base_props.update({
                        'base_prima': False,
                        'base_cesantias': False,
                        'base_vacaciones': False,
                        'base_seguridad_social': True,
                        'base_parafiscales': False,
                    })
                # LICENCIAS REMUNERADAS - Según tipo
                elif category_code in ['LICENCIA_REMUNERADA', 'LICENCIA_MATERNIDAD']:
                    base_props.update({
                        'base_prima': False,
                        'base_cesantias': False,
                        'base_vacaciones': False,
                        'base_seguridad_social': True,
                        'base_parafiscales': False,
                    })
                # ACCIDENTE DE TRABAJO - Solo base seguridad social
                elif category_code == 'ACCIDENTE_TRABAJO':
                    base_props.update({
                        'base_prima': False,
                        'base_cesantias': False,
                        'base_vacaciones': False,
                        'base_seguridad_social': True,
                        'base_parafiscales': False,
                    })
                # VACACIONES - Afectan prima y cesantías
                elif category_code == 'VACACIONES':
                    base_props.update({
                        'base_prima': True,
                        'base_cesantias': True,
                        'base_vacaciones': False,  # No se autoincluye
                        'base_seguridad_social': True,
                        'base_parafiscales': True,
                    })
                # AUXILIOS (transporte, conectividad) - NO afectan bases
                elif category_code == 'AUX':
                    base_props.update({
                        'base_prima': False,
                        'base_cesantias': False,
                        'base_vacaciones': False,
                        'base_seguridad_social': False,
                        'base_parafiscales': False,
                    })
                # DEVENGOS NO SALARIALES - NO afectan bases
                elif category_code == 'DEV_NO_SALARIAL':
                    base_props.update({
                        'base_prima': False,
                        'base_cesantias': False,
                        'base_vacaciones': False,
                        'base_seguridad_social': False,
                        'base_parafiscales': False,
                    })
                # PRESTACIONES SOCIALES - NO afectan bases (ellas SON las prestaciones)
                elif category_code in ['PRESTACIONES_SOCIALES', 'PRIMA', 'PROV']:
                    base_props.update({
                        'base_prima': False,
                        'base_cesantias': False,
                        'base_vacaciones': False,
                        'base_seguridad_social': False,
                        'base_parafiscales': False,
                    })
                # INDEMNIZACIONES - No afectan bases regulares
                elif category_code == 'INDEM':
                    base_props.update({
                        'base_prima': False,
                        'base_cesantias': False,
                        'base_vacaciones': False,
                        'base_seguridad_social': False,
                        'base_parafiscales': False,
                    })
                # LICENCIAS NO REMUNERADAS / SANCIONES - No afectan bases
                elif category_code in ['LICENCIA_NO_REMUNERADA', 'AUSENCIA_NO_PAGO', 'SANCIONES']:
                    base_props.update({
                        'base_prima': False,
                        'base_cesantias': False,
                        'base_vacaciones': False,
                        'base_seguridad_social': False,
                        'base_parafiscales': False,
                    })
                # OTROS DEVENGOS - Por defecto no afectan bases
                else:
                    base_props.update({
                        'base_prima': False,
                        'base_cesantias': False,
                        'base_vacaciones': False,
                        'base_seguridad_social': False,
                        'base_parafiscales': False,
                    })
            else:
                # DEDUCCIONES - Nunca afectan bases de prestaciones
                base_props.update({
                    'base_prima': False,
                    'base_cesantias': False,
                    'base_vacaciones': False,
                    'base_seguridad_social': False,
                    'base_parafiscales': False,
                })
                
        elif rule_type == 'totalizador':
            # Los totalizadores y neto a pagar NO deben tener provisiones
            base_props.update({
                'category_id': category.id,
                'condition_select': 'none',
                'amount_select': 'concept',
                'type_concepts': 'consolidacion',
                # Totalizadores NO afectan bases de prestaciones
                'base_prima': False,
                'base_cesantias': False,
                'base_vacaciones': False,
                'base_seguridad_social': False,
                'base_parafiscales': False,
            })
        
        return base_props
    
    def _create_or_update_rule(self, rule_data):
        """
        Crea o actualiza una regla salarial
        """
        if not rule_data:
            _logger.warning("No se proporcionaron datos para crear o actualizar la regla")
            return None
        # Buscar si ya existe la regla por código
        existing_rule = self.env['hr.salary.rule'].search([
            ('code', '=', rule_data.get('code','')),
            ('active', '=', True),
        ], limit=1)
        
        if existing_rule:
            existing_rule.write(rule_data)
            return existing_rule
        else:
            # Crear nueva regla
            new_rule = self.env['hr.salary.rule'].create(rule_data)
            return new_rule
    
    def _generate_all_structures(self):
        """Generar todas las estructuras salariales necesarias"""
        # Obtener o crear el tipo de estructura salarial una sola vez
        structure_type = self._get_or_create_structure_type()

        # Crear estructura para Nomina
        nomina_structure = self._create_or_update_structure(
            name='Nomina Colombia',
            process_type='nomina',
            sequence=1,
            reference='Estructura para nomina regular',
            structure_type=structure_type
        )
        
        # Crear estructura para Vacaciones
        vacaciones_structure = self._create_or_update_structure(
            name='Vacaciones Colombia',
            process_type='vacaciones',
            sequence=2,
            reference='Estructura para liquidacion de vacaciones',
            structure_type=structure_type
        )

        # Crear estructura para Prima
        prima_structure = self._create_or_update_structure(
            name='Prima Colombia',
            process_type='prima',
            sequence=3,
            reference='Estructura para liquidacion de prima de servicios',
            structure_type=structure_type
        )

        # Crear estructura para Cesantias
        cesantias_structure = self._create_or_update_structure(
            name='Cesantias Colombia',
            process_type='cesantias',
            sequence=4,
            reference='Estructura para liquidacion de cesantias',
            structure_type=structure_type
        )

        # Crear estructura para Liquidacion de Contrato
        liquidacion_structure = self._create_or_update_structure(
            name='Liquidacion de Contrato Colombia',
            process_type='contrato',
            sequence=5,
            reference='Estructura para liquidacion final de contrato',
            structure_type=structure_type
        )

        # Crear estructura para intereses_cesantias de Cesantias
        intereses_structure = self._create_or_update_structure(
            name='Intereses de Cesantias Colombia',
            process_type='intereses_cesantias',
            sequence=6,
            reference='Estructura para liquidacion de intereses sobre cesantias',
            structure_type=structure_type
        )
        
        return {
            'nomina': nomina_structure,
            'vacaciones': vacaciones_structure,
            'prima': prima_structure,
            'cesantias': cesantias_structure,
            'contrato': liquidacion_structure,
            'intereses_cesantias': intereses_structure,
        }
    
    def _generate_all_rules(self):
        """
        Genera todas las reglas salariales usando generadores modulares por categoría.
        
        Este método delega la generación de reglas a módulos helper organizados
        por categoría, mejorando la mantenibilidad y facilitando la auditoría.
        """
        from .rule_generators import ALL_GENERATORS
        
        total_rules = 0
        for generator_class in ALL_GENERATORS:
            generator_name = generator_class.__name__
            
            try:
                rules = generator_class.get_rules()
                category_count = 0
                
                for rule_data in rules:
                    # Extraer parámetros con valores por defecto
                    rule_props = self._get_rule_properties(
                        code=rule_data.get('code'),
                        name=rule_data.get('name'),
                        category_code=rule_data.get('category_code'),
                        sequence=rule_data.get('sequence'),
                        process_code=rule_data.get('process_code', 'nomina'),
                        rule_type=rule_data.get('rule_type', 'concept'),
                        is_leave=rule_data.get('is_leave', False),
                        dev_or_ded=rule_data.get('dev_or_ded', 'devengo'),
                        is_recargo=rule_data.get('is_recargo', False),
                        modality_value=rule_data.get('modality_value', 'fijo'),
                        appears_on_payslip=rule_data.get('appears_on_payslip', True)
                    )
                    
                    if rule_props:
                        self._create_or_update_rule(rule_props)
                        category_count += 1
                        total_rules += 1
                
            except Exception as e:
                _logger.error(f"Error generando reglas de {generator_name}: {str(e)}")
                continue
        
    def _generate_overtime_types(self):
        """Genera los tipos de horas extras basados en las reglas salariales"""
        overtime_mapping = {
            'HEYREC001': {
                'type_overtime': 'overtime_ext_d',
                'name': 'EXT-D | Extra diurna',
                'percentage': 1.25,
                'start_time': 6.0,
                'end_time': 21.0,
                'start_time_two': 0.0,
                'end_time_two': 0.0,
                'contains_holidays': False,
                'mon': True, 'tue': True, 'wed': True, 'thu': True, 'fri': True,
                'sat': False, 'sun': False
            },
            'HEYREC002': {
                'type_overtime': 'overtime_eddf',
                'name': 'E-D-D/F | Extra diurna dominical/festivo',
                'percentage': 2.0,
                'start_time': 6.0,
                'end_time': 21.0,
                'start_time_two': 0.0,
                'end_time_two': 0.0,
                'contains_holidays': True,
                'mon': False, 'tue': False, 'wed': False, 'thu': False, 'fri': False,
                'sat': False, 'sun': True
            },
            'HEYREC003': {
                'type_overtime': 'overtime_ext_n',
                'name': 'EXT-N | Extra nocturna',
                'percentage': 1.75,
                'start_time': 21.0,
                'end_time': 24.0,
                'start_time_two': 0.0,
                'end_time_two': 6.0,
                'contains_holidays': False,
                'mon': True, 'tue': True, 'wed': True, 'thu': True, 'fri': True,
                'sat': False, 'sun': False
            },
            'HEYREC004': {
                'type_overtime': 'overtime_rdf',
                'name': 'R-D/F | Recargo dominical/festivo',
                'percentage': 0.75,
                'start_time': 0.0,
                'end_time': 24.0,
                'start_time_two': 0.0,
                'end_time_two': 0.0,
                'contains_holidays': True,
                'mon': False, 'tue': False, 'wed': False, 'thu': False, 'fri': False,
                'sat': False, 'sun': True
            },
            'HEYREC005': {
                'type_overtime': 'overtime_rn',
                'name': 'RN | Recargo nocturno',
                'percentage': 0.35,
                'start_time': 21.0,
                'end_time': 24.0,
                'start_time_two': 0.0,
                'end_time_two': 6.0,
                'contains_holidays': False,
                'mon': True, 'tue': True, 'wed': True, 'thu': True, 'fri': True,
                'sat': True, 'sun': False
            },
            'HEYREC006': {
                'type_overtime': 'overtime_endf',
                'name': 'E-N-D/F | Extra nocturna dominical/festivo',
                'percentage': 2.5,
                'start_time': 21.0,
                'end_time': 24.0,
                'start_time_two': 0.0,
                'end_time_two': 6.0,
                'contains_holidays': True,
                'mon': False, 'tue': False, 'wed': False, 'thu': False, 'fri': False,
                'sat': False, 'sun': True
            },
            'HEYREC007': {
                'type_overtime': 'overtime_dof',
                'name': 'D o F | Dominicales o festivos',
                'percentage': 1.75,
                'start_time': 0.0,
                'end_time': 24.0,
                'start_time_two': 0.0,
                'end_time_two': 0.0,
                'contains_holidays': True,
                'mon': False, 'tue': False, 'wed': False, 'thu': False, 'fri': False,
                'sat': False, 'sun': True
            },
            'HEYREC008': {
                'type_overtime': 'overtime_rndf',
                'name': 'RN-D/F | Recargo nocturno dominical/festivo',
                'percentage': 1.1,
                'start_time': 21.0,
                'end_time': 24.0,
                'start_time_two': 0.0,
                'end_time_two': 6.0,
                'contains_holidays': True,
                'mon': False, 'tue': False, 'wed': False, 'thu': False, 'fri': False,
                'sat': False, 'sun': True
            },
        }
        
        for rule_code, overtime_data in overtime_mapping.items():
            rule = self.env['hr.salary.rule'].search([
                ('code', '=', rule_code),
                ('active', '=', True),
            ], limit=1)
            
            if not rule:
                _logger.warning(f"Regla salarial {rule_code} no encontrada para crear tipo de hora extra")
                continue
            
            existing_overtime = self.env['hr.type.overtime'].search([
                ('type_overtime', '=', overtime_data['type_overtime'])
            ], limit=1)
            
            overtime_values = {
                'name': overtime_data['name'],
                'salary_rule': rule.id,
                'type_overtime': overtime_data['type_overtime'],
                'percentage': overtime_data['percentage'] * 100,  # Convertir a porcentaje
                'start_time': overtime_data['start_time'],
                'end_time': overtime_data['end_time'],
                'start_time_two': overtime_data['start_time_two'],
                'end_time_two': overtime_data['end_time_two'],
                'contains_holidays': overtime_data['contains_holidays'],
                'mon': overtime_data['mon'],
                'tue': overtime_data['tue'],
                'wed': overtime_data['wed'],
                'thu': overtime_data['thu'],
                'fri': overtime_data['fri'],
                'sat': overtime_data['sat'],
                'sun': overtime_data['sun'],
            }
            
            if existing_overtime:
                existing_overtime.write(overtime_values)
            else:
                new_overtime = self.env['hr.type.overtime'].create(overtime_values)
                
