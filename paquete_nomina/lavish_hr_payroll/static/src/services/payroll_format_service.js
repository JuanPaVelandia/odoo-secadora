/** @odoo-module **/
/**
 * Servicio centralizado de formateo para nomina.
 * Elimina duplicacion de funciones formatCurrency/formatNumber en componentes.
 *
 * Uso:
 *   import { useService } from "@web/core/utils/hooks";
 *   const format = useService("payroll_format");
 *   format.currency(1500000);  // "$1.500.000"
 *   format.number(3.5, 1);     // "3,5"
 */

import { registry } from "@web/core/registry";

export const payrollFormatService = {
    dependencies: [],

    start(env) {
        const locale = 'es-CO';
        const defaultCurrency = 'COP';

        return {
            /**
             * Formatea un valor como moneda colombiana.
             * @param {number} value - Valor a formatear
             * @param {Object} options - Opciones de formateo
             * @param {string} options.currency - Codigo de moneda (default: COP)
             * @param {number} options.minDigits - Digitos decimales minimos (default: 0)
             * @param {number} options.maxDigits - Digitos decimales maximos (default: 0)
             * @returns {string} Valor formateado
             */
            currency(value, options = {}) {
                const {
                    currency = defaultCurrency,
                    minDigits = 0,
                    maxDigits = 0,
                } = options;

                return new Intl.NumberFormat(locale, {
                    style: 'currency',
                    currency: currency,
                    minimumFractionDigits: minDigits,
                    maximumFractionDigits: maxDigits,
                }).format(value || 0);
            },

            /**
             * Formatea un numero con separadores de miles.
             * @param {number} value - Valor a formatear
             * @param {number} maxFractionDigits - Digitos decimales maximos (default: 2)
             * @returns {string} Valor formateado
             */
            number(value, maxFractionDigits = 2) {
                return new Intl.NumberFormat(locale, {
                    minimumFractionDigits: 0,
                    maximumFractionDigits: maxFractionDigits,
                }).format(value || 0);
            },

            /**
             * Formatea un valor como porcentaje.
             * @param {number} value - Valor decimal (0.15 = 15%)
             * @param {number} decimals - Digitos decimales (default: 1)
             * @returns {string} Valor formateado con simbolo %
             */
            percentage(value, decimals = 1) {
                const formatted = new Intl.NumberFormat(locale, {
                    minimumFractionDigits: 0,
                    maximumFractionDigits: decimals,
                }).format((value || 0) * 100);
                return `${formatted}%`;
            },

            /**
             * Formatea un numero compacto (1.5M, 2.3K).
             * @param {number} value - Valor a formatear
             * @returns {string} Valor compacto
             */
            compact(value) {
                if (!value) return '0';

                const abs = Math.abs(value);
                if (abs >= 1e9) {
                    return `${this.number(value / 1e9, 1)}B`;
                } else if (abs >= 1e6) {
                    return `${this.number(value / 1e6, 1)}M`;
                } else if (abs >= 1e3) {
                    return `${this.number(value / 1e3, 1)}K`;
                }
                return this.number(value, 0);
            },

            /**
             * Formatea horas (ej: 8.5 -> "8,5 h").
             * @param {number} value - Horas
             * @param {number} decimals - Decimales (default: 1)
             * @returns {string} Horas formateadas
             */
            hours(value, decimals = 1) {
                return `${this.number(value, decimals)} h`;
            },

            /**
             * Formatea dias (ej: 15 -> "15 dias").
             * @param {number} value - Dias
             * @param {number} decimals - Decimales (default: 0)
             * @returns {string} Dias formateados
             */
            days(value, decimals = 0) {
                const formatted = this.number(value, decimals);
                const label = Math.abs(value) === 1 ? 'dia' : 'dias';
                return `${formatted} ${label}`;
            },
        };
    },
};

registry.category("services").add("payroll_format", payrollFormatService);
