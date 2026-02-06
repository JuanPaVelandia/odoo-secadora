/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onMounted, onWillUnmount } from "@odoo/owl";

class PesoActualField extends Component {
    setup() {
        this.state = useState({
            peso: this.props.value || 0.0,
            timestamp: new Date().toLocaleTimeString("es-CO"),
        });

        onMounted(() => {
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
        if (!record) return;

        const state = record.data.state;
        if (state === "completado" || state === "cancelado") {
            this.stopPolling();
            return;
        }

        try {
            await record.load();
            const nuevoPeso = record.data.peso_actual || 0.0;

            if (this.state.peso !== nuevoPeso) {
                this.state.peso = nuevoPeso;
                this.state.timestamp = new Date().toLocaleTimeString("es-CO");
            }
        } catch (error) {
            console.error("Error updating peso:", error);
        }
    }

    get formattedPeso() {
        return this.state.peso.toFixed(2);
    }
}

PesoActualField.template = "bascula.PesoActualField";

registry.category("fields").add("peso_actual_field", {
    component: PesoActualField,
});
