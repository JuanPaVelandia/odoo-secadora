/** @odoo-module **/

import { Component, useState } from "@odoo/owl";

/**
 * PayslipLineIBD - Componente para Ingreso Base de Cotizacion
 *
 * Codigos: IBD, IBC, IBC_R
 * Base Legal: Ley 1393/2010 Art. 30
 *
 * Calcula:
 * - Devengos salariales
 * - Devengos no salariales (limite 40%)
 * - Validaciones (minimo SMMLV, maximo 25 SMMLV)
 *
 * Props:
 * - ibdData: Object - Datos del calculo IBD
 * - ruleConfig: Object - Configuracion visual
 * - formatCurrency: Function - Formatear moneda
 * - formatValue: Function - Formatear valores
 * - getLeyUrl: Function - URL de ley
 */
export class PayslipLineIBD extends Component {
    static template = "lavish_hr_payroll.PayslipLineIBD";
    static props = {
        ibdData: { type: Object },
        ruleConfig: { type: Object, optional: true },
        formatCurrency: { type: Function },
        formatValue: { type: Function },
        getLeyUrl: { type: Function, optional: true },
    };

    static STEP_COLORS = ['#3B82F6', '#8B5CF6', '#F97316', '#22C55E', '#EC4899', '#14B8A6', '#EF4444'];

    setup() {
        this.state = useState({
            expandedSteps: { 1: true, 2: false, 3: false, 4: true },
            showComponentes: false,
            showValidaciones: true,
        });
    }

    get data() {
        return this.props.ibdData || {};
    }

    // KPIs principales
    get kpis() {
        const d = this.data;
        return [
            { id: 'ibc_mensual', label: 'IBC Mensual', value: d.ibc_mensual || d.base_mensual || 0, format: 'currency', icon: 'fa-building', color: 'primary' },
            { id: 'ibd_diario', label: 'IBD Diario', value: d.ibd_diario || d.base_diaria || 0, format: 'currency', icon: 'fa-calendar-o', color: 'info' },
            { id: 'dias', label: 'Dias', value: d.dias || 30, format: 'number', icon: 'fa-calendar', color: 'success' },
        ].filter(k => k.value > 0);
    }

    // Pasos del calculo IBD
    get pasos() {
        const d = this.data;
        const pasos = d.pasos || [];

        if (pasos.length > 0) return pasos;

        // Construir pasos por defecto
        return [
            {
                numero: 1,
                titulo: 'Devengos Salariales',
                subtitulo: 'Art. 127 C.S.T.',
                valor: d.devengos_salariales || 0,
                formato: 'currency',
                items: d.componentes_salariales || [],
                icono: 'fa-plus-circle',
                color: 'success',
            },
            {
                numero: 2,
                titulo: 'Devengos No Salariales',
                subtitulo: 'Ley 1393/2010 - Limite 40%',
                valor: d.devengos_no_salariales || 0,
                formato: 'currency',
                items: d.componentes_no_salariales || [],
                icono: 'fa-plus',
                color: 'info',
                limite_40: d.limite_40 || 0,
                excedente: d.excedente_40 || 0,
            },
            {
                numero: 3,
                titulo: 'Validaciones',
                subtitulo: 'Limites legales',
                valor: null,
                items: [
                    { nombre: 'Minimo (1 SMMLV)', valor: d.minimo_smmlv || 0, aplica: d.aplica_minimo },
                    { nombre: 'Maximo (25 SMMLV)', valor: d.maximo_smmlv || 0, aplica: d.aplica_maximo },
                ],
                icono: 'fa-check-circle',
                color: 'warning',
            },
            {
                numero: 4,
                titulo: 'IBC Final',
                subtitulo: 'Base de cotizacion',
                valor: d.ibc_mensual || d.total || 0,
                formato: 'currency',
                icono: 'fa-flag-checkered',
                color: 'primary',
                highlight: true,
            },
        ];
    }

    // Componentes que suman al IBC
    get componentes() {
        return this.data.componentes || [];
    }

    get hasComponentes() {
        return this.componentes.length > 0;
    }

    // Validaciones aplicadas
    get validaciones() {
        const d = this.data;
        const validaciones = [];

        if (d.aplica_minimo) {
            validaciones.push({
                tipo: 'minimo',
                label: 'Limite Minimo Aplicado',
                descripcion: 'IBC ajustado al minimo de 1 SMMLV',
                valor: d.minimo_smmlv,
                icon: 'fa-arrow-up',
                color: 'warning',
            });
        }

        if (d.aplica_maximo) {
            validaciones.push({
                tipo: 'maximo',
                label: 'Limite Maximo Aplicado',
                descripcion: 'IBC limitado a 25 SMMLV',
                valor: d.maximo_smmlv,
                icon: 'fa-arrow-down',
                color: 'danger',
            });
        }

        if (d.excedente_40 > 0) {
            validaciones.push({
                tipo: 'excedente',
                label: 'Excedente 40% No Salarial',
                descripcion: 'Exceso sobre limite 40% incluido en IBC',
                valor: d.excedente_40,
                icon: 'fa-plus',
                color: 'info',
            });
        }

        return validaciones;
    }

    get hasValidaciones() {
        return this.validaciones.length > 0;
    }

    // Base legal
    get baseLegal() {
        return this.data.base_legal || this.props.ruleConfig?.baseLegal || 'Ley 1393/2010';
    }

    // Toggle pasos
    toggleStep(stepIndex) {
        this.state.expandedSteps[stepIndex] = !this.state.expandedSteps[stepIndex];
    }

    isStepExpanded(stepIndex) {
        return this.state.expandedSteps[stepIndex] !== false;
    }

    toggleComponentes() {
        this.state.showComponentes = !this.state.showComponentes;
    }

    toggleValidaciones() {
        this.state.showValidaciones = !this.state.showValidaciones;
    }

    // Color del paso
    getStepColor(index) {
        return PayslipLineIBD.STEP_COLORS[index % PayslipLineIBD.STEP_COLORS.length];
    }

    // Formatear valor
    formatPasoValue(paso) {
        if (!paso.valor && paso.valor !== 0) return '';
        if (paso.formato === 'currency') {
            return this.props.formatCurrency(paso.valor);
        }
        return this.props.formatValue(paso.valor, paso.formato);
    }
}
