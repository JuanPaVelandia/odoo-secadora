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
        if (!record || !record.resId) return;

        const state = record.data.state;
        if (state === "completado" || state === "cancelado") {
            this.stopPolling();
            return;
        }

        try {
            // Leer SOLO el campo peso_actual usando ORM service
            const result = await this.orm.read(
                "secadora.pesaje",
                [record.resId],
                ["peso_actual", "escuchando_bascula"]
            );

            if (result && result.length > 0) {
                const nuevoPeso = result[0].peso_actual || 0.0;

                if (Math.abs(this.state.peso - nuevoPeso) > 0.01) {
                    this.state.peso = nuevoPeso;
                    this.state.timestamp = new Date().toLocaleTimeString("es-CO");

                    // Actualizar solo este campo en el record sin recargar todo
                    record.data.peso_actual = nuevoPeso;
                    record.data.escuchando_bascula = result[0].escuchando_bascula;
                }
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
