/** @odoo-module **/

/**
 * Navegación entre Pasos
 * 
 * Funciones para navegar entre pasos en visualizaciones multi-paso.
 * 
 * Parámetros:
 * - pasoActual: Número del paso actual
 * - totalPasos: Número total de pasos
 * - expandedSteps: Estado de pasos expandidos
 */

/**
 * Obtiene el número del siguiente paso
 * @param {number} pasoActual - Paso actual
 * @param {number} totalPasos - Total de pasos
 * @returns {number|null} Número del siguiente paso o null si no hay
 */
export function getNextStep(pasoActual, totalPasos) {
    if (pasoActual >= totalPasos) {
        return null;
    }
    return pasoActual + 1;
}

/**
 * Obtiene el número del paso anterior
 * @param {number} pasoActual - Paso actual
 * @returns {number|null} Número del paso anterior o null si no hay
 */
export function getPreviousStep(pasoActual) {
    if (pasoActual <= 1) {
        return null;
    }
    return pasoActual - 1;
}

/**
 * Expande y hace scroll a un paso específico
 * @param {number} pasoNumero - Número del paso
 * @param {Object} expandedSteps - Estado actual de pasos expandidos
 * @param {Function} toggleStep - Función para alternar paso
 * @param {Function} scrollToStep - Función para hacer scroll al paso
 * @returns {Object} Nuevo estado de pasos expandidos
 */
export function navigateToStep(pasoNumero, expandedSteps, toggleStep, scrollToStep) {
    // Expandir el paso si no está expandido
    let newState = expandedSteps;
    if (!expandedSteps[pasoNumero]) {
        newState = toggleStep(expandedSteps, pasoNumero);
    }
    
    // Hacer scroll al paso
    if (scrollToStep) {
        scrollToStep(pasoNumero);
    }
    
    return newState;
}

/**
 * Expande y navega al siguiente paso
 * @param {number} pasoActual - Paso actual
 * @param {number} totalPasos - Total de pasos
 * @param {Object} expandedSteps - Estado actual de pasos expandidos
 * @param {Function} toggleStep - Función para alternar paso
 * @param {Function} scrollToStep - Función para hacer scroll al paso
 * @returns {Object|null} Nuevo estado de pasos expandidos o null si no hay siguiente
 */
export function navigateToNextStep(pasoActual, totalPasos, expandedSteps, toggleStep, scrollToStep) {
    const siguiente = getNextStep(pasoActual, totalPasos);
    if (!siguiente) {
        return null;
    }
    return navigateToStep(siguiente, expandedSteps, toggleStep, scrollToStep);
}

/**
 * Expande y navega al paso anterior
 * @param {number} pasoActual - Paso actual
 * @param {Object} expandedSteps - Estado actual de pasos expandidos
 * @param {Function} toggleStep - Función para alternar paso
 * @param {Function} scrollToStep - Función para hacer scroll al paso
 * @returns {Object|null} Nuevo estado de pasos expandidos o null si no hay anterior
 */
export function navigateToPreviousStep(pasoActual, expandedSteps, toggleStep, scrollToStep) {
    const anterior = getPreviousStep(pasoActual);
    if (!anterior) {
        return null;
    }
    return navigateToStep(anterior, expandedSteps, toggleStep, scrollToStep);
}
