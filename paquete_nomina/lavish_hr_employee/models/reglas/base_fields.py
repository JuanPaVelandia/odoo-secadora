# -*- coding: utf-8 -*-

"""
BASE FIELDS - DOCUMENTACIÓN DE MIXINS
======================================

Este archivo centraliza la documentación de todos los mixins de reglas salariales.

NOTA: Los mixins se cargan automáticamente por Odoo usando _inherit,
NO es necesario importarlos explícitamente.

Uso en hr_rule_adapted.py:
    class HrSalaryRuleAdapted(models.Model):
        _name = 'hr.salary.rule'
        _inherit = [
            'hr.salary.rule',
            'mail.thread',
            'mail.activity.mixin',
            'hr.salary.rule.basic',      # <- Odoo carga automáticamente
            'hr.salary.rule.aux',         # <- por su _name
            # ... etc
        ]
"""


# ══════════════════════════════════════════════════════════════════════════
# DOCUMENTACIÓN DE MIXINS
# ══════════════════════════════════════════════════════════════════════════

MIXINS_INFO = {
    'hr.salary.rule.basic': {
        'clase': 'HrSalaryRuleBasic',
        'archivo': 'basic.py',
        'descripcion': 'Cálculo de salario básico y variantes',
        'metodos_principales': [
            '_calculate_salary_generic',
            '_basic',
            '_basic002',
            '_basic003',
            '_basic004',
            '_basic005',
        ]
    },
    'hr.salary.rule.aux': {
        'clase': 'HrSalaryRuleAux',
        'archivo': 'auxilios.py',
        'descripcion': 'Auxilios de transporte y conectividad',
        'metodos_principales': [
            '_calculate_auxilio_generic',
            '_calculate_devolucion_generic',
            '_aux000',
            '_aux00c',
            '_dev_aux000',
            '_dev_aux00c',
        ]
    },
    'hr.salary.rule.ibd.sss': {
        'clase': 'HrSalaryRuleIbdSss',
        'archivo': 'ibd_sss.py',
        'descripcion': 'IBD (Ingreso Base de Cotizacion)',
        'metodos_principales': [
            '_ibd',
            '_get_ibd_data_from_rules',
            '_obtener_ibc_diario_previo',
            '_get_ibd_legal_explanation',
        ]
    },
    'hr.salary.rule.ss': {
        'clase': 'HrSalaryRuleSS',
        'archivo': 'seguridad_social.py',
        'descripcion': 'Seguridad Social (Salud, Pension, FSP, Subsistencia)',
        'metodos_principales': [
            '_calculate_ss_generic',  # Metodo generico con hooks
            '_ssocial001',  # Salud
            '_ssocial002',  # Pension
            '_ssocial003',  # Fondo Solidaridad
            '_ssocial004',  # Fondo Subsistencia
        ],
        'hooks': [
            'SSHooks.check_contribution',
            'SSHooks.is_apprentice',
            'SSHooks.is_pensioner',
            'SSHooks.should_skip_by_cobro',
            'SSHooks.should_project_funds',
            'SSParamsBuilder',  # Builder para parametros comunes
        ]
    },
    'hr.salary.rule.prestaciones': {
        'clase': 'HrSalaryRulePrestaciones',
        'archivo': 'prestaciones_sociales.py',
        'descripcion': 'Prestaciones sociales y provisiones',
        'metodos_principales': [
            '_compute_social_benefits',
            '_prima',
            '_cesantias',
            '_intcesantias',
            '_vaccontrato',
            '_calculate_prestacion_generic',
            '_calculate_provision',
            '_compute_prestaciones_counts',
        ]
    },
    'hr.salary.rule.retenciones': {
        'clase': 'HrSalaryRuleRetenciones',
        'archivo': 'retenciones.py',
        'descripcion': 'Retenciones en la fuente',
        'metodos_principales': [
            '_calculate_retention_generic',
            '_rtf_prima',
        ]
    },
    'hr.salary.rule.indem': {
        'clase': 'HrSalaryRuleIndemnizacion',
        'archivo': 'indemnizacion.py',
        'descripcion': 'Indemnización por terminación de contrato',
        'metodos_principales': [
            '_indem',
        ]
    },
    'hr.salary.rule.horas.extras': {
        'clase': 'HrSalaryRuleHorasExtras',
        'archivo': 'horas_extras.py',
        'descripcion': 'Horas extras y recargos',
        'metodos_principales': [
            '_compute_overtime_generic',
            '_compute_overtime_with_log',
            '_heyrec001',  # Extra diurna
            '_heyrec002',  # Extra nocturna
            '_heyrec003',  # Recargo nocturno
            '_heyrec004',  # Extra festiva diurna
            '_heyrec005',  # Extra festiva nocturna
            '_heyrec006',  # Recargo festivo diurno
            '_heyrec007',  # Recargo festivo nocturno
            '_heyrec008',  # Extra festiva ordinaria
        ]
    },
    'hr.salary.rule.otros': {
        'clase': 'HrSalaryRuleOtros',
        'archivo': 'otros.py',
        'descripcion': 'Métodos auxiliares y totales',
        'metodos_principales': [
            '_get_employee_partner_id',
        ]
    },
}


# ══════════════════════════════════════════════════════════════════════════
# MÉTODOS COMUNES (permanecen en hr_rule_adapted.py)
# ══════════════════════════════════════════════════════════════════════════

COMMON_METHODS_INFO = {
    '_get_totalizar_reglas': {
        'linea': 347,
        'descripcion': 'Totaliza reglas de nómina por códigos',
        'usado_por': ['ibd_sss', 'prestaciones_sociales', 'aux'],
    },
    '_get_totalizar_categorias': {
        'linea': 408,
        'descripcion': 'Totaliza categorías de nómina con filtros',
        'usado_por': ['prestaciones_sociales', 'ibd_sss', 'retenciones'],
    },
    '_get_periodo': {
        'linea': 1491,
        'descripcion': 'Genera etiquetas de periodo (ej: "Primera Q1 01-25")',
        'usado_por': ['prestaciones_sociales', 'ibd_sss'],
    },
}


# ══════════════════════════════════════════════════════════════════════════
# CAMPOS (permanecen en hr_rule_adapted.py)
# ══════════════════════════════════════════════════════════════════════════

FIELDS_INFO = {
    'ubicacion': 'hr_rule_adapted.py líneas 131-239',
    'total_campos': 58,
    'categorias': {
        'proyeccion': ['proyectar_nom', 'proyectar_ret'],
        'configuracion': ['types_employee', 'dev_or_ded', 'type_concepts', 'aplicar_cobro', 'modality_value'],
        'prestaciones': ['base_prima', 'base_cesantias', 'base_vacaciones', 'base_intereses_cesantias'],
        'seguridad_social': ['base_seguridad_social', 'base_arl', 'base_parafiscales'],
        'retenciones': ['excluir_ret', 'is_projectable_rtf'],
        'contadores': ['prima_rules_count', 'cesantias_rules_count', 'vacaciones_rules_count'],
    }
}
