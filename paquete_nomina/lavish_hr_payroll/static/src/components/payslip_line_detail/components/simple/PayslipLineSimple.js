/** @odoo-module **/

import { Component } from "@odoo/owl";

/**
 * PayslipLineSimple - Vista simple con KPIs en fila
 * Muestra: KPIs horizontales + fórmula corta + total
 * 
 * Props:
 * - kpis: Array - Lista de KPIs [{etiqueta, valor, formato, subtitulo}]
 * - formula: String - Fórmula corta opcional
 * - total: Number - Valor total de la línea
 * - ruleConfig: Object - Configuración visual de la regla
 * - formatValue: Function - Función para formatear valores
 * - formatCurrency: Function - Función para formatear moneda
 */
export class PayslipLineSimple extends Component {
    static template = "lavish_hr_payroll.PayslipLineSimple";
    static props = {
        kpis: { type: Array },
        formula: { type: String, optional: true },
        total: { type: Number },
        ruleConfig: { type: Object },
        formatValue: { type: Function },
        formatCurrency: { type: Function },
    };
}
