/** @odoo-module **/

import { Component, useState } from "@odoo/owl";

/**
 * PayslipLineSSocial - Componente para Seguridad Social
 *
 * Codigos: SSOCIAL001, SSOCIAL002, SSOCIAL003, SSOCIAL004
 * Base Legal: Ley 100/1993, Ley 797/2003
 *
 * Tipos:
 * - SSOCIAL001: Salud (4% empleado)
 * - SSOCIAL002: Pension (4% empleado)
 * - SSOCIAL003: Fondo Solidaridad Pensional (0.5-2%)
 * - SSOCIAL004: Fondo Subsistencia (0.2-1.5%)
 *
 * Props:
 * - ssocialData: Object - Datos del calculo SS
 * - ruleConfig: Object - Configuracion visual
 * - formatCurrency: Function - Formatear moneda
 * - formatValue: Function - Formatear valores
 */
export class PayslipLineSSocial extends Component {
    static template = "lavish_hr_payroll.PayslipLineSSocial";
    static props = {
        ssocialData: { type: Object },
        ruleConfig: { type: Object, optional: true },
        formatCurrency: { type: Function },
        formatValue: { type: Function },
    };

    setup() {
        this.state = useState({
            showTablaRangos: false,
            showDistribucion: true,
        });
    }

    get data() {
        return this.props.ssocialData || {};
    }

    // Tipo de aporte
    get tipoAporte() {
        const tipo = this.data.tipo || 'salud';
        const labels = {
            'salud': 'Aporte Salud',
            'pension': 'Aporte Pension',
            'solidaridad': 'Fondo Solidaridad Pensional',
            'subsistencia': 'Fondo Subsistencia',
        };
        return labels[tipo] || tipo;
    }

    get tipoIcon() {
        const tipo = this.data.tipo || 'salud';
        const icons = {
            'salud': 'fa-heartbeat',
            'pension': 'fa-shield',
            'solidaridad': 'fa-university',
            'subsistencia': 'fa-users',
        };
        return icons[tipo] || 'fa-shield';
    }

    get tipoColor() {
        const tipo = this.data.tipo || 'salud';
        const colors = {
            'salud': 'danger',
            'pension': 'primary',
            'solidaridad': 'purple',
            'subsistencia': 'teal',
        };
        return colors[tipo] || 'secondary';
    }

    // Porcentajes
    get porcentajeEmpleado() {
        return this.data.porcentaje_empleado || this.data.porcentaje || 0;
    }

    get porcentajeEmpleador() {
        return this.data.porcentaje_empleador || 0;
    }

    get porcentajeTotal() {
        return this.porcentajeEmpleado + this.porcentajeEmpleador;
    }

    // Es variable (FSP o Subsistencia)?
    get esVariable() {
        const tipo = this.data.tipo;
        return tipo === 'solidaridad' || tipo === 'subsistencia';
    }

    // KPIs
    get kpis() {
        const d = this.data;
        return [
            { id: 'ibc', label: 'Base IBC', value: d.ibc || d.base || 0, format: 'currency', icon: 'fa-building', color: 'info' },
            { id: 'porcentaje', label: 'Tasa', value: this.porcentajeEmpleado, format: 'percent', icon: 'fa-percent', color: this.tipoColor },
            { id: 'total', label: 'Aporte', value: d.total || 0, format: 'currency', icon: 'fa-check-circle', color: this.tipoColor, highlight: true },
        ].filter(k => k.value !== 0 || k.highlight);
    }

    // Distribucion empleado/empleador
    get distribucion() {
        const d = this.data;
        if (!this.porcentajeEmpleador) return null;

        return {
            empleado: {
                porcentaje: this.porcentajeEmpleado,
                valor: d.total || 0,
            },
            empleador: {
                porcentaje: this.porcentajeEmpleador,
                valor: d.aporte_empleador || 0,
            },
            total: {
                porcentaje: this.porcentajeTotal,
                valor: (d.total || 0) + (d.aporte_empleador || 0),
            },
        };
    }

    get hasDistribucion() {
        return this.distribucion !== null && this.porcentajeEmpleador > 0;
    }

    // Tabla de rangos (FSP y Subsistencia)
    get tablaRangos() {
        if (!this.esVariable) return [];

        const tipo = this.data.tipo;

        if (tipo === 'solidaridad') {
            return [
                { rango: '4 - 16 SMMLV', porcentaje: '1.0%', aplica: this.data.rango_aplicado === '4-16' },
                { rango: '16 - 17 SMMLV', porcentaje: '1.2%', aplica: this.data.rango_aplicado === '16-17' },
                { rango: '17 - 18 SMMLV', porcentaje: '1.4%', aplica: this.data.rango_aplicado === '17-18' },
                { rango: '18 - 19 SMMLV', porcentaje: '1.6%', aplica: this.data.rango_aplicado === '18-19' },
                { rango: '19 - 20 SMMLV', porcentaje: '1.8%', aplica: this.data.rango_aplicado === '19-20' },
                { rango: '> 20 SMMLV', porcentaje: '2.0%', aplica: this.data.rango_aplicado === '>20' },
            ];
        }

        if (tipo === 'subsistencia') {
            return [
                { rango: '16 - 17 SMMLV', porcentaje: '0.2%', aplica: this.data.rango_aplicado === '16-17' },
                { rango: '17 - 18 SMMLV', porcentaje: '0.4%', aplica: this.data.rango_aplicado === '17-18' },
                { rango: '18 - 19 SMMLV', porcentaje: '0.6%', aplica: this.data.rango_aplicado === '18-19' },
                { rango: '19 - 20 SMMLV', porcentaje: '0.8%', aplica: this.data.rango_aplicado === '19-20' },
                { rango: '> 20 SMMLV', porcentaje: '1.0%+', aplica: this.data.rango_aplicado === '>20' },
            ];
        }

        return this.data.tabla_rangos || [];
    }

    get hasTablaRangos() {
        return this.tablaRangos.length > 0;
    }

    // SMMLV aplicado
    get smmlvAplicado() {
        const ibc = this.data.ibc || this.data.base || 0;
        const smmlv = this.data.smmlv || 1;
        return (ibc / smmlv).toFixed(1);
    }

    // Base legal
    get baseLegal() {
        const tipo = this.data.tipo || 'salud';
        const leyes = {
            'salud': 'Ley 100/1993 Art. 204',
            'pension': 'Ley 100/1993 Art. 20',
            'solidaridad': 'Ley 797/2003 Art. 7',
            'subsistencia': 'Ley 797/2003 Art. 8',
        };
        return this.data.base_legal || this.props.ruleConfig?.baseLegal || leyes[tipo] || 'Ley 100/1993';
    }

    // Formula
    get formula() {
        return `IBC x ${this.porcentajeEmpleado}%`;
    }

    // Toggle secciones
    toggleTablaRangos() {
        this.state.showTablaRangos = !this.state.showTablaRangos;
    }

    toggleDistribucion() {
        this.state.showDistribucion = !this.state.showDistribucion;
    }
}
