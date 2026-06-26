/** @odoo-module **/

/**
 * ═══════════════════════════════════════════════════════════════════════════
 * ÍNDICE DE TEMPLATES PARA REGLAS SALARIALES
 * ═══════════════════════════════════════════════════════════════════════════
 *
 * Este archivo exporta todos los componentes del sistema de templates.
 * Importar desde aquí para acceder a toda la funcionalidad.
 */

export {
    RuleTemplateRegistry,
    RULE_TEMPLATE_CONFIGS,
    RuleDataProcessors,
} from './rule_template_registry';

/**
 * ═══════════════════════════════════════════════════════════════════════════
 * CONFIGURACIÓN DE TEMPLATES DISPONIBLES
 * ═══════════════════════════════════════════════════════════════════════════
 *
 * Templates por tipo de regla:
 *
 * 1. RETENCIÓN EN LA FUENTE
 *    - RT_MET_01: Procedimiento 1 (Art. 385 E.T.)
 *    - RT_MET_02: Procedimiento 2 (Art. 386 E.T.)
 *    - RTEFTE*, RETEFUENTE*: Patrones alternativos
 *
 * 2. INGRESO BASE DE COTIZACIÓN
 *    - IBD: Ingreso Base Diario
 *    - IBC: Ingreso Base de Cotización
 *    - IBC_R: IBC para reportes
 *
 * 3. PRESTACIONES SOCIALES
 *    - PRIMA*, PRIMA_SERVICIOS: Prima de servicios
 *    - CESANTIAS*: Cesantías
 *    - INT_CES*, ICES*: Intereses sobre cesantías
 *    - VAC*, VACACIONES: Vacaciones
 *
 * 4. SEGURIDAD SOCIAL
 *    - SSOCIAL001: Aporte Salud Empleado
 *    - SSOCIAL002: Aporte Pensión Empleado
 *    - SSOCIAL003: Fondo de Solidaridad Pensional
 *    - SSOCIAL004: Fondo de Subsistencia (>20 SMMLV)
 *
 * 5. PROVISIONES
 *    - PROV_PRIMA: Provisión Prima
 *    - PROV_CESANTIAS: Provisión Cesantías
 *    - PROV_INT_CES: Provisión Int. Cesantías
 *    - PROV_VAC: Provisión Vacaciones
 */

export const TEMPLATE_CODES = {
    // Retención en la Fuente
    RETENCION_PROC1: ['RT_MET_01', 'RTEFTE', 'RETEFUENTE'],
    RETENCION_PROC2: ['RT_MET_02'],

    // IBC/IBD
    IBC: ['IBD', 'IBC', 'IBC_R'],

    // Prestaciones Sociales
    PRIMA: ['PRIMA', 'PRIMA_SERVICIOS', 'PRIMA_LEGAL'],
    CESANTIAS: ['CESANTIAS', 'CES', 'CESANTIA'],
    INT_CESANTIAS: ['INT_CESANTIAS', 'ICES', 'INT_CES', 'INTERESES_CESANTIAS'],
    VACACIONES: ['VAC', 'VACACIONES', 'VACACIONES_DIS'],

    // Seguridad Social
    SALUD: ['SSOCIAL001', 'SALUD_EMP', 'EPS_EMP'],
    PENSION: ['SSOCIAL002', 'PENSION_EMP', 'AFP_EMP'],
    SOLIDARIDAD: ['SSOCIAL003', 'FSP', 'SOLIDARIDAD'],
    SUBSISTENCIA: ['SSOCIAL004', 'FSP_SUB', 'SUBSISTENCIA'],

    // Provisiones
    PROV_PRIMA: ['PROV_PRIMA', 'PROVISION_PRIMA'],
    PROV_CESANTIAS: ['PROV_CESANTIAS', 'PROVISION_CESANTIAS', 'PROV_CES'],
    PROV_INT_CES: ['PROV_INT_CES', 'PROVISION_INT_CESANTIAS', 'PROV_ICES'],
    PROV_VAC: ['PROV_VAC', 'PROVISION_VACACIONES', 'PROV_VACACIONES'],
};

/**
 * Verifica si un código pertenece a un tipo de template
 * @param {string} code - Código de la regla
 * @param {string} templateType - Tipo de template (ej: 'RETENCION_PROC1')
 * @returns {boolean}
 */
export function isTemplateType(code, templateType) {
    const codes = TEMPLATE_CODES[templateType] || [];
    return codes.some(c => code === c || code.startsWith(c));
}

/**
 * Obtiene el tipo de template para un código
 * @param {string} code - Código de la regla
 * @returns {string|null} - Tipo de template o null
 */
export function getTemplateType(code) {
    for (const [type, codes] of Object.entries(TEMPLATE_CODES)) {
        if (codes.some(c => code === c || code.startsWith(c))) {
            return type;
        }
    }
    return null;
}
