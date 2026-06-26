/** @odoo-module **/

/**
 * Índice de Procesadores de Datos
 * 
 * Exporta todos los procesadores de datos organizados por categoría:
 * - contextual: Información contextual (préstamos, novedades, ausencias)
 * - simple: KPIs y fórmulas simples
 * - social_security: Resumen de seguridad social
 */

// Contextual
export {
    processContextualInfo,
    formatDate,
    BADGE_CONFIG,
    CONCEPT_LABELS,
    LOAN_TYPE_LABELS,
} from "./contextual";

// Simple
export {
    processSimpleKpis,
    processSimpleFormula,
    KPI_CONFIG,
} from "./simple";

// Social Security
export {
    processSocialSecurityResumen,
    calcularPorcentajeSubsistencia,
    SS_PORCENTAJES,
    SS_CONDICIONES,
    SUBSISTENCIA_ESCALA,
} from "./social_security";
