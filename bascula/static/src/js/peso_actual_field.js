/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onMounted, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

class PesoActualField extends Component {
    setup() {
        this.orm = useService("orm");
        this.state = useState({
            peso: this.props.record.data.peso_actual || 0.0,
            timestamp: new Date().toLocaleTimeString("es-CO"),
        });

        onMounted(() => {
            // Leer peso inmediatamente al montar (no esperar 2 seg)
            this.updatePeso();
            this.startPolling();
        });

        onWillUnmount(() => {
            this.stopPolling();
        });
    }

    startPolling() {
        this.pollInterval = setInterval(async () => {
            await this.updatePeso();
        }, 2000);
    }

    stopPolling() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
    }

    async updatePeso() {
        const record = this.props.record;
        const state = record?.data?.state;

        if (state === "completado" || state === "cancelado") {
            this.stopPolling();
            return;
        }

        try {
            // Siempre leer el peso global (es la fuente de verdad de la báscula)
            const globalResult = await this.orm.call(
                "secadora.pesaje",
                "obtener_peso_actual_global_ui",
                []
            );

            let nuevoPeso = 0.0;

            if (globalResult && globalResult.success && globalResult.peso_actual > 0.01) {
                nuevoPeso = globalResult.peso_actual;
            } else if (record && record.resId) {
                // Fallback: leer del registro si no hay peso global
                const result = await this.orm.call(
                    "secadora.pesaje",
                    "read",
                    [[record.resId], ["peso_actual"]],
                    { context: { bin_size: false } }
                );
                if (result && result.length > 0) {
                    nuevoPeso = result[0].peso_actual || 0.0;
                }
            }

            // Solo actualizar el state del widget, NUNCA tocar record.data
            // para evitar que Odoo envíe peso_actual en el save/create
            if (Math.abs(this.state.peso - nuevoPeso) > 0.01) {
                this.state.peso = nuevoPeso;
                this.state.timestamp = new Date().toLocaleTimeString("es-CO");
            }

        } catch (error) {
            console.error("[PESO WIDGET] Error updating peso:", error);
        }
    }

    get formattedPeso() {
        const peso = this.state.peso;
        if (peso % 1 === 0) {
            return peso.toLocaleString("es-CO", { maximumFractionDigits: 0 });
        }
        return peso.toLocaleString("es-CO", { minimumFractionDigits: 1, maximumFractionDigits: 2 });
    }
}

PesoActualField.template = "bascula.PesoActualField";

registry.category("fields").add("peso_actual_field", {
    component: PesoActualField,
});
