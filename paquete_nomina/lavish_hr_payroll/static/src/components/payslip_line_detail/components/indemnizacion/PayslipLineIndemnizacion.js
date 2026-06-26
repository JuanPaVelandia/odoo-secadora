/** @odoo-module **/

import { Component, useState } from "@odoo/owl";

/**
 * PayslipLineIndemnizacion - Componente especializado para indemnizacion por despido
 *
 * Base legal: Art. 64 C.S.T.
 *
 * Tipos de contrato:
 * - Termino fijo: Dias restantes del contrato
 * - Termino indefinido:
 *   - Salario <= 10 SMMLV: 30 dias primer ano + 20 dias por ano adicional
 *   - Salario > 10 SMMLV: 20 dias primer ano + 15 dias por ano adicional
 */
export class PayslipLineIndemnizacion extends Component {
    static template = "lavish_hr_payroll.PayslipLineIndemnizacion";
    static props = {
        indemnizacionData: { type: Object },
        ruleConfig: { type: Object, optional: true },
        formatCurrency: { type: Function },
        formatValue: { type: Function },
    };

    setup() {
        this.state = useState({
            showDetalleCalculo: true,
            showTablaReferencia: false,
        });
    }

    get baseLegal() {
        return this.props.indemnizacionData?.base_legal || 'Art. 64 C.S.T.';
    }

    get tipoContrato() {
        const data = this.props.indemnizacionData || {};
        return data.tipo_contrato || data.contract_type || 'indefinido';
    }

    get tipoContratoLabel() {
        const tipos = {
            'fijo': 'Termino Fijo',
            'indefinido': 'Termino Indefinido',
            'obra_labor': 'Obra o Labor',
        };
        return tipos[this.tipoContrato] || this.tipoContrato;
    }

    get rangoSalarial() {
        const data = this.props.indemnizacionData || {};
        return data.rango_salarial || data.salary_range || 'normal';
    }

    get rangoSalarialLabel() {
        const rangos = {
            'normal': '<= 10 SMMLV',
            'alto': '> 10 SMMLV',
        };
        return rangos[this.rangoSalarial] || this.rangoSalarial;
    }

