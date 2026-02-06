/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onMounted, onWillUnmount } from "@odoo/owl";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

export class PesoActualField extends Component {
    static template = "bascula.PesoActualField";
    static props = standardFieldProps;

    setup() {
        super.setup();
        this.state = useState({
            peso: this.props.record.data[this.props.name] || 0.0,
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
        const state = record.data.state;

        if (state === "completado" || state === "cancelado") {
            this.stopPolling();
            return;
        }

        try {
            await record.load();
            const nuevoPeso = record.data[this.props.name] || 0.0;

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

registry.category("fields").add("peso_actual_field", PesoActualField);
