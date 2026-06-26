/** @odoo-module **/

/**
 * Índice de módulos helper para PayslipLineDetail
 * 
 * Este archivo exporta todos los helpers para facilitar su importación
 * en el componente principal.
 */

// Configuraciones estáticas
export {
    VISUALIZATION_TYPE_MAP,
    RULE_CONFIG,
    STEP_COLORS,
    getRuleConfig,
} from "./config";

// URLs legales
export { getLeyUrl } from "./legal_urls";

// Formateadores
export {
    formatValue,
    formatCurrency,
    translateKey,
    getStepColor,
} from "./formatters";

// Procesadores de datos
export {
    processContextualInfo,
    formatDate,
    BADGE_CONFIG,
    CONCEPT_LABELS,
    LOAN_TYPE_LABELS,
    processSimpleKpis,
    processSimpleFormula,
    KPI_CONFIG,
    processSocialSecurityResumen,
    calcularPorcentajeSubsistencia,
    SS_PORCENTAJES,
    SS_CONDICIONES,
    SUBSISTENCIA_ESCALA,
} from "./data_processors";

// Parsers de computation
export {
    parseProvisionComputation,
    detectProvisionType,
    normalizeFormulaPasos,
    PROVISION_TYPES,
    parseMultiPasoComputation,
    normalizeStep,
    generateTimeline,
    parseFormulaComputation,
    normalizeTablaRangos,
    normalizeColumnas,
} from "./computation";

// Helpers de pasos
export {
    initializeExpandedSteps,
    toggleStep,
    expandAllSteps,
    collapseAllSteps,
    isStepExpanded,
    getExpandedStepsCount,
    getNextStep,
    getPreviousStep,
    navigateToStep,
    navigateToNextStep,
    navigateToPreviousStep,
} from "./steps";
