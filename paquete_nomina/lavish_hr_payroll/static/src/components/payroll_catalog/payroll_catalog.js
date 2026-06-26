/** @odoo-module **/

/**
 * ============================================================================
 * CATALOGO DE REGLAS DE NOMINA COLOMBIANA
 * ============================================================================
 *
 * Componente OWL para visualizar reglas de nomina con:
 * - Iconos SVG locales (sin CDN)
 * - Animaciones CSS puras
 * - Simuladores de calculo
 * - Referencias legales
 */

import { Component, useState, xml } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import {
    REGLAS_NOMINA,
    UVT_2025,
    SMMLV_2025,
    AUX_TRANSPORTE_2025,
    PayrollCalculations
} from "./reglas_nomina_data";


// ============================================================================
// COMPONENTE: ICONO SVG ANIMADO
// ============================================================================

const SVG_ICONS = {
    money: xml`
        <svg class="animated-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <circle class="icon-path" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/>
            <path class="icon-path" d="M12 6v12M9 9h6M9 15h6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        </svg>
    `,
    shield: xml`
        <svg class="animated-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path class="icon-path" d="M12 2L4 6v6c0 5.55 3.84 10.74 8 12 4.16-1.26 8-6.45 8-12V6l-8-4z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <path class="icon-path" d="M9 12l2 2 4-4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
    `,
    percent: xml`
        <svg class="animated-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <circle class="icon-path" cx="7" cy="7" r="2" stroke="currentColor" stroke-width="2"/>
            <circle class="icon-path" cx="17" cy="17" r="2" stroke="currentColor" stroke-width="2"/>
            <path class="icon-path" d="M19 5L5 19" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        </svg>
    `,
    gift: xml`
        <svg class="animated-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect class="icon-path" x="3" y="10" width="18" height="10" rx="2" stroke="currentColor" stroke-width="2"/>
            <path class="icon-path" d="M12 10V20M3 14h18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            <path class="icon-path" d="M12 10c0-2 1-4 3-4s2 2 0 4M12 10c0-2-1-4-3-4s-2 2 0 4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        </svg>
    `,
    calendar: xml`
        <svg class="animated-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect class="icon-path" x="3" y="4" width="18" height="18" rx="2" stroke="currentColor" stroke-width="2"/>
            <path class="icon-path" d="M3 10h18M8 2v4M16 2v4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            <circle class="icon-path" cx="8" cy="14" r="1" fill="currentColor"/>
            <circle class="icon-path" cx="12" cy="14" r="1" fill="currentColor"/>
            <circle class="icon-path" cx="16" cy="14" r="1" fill="currentColor"/>
        </svg>
    `,
    chart: xml`
        <svg class="animated-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path class="icon-path" d="M3 20l6-6 4 4 8-8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <circle class="icon-path" cx="3" cy="20" r="2" fill="currentColor"/>
            <circle class="icon-path" cx="9" cy="14" r="2" fill="currentColor"/>
            <circle class="icon-path" cx="13" cy="18" r="2" fill="currentColor"/>
            <circle class="icon-path" cx="21" cy="10" r="2" fill="currentColor"/>
        </svg>
    `,
    check: xml`
        <svg class="animated-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <circle class="icon-path" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/>
            <path class="icon-path" d="M8 12l3 3 5-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
    `,
    alert: xml`
        <svg class="animated-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path class="icon-path" d="M12 2L2 20h20L12 2z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <path class="icon-path" d="M12 9v4M12 17h.01" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        </svg>
    `,
    building: xml`
        <svg class="animated-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect class="icon-path" x="4" y="2" width="16" height="20" rx="2" stroke="currentColor" stroke-width="2"/>
            <path class="icon-path" d="M8 6h2M14 6h2M8 10h2M14 10h2M8 14h2M14 14h2M10 18h4v4h-4z" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        </svg>
    `,
    calculator: xml`
        <svg class="animated-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect class="icon-path" x="4" y="2" width="16" height="20" rx="2" stroke="currentColor" stroke-width="2"/>
            <rect class="icon-path" x="7" y="5" width="10" height="4" rx="1" stroke="currentColor" stroke-width="2"/>
            <circle class="icon-path" cx="8" cy="13" r="1" fill="currentColor"/>
            <circle class="icon-path" cx="12" cy="13" r="1" fill="currentColor"/>
            <circle class="icon-path" cx="16" cy="13" r="1" fill="currentColor"/>
            <circle class="icon-path" cx="8" cy="17" r="1" fill="currentColor"/>
            <circle class="icon-path" cx="12" cy="17" r="1" fill="currentColor"/>
            <circle class="icon-path" cx="16" cy="17" r="1" fill="currentColor"/>
        </svg>
    `
};

export class AnimatedIcon extends Component {
    static template = "lavish_hr_payroll.AnimatedIcon";
    static props = {
        name: String,
        style: { type: String, optional: true }
    };

