# -*- coding: utf-8 -*-
"""
Servicio de Configuracion de Nomina Colombia
=============================================
Servicio centralizado para configurar parametrizaciones de nomina colombiana:
- Tipos y subtipos de cotizante (PILA)
- Tipos de horas extras
- Categorias de reglas salariales
- Tipos de ausencia
"""

from odoo import api, models, _
import logging

_logger = logging.getLogger(__name__)


class PayrollSetupService(models.AbstractModel):
    _name = 'hr.payroll.setup.service'
    _description = 'Servicio de Configuracion de Nomina'

    # =========================================================================
    # TIPOS Y SUBTIPOS DE COTIZANTE (PILA)
    # =========================================================================

    @api.model
    def get_tipos_cotizante_data(self):
        """Datos maestros de tipos de cotizante segun PILA Colombia 2025"""
        return [
            {
                'code': '01', 'name': '01 - Dependiente',
                'description': 'Trabajador vinculado mediante contrato laboral o reglamento',
                'aplicacion_practica': 'Empleados del sector publico o privado con contrato laboral',
                'referencia_normativa': 'Decreto 1406 de 1999'
            },
            {
                'code': '02', 'name': '02 - Servicio Domestico',
                'description': 'Personas que laboran en hogares realizando oficios varios',
                'aplicacion_practica': 'Empleadas domesticas, nineras, conductores de hogar',
                'referencia_normativa': 'Ley 1595 de 2012'
            },
            {
                'code': '03', 'name': '03 - Independiente',
                'description': 'Persona natural que realiza actividades economicas por cuenta propia sin contrato',
                'aplicacion_practica': 'Comerciantes, profesionales independientes',
                'referencia_normativa': 'Decreto 1072 de 2015'
            },
            {
                'code': '12', 'name': '12 - Aprendiz SENA etapa lectiva',
                'description': 'Jovenes en etapa lectiva de formacion del SENA. Solo aporta ARL (Planilla K)',
                'aplicacion_practica': 'Aprendices en etapa de estudio teorico',
                'referencia_normativa': 'Decreto 933 de 2003'
            },
            {
                'code': '19', 'name': '19 - Aprendiz SENA etapa productiva',
                'description': 'Jovenes en etapa productiva de formacion del SENA. Aporta EPS y ARL',
                'aplicacion_practica': 'Aprendices en etapa practica en empresas',
                'referencia_normativa': 'Decreto 933 de 2003'
            },
            {
                'code': '20', 'name': '20 - Estudiante practicas',
                'description': 'Personas que realizan practicas universitarias. Solo aporta ARL (Planilla K)',
                'aplicacion_practica': 'Estudiantes en practicas profesionales con riesgo ocupacional',
                'referencia_normativa': 'Decreto 933 de 2003'
            },
            {
                'code': '21', 'name': '21 - Independiente con contrato',
                'description': 'Persona natural que presta servicios sin vinculo laboral y cuyo contrato es superior a un mes',
                'aplicacion_practica': 'Contratistas por prestacion de servicios',
                'referencia_normativa': 'Decreto 1072 de 2015'
            },
            {
                'code': '22', 'name': '22 - Profesor establecimiento particular',
                'description': 'Docente vinculado a una institucion educativa privada',
                'aplicacion_practica': 'Profesores de colegios privados',
                'referencia_normativa': 'Decreto 1072 de 2015'
            },
            {
                'code': '23', 'name': '23 - Trabajador tiempo parcial',
                'description': 'Persona que labora menos de la jornada legal y cotiza proporcionalmente',
                'aplicacion_practica': 'Trabajadores con jornadas reducidas',
                'referencia_normativa': 'Resolucion 000467 de 2025'
            },
            {
                'code': '30', 'name': '30 - Dependiente entidad publica',
                'description': 'Trabajador vinculado a entidades o universidades publicas de los regimenes especial y de excepcion',
                'aplicacion_practica': 'Empleados de universidades publicas',
                'referencia_normativa': 'Decreto 1072 de 2015'
            },
            {
                'code': '31', 'name': '31 - Cooperado trabajo asociado',
                'description': 'Persona vinculada a una cooperativa o pre-cooperativa de trabajo asociado',
                'aplicacion_practica': 'Miembros de cooperativas de trabajo',
                'referencia_normativa': 'Decreto 1072 de 2015'
            },
            {
                'code': '51', 'name': '51 - Trabajador medio tiempo',
                'description': 'Persona que labora menos de la jornada legal y cotiza proporcionalmente',
                'aplicacion_practica': 'Trabajadores con jornadas reducidas (semanas cotizadas)',
                'referencia_normativa': 'Resolucion 000467 de 2025'
            },
            {
                'code': '52', 'name': '52 - Beneficiario Mecanismo Proteccion Cesante',
                'description': 'Persona que recibe beneficios del Mecanismo de Proteccion al Cesante',
                'aplicacion_practica': 'Desempleados con subsidio',
                'referencia_normativa': 'Ley 1636 de 2013'
            },
        ]

    @api.model
    def get_subtipos_cotizante_data(self):
        """Datos maestros de subtipos de cotizante segun PILA Colombia 2025"""
        return [
            {
                'code': '00', 'name': '00 - Sin subtipo',
                'description': 'Cotizante sin condicion especial',
                'aplicacion_practica': 'Trabajadores regulares sin condiciones especiales',
                'not_contribute_eps': False, 'not_contribute_pension': False
            },
            {
                'code': '01', 'name': '01 - Pensionado por vejez activo',
                'description': 'Persona que recibe pension de vejez y continua trabajando',
                'aplicacion_practica': 'Pensionados que siguen laborando. No aportan a pension',
                'referencia_normativa': 'Decreto 806 de 1998',
                'not_contribute_eps': False, 'not_contribute_pension': True
            },
            {
                'code': '02', 'name': '02 - Pensionado vejez exonerado',
                'description': 'Persona pensionada por vejez con exoneracion de aportes',
                'aplicacion_practica': 'Pensionados exonerados de aportar a pension',
                'not_contribute_eps': False, 'not_contribute_pension': True
            },
            {
                'code': '03', 'name': '03 - No obligado pension por edad',
                'description': 'Persona que por su edad no esta obligada a cotizar al sistema de pensiones',
                'aplicacion_practica': 'Adultos mayores que superan la edad maxima de cotizacion (H>=62, M>=57)',
                'referencia_normativa': 'Resolucion 000467 de 2025',
                'not_contribute_eps': False, 'not_contribute_pension': True
            },
            {
                'code': '04', 'name': '04 - Requisitos cumplidos pension',
                'description': 'Persona que ha cumplido los requisitos para pension, indemnizacion sustitutiva o devolucion de saldos',
                'aplicacion_practica': 'Personas en proceso de reconocimiento de pension',
                'referencia_normativa': 'Resolucion 000467 de 2025',
                'not_contribute_eps': False, 'not_contribute_pension': True
            },
            {
                'code': '05', 'name': '05 - Extranjero no obligado pension',
                'description': 'Extranjero no obligado a cotizar pension por convenio o normativa',
                'aplicacion_practica': 'Trabajadores extranjeros con exencion de pension',
                'not_contribute_eps': False, 'not_contribute_pension': True
            },
            {
                'code': '06', 'name': '06 - Venezolano PEP/PPT',
                'description': 'Venezolano con Permiso Especial de Permanencia o Permiso por Proteccion Temporal',
                'aplicacion_practica': 'Ciudadanos venezolanos regularizados en Colombia',
                'not_contribute_eps': False, 'not_contribute_pension': False
            },
            {
                'code': '07', 'name': '07 - Colombiano residente exterior',
                'description': 'Colombiano que reside en el exterior y cotiza voluntariamente',
                'aplicacion_practica': 'Colombianos en el exterior que mantienen cotizaciones',
                'not_contribute_eps': False, 'not_contribute_pension': False
            },
        ]

    @api.model
    def get_parametrizaciones_data(self):
        """Matriz de parametrizaciones por combinacion tipo+subtipo"""
        return [
            # DEPENDIENTE (01)
            {'tipo': '01', 'subtipo': '00', 'eps_emp': True, 'pension_emp': True, 'aux_transp': True, 'fsp': True,
             'eps_cia': True, 'pension_cia': True, 'arl': True, 'sena': True, 'icbf': True, 'ccf': True},
            {'tipo': '01', 'subtipo': '01', 'eps_emp': True, 'pension_emp': False, 'aux_transp': True, 'fsp': False,
             'eps_cia': True, 'pension_cia': False, 'arl': True, 'sena': True, 'icbf': True, 'ccf': True},
            {'tipo': '01', 'subtipo': '02', 'eps_emp': True, 'pension_emp': False, 'aux_transp': True, 'fsp': False,
             'eps_cia': True, 'pension_cia': False, 'arl': True, 'sena': True, 'icbf': True, 'ccf': True},
            {'tipo': '01', 'subtipo': '03', 'eps_emp': True, 'pension_emp': False, 'aux_transp': True, 'fsp': False,
             'eps_cia': True, 'pension_cia': False, 'arl': True, 'sena': True, 'icbf': True, 'ccf': True},
            {'tipo': '01', 'subtipo': '04', 'eps_emp': True, 'pension_emp': True, 'aux_transp': True, 'fsp': True,
             'eps_cia': True, 'pension_cia': True, 'arl': True, 'sena': True, 'icbf': True, 'ccf': True},
            {'tipo': '01', 'subtipo': '05', 'eps_emp': True, 'pension_emp': False, 'aux_transp': True, 'fsp': False,
             'eps_cia': True, 'pension_cia': False, 'arl': True, 'sena': True, 'icbf': True, 'ccf': True},
            {'tipo': '01', 'subtipo': '06', 'eps_emp': True, 'pension_emp': True, 'aux_transp': True, 'fsp': True,
             'eps_cia': True, 'pension_cia': True, 'arl': True, 'sena': True, 'icbf': True, 'ccf': True},
            {'tipo': '01', 'subtipo': '07', 'eps_emp': True, 'pension_emp': True, 'aux_transp': False, 'fsp': True,
             'eps_cia': True, 'pension_cia': True, 'arl': True, 'sena': True, 'icbf': True, 'ccf': True},
            # SERVICIO DOMESTICO (02)
            {'tipo': '02', 'subtipo': '00', 'eps_emp': True, 'pension_emp': True, 'aux_transp': True, 'fsp': True,
             'eps_cia': True, 'pension_cia': True, 'arl': True, 'sena': False, 'icbf': False, 'ccf': True},
            # INDEPENDIENTE (03)
            {'tipo': '03', 'subtipo': '00', 'eps_emp': True, 'pension_emp': True, 'aux_transp': False, 'fsp': True,
             'eps_cia': False, 'pension_cia': False, 'arl': True, 'sena': False, 'icbf': False, 'ccf': False},
            # APRENDIZ LECTIVA (12) - Solo ARL
            {'tipo': '12', 'subtipo': '00', 'eps_emp': False, 'pension_emp': False, 'aux_transp': False, 'fsp': False,
             'eps_cia': False, 'pension_cia': False, 'arl': True, 'sena': False, 'icbf': False, 'ccf': False},
            # APRENDIZ PRODUCTIVA (19) - EPS y ARL
            {'tipo': '19', 'subtipo': '00', 'eps_emp': False, 'pension_emp': False, 'aux_transp': False, 'fsp': False,
             'eps_cia': True, 'pension_cia': False, 'arl': True, 'sena': False, 'icbf': False, 'ccf': False},
            # ESTUDIANTE PRACTICA (20) - Solo ARL
            {'tipo': '20', 'subtipo': '00', 'eps_emp': False, 'pension_emp': False, 'aux_transp': False, 'fsp': False,
             'eps_cia': False, 'pension_cia': False, 'arl': True, 'sena': False, 'icbf': False, 'ccf': False},
            # INDEPENDIENTE CON CONTRATO (21)
            {'tipo': '21', 'subtipo': '00', 'eps_emp': True, 'pension_emp': True, 'aux_transp': False, 'fsp': True,
             'eps_cia': True, 'pension_cia': True, 'arl': True, 'sena': False, 'icbf': False, 'ccf': False},
            # PROFESOR (22)
            {'tipo': '22', 'subtipo': '00', 'eps_emp': True, 'pension_emp': True, 'aux_transp': False, 'fsp': False,
             'eps_cia': True, 'pension_cia': True, 'arl': True, 'sena': False, 'icbf': False, 'ccf': False},
            # TIEMPO PARCIAL (23)
            {'tipo': '23', 'subtipo': '00', 'eps_emp': True, 'pension_emp': True, 'aux_transp': True, 'fsp': True,
             'eps_cia': True, 'pension_cia': True, 'arl': True, 'sena': True, 'icbf': True, 'ccf': True},
            # MEDIO TIEMPO (51)
            {'tipo': '51', 'subtipo': '00', 'eps_emp': True, 'pension_emp': True, 'aux_transp': True, 'fsp': True,
             'eps_cia': True, 'pension_cia': True, 'arl': True, 'sena': True, 'icbf': True, 'ccf': True},
        ]

    @api.model
    def create_default_parameterization(self):
        """Crea todas las parametrizaciones de seguridad social"""
        TipoCotizante = self.env['hr.tipo.cotizante']
        SubtipoCotizante = self.env['hr.subtipo.cotizante']
        Parameterization = self.env['hr.parameterization.of.contributors']

        # Crear tipos
        tipos_creados = {}
        for tipo_data in self.get_tipos_cotizante_data():
            tipo = TipoCotizante.search([('code', '=', tipo_data['code'])], limit=1)
            if not tipo:
                tipo = TipoCotizante.create(tipo_data)
                _logger.info(f"Tipo cotizante creado: {tipo_data['code']}")
            else:
                tipo.write({k: v for k, v in tipo_data.items() if k != 'code'})
            tipos_creados[tipo_data['code']] = tipo

        # Crear subtipos
        subtipos_creados = {}
        for subtipo_data in self.get_subtipos_cotizante_data():
            subtipo = SubtipoCotizante.search([('code', '=', subtipo_data['code'])], limit=1)
            if not subtipo:
                subtipo = SubtipoCotizante.create(subtipo_data)
                _logger.info(f"Subtipo cotizante creado: {subtipo_data['code']}")
            else:
                subtipo.write({k: v for k, v in subtipo_data.items() if k != 'code'})
            subtipos_creados[subtipo_data['code']] = subtipo

        # Crear parametrizaciones
        created_count = 0
        updated_count = 0

        for param_data in self.get_parametrizaciones_data():
            tipo = tipos_creados.get(param_data['tipo'])
            subtipo = subtipos_creados.get(param_data['subtipo'])

            if not tipo or not subtipo:
                continue

            existing = Parameterization.search([
                ('type_of_contributor', '=', tipo.id),
                ('contributor_subtype', '=', subtipo.id)
            ], limit=1)

            vals = {
                'type_of_contributor': tipo.id,
                'contributor_subtype': subtipo.id,
                'liquidated_eps_employee': param_data['eps_emp'],
                'liquidate_employee_pension': param_data['pension_emp'],
                'liquidated_aux_transport': param_data['aux_transp'],
                'liquidates_solidarity_fund': param_data['fsp'],
                'liquidates_eps_company': param_data['eps_cia'],
                'liquidated_company_pension': param_data['pension_cia'],
                'liquidated_arl': param_data['arl'],
                'liquidated_sena': param_data['sena'],
                'liquidated_icbf': param_data['icbf'],
                'liquidated_compensation_fund': param_data['ccf'],
                'tarifa_especial_pension': 'normal',
                'tarifa_especial_salud': 'normal',
            }

            if existing:
                existing.write(vals)
                updated_count += 1
            else:
                Parameterization.create(vals)
                created_count += 1

        _logger.info(f"Parametrizaciones: {created_count} creadas, {updated_count} actualizadas")
        return {'created': created_count, 'updated': updated_count, 'tipos': len(tipos_creados), 'subtipos': len(subtipos_creados)}

    # =========================================================================
    # TIPOS DE HORAS EXTRAS - LEY 2466/2025
    # =========================================================================

    @api.model
    def get_overtime_periods_data(self):
        """
        Periodos de vigencia segun Ley 2466/2025 y gradualidad establecida.

        Cambios principales:
        - Jornada nocturna: 7pm-6am (antes 9pm-6am) desde 25/dic/2025
        - Recargo dom/fest: 75% -> 80% (dic 2025), 90% (jul 2026), 100% (jul 2027)
        - Horas extras dom/fest aumentan proporcionalmente

        Periodos:
        1. Antes del 25/dic/2025: Ley anterior (nocturna 9pm, dom/fest 75%)
        2. 25/dic/2025 - 30/jun/2026: Primera fase (nocturna 7pm, dom/fest 80%)
        3. 01/jul/2026 - 30/jun/2027: Segunda fase (dom/fest 90%)
        4. 01/jul/2027 en adelante: Tercera fase (dom/fest 100%)
        """
        from datetime import date

        return {
            # Periodo 1: Antes de Ley 2466 (historico)
            'periodo_1': {
                'valid_from': date(2000, 1, 1),
                'valid_to': date(2025, 12, 24),
                'legal_ref': 'CST Art. 160-168 (antes Ley 2466)',
                'night_start': 21.0,  # 9:00 PM
                'night_end': 6.0,
                'day_start': 6.0,
                'day_end': 21.0,  # 9:00 PM
                'percentages': {
                    'overtime_rn': 35.0,       # Recargo nocturno
                    'overtime_ext_d': 125.0,   # HE diurna
                    'overtime_ext_n': 175.0,   # HE nocturna
                    'overtime_rdf': 75.0,      # Recargo dom/fest
                    'overtime_dof': 175.0,     # Dominical/festivo (100+75)
                    'overtime_rndf': 110.0,    # Recargo noct dom/fest (35+75)
                    'overtime_eddf': 200.0,    # HE diurna dom/fest (100+25+75)
                    'overtime_endf': 250.0,    # HE nocturna dom/fest (100+75+75)
                }
            },
            # Periodo 2: Primera fase Ley 2466 (25/dic/2025 - 30/jun/2026)
            'periodo_2': {
                'valid_from': date(2025, 12, 25),
                'valid_to': date(2026, 6, 30),
                'legal_ref': 'Ley 2466/2025 Art. 10 (fase 1)',
                'night_start': 19.0,  # 7:00 PM
                'night_end': 6.0,
                'day_start': 6.0,
                'day_end': 19.0,  # 7:00 PM
                'percentages': {
                    'overtime_rn': 35.0,
                    'overtime_ext_d': 125.0,
                    'overtime_ext_n': 175.0,
                    'overtime_rdf': 80.0,      # Aumenta a 80%
                    'overtime_dof': 180.0,     # 100+80
                    'overtime_rndf': 115.0,    # 35+80
                    'overtime_eddf': 205.0,    # 100+25+80
                    'overtime_endf': 255.0,    # 100+75+80
                }
            },
            # Periodo 3: Segunda fase (01/jul/2026 - 30/jun/2027)
            'periodo_3': {
                'valid_from': date(2026, 7, 1),
                'valid_to': date(2027, 6, 30),
                'legal_ref': 'Ley 2466/2025 Art. 10 (fase 2)',
                'night_start': 19.0,
                'night_end': 6.0,
                'day_start': 6.0,
                'day_end': 19.0,
                'percentages': {
                    'overtime_rn': 35.0,
                    'overtime_ext_d': 125.0,
                    'overtime_ext_n': 175.0,
                    'overtime_rdf': 90.0,      # Aumenta a 90%
                    'overtime_dof': 190.0,     # 100+90
                    'overtime_rndf': 125.0,    # 35+90
                    'overtime_eddf': 215.0,    # 100+25+90
                    'overtime_endf': 265.0,    # 100+75+90
                }
            },
            # Periodo 4: Tercera fase (01/jul/2027 en adelante)
            'periodo_4': {
                'valid_from': date(2027, 7, 1),
                'valid_to': None,  # Sin limite
                'legal_ref': 'Ley 2466/2025 Art. 10 (fase final)',
                'night_start': 19.0,
                'night_end': 6.0,
                'day_start': 6.0,
                'day_end': 19.0,
                'percentages': {
                    'overtime_rn': 35.0,
                    'overtime_ext_d': 125.0,
                    'overtime_ext_n': 175.0,
                    'overtime_rdf': 100.0,     # Aumenta a 100%
                    'overtime_dof': 200.0,     # 100+100
                    'overtime_rndf': 135.0,    # 35+100
                    'overtime_eddf': 225.0,    # 100+25+100
                    'overtime_endf': 275.0,    # 100+75+100
                }
            },
        }

    @api.model
    def get_overtime_type_config(self):
        """
        Configuracion base de cada tipo de hora extra.
        """
        return {
            'overtime_rn': {
                'name_template': 'Recargo nocturno ({pct}%)',
                'rule_code': 'HEYREC005',
                'is_night': True,
                'weekdays': {'mon': True, 'tue': True, 'wed': True, 'thu': True, 'fri': True, 'sat': True, 'sun': False},
                'contains_holidays': False,
            },
            'overtime_ext_d': {
                'name_template': 'Hora extra diurna ({pct}%)',
                'rule_code': 'HEYREC001',
                'is_night': False,
                'weekdays': {'mon': True, 'tue': True, 'wed': True, 'thu': True, 'fri': True, 'sat': True, 'sun': False},
                'contains_holidays': False,
            },
            'overtime_ext_n': {
                'name_template': 'Hora extra nocturna ({pct}%)',
                'rule_code': 'HEYREC003',
                'is_night': True,
                'weekdays': {'mon': True, 'tue': True, 'wed': True, 'thu': True, 'fri': True, 'sat': True, 'sun': False},
                'contains_holidays': False,
            },
            'overtime_rdf': {
                'name_template': 'Recargo dom/fest ({pct}%)',
                'rule_code': 'HEYREC004',
                'is_night': False,
                'weekdays': {'mon': False, 'tue': False, 'wed': False, 'thu': False, 'fri': False, 'sat': False, 'sun': True},
                'contains_holidays': True,
            },
            'overtime_dof': {
                'name_template': 'Dominical o festivo ({pct}%)',
                'rule_code': 'HEYREC007',
                'is_night': False,
                'weekdays': {'mon': False, 'tue': False, 'wed': False, 'thu': False, 'fri': False, 'sat': False, 'sun': True},
                'contains_holidays': True,
            },
            'overtime_rndf': {
                'name_template': 'Recargo nocturno dom/fest ({pct}%)',
                'rule_code': 'HEYREC008',
                'is_night': True,
                'weekdays': {'mon': False, 'tue': False, 'wed': False, 'thu': False, 'fri': False, 'sat': False, 'sun': True},
                'contains_holidays': True,
            },
            'overtime_eddf': {
                'name_template': 'Hora extra diurna dom/fest ({pct}%)',
                'rule_code': 'HEYREC002',
                'is_night': False,
                'weekdays': {'mon': False, 'tue': False, 'wed': False, 'thu': False, 'fri': False, 'sat': False, 'sun': True},
                'contains_holidays': True,
            },
            'overtime_endf': {
                'name_template': 'Hora extra nocturna dom/fest ({pct}%)',
                'rule_code': 'HEYREC006',
                'is_night': True,
                'weekdays': {'mon': False, 'tue': False, 'wed': False, 'thu': False, 'fri': False, 'sat': False, 'sun': True},
                'contains_holidays': True,
            },
        }

    @api.model
    def create_default_overtime_types(self):
        """
        Crea los tipos de horas extras con rangos de fechas segun Ley 2466/2025.
        Genera registros para cada periodo de gradualidad.
        """
        TypeOvertime = self.env['hr.type.overtime']
        SalaryRule = self.env['hr.salary.rule']
        ConfigSettings = self.env['res.config.settings']

        created = 0
        updated = 0
        rules_created = []

        periods = self.get_overtime_periods_data()
        type_configs = self.get_overtime_type_config()

        # Primero crear las reglas salariales si no existen
        max_sequence = 43
        existing_heyrec = SalaryRule.search([('code', 'like', 'HEYREC%')], order='sequence desc', limit=1)
        if existing_heyrec:
            max_sequence = existing_heyrec.sequence

        salary_rules = {}
        for ot_type, config in type_configs.items():
            rule_code = config['rule_code']
            salary_rule = SalaryRule.search([('code', '=', rule_code)], limit=1)

            if not salary_rule:
                max_sequence += 1
                # Usar el nombre del periodo actual para la regla
                current_pct = periods['periodo_2']['percentages'].get(ot_type, 100)
                rule_name = config['name_template'].format(pct=int(current_pct))

                rule_props = ConfigSettings._get_rule_properties(
                    code=rule_code,
                    name=rule_name,
                    category_code='HEYREC',
                    sequence=max_sequence,
                    process_code='nomina',
                    is_recargo=True,
                    modality_value='diario'
                )
                if rule_props:
                    salary_rule = ConfigSettings._create_or_update_rule(rule_props)
                    if salary_rule:
                        rules_created.append(rule_code)
                        _logger.info(f"Regla HEYREC creada: {rule_code}")

            salary_rules[rule_code] = salary_rule

        # Crear registros de tipo de hora extra para cada periodo
        for period_key, period_data in periods.items():
            legal_ref = period_data['legal_ref']
            valid_from = period_data['valid_from']
            valid_to = period_data['valid_to']

            for ot_type, percentage in period_data['percentages'].items():
                config = type_configs.get(ot_type)
                if not config:
                    continue

                # Determinar horarios segun si es nocturno o diurno
                if config['is_night']:
                    start_time = period_data['night_start']
                    end_time = period_data['night_end']
                else:
                    start_time = period_data['day_start']
                    end_time = period_data['day_end']

                name = config['name_template'].format(pct=int(percentage))
                rule_code = config['rule_code']
                salary_rule = salary_rules.get(rule_code)

                # Buscar si ya existe este tipo para este rango de fechas
                existing = TypeOvertime.search([
                    ('type_overtime', '=', ot_type),
                    ('valid_from', '=', valid_from),
                ], limit=1)

                vals = {
                    'name': name,
                    'type_overtime': ot_type,
                    'percentage': percentage,
                    'valid_from': valid_from,
                    'valid_to': valid_to,
                    'start_time': start_time,
                    'end_time': end_time,
                    'start_time_two': 0.0,
                    'end_time_two': 0.0,
                    'legal_reference': legal_ref,
                    'contains_holidays': config['contains_holidays'],
                    **config['weekdays'],
                }

                if salary_rule:
                    vals['salary_rule'] = salary_rule.id

                if existing:
                    existing.write(vals)
                    updated += 1
                else:
                    TypeOvertime.create(vals)
                    created += 1

        _logger.info(f"Tipos horas extras: {created} creados, {updated} actualizados. "
                     f"Periodos: {len(periods)}. Reglas creadas: {len(rules_created)}")

        return {
            'created': created,
            'updated': updated,
            'periods': len(periods),
            'rules_created': rules_created
        }

    @api.model
    def get_overtime_types_data(self):
        """
        Retorna datos de tipos de horas extras en formato simple para configuracion.
        Usa el periodo actual (periodo_2: Ley 2466/2025 fase 1).
        """
        periods = self.get_overtime_periods_data()
        type_configs = self.get_overtime_type_config()

        # Usar periodo 2 (Ley 2466 fase 1) como base
        current_period = periods.get('periodo_2', periods.get('periodo_1'))

        result = []
        for ot_type, config in type_configs.items():
            percentage = current_period['percentages'].get(ot_type, 100)

            # Determinar horarios segun si es nocturno o diurno
            if config['is_night']:
                start_time = current_period['night_start']
                end_time = current_period['night_end']
            else:
                start_time = current_period['day_start']
                end_time = current_period['day_end']

            result.append({
                'rule_code': config['rule_code'],
                'type_overtime': ot_type,
                'name': config['name_template'].format(pct=int(percentage)),
                'percentage': percentage,
                'start_time': start_time,
                'end_time': end_time,
                'mon': config['weekdays'].get('mon', False),
                'tue': config['weekdays'].get('tue', False),
                'wed': config['weekdays'].get('wed', False),
                'thu': config['weekdays'].get('thu', False),
                'fri': config['weekdays'].get('fri', False),
                'sat': config['weekdays'].get('sat', False),
                'sun': config['weekdays'].get('sun', False),
                'contains_holidays': config['contains_holidays'],
            })

        return result

    # =========================================================================
    # ASIGNACION MASIVA
    # =========================================================================

    @api.model
    def assign_default_tipo_cotizante(self):
        """Asigna tipo Dependiente/00 a empleados sin configuracion"""
        TipoCotizante = self.env['hr.tipo.cotizante']
        SubtipoCotizante = self.env['hr.subtipo.cotizante']
        Employee = self.env['hr.employee']

        tipo_dependiente = TipoCotizante.search([('code', '=', '01')], limit=1)
        subtipo_ninguno = SubtipoCotizante.search([('code', '=', '00')], limit=1)

        if not tipo_dependiente or not subtipo_ninguno:
            return {'success': False, 'message': 'Primero debe crear la parametrizacion por defecto', 'count': 0}

        employees = Employee.search([
            ('active', '=', True),
            '|',
            ('tipo_coti_id', '=', False),
            ('subtipo_coti_id', '=', False)
        ])

        count = 0
        for emp in employees:
            emp.write({
                'tipo_coti_id': tipo_dependiente.id,
                'subtipo_coti_id': subtipo_ninguno.id
            })
            count += 1

        _logger.info(f"Asignado tipo/subtipo cotizante a {count} empleados")
        return {'success': True, 'count': count}
