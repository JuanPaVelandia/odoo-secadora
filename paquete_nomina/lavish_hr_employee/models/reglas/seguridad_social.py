# -*- coding: utf-8 -*-

"""
REGLAS SALARIALES - SEGURIDAD SOCIAL
=====================================

Metodos para calculos de Salud, Pension, FSP y Subsistencia.
Separado de ibd_sss.py para evitar conflictos y facilitar mantenimiento.

Usa hooks para reducir duplicacion de codigo.
"""

from odoo import models, api
from .config_reglas import DAYS_MONTH
from dateutil.relativedelta import relativedelta
import logging

_logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# HOOKS Y HELPERS PARA SEGURIDAD SOCIAL
# ══════════════════════════════════════════════════════════════════════════════

class SSHooks:
    """
    Hooks estaticos para calculos de seguridad social.
    Centraliza logica comun para reducir duplicacion.
    """

    @staticmethod
    def check_contribution(employee, contribution_type='all'):
        """
        Hook: Verifica si empleado debe contribuir a seguridad social.

        Args:
            employee: hr.employee record
            contribution_type: 'salud', 'pension', 'all'

        Returns:
            dict: {
                'contribuye': bool,
                'salud': bool,
                'pension': bool,
                'parameterization': record or None,
                'razon_exclusion': str or None
            }
        """
        info = employee.should_contribute_social_security(contribution_type)

        if isinstance(info, bool):
            return {
                'contribuye': info,
                'salud': info,
                'pension': info,
                'parameterization': None,
                'razon_exclusion': None if info else 'Empleado excluido de SS'
            }

        return {
            'contribuye': info.get('salud', False) or info.get('pension', False),
            'salud': info.get('salud', False),
            'pension': info.get('pension', False),
            'parameterization': info.get('parameterization'),
            'razon_exclusion': None
        }

    @staticmethod
    def is_apprentice(contract):
        """Hook: Verifica si es contrato de aprendizaje."""
        if not contract.contract_type_id:
            return False
        return contract.contract_type_id.contract_category == 'aprendizaje'

    @staticmethod
    def is_pensioner(employee):
        """Hook: Verifica si es pensionado (subtipo != '00')."""
        if not employee.subtipo_coti_id:
            return False
        return employee.subtipo_coti_id.code not in ['00', False]

    @staticmethod
    def should_skip_by_cobro(aplicar_cobro, slip_day):
        """
        Hook: Determina si debe omitir calculo por quincena de cobro.

        Args:
            aplicar_cobro: '15' o '30'
            slip_day: dia del slip.date_from

        Returns:
            bool: True si debe omitir
        """
        if aplicar_cobro == '15' and slip_day >= 15:
            return True
        if aplicar_cobro == '30' and slip_day < 15:
            return True
        return False

    @staticmethod
    def should_project_funds(contract, slip):
        """
        Hook: Verifica si debe proyectar aportes a fondos (quincenal).

        Solo proyecta si:
        1) Contrato tiene proyectar_fondos=True
        2) Periodo es quincenal (<= 16 dias)
        3) Es primera quincena (date_from.day <= 15)
        """
        if not contract.proyectar_fondos:
            return False
        if not slip.date_from or not slip.date_to:
            return False
        dias_periodo = (slip.date_to - slip.date_from).days + 1
        return dias_periodo <= 16 and slip.date_from.day <= 15