    get kpis() {
        const data = this.props.indemnizacionData || {};
        const kpis = [];

        // Tiempo de servicio
        if (data.anos_servicio !== undefined || data.years_service !== undefined) {
            const anos = data.anos_servicio || data.years_service;
            kpis.push({
                id: 'anos_servicio',
                label: 'Años de Servicio',
                value: Math.round(anos * 100) / 100,
                format: 'number',
                icon: 'fa-calendar',
                color: 'primary',
            });
        }

        // Dias de indemnizacion
        if (data.dias_indemnizacion !== undefined || data.days_indemnity !== undefined) {
            const dias = data.dias_indemnizacion || data.days_indemnity;
            kpis.push({
                id: 'dias_indem',
                label: 'Dias Indemnizacion',
                value: dias,
                format: 'number',
                icon: 'fa-hashtag',
                color: 'info',
            });
        }

        // Salario base
        if (data.salario_base !== undefined || data.base_salary !== undefined) {
            const salario = data.salario_base || data.base_salary;
            kpis.push({
                id: 'salario_base',
                label: 'Salario Base',
                value: salario,
                format: 'currency',
                icon: 'fa-money',
                color: 'secondary',
            });
        }

        // Valor diario
        if (data.valor_diario) {
            kpis.push({
                id: 'valor_diario',
                label: 'Valor Diario',
                value: data.valor_diario,
                format: 'currency',
                icon: 'fa-money',
                color: 'warning',
            });
        }

        // Total indemnizacion
        if (data.total !== undefined || data.total_value !== undefined) {
            const total = data.total || data.total_value;
            kpis.push({
                id: 'total',
                label: 'Total Indemnizacion',
                value: total,
                format: 'currency',
                icon: 'fa-calculator',
                color: 'danger',
                highlight: true,
            });
        }

        // Fechas
        if (data.fecha_inicio) {
            kpis.push({
                id: 'fecha_inicio',
                label: 'Fecha Ingreso',
                value: data.fecha_inicio,
                format: 'text',
                icon: 'fa-calendar-o',
                color: 'primary',
            });
        }
        if (data.fecha_liquidacion) {
            kpis.push({
                id: 'fecha_liquidacion',
                label: 'Fecha Liquidacion',
                value: data.fecha_liquidacion,
                format: 'text',
                icon: 'fa-calendar-check-o',
                color: 'danger',
            });
        }

        // KPIs adicionales del backend (evitar duplicados por coincidencia parcial de label)
        if (data.indicadores) {
            data.indicadores.forEach((ind, idx) => {
                const indLabel = (ind.label || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
                const isDuplicate = kpis.some(k => {
                    const kLabel = (k.label || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
                    return kLabel === indLabel || kLabel.startsWith(indLabel) || indLabel.startsWith(kLabel);
                });
                if (!isDuplicate) {
                    kpis.push({
                        id: `ind_${idx}`,
                        label: ind.label,
                        value: ind.value,
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
        const data = this.props.indemnizacionData || {};

        if (data.formula) {
            return data.formula;
        }

        // Formula segun tipo de contrato
        if (this.tipoContrato === 'fijo') {
            return 'Salario Diario x Dias Restantes del Contrato';
        }

        if (this.rangoSalarial === 'alto') {
            return '20 dias x 1er año + 15 dias x cada año adicional';
        }

        return '30 dias x 1er año + 20 dias x cada año adicional';
    }

    get pasos() {
        const data = this.props.indemnizacionData || {};
        if (data.pasos && Array.isArray(data.pasos)) {
            return data.pasos;
        }
        return [];
    }

    get hasPasos() {
        return this.pasos.length > 0;
    }

    get desglose() {
        const data = this.props.indemnizacionData || {};
        if (data.desglose && Array.isArray(data.desglose)) {
            return data.desglose;
        }
        return [];
    }

    get hasDesglose() {
        return this.desglose.length > 0;
    }

    get tablaReferencia() {
        return [
            {
                tipo: 'Termino Fijo',
                condicion: 'Cualquier salario',
                formula: 'Dias restantes del contrato',
            },
            {
                tipo: 'Indefinido',
                condicion: '<= 10 SMMLV',
                formula: '30 dias (1er año) + 20 dias (años adicionales)',
            },
            {
                tipo: 'Indefinido',
                condicion: '> 10 SMMLV',
                formula: '20 dias (1er año) + 15 dias (años adicionales)',
            },
            {
                tipo: 'Obra/Labor',
                condicion: 'Cualquier salario',
                formula: 'Tiempo restante de la obra',
            },
        ];
    }

    toggleDetalleCalculo() {
        this.state.showDetalleCalculo = !this.state.showDetalleCalculo;
    }

    toggleTablaReferencia() {
        this.state.showTablaReferencia = !this.state.showTablaReferencia;
    }

    formatPasoValue(paso) {
        if (paso.formato === 'currency' || paso.format === 'currency') {
            return this.props.formatCurrency(paso.valor || paso.value);
        }
        if (paso.formato === 'days' || paso.format === 'days') {
            return `${paso.valor || paso.value} dias`;
        }
        if (paso.formato === 'years' || paso.format === 'years') {
            return `${paso.valor || paso.value} años`;
        }
        if (paso.formato === 'percent' || paso.format === 'percent') {
            return `${paso.valor || paso.value}%`;
        }
        return paso.valor || paso.value;
    }

    getTipoContratoColor() {
        const colors = {
            'fijo': 'primary',
            'indefinido': 'success',
            'obra_labor': 'warning',
        };
        return colors[this.tipoContrato] || 'secondary';
    }

    getRangoColor() {
        return this.rangoSalarial === 'alto' ? 'danger' : 'info';
    }
}
