/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class GenerateBatchModal extends Component {
    static template = "lavish_hr_payroll.GenerateBatchModal";
    static props = {
        period: Object,
        onClose: Function,
        onGenerated: Function,
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");

        this.state = useState({
            includePrima: this.props.period.is_prima_month,
            generating: false,
        });
    }

    async generateBatch() {
        this.state.generating = true;

        try {
            // Aquí llamarías al método del backend para generar el lote
            // Por ahora es un placeholder
            await new Promise(resolve => setTimeout(resolve, 1000));

            this.notification.add("Lote generado exitosamente", {
                type: "success",
            });

            this.props.onGenerated();
        } catch (error) {
            console.error("Error generating batch:", error);
            this.notification.add("Error al generar lote: " + error.message, {
                type: "danger",
            });
        } finally {
            this.state.generating = false;
        }
    }

    get isPrimaPeriod() {
        return this.props.period.is_prima_month;
    }

    get primaMonth() {
        return this.props.period.month === 6 ? "Junio" : "Diciembre";
    }
}