    get iconTemplate() {
        return SVG_ICONS[this.props.name] || SVG_ICONS.check;
    }
}


// ============================================================================
// COMPONENTE PRINCIPAL: CATALOGO DE REGLAS
// ============================================================================

export class PayrollCatalog extends Component {
    static template = "lavish_hr_payroll.PayrollCatalog";
    static components = { AnimatedIcon };

    setup() {
        this.action = useService("action");
        this.notification = useService("notification");

        this.state = useState({
            seccionActiva: 'ibc',
            mostrarDetalles: {},
            simulador: {
                salarioBasico: 4500000,
                auxTransporte: AUX_TRANSPORTE_2025,
                devengosNoSalariales: 1500000,
                diasTrabajados: 30
            }
        });

        // Constantes
        this.UVT = UVT_2025;
        this.SMMLV = SMMLV_2025;
        this.AUX_TRANSPORTE = AUX_TRANSPORTE_2025;
        this.REGLAS = REGLAS_NOMINA;
    }

    // Secciones disponibles
    get secciones() {
        return [
            { id: 'ibc', nombre: 'IBC', icono: 'building', color: 'blue' },
            { id: 'seguridad', nombre: 'Seguridad Social', icono: 'shield', color: 'green' },
            { id: 'retenciones', nombre: 'Retenciones', icono: 'percent', color: 'red' },
            { id: 'prestaciones', nombre: 'Prestaciones', icono: 'gift', color: 'amber' },
            { id: 'parafiscales', nombre: 'Parafiscales', icono: 'building', color: 'violet' }
        ];
    }

    // ========================================================================
    // CALCULOS
    // ========================================================================

    calcularIBC() {
        const { salarioBasico, devengosNoSalariales } = this.state.simulador;
        return PayrollCalculations.calcularIBC(salarioBasico, devengosNoSalariales);
    }

    calcularPrima() {
        const { salarioBasico, auxTransporte, diasTrabajados } = this.state.simulador;
        return PayrollCalculations.calcularPrima(salarioBasico, auxTransporte, diasTrabajados);
    }

    calcularCesantias() {
        const { salarioBasico, auxTransporte, diasTrabajados } = this.state.simulador;
        return PayrollCalculations.calcularCesantias(salarioBasico, auxTransporte, diasTrabajados);
    }

    calcularInteresesCesantias() {
        const cesantias = this.calcularCesantias();
        return PayrollCalculations.calcularInteresesCesantias(cesantias, this.state.simulador.diasTrabajados);
    }

    calcularVacaciones() {
        const { salarioBasico, diasTrabajados } = this.state.simulador;
        return PayrollCalculations.calcularVacaciones(salarioBasico, diasTrabajados);
    }

    // ========================================================================
    // FORMATO
    // ========================================================================

    formatCurrency(value) {
        return PayrollCalculations.formatCurrency(value);
    }

    formatPercent(value) {
        return `${value}%`;
    }

    // ========================================================================
    // HANDLERS
    // ========================================================================

    onSeccionClick(seccionId) {
        this.state.seccionActiva = seccionId;
    }

    onInputChange(field, event) {
        this.state.simulador[field] = Number(event.target.value) || 0;
    }

    toggleDetalle(id) {
        this.state.mostrarDetalles[id] = !this.state.mostrarDetalles[id];
    }

    // ========================================================================
    // GETTERS PARA CALCULOS DERIVADOS
    // ========================================================================

    get remuneracionTotal() {
        return this.state.simulador.salarioBasico + this.state.simulador.devengosNoSalariales;
    }

    get limite40() {
        return this.remuneracionTotal * 0.4;
    }

    get excesoNoSalarial() {
        return Math.max(0, this.state.simulador.devengosNoSalariales - this.limite40);
    }

    get ibcCalculado() {
        return this.calcularIBC();
    }

    // Seguridad Social
    get saludEmpleador() {
        return this.ibcCalculado * 0.085;
    }

    get saludTrabajador() {
        return this.ibcCalculado * 0.04;
    }

    get pensionEmpleador() {
        return this.ibcCalculado * 0.12;
    }

    get pensionTrabajador() {
        return this.ibcCalculado * 0.04;
    }

    get fsp() {
        return PayrollCalculations.calcularFSP(this.ibcCalculado, this.SMMLV);
    }

    // Prestaciones
    get primaCalculada() {
        return this.calcularPrima();
    }

    get cesantiasCalculadas() {
        return this.calcularCesantias();
    }

    get interesesCalculados() {
        return this.calcularInteresesCesantias();
    }

    get vacacionesCalculadas() {
        return this.calcularVacaciones();
    }
}

// Registrar el componente como accion
registry.category("actions").add("payroll_catalog", PayrollCatalog);
