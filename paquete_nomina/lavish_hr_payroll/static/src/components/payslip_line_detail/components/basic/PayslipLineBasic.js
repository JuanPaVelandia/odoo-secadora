/** @odoo-module **/

import { Component, useState } from "@odoo/owl";

/**
 * PayslipLineBasic - Componente para Salario Basico
 *
 * Codigos: BASIC, BASIC001, BASIC002, BASIC003, BASIC005
 * Base Legal: Art. 127 C.S.T.
 *
 * Modalidades:
 * - BASIC: Salario ordinario
 * - BASIC001: Salario integral (70%)
 * - BASIC002: Sostenimiento aprendiz
 * - BASIC003: Tiempo parcial
 * - BASIC005: Basico por dia (liquidacion)
 *
 * Props:
 * - basicData: Object - Datos del calculo de salario basico
 * - ruleConfig: Object - Configuracion visual
 * - formatCurrency: Function - Formatear moneda
 * - formatValue: Function - Formatear valores
 */
export class PayslipLineBasic extends Component {
    static template = "lavish_hr_payroll.PayslipLineBasic";
    static props = {
        basicData: { type: Object },
        ruleConfig: { type: Object, optional: true },
        formatCurrency: { type: Function },
        formatValue: { type: Function },
    };

    setup() {
        this.state = useState({
            showCambiosSalario: false,
            showDetalleCalculo: false,
        });
    }

    get data() {
        return this.props.basicData || {};
    }

    // KPIs principales
    get kpis() {
        const d = this.data;
        return [
            { id: 'salario_mensual', label: 'Salario Mensual', value: d.salario_mensual || 0, format: 'currency', icon: 'fa-money', color: 'primary' },
            { id: 'valor_diario', label: 'Valor Diario', value: d.valor_diario || 0, format: 'currency', icon: 'fa-calendar-o', color: 'info' },
            { id: 'dias', label: 'Dias', value: d.dias || 0, format: 'number', icon: 'fa-calendar', color: 'success' },
            { id: 'total', label: 'Total', value: d.total || 0, format: 'currency', icon: 'fa-check-circle', color: 'warning', highlight: true },
        ].filter(k => k.value > 0 || k.highlight);
    }

    // Modalidad del salario
    get modalidad() {
        const mod = this.data.modalidad || 'basico';
        const labels = {
            'basico': 'Salario Ordinario',
            'integral': 'Salario Integral (70%)',
            'sostenimiento': 'Sostenimiento Aprendiz',
            'parcial': 'Tiempo Parcial',
            'dia': 'Por Dia',
        };
        return labels[mod] || mod;
    }

    get modalidadColor() {
        const mod = this.data.modalidad || 'basico';
        const colors = {
            'basico': 'primary',
            'integral': 'warning',
            'sostenimiento': 'info',
            'parcial': 'secondary',
            'dia': 'success',
        };
        return colors[mod] || 'secondary';
    }

    // Tiene cambios de salario en el periodo?
    get hasCambiosSalario() {
        return this.data.cambios_salario && this.data.cambios_salario.length > 0;
    }

    get cambiosSalario() {
        return this.data.cambios_salario || [];
    }

    // Pasos del calculo
    get pasos() {
        return this.data.pasos || this.data.steps || [];
    }

    get hasPasos() {
        return this.pasos.length > 0;
    }

    // Formula
    get formula() {
        return this.data.formula || 'Salario / 30 x Dias';
    }

    // Base legal
    get baseLegal() {
        return this.data.base_legal || this.props.ruleConfig?.baseLegal || 'Art. 127 C.S.T.';
    }

    // Toggle secciones
    toggleCambiosSalario() {
        this.state.showCambiosSalario = !this.state.showCambiosSalario;
    }

    toggleDetalleCalculo() {
        this.state.showDetalleCalculo = !this.state.showDetalleCalculo;
    }

    // Formatear valor segun formato
    formatPasoValue(paso) {
        if (paso.format === 'currency' || paso.formato === 'currency') {
            return this.props.formatCurrency(paso.value || paso.valor);
        }
        return this.props.formatValue(paso.value || paso.valor, paso.format || paso.formato);
    }
}
