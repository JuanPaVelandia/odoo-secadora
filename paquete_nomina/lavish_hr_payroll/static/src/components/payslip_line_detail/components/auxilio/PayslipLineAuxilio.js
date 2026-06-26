/** @odoo-module **/

import { Component, useState } from "@odoo/owl";

/**
 * PayslipLineAuxilio - Componente para Auxilios
 *
 * Codigos: AUX000, AUX00C, DEV_AUX
 * Base Legal: Ley 15/1959, Decreto 1258/1959
 *
 * Tipos:
 * - AUX000: Auxilio de transporte
 * - AUX00C: Auxilio de conectividad
 * - DEV_AUX: Devolucion auxilio
 *
 * Props:
 * - auxilioData: Object - Datos del calculo de auxilio
 * - ruleConfig: Object - Configuracion visual
 * - formatCurrency: Function - Formatear moneda
 * - formatValue: Function - Formatear valores
 */
export class PayslipLineAuxilio extends Component {
    static template = "lavish_hr_payroll.PayslipLineAuxilio";
    static props = {
        auxilioData: { type: Object },
        ruleConfig: { type: Object, optional: true },
        formatCurrency: { type: Function },
        formatValue: { type: Function },
    };

    setup() {
        this.state = useState({
            showDetalleCalculo: false,
        });
    }

    get data() {
        return this.props.auxilioData || {};
    }

    // Tipo de auxilio
    get tipoAuxilio() {
        const tipo = this.data.tipo || 'transporte';
        const labels = {
            'transporte': 'Auxilio de Transporte',
            'conectividad': 'Auxilio de Conectividad',
            'devolucion': 'Devolucion Auxilio',
        };
        return labels[tipo] || tipo;
    }

    get tipoIcon() {
        const tipo = this.data.tipo || 'transporte';
        const icons = {
            'transporte': 'fa-bus',
            'conectividad': 'fa-wifi',
            'devolucion': 'fa-undo',
        };
        return icons[tipo] || 'fa-money';
    }

    get tipoColor() {
        const tipo = this.data.tipo || 'transporte';
        const colors = {
            'transporte': 'success',
            'conectividad': 'info',
            'devolucion': 'warning',
        };
        return colors[tipo] || 'secondary';
    }

    // Es devolucion?
    get esDevolucion() {
        return this.data.tipo === 'devolucion' || this.data.es_devolucion;
    }

    // KPIs
    get kpis() {
        const d = this.data;
        const kpis = [
            { id: 'valor_mensual', label: 'Valor Mensual', value: d.valor_mensual || 0, format: 'currency', icon: 'fa-calendar-o' },
            { id: 'dias', label: 'Dias', value: d.dias || 0, format: 'number', icon: 'fa-calendar' },
            { id: 'total', label: 'Total', value: d.total || 0, format: 'currency', icon: 'fa-check-circle', highlight: true },
        ];

        // Si es devolucion, agregar auxilio pagado
        if (this.esDevolucion && d.auxilio_pagado) {
            kpis.splice(2, 0, {
                id: 'auxilio_pagado',
                label: 'Auxilio Pagado',
                value: d.auxilio_pagado,
                format: 'currency',
                icon: 'fa-minus-circle',
                color: 'danger'
            });
        }

        return kpis.filter(k => k.value !== 0 || k.highlight);
    }

    // Aplica auxilio?
    get aplicaAuxilio() {
        return this.data.aplica !== false;
    }

    // Razon de no aplicar
    get razonNoAplica() {
        return this.data.razon_no_aplica || 'Salario superior a 2 SMMLV';
    }

    // Limite salarial
    get limiteSalarial() {
        return this.data.limite_salarial || this.data.dos_smmlv || 0;
    }

    // Salario del empleado
    get salarioEmpleado() {
        return this.data.salario_empleado || this.data.salario || 0;
    }

    // Formula
    get formula() {
        if (this.esDevolucion) {
            return 'Auxilio Pagado - (Valor Mensual / 30 x Dias)';
        }
        return 'Valor Mensual / 30 x Dias';
    }

    // Base legal
    get baseLegal() {
        return this.data.base_legal || this.props.ruleConfig?.baseLegal || 'Ley 15/1959';
    }

    // Pasos del calculo
    get pasos() {
        return this.data.pasos || this.data.steps || [];
    }

    get hasPasos() {
        return this.pasos.length > 0;
    }

    // Toggle detalle
    toggleDetalleCalculo() {
        this.state.showDetalleCalculo = !this.state.showDetalleCalculo;
    }

    // Formatear valor
    formatPasoValue(paso) {
        if (paso.format === 'currency' || paso.formato === 'currency') {
            return this.props.formatCurrency(paso.value || paso.valor);
        }
        return this.props.formatValue(paso.value || paso.valor, paso.format || paso.formato);
    }
}