class SSParamsBuilder:
    """
    Builder para construir parametros comunes de seguridad social.
    Evita duplicacion en _ssocial001, _ssocial002, etc.
    """

    def __init__(self, rule_instance, localdict, tipo_aporte):
        """
        Args:
            rule_instance: instancia de hr.salary.rule (self)
            localdict: diccionario de contexto
            tipo_aporte: 'salud', 'pension', 'fondo_solidaridad', 'fondo_subsistencia'
        """
        self.rule = rule_instance
        self.localdict = localdict
        self.tipo_aporte = tipo_aporte

        # Extraer objetos comunes
        self.slip = localdict['slip']
        self.contract = localdict['contract']
        self.employee = localdict['employee']
        self.annual_parameters = localdict['annual_parameters']

        # Estado inicial
        self._ibd_data = None
        self._contribucion_info = None

    def get_ibd_data(self):
        """Obtiene datos de IBD de manera lazy."""
        if self._ibd_data is None:
            self._ibd_data = self.rule._get_ibd_data_from_rules(self.localdict)
            _logger.info(
                f"[SS] get_ibd_data() - Employee: {self.employee.name}, "
                f"Slip: {self.slip.id}, Struct: {self.slip.struct_id.name}, "
                f"IBD Data: {self._ibd_data}"
            )
        return self._ibd_data

    def get_contribucion_info(self, check_type='all'):
        """Obtiene info de contribucion de manera lazy."""
        if self._contribucion_info is None:
            self._contribucion_info = SSHooks.check_contribution(self.employee, check_type)
            _logger.info(
                f"[SS] get_contribucion_info() - Employee: {self.employee.name}, "
                f"check_type: {check_type}, Result: {self._contribucion_info}"
            )
        return self._contribucion_info

    def get_periodo_label(self):
        """Obtiene etiqueta de periodo."""
        return self.rule._get_periodo(self.slip).upper()

    def is_apprentice(self):
        """Verifica si es aprendiz."""
        return SSHooks.is_apprentice(self.contract)

    def is_pensioner(self):
        """Verifica si es pensionado."""
        return SSHooks.is_pensioner(self.employee)

    def should_skip_cobro(self):
        """Verifica si debe omitir por quincena de cobro."""
        return SSHooks.should_skip_by_cobro(
            self.rule.aplicar_cobro,
            self.slip.date_from.day
        )

    def should_project(self):
        """Verifica si debe proyectar fondos."""
        return SSHooks.should_project_funds(self.contract, self.slip)

    def calculate_base_with_projection(self, porcentaje):
        """
        Calcula base considerando proyeccion si aplica.

        Returns:
            tuple: (base_calculo, ibc_anterior, debe_proyectar)
        """
        ibd_data = self.get_ibd_data()
        debe_proyectar = self.should_project()

        if debe_proyectar:
            # Calcular proyeccion
            total, qty_days = self.rule._get_totalizar_categorias(
                self.localdict, categorias=['BASIC'],
                incluir_current=False, incluir_before=False, incluir_multi=True
            )
            total_dev, _ = self.rule._get_totalizar_categorias(
                self.localdict, categorias=['DEV_SALARIAL'], categorias_excluir="BASIC",
                incluir_current=False, incluir_before=False, incluir_multi=True
            )

            if self.slip.struct_type_id.wage_type == "hourly" and qty_days > 0:
                hours_daily = self.annual_parameters.hours_daily
                qty_days = qty_days / hours_daily

            total_basic = total / qty_days if qty_days > 0 else 0
            days_project = qty_days + 15
            BASIC = total_basic * days_project
            ingreso_base_cotizacion = BASIC + total_dev
        else:
            ingreso_base_cotizacion = ibd_data['ingreso_base_cotizacion']

        return ingreso_base_cotizacion, debe_proyectar

    def get_valor_anterior(self, rule_code, porcentaje):
        """Obtiene valor del mes anterior para una regla."""
        valor = self.rule._get_totalizar_reglas(
            self.localdict, rule_code,
            incluir_current=True, incluir_before=False, incluir_multi=False,
            devolver_cantidad=False
        )
        return valor

    def build_log_data(self, **kwargs):
        """
        Construye dict de log_data estandarizado.

        Args:
            **kwargs: Valores especificos a incluir

        Returns:
            dict: log_data para el widget
        """
        ibd_data = self.get_ibd_data()

        base_data = {
            'tipo_aporte': self.tipo_aporte,
            'ibc': ibd_data['ibc_full'],
            'ibc_periodo': kwargs.get('ingreso_base_cotizacion', 0),
            'ibc_anterior': kwargs.get('ibc_anterior', 0),
            'base_calculo': kwargs.get('base_calculo', 0),
            'porcentaje': kwargs.get('porcentaje', 0),
            'vacaciones_monto': ibd_data.get('vac_monto', 0),
            'vacaciones_dias': ibd_data.get('vac_dias', 0),
        }

        # Agregar datos adicionales
        base_data.update(kwargs)

        return base_data


# ══════════════════════════════════════════════════════════════════════════════
# MIXIN DE SEGURIDAD SOCIAL
# ══════════════════════════════════════════════════════════════════════════════

