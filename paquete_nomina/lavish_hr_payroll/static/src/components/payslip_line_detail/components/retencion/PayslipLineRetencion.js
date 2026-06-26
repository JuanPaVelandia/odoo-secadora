/** @odoo-module **/

import { Component, useState } from "@odoo/owl";

/**
 * PayslipLineRetencion - Componente para Retencion en la Fuente
 *
 * Codigos: RT_MET_01, RT_MET_02, RTEFTE, RET_PRIMA, RTF_INDEM
 * Base Legal: Art. 383-387 Estatuto Tributario
 *
 * Procedimientos:
 * - Procedimiento 1 (RT_MET_01): Calculo mensual
 * - Procedimiento 2 (RT_MET_02): Promedio 12 meses
 *
 * Props:
 * - retencionData: Object - Datos del calculo de retencion
 * - ruleConfig: Object - Configuracion visual
 * - formatCurrency: Function - Formatear moneda
 * - formatValue: Function - Formatear valores
 * - getLeyUrl: Function - URL de ley
 */
export class PayslipLineRetencion extends Component {
    static template = "lavish_hr_payroll.PayslipLineRetencion";
    static props = {
        retencionData: { type: Object },
        ruleConfig: { type: Object, optional: true },
        formatCurrency: { type: Function },
        formatValue: { type: Function },
        getLeyUrl: { type: Function, optional: true },
    };

    static STEP_COLORS = ['#3B82F6', '#8B5CF6', '#F97316', '#22C55E', '#EC4899', '#14B8A6', '#EF4444'];

    setup() {
        this.state = useState({
            expandedSteps: { 1: true, 2: true, 3: true, 4: true },
            showTablaTarifas: false,
        });
    }

    get data() {
        return this.props.retencionData || {};
    }

    // Procedimiento utilizado
    get procedimiento() {
        return this.data.procedimiento || 1;
    }

    get procedimientoLabel() {
        return this.procedimiento === 1 ? 'Procedimiento 1 (Mensual)' : 'Procedimiento 2 (Promedio)';
    }

    // KPIs principales
    get kpis() {
        const d = this.data;
        return [
            { id: 'ingresos', label: 'Ingresos Brutos', value: d.ingresos_brutos || d.ibr || 0, format: 'currency', icon: 'fa-money', color: 'success' },
            { id: 'base_gravable', label: 'Base Gravable', value: d.base_gravable || 0, format: 'currency', icon: 'fa-file-text-o', color: 'info' },
            { id: 'uvt', label: 'En UVT', value: d.base_uvt || 0, format: 'number', icon: 'fa-calculator', color: 'secondary' },
            { id: 'retencion', label: 'Retencion', value: d.total || d.retencion || 0, format: 'currency', icon: 'fa-percent', color: 'danger', highlight: true },
        ].filter(k => k.value !== 0 || k.highlight);
    }

