/** @odoo-module **/

import { STEP_COLORS } from "./config";

/**
 * Utilidades de formateo para PayslipLineDetail
 * 
 * Este módulo contiene funciones para formatear valores monetarios,
 * porcentajes, días, y traducir claves.
 */

/**
 * Formatea un valor según el formato especificado
 * @param {number|string} value - Valor a formatear
 * @param {string} formato - Tipo de formato ('currency', 'percent', 'decimal', 'integer', 'days', 'text')
 * @returns {string} Valor formateado o '-' si es inválido
 */
export function formatValue(value, formato = 'currency') {
    if (value === null || value === undefined || (typeof value === 'number' && isNaN(value))) {
        return '-';
    }

    switch (formato) {
        case 'currency':
            return formatCurrency(value);
        case 'percent':
        case 'percentage':
            return `${value}%`;
        case 'decimal':
            return new Intl.NumberFormat('es-CO', { maximumFractionDigits: 2 }).format(value);
        case 'integer':
        case 'entero':
            return new Intl.NumberFormat('es-CO', { maximumFractionDigits: 0 }).format(value);
        case 'days':
        case 'dias':
            return `${Math.round(value)} días`;
        case 'uvt':
            return `${value} UVT`;
        case 'text':
        default:
            return String(value);
    }
}

/**
 * Formatea un valor como moneda colombiana (COP)
 * @param {number} value - Valor a formatear
 * @returns {string} Valor formateado como moneda o '-' si es inválido
 */
export function formatCurrency(value) {
    if (value === null || value === undefined || (typeof value === 'number' && isNaN(value))) {
        return '-';
    }
    return new Intl.NumberFormat('es-CO', {
        style: 'currency',
        currency: 'COP',
        minimumFractionDigits: 0,
        maximumFractionDigits: 0,
    }).format(value);
}

/**
 * Traduce una clave de campo a español
 * @param {string} key - Clave a traducir
 * @returns {string} Traducción o clave formateada
 */
export function translateKey(key) {
    const translations = {
        'wage': 'Salario',
        'days': 'Dias',
        'rate': 'Tasa',
        'total': 'Total',
        'amount': 'Monto',
        'quantity': 'Cantidad',
        'salary': 'Salario',
        'basic': 'Basico',
        'base': 'Base',
        'effective_days': 'Dias Efectivos',
        'days_worked': 'Dias Trabajados',
        'worked_days': 'Dias Trabajados',
        'period_days': 'Dias del Periodo',
        'ibc': 'IBC',
        'ibd': 'IBD',
        'smmlv': 'SMMLV',
        'day_value': 'Valor Diario',
        'dias_trabajados': 'Dias Trabajados',
    };
    const lower = key.toLowerCase();
    return translations[lower] || key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
}

/**
 * Obtiene el color para un paso del timeline según su índice
 * @param {number} index - Índice del paso (0-based)
 * @returns {string} Color hexadecimal
 */
export function getStepColor(index) {
    return STEP_COLORS[index % STEP_COLORS.length];
}
