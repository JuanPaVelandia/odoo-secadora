/** @odoo-module **/

/**
 * Gestor de Pasos Expandibles
 * 
 * Maneja el estado de expansión/colapso de pasos en visualizaciones multi-paso.
 * 
 * Parámetros:
 * - totalPasos: Número total de pasos
 * - expandirPrimerPaso: Si expandir el primer paso por defecto
 * - expandirUltimoPaso: Si expandir el último paso por defecto
 */

/**
 * Inicializa estado de pasos expandidos
 * @param {number} totalPasos - Número total de pasos
 * @param {boolean} expandirPrimerPaso - Expandir primer paso
 * @param {boolean} expandirUltimoPaso - Expandir último paso
 * @returns {Object} Estado inicial de pasos expandidos
 */
export function initializeExpandedSteps(totalPasos, expandirPrimerPaso = true, expandirUltimoPaso = true) {
    const expanded = {};
    
    if (totalPasos === 0) {
        return expanded;
    }
    
    // Expandir primer paso
    if (expandirPrimerPaso) {
        expanded[1] = true;
    }
    
    // Expandir último paso
    if (expandirUltimoPaso && totalPasos > 1) {
        expanded[totalPasos] = true;
    }
    
    return expanded;
}

/**
 * Alterna estado de un paso
 * @param {Object} expandedSteps - Estado actual de pasos expandidos
 * @param {number} pasoNumero - Número del paso a alternar
 * @returns {Object} Nuevo estado de pasos expandidos
 */
export function toggleStep(expandedSteps, pasoNumero) {
    const newState = { ...expandedSteps };
    newState[pasoNumero] = !newState[pasoNumero];
    return newState;
}

/**
 * Expande todos los pasos
 * @param {number} totalPasos - Número total de pasos
 * @returns {Object} Estado con todos los pasos expandidos
 */
export function expandAllSteps(totalPasos) {
    const expanded = {};
    for (let i = 1; i <= totalPasos; i++) {
        expanded[i] = true;
    }
    return expanded;
}

/**
 * Colapsa todos los pasos
 * @returns {Object} Estado con todos los pasos colapsados
 */
export function collapseAllSteps() {
    return {};
}

/**
 * Verifica si un paso está expandido
 * @param {Object} expandedSteps - Estado actual de pasos expandidos
 * @param {number} pasoNumero - Número del paso a verificar
 * @returns {boolean} True si está expandido
 */
export function isStepExpanded(expandedSteps, pasoNumero) {
    return expandedSteps[pasoNumero] === true;
}

/**
 * Obtiene número de pasos expandidos
 * @param {Object} expandedSteps - Estado actual de pasos expandidos
 * @returns {number} Número de pasos expandidos
 */
export function getExpandedStepsCount(expandedSteps) {
    return Object.values(expandedSteps).filter(v => v === true).length;
}
