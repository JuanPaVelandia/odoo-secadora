/** @odoo-module **/

/**
 * Índice de Parsers de Computation
 * 
 * Exporta todos los parsers de computation organizados por tipo:
 * - provision_parser: Parsea datos de provisiones
 * - multi_paso_parser: Parsea datos multi-paso
 * - formula_parser: Parsea datos de fórmulas
 */

// Provision Parser
export {
    parseProvisionComputation,
    detectProvisionType,
    normalizeFormulaPasos,
    PROVISION_TYPES,
} from "./provision_parser";

// Multi-Paso Parser
export {
    parseMultiPasoComputation,
    normalizeStep,
    generateTimeline,
} from "./multi_paso_parser";

// Formula Parser
export {
    parseFormulaComputation,
    normalizeTablaRangos,
    normalizeColumnas,
} from "./formula_parser";
