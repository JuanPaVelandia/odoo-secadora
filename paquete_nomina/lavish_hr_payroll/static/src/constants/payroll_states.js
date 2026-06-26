/** @odoo-module **/
/**
 * Constantes centralizadas para estados de nomina.
 * Elimina duplicacion de getStateColor/getStateBadge en componentes.
 */

/**
 * Estados de nomina (hr.payslip)
 */
export const PAYSLIP_STATES = {
    draft: {
        key: 'draft',
        color: '#9E9E9E',
        bgColor: '#EEEEEE',
        textColor: '#757575',
        label: 'Borrador',
        icon: 'fa-file-o',
        cssClass: 'payslip-state--draft',
    },
    verify: {
        key: 'verify',
        color: '#5C6BC0',
        bgColor: '#E8EAF6',
        textColor: '#3949AB',
        label: 'Verificar',
        icon: 'fa-check-circle',
        cssClass: 'payslip-state--verify',
    },
    done: {
        key: 'done',
        color: '#4CAF50',
        bgColor: '#E8F5E9',
        textColor: '#2E7D32',
        label: 'Hecho',
        icon: 'fa-check',
        cssClass: 'payslip-state--done',
    },
    paid: {
        key: 'paid',
        color: '#0288D1',
        bgColor: '#E1F5FE',
        textColor: '#0277BD',
        label: 'Pagado',
        icon: 'fa-money',
        cssClass: 'payslip-state--paid',
    },
    cancel: {
        key: 'cancel',
        color: '#E53935',
        bgColor: '#FFEBEE',
        textColor: '#C62828',
        label: 'Cancelado',
        icon: 'fa-times',
        cssClass: 'payslip-state--cancel',
    },
};

/**
 * Estados de ausencias (hr.leave)
 */
export const LEAVE_STATES = {
    draft: {
        key: 'draft',
        color: '#9E9E9E',
        bgColor: '#EEEEEE',
        label: 'Borrador',
        icon: 'fa-file-o',
    },
    confirm: {
        key: 'confirm',
        color: '#FF9800',
        bgColor: '#FFF3E0',
        label: 'Por Aprobar',
        icon: 'fa-clock-o',
    },
    validate1: {
        key: 'validate1',
        color: '#2196F3',
        bgColor: '#E3F2FD',
        label: 'Primera Aprobacion',
        icon: 'fa-check',
    },
    validate: {
        key: 'validate',
        color: '#4CAF50',
        bgColor: '#E8F5E9',
        label: 'Aprobado',
        icon: 'fa-check-circle',
    },
    refuse: {
        key: 'refuse',
        color: '#F44336',
        bgColor: '#FFEBEE',
        label: 'Rechazado',
        icon: 'fa-times',
    },
};

/**
 * Obtiene configuracion de estado de nomina.
 * @param {string} state - Codigo de estado
 * @returns {Object} Configuracion del estado
 */
export function getPayslipState(state) {
    return PAYSLIP_STATES[state] || PAYSLIP_STATES.draft;
}

/**
 * Obtiene color de borde para estado.
 * @param {string} state - Codigo de estado
 * @returns {string} Color hexadecimal
 */
export function getStateColor(state) {
    return getPayslipState(state).color;
}

/**
 * Obtiene configuracion de badge para estado.
 * @param {string} state - Codigo de estado
 * @returns {Object} { bg, color, text }
 */
export function getStateBadge(state) {
    const config = getPayslipState(state);
    return {
        bg: config.bgColor,
        color: config.textColor,
        text: config.label,
    };
}

/**
 * Obtiene configuracion de estado de ausencia.
 * @param {string} state - Codigo de estado
 * @returns {Object} Configuracion del estado
 */
export function getLeaveState(state) {
    return LEAVE_STATES[state] || LEAVE_STATES.draft;
}
