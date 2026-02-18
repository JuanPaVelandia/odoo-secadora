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

        console.log("[PESO WIDGET] Iniciando actualización...");
        console.log("[PESO WIDGET] Record:", record);
        console.log("[PESO WIDGET] ResId:", record?.resId);

        const state = record?.data?.state;

        // Si está completado o cancelado, detener polling
        if (state === "completado" || state === "cancelado") {
            console.log("[PESO WIDGET] Pesaje completado/cancelado, deteniendo polling");
            this.stopPolling();
            return;
        }

        try {
            let nuevoPeso = 0.0;

            if (!record || !record.resId) {
                // NO HAY resId (registro nuevo no guardado)
                // Usar endpoint global que devuelve el último peso disponible
                console.log("[PESO WIDGET] Sin resId, usando peso_actual_global...");

                const result = await this.orm.call(
                    "secadora.pesaje",
                    "obtener_peso_actual_global_ui",
                    []
                );

                if (result && result.success) {
                    nuevoPeso = result.peso_actual || 0.0;
                    console.log("[PESO WIDGET] Peso global obtenido:", nuevoPeso);
                } else {
                    console.log("[PESO WIDGET] No hay peso global disponible");
                    nuevoPeso = 0.0;
                }

            } else {
                // SÍ HAY resId (registro guardado)
                // Leer el peso específico de este pesaje
                console.log("[PESO WIDGET] Con resId, leyendo peso específico...");

                const result = await this.orm.call(
                    "secadora.pesaje",
                    "read",
                    [[record.resId], ["peso_actual", "escuchando_bascula"]],
                    { context: { bin_size: false } }
                );

                console.log("[PESO WIDGET] Resultado ORM:", result);

                if (result && result.length > 0) {
                    nuevoPeso = result[0].peso_actual || 0.0;
                    record.data.escuchando_bascula = result[0].escuchando_bascula;
                }
            }

            console.log("[PESO WIDGET] Peso actual:", nuevoPeso);
            console.log("[PESO WIDGET] Peso en state:", this.state.peso);

            // Actualizar UI si cambió
            if (Math.abs(this.state.peso - nuevoPeso) > 0.01) {
                console.log("[PESO WIDGET] ¡Peso cambió! Actualizando UI...");
                this.state.peso = nuevoPeso;
                this.state.timestamp = new Date().toLocaleTimeString("es-CO");

                // Actualizar el campo en el record (si existe)
                if (record && record.data) {
                    record.data.peso_actual = nuevoPeso;
                }
            } else {
                console.log("[PESO WIDGET] Peso no cambió significativamente");
            }

        } catch (error) {
            console.error("[PESO WIDGET] Error updating peso:", error);
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