    // Pasos del calculo de retencion
    get pasos() {
        const d = this.data;
        const pasos = d.pasos || [];

        if (pasos.length > 0) return pasos;

        // Construir pasos por defecto segun estructura tipica
        return [
            {
                numero: 1,
                titulo: 'Ingresos Brutos',
                subtitulo: 'Art. 103 E.T. - Rentas de Trabajo',
                valor: d.ingresos_brutos || d.ibr || 0,
                formato: 'currency',
                items: d.componentes_ingresos || [],
                icono: 'fa-plus-circle',
                color: 'success',
            },
            {
                numero: 2,
                titulo: '(-) INCR',
                subtitulo: 'Art. 55-56 E.T. - No Constitutivos de Renta',
                valor: d.incr || d.no_constitutivos || 0,
                formato: 'currency',
                items: [
                    { nombre: 'Aporte Salud Empleado', valor: d.aporte_salud || 0 },
                    { nombre: 'Aporte Pension Empleado', valor: d.aporte_pension || 0 },
                ],
                icono: 'fa-minus-circle',
                color: 'info',
            },
            {
                numero: 3,
                titulo: '(-) Deducciones',
                subtitulo: 'Art. 387 E.T. - Deducciones',
                valor: d.deducciones || 0,
                formato: 'currency',
                items: d.componentes_deducciones || [
                    { nombre: 'Dependientes', valor: d.dependientes || 0, limite: '32 UVT' },
                    { nombre: 'Medicina Prepagada', valor: d.medicina_prepagada || 0, limite: '16 UVT' },
                    { nombre: 'Intereses Vivienda', valor: d.intereses_vivienda || 0, limite: '100 UVT' },
                ],
                icono: 'fa-minus',
                color: 'warning',
            },
            {
                numero: 4,
                titulo: 'Aplicar Tarifa',
                subtitulo: 'Art. 383 E.T. - Tabla Marginal',
                valor: d.total || d.retencion || 0,
                formato: 'currency',
                items: d.calculo_tarifa ? [
                    { nombre: 'Base en UVT', valor: d.base_uvt, formato: 'uvt' },
                    { nombre: 'Rango Aplicado', valor: d.rango_aplicado, formato: 'text' },
                    { nombre: 'Tarifa Marginal', valor: d.tarifa_marginal, formato: 'percent' },
                ] : [],
                icono: 'fa-flag-checkered',
                color: 'danger',
                highlight: true,
            },
        ];
    }

    // Tabla de tarifas Art. 383 E.T.
    get tablaTarifas() {
        return this.data.tabla_tarifas || [
            { desde: 0, hasta: 95, tarifa: '0%', impuesto: '0' },
            { desde: 95, hasta: 150, tarifa: '19%', impuesto: '(UVT-95)*19%' },
            { desde: 150, hasta: 360, tarifa: '28%', impuesto: '(UVT-150)*28% + 10 UVT' },
            { desde: 360, hasta: 640, tarifa: '33%', impuesto: '(UVT-360)*33% + 69 UVT' },
            { desde: 640, hasta: 945, tarifa: '35%', impuesto: '(UVT-640)*35% + 162 UVT' },
            { desde: 945, hasta: 2300, tarifa: '37%', impuesto: '(UVT-945)*37% + 268 UVT' },
            { desde: 2300, hasta: null, tarifa: '39%', impuesto: '(UVT-2300)*39% + 770 UVT' },
        ];
    }

    // Rango aplicado
    get rangoAplicado() {
        const baseUvt = this.data.base_uvt || 0;
        for (const rango of this.tablaTarifas) {
            if (rango.hasta === null || baseUvt <= rango.hasta) {
                return rango;
            }
        }
        return this.tablaTarifas[this.tablaTarifas.length - 1];
    }

    // Base legal
    get baseLegal() {
        return this.data.base_legal || this.props.ruleConfig?.baseLegal || 'Art. 383-387 E.T.';
    }

    // Toggle pasos
    toggleStep(stepIndex) {
        this.state.expandedSteps[stepIndex] = !this.state.expandedSteps[stepIndex];
    }

    isStepExpanded(stepIndex) {
        return this.state.expandedSteps[stepIndex] !== false;
    }

    toggleTablaTarifas() {
        this.state.showTablaTarifas = !this.state.showTablaTarifas;
    }

    // Color del paso
    getStepColor(index) {
        return PayslipLineRetencion.STEP_COLORS[index % PayslipLineRetencion.STEP_COLORS.length];
    }

    // Formatear valor
    formatPasoValue(paso) {
        if (!paso.valor && paso.valor !== 0) return '';
        if (paso.formato === 'currency') {
            return this.props.formatCurrency(paso.valor);
        }
        if (paso.formato === 'uvt') {
            return `${paso.valor} UVT`;
        }
        if (paso.formato === 'percent') {
            return `${paso.valor}%`;
        }
        return this.props.formatValue(paso.valor, paso.formato);
    }
}