class HrSalaryRuleSS(models.AbstractModel):
    """Mixin para reglas de seguridad social (Salud, Pension, FSP, Subsistencia)"""

    _name = 'hr.salary.rule.ss'
    _description = 'Metodos para Reglas de Seguridad Social'

    # ══════════════════════════════════════════════════════════════════════════
    # METODO GENERICO PARA SS
    # ══════════════════════════════════════════════════════════════════════════

    def _calculate_ss_generic(self, localdict, tipo_aporte, rule_code, porcentaje_field,
                              check_fondo=False, check_subsistencia=False):
        """
        Metodo generico para calcular deducciones de seguridad social.

        Args:
            localdict: contexto de calculo
            tipo_aporte: 'salud', 'pension', 'fondo_solidaridad', 'fondo_subsistencia'
            rule_code: codigo de la regla (SSOCIAL001, SSOCIAL002, etc.)
            porcentaje_field: campo de annual_parameters para obtener porcentaje
            check_fondo: True si debe verificar topes de fondo (>4 SMMLV)
            check_subsistencia: True si debe calcular porcentaje variable

        Returns:
            tuple: (amount, quantity, rate, name, note, log_data)
        """
        from odoo.addons.lavish_hr_employee.models.hr_slip_utils import round_1_decimal

        slip = localdict.get('slip')
        employee = localdict.get('employee')

        # Construir parametros
        params = SSParamsBuilder(self, localdict, tipo_aporte)
        periodo = params.get_periodo_label()

        # Regla de negocio: aprendiz etapa lectiva no aporta salud ni pensión.
        # Se determina la etapa efectiva del PERIODO de la nómina comparando
        # slip.date_to contra contract.apr_prod_date, evitando que el campo
        # computado apprentice_stage (que refleja el estado actual del contrato)
        # afecte incorrectamente a períodos históricos ya liquidados.
        if tipo_aporte in ('salud', 'pension'):
            tipo_coti_code = (
                params.employee.tipo_coti_id.code
                if params.employee and params.employee.tipo_coti_id
                else False
            )
            if params.is_apprentice():
                apr_prod_date = getattr(params.contract, 'apr_prod_date', False)
                if apr_prod_date:
                    # Etapa según las fechas del período: si date_to < apr_prod_date → lectiva
                    stage_periodo = 'lectiva' if slip.date_to < apr_prod_date else 'productiva'
                else:
                    # Sin fecha de productiva definida: usar tipo cotizante o asumir lectiva
                    stage_periodo = 'lectiva' if tipo_coti_code == '12' else (
                        getattr(params.contract, 'apprentice_stage', 'lectiva') or 'lectiva'
                    )
                if stage_periodo == 'lectiva':
                    return 0, 0, 0, '', False, {}


        if callable(porcentaje_field):
            porcentaje = porcentaje_field(params)
        else:
            try:
                if params.annual_parameters and porcentaje_field in params.annual_parameters._fields:
                    porcentaje = getattr(params.annual_parameters, porcentaje_field)
                else:
                    porcentaje = 0
            except (AttributeError, KeyError) as e:
                porcentaje = 0
            if porcentaje > 1:
                porcentaje_decimal = porcentaje / 100
            else:
                porcentaje_decimal = porcentaje

        # Verificar contribucion
        contribucion_info = params.get_contribucion_info()

        if tipo_aporte == 'salud' and not contribucion_info['salud']:
            return 0, 0, 0, '', False, {}

        if tipo_aporte in ['pension', 'fondo_solidaridad', 'fondo_subsistencia']:
            if not contribucion_info['pension']:
                return 0, 0, porcentaje, '', False, {}

        if check_fondo or check_subsistencia:
            # Verificar pensionado
            if params.is_pensioner():
                return 0, 0, porcentaje, '', False, {}

            # Verificar parametrizacion de fondos
            param_info = contribucion_info.get('parameterization')
            if param_info:
                if check_fondo and not param_info.liquidates_solidarity_fund:
                    return 0, 0, porcentaje, '', False, {}

        # Obtener datos IBD
        ibd_data = params.get_ibd_data()
        ingreso_base_cotizacion, debe_proyectar = params.calculate_base_with_projection(porcentaje)

    
        # VACACIONES FRAGMENTADAS: Aplicar IBC al 40% si hay nómina en el mismo mes
        vacaciones_fragmentadas = params.slip.env['ir.config_parameter'].sudo().get_param(
            'lavish_hr_payroll.vacaciones_fragmentadas', False
        )

        if vacaciones_fragmentadas and params.slip.struct_id.process == 'vacaciones':
            # Verificar si hay nómina (proceso='nomina') en el mismo mes
            mismo_mes_domain = [
                ('employee_id', '=', params.slip.employee_id.id),
                ('state', 'in', ('done', 'paid')),
                ('struct_id.process', '=', 'nomina'),
                ('date_from', '>=', params.slip.date_from.replace(day=1)),
                ('date_from', '<', (params.slip.date_from.replace(day=1) + relativedelta(months=1))),
                ('id', '!=', params.slip.id),
            ]

            hay_nomina_mismo_mes = params.slip.env['hr.payslip'].search_count(mismo_mes_domain) > 0

            if hay_nomina_mismo_mes:
                # Aplicar IBC al 40% para vacaciones fragmentadas con nómina en el mismo mes
                ingreso_base_cotizacion = ingreso_base_cotizacion * 0.40

        # Tipo 51 (Tiempo parcial): Restar SS ya computado del IBC
        if params.contract.tipo_cotizante_code == '51' and tipo_aporte in ('salud', 'pension'):
            ss_data = self._get_current_period_data(localdict, filters={'rules': ['IBD', 'IBC']})
            if ss_data['total'] != 0:
                valor_ss_previo = abs(ss_data['total'])
                _logger.info(
                    f"[SS] {rule_code} - Tipo 51: Restando SS previo del IBC, "
                    f"valor_ss={valor_ss_previo}, IBC antes={ingreso_base_cotizacion}"
                )
                ingreso_base_cotizacion = ingreso_base_cotizacion - valor_ss_previo
               
        # Verificar tope minimo para fondos
        if check_fondo or check_subsistencia:
            tope_4_smmlv = params.annual_parameters.top_four_fsp_smmlv
            if round_1_decimal(ingreso_base_cotizacion) <= round_1_decimal(tope_4_smmlv):
                return 0, 0, porcentaje, '', False, {}

        # Para subsistencia: calcular porcentaje variable
        if check_subsistencia:
            porcentaje = self._get_porcentaje_subsistencia(
                ingreso_base_cotizacion,
                params.annual_parameters.smmlv_monthly
            )
            if porcentaje == 0:
                return 0, 0, 0, '', False, {}

        # Calcular base
        valor_mes_anterior = params.get_valor_anterior(rule_code, porcentaje)

        if valor_mes_anterior != 0 and porcentaje > 0:
            base_mes_anterior = valor_mes_anterior / (porcentaje / 100)
        else:
            base_mes_anterior = 0

        # Para salud/pension: ajustar con vacaciones
        vac = ibd_data.get('vac_monto', 0)
        vac_dias = ibd_data.get('vac_dias', 0)

        if tipo_aporte in ['salud', 'pension']:
            ibc_anterior = base_mes_anterior
            ibc_adjustado = ibd_data['ibc'] + ibc_anterior - vac
            base_calculo = ibd_data['ingreso_base_cotizacion'] + ibc_adjustado
        else:
            # Para fondos
            base_calculo = ingreso_base_cotizacion - abs(base_mes_anterior)

            # Verificar si hay vacaciones previas
            if self._get_totalizar_reglas(localdict, rule_code, incluir_before=True) == 0:
                vac = 0

        # Construir log_data
        log_data = params.build_log_data(
            ingreso_base_cotizacion=ingreso_base_cotizacion,
            ibc_anterior=base_mes_anterior,
            base_calculo=base_calculo,
            porcentaje=porcentaje,
            debe_proyectar=debe_proyectar,
            vacaciones_monto=vac,
            vacaciones_dias=vac_dias,
        )

        # Agregar datos especificos de fondos
        if check_fondo or check_subsistencia:
            log_data['tope_minimo'] = params.annual_parameters.top_four_fsp_smmlv

        if check_subsistencia:
            smmlv = params.annual_parameters.smmlv_monthly
            multiples_sm = ingreso_base_cotizacion / smmlv if smmlv > 0 else 0
            log_data['multiples_sm'] = multiples_sm
            log_data['rango_aplicado'] = self._get_rango_subsistencia(multiples_sm)

        # Comparacion con periodo anterior (salud/pension)
        if tipo_aporte in ['salud', 'pension']:
            valor_anterior_line = self._get_previous_payslip_line(
                params.contract, rule_code, params.slip.date_from
            )
            valor_anterior = abs(valor_anterior_line.total) if valor_anterior_line else 0
            valor_actual = base_calculo * (porcentaje / 100) if base_calculo > 0 else 0

            log_data['valor_anterior'] = valor_anterior
            log_data['valor_actual'] = valor_actual
            log_data['diferencia'] = valor_actual - valor_anterior
            log_data['payslip_line_anterior'] = self._build_payslip_line_info(
                valor_anterior_line, include_total=False, include_amount=False, include_quantity=False
            )

        # Verificar si omitir por cobro
        if params.should_skip_cobro():
            return 0, 0, porcentaje, '', False, log_data

        # Aplicar proyeccion si corresponde
        if debe_proyectar and base_calculo > 0 and (check_fondo or check_subsistencia):
            base_calculo = base_calculo / 2
            log_data['base_proyectada'] = True

        # Restar vacaciones para fondos
        if check_fondo or check_subsistencia:
            base_calculo = base_calculo - vac

        return base_calculo, -1, porcentaje, periodo, False, log_data

    def _get_porcentaje_subsistencia(self, ingreso_base, salario_minimo):
        """Determina el porcentaje de subsistencia segun rango de IBC."""
        if ingreso_base <= 4 * salario_minimo:
            return 0.0
        elif ingreso_base <= 16 * salario_minimo:
            return 0.5
        elif ingreso_base <= 17 * salario_minimo:
            return 0.7
        elif ingreso_base <= 18 * salario_minimo:
            return 0.9
        elif ingreso_base <= 19 * salario_minimo:
            return 1.1
        elif ingreso_base <= 20 * salario_minimo:
            return 1.3
        else:
            return 1.5

    def _get_rango_subsistencia(self, multiples_sm):
        """Retorna el rango aplicado segun multiplos de SMMLV."""
        if multiples_sm <= 4:
            return "<= 4 SMMLV"
        elif multiples_sm <= 16:
            return "4-16 SMMLV"
        elif multiples_sm <= 17:
            return "16-17 SMMLV"
        elif multiples_sm <= 18:
            return "17-18 SMMLV"
        elif multiples_sm <= 19:
            return "18-19 SMMLV"
        elif multiples_sm <= 20:
            return "19-20 SMMLV"
        else:
            return "> 20 SMMLV"

    # ══════════════════════════════════════════════════════════════════════════
    # REGLAS INDIVIDUALES (usan metodo generico)
    # ══════════════════════════════════════════════════════════════════════════

    def _ssocial001(self, localdict):
        """Calcula la deduccion de salud del empleado."""
        return self._calculate_ss_generic(
            localdict,
            tipo_aporte='salud',
            rule_code='SSOCIAL001',
            porcentaje_field='value_porc_health_employee'
        )

    def _ssocial002(self, localdict):
        """Calcula la deduccion de pension del empleado."""
        return self._calculate_ss_generic(
            localdict,
            tipo_aporte='pension',
            rule_code='SSOCIAL002',
            porcentaje_field='value_porc_pension_employee'
        )

    def _ssocial003(self, localdict):
        """Calcula el aporte a fondo de solidaridad pensional (FSP) - 0.5%."""
        return self._calculate_ss_generic(
            localdict,
            tipo_aporte='fondo_solidaridad',
            rule_code='SSOCIAL003',
            porcentaje_field=lambda p: 0.5,  # FSP siempre 0.5%
            check_fondo=True
        )

    def _ssocial004(self, localdict):
        """Calcula el aporte al fondo de subsistencia pensional."""
        return self._calculate_ss_generic(
            localdict,
            tipo_aporte='fondo_subsistencia',
            rule_code='SSOCIAL004',
            porcentaje_field=lambda p: 0,  # Se calcula dinamicamente
            check_subsistencia=True
        )
