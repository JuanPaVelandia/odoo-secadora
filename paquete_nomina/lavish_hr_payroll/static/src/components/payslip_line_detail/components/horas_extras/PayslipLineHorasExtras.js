/** @odoo-module **/

import { Component, useState } from "@odoo/owl";

/**
 * PayslipLineHorasExtras - Componente especializado para horas extras y recargos
 *
 * Tipos de horas extras en Colombia (CST Art. 159-168):
 * - HE_ED: Hora Extra Diurna (+25%)
 * - HE_EN: Hora Extra Nocturna (+75%)
 * - HE_RN: Recargo Nocturno (+35%)
 * - HE_EFES: Hora Extra Festivo Diurna (+100%)
 * - HE_NFES: Hora Extra Festivo Nocturna (+150%)
 * - RN_FES: Recargo Nocturno Festivo (+110%)
 * - HEYREC: Consolidado de horas y recargos
 */
export class PayslipLineHorasExtras extends Component {
    static template = "lavish_hr_payroll.PayslipLineHorasExtras";
    static props = {
        horasData: { type: Object },
        ruleConfig: { type: Object, optional: true },
        formatCurrency: { type: Function },
        formatValue: { type: Function },
    };

    setup() {
        this.state = useState({
            showDesglose: true,
            showDetalleDias: false,
        });
    }

    // Configuracion de tipos de horas extras
    get tiposHorasConfig() {
        return {
            'HE_ED': { label: 'Hora Extra Diurna', porcentaje: 25, color: 'primary', icon: 'fa-sun-o' },
            'HE_EN': { label: 'Hora Extra Nocturna', porcentaje: 75, color: 'info', icon: 'fa-moon-o' },
            'RN': { label: 'Recargo Nocturno', porcentaje: 35, color: 'secondary', icon: 'fa-adjust' },
            'HE_EFES': { label: 'Hora Extra Festivo Diurna', porcentaje: 100, color: 'warning', icon: 'fa-star' },
            'HE_NFES': { label: 'Hora Extra Festivo Nocturna', porcentaje: 150, color: 'danger', icon: 'fa-star-half-o' },
            'RN_FES': { label: 'Recargo Nocturno Festivo', porcentaje: 110, color: 'dark', icon: 'fa-moon-o' },
            'RD_FES': { label: 'Recargo Diurno Festivo', porcentaje: 75, color: 'success', icon: 'fa-sun-o' },
        };
    }

    get baseLegal() {
        return this.props.horasData?.base_legal || 'Art. 159-168 C.S.T.';
    }

    get kpis() {
        const data = this.props.horasData || {};
        const kpis = [];

        // Valor hora base
        if (data.valor_hora_base !== undefined) {
            kpis.push({
                id: 'valor_hora',
                label: 'Valor Hora Base',
                value: data.valor_hora_base,
                format: 'currency',
                icon: 'fa-clock-o',
                color: 'primary',
            });
        }

        // Total horas
        if (data.total_horas !== undefined) {
            kpis.push({
                id: 'total_horas',
                label: 'Total Horas',
                value: data.total_horas,
                format: 'number',
                icon: 'fa-hourglass-half',
                color: 'info',
            });
        }

        // Total valor
        if (data.total_valor !== undefined) {
            kpis.push({
                id: 'total_valor',
                label: 'Total Horas Extras',
                value: data.total_valor,
                format: 'currency',
                icon: 'fa-money',
                color: 'success',
                highlight: true,
            });
        }

        // KPIs adicionales del backend
        if (data.indicadores) {
            data.indicadores.forEach((ind, idx) => {
                if (!kpis.find(k => k.label === ind.label)) {
                    kpis.push({
                        id: `ind_${idx}`,
                        label: ind.label,
                        value: ind.valor,
                        format: ind.formato || 'currency',
                        icon: ind.icono || 'fa-info-circle',
                        color: ind.color || 'secondary',
                        highlight: ind.destacado || false,
                    });
                }
            });
        }

        return kpis;
    }

    get formula() {
        return this.props.horasData?.formula || 'Valor Hora Base x Horas x (1 + Recargo%)';
    }

    get desglose() {
        const data = this.props.horasData || {};
        const desglose = [];

        // Si viene desglose desde el backend
        if (data.desglose && Array.isArray(data.desglose)) {
            return data.desglose.map(item => ({
                ...item,
                config: this.tiposHorasConfig[item.tipo] || {
                    label: item.nombre || item.tipo,
                    color: 'secondary',
                    icon: 'fa-clock-o'
                },
            }));
        }

        // Si vienen tipos individuales
        if (data.tipos) {
            Object.entries(data.tipos).forEach(([tipo, valores]) => {
                const config = this.tiposHorasConfig[tipo];
                if (config && valores.horas > 0) {
                    desglose.push({
                        tipo,
                        nombre: config.label,
                        horas: valores.horas,
                        porcentaje: config.porcentaje,
                        valor_hora: valores.valor_hora || data.valor_hora_base,
                        subtotal: valores.subtotal,
                        config,
                    });
                }
            });
        }

        return desglose;
    }

    get hasDesglose() {
        return this.desglose.length > 0;
    }

    get detalleDias() {
        return this.props.horasData?.detalle_dias || [];
    }

    get hasDetalleDias() {
        return this.detalleDias.length > 0;
    }

    get pasos() {
        const data = this.props.horasData || {};
        if (data.pasos && Array.isArray(data.pasos)) {
            return data.pasos;
        }
        return [];
    }

    get hasPasos() {
        return this.pasos.length > 0;
    }

    toggleDesglose() {
        this.state.showDesglose = !this.state.showDesglose;
    }

    toggleDetalleDias() {
        this.state.showDetalleDias = !this.state.showDetalleDias;
    }

    formatPasoValue(paso) {
        if (paso.formato === 'currency' || paso.format === 'currency') {
            return this.props.formatCurrency(paso.valor || paso.value);
        }
        if (paso.formato === 'percent' || paso.format === 'percent') {
            return `${paso.valor || paso.value}%`;
        }
        if (paso.formato === 'hours' || paso.format === 'hours') {
            return `${paso.valor || paso.value} hrs`;
        }
        return paso.valor || paso.value;
    }

    calcularSubtotal(item) {
        if (item.subtotal !== undefined) {
            return item.subtotal;
        }
        const valorHora = item.valor_hora || this.props.horasData?.valor_hora_base || 0;
        const factor = 1 + (item.porcentaje / 100);
        return valorHora * item.horas * factor;
    }
}
