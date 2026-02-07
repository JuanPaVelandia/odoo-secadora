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

        if (!record || !record.resId) {
            console.log("[PESO WIDGET] No hay record o resId aún, esperando...");
            // NO detener el polling, solo esperar al siguiente ciclo
            // Cuando el usuario guarde, en el siguiente ciclo sí tendrá resId
            return;
        }

        const state = record.data.state;
        console.log("[PESO WIDGET] Estado:", state);

        if (state === "completado" || state === "cancelado") {
            console.log("[PESO WIDGET] Pesaje completado/cancelado, deteniendo polling");
            this.stopPolling();
            return;
        }

        try {
            console.log("[PESO WIDGET] Llamando a ORM.read...");

            // Forzar invalidación de caché antes de leer
            // Esto asegura que obtengamos datos frescos de la BD
            const result = await this.orm.call(
                "secadora.pesaje",
                "read",
                [[record.resId], ["peso_actual", "escuchando_bascula"]],
                { context: { bin_size: false } }
            );

            console.log("[PESO WIDGET] Resultado ORM:", result);

            if (result && result.length > 0) {
                const nuevoPeso = result[0].peso_actual || 0.0;
                console.log("[PESO WIDGET] Peso actual en BD:", nuevoPeso);
                console.log("[PESO WIDGET] Peso en state:", this.state.peso);

                if (Math.abs(this.state.peso - nuevoPeso) > 0.01) {
                    console.log("[PESO WIDGET] ¡Peso cambió! Actualizando UI...");
                    this.state.peso = nuevoPeso;
                    this.state.timestamp = new Date().toLocaleTimeString("es-CO");

                    // Actualizar solo este campo en el record sin recargar todo
                    record.data.peso_actual = nuevoPeso;
                    record.data.escuchando_bascula = result[0].escuchando_bascula;
                } else {
                    console.log("[PESO WIDGET] Peso no cambió significativamente");
                }
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
