/** @odoo-module **/

import { Component } from "@odoo/owl";

/**
 * PayslipLineContextual - Información contextual de la línea de nómina
 * Muestra información según el tipo de relación:
 * - Préstamos (loan_id)
 * - Novedades de contrato (concept_id)
 * - Ausencias (leave_id)
 * - Vacaciones (vacation_leave_id)
 * 
 * Props:
 * - contextualInfo: Object - Datos contextuales procesados
 * - formatCurrency: Function - Función para formatear moneda
 */
export class PayslipLineContextual extends Component {
    static template = "lavish_hr_payroll.PayslipLineContextual";
    static props = {
        contextualInfo: { type: Object },
        formatCurrency: { type: Function },
    };

    get hasRelation() {
        return this.props.contextualInfo?.has_relation || false;
    }

    get relationType() {
        return this.props.contextualInfo?.relation_type || null;
    }

    get relationData() {
        return this.props.contextualInfo?.relation_data || {};
    }

    get badges() {
        return this.props.contextualInfo?.badges || [];
    }

    get kpis() {
        return this.props.contextualInfo?.kpis || [];
    }

    get progress() {
        return this.props.contextualInfo?.progress || null;
    }

    get acciones() {
        return this.props.contextualInfo?.acciones || [];
    }

    get notas() {
        return this.props.contextualInfo?.notas || [];
    }

    formatValue(value, format) {
        if (format === 'currency') {
            return this.props.formatCurrency(value);
        }
        return value;
    }
}
