/** @odoo-module **/

/**
 * Índice de Helpers de Pasos
 * 
 * Exporta todas las funciones de gestión de pasos:
 * - step_manager: Gestión de estado de pasos expandibles
 * - navigation: Navegación entre pasos
 */

// Step Manager
export {
    initializeExpandedSteps,
    toggleStep,
    expandAllSteps,
    collapseAllSteps,
    isStepExpanded,
    getExpandedStepsCount,
} from "./step_manager";

// Navigation
export {
    getNextStep,
    getPreviousStep,
    navigateToStep,
    navigateToNextStep,
    navigateToPreviousStep,
} from "./navigation";
