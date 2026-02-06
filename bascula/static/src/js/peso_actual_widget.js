/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onMounted, onWillUnmount, useState } from "@odoo/owl";

/**
 * Widget para mostrar el peso actual de la báscula con auto-refresh
 */
export class PesoActualWidget extends Component {
    setup() {
        this.orm = useService("orm");
        this.state = useState({
            peso: 0,
            ultimaActualizacion: "",
        });

        this.intervalId = null;

        onMounted(() => {
            // Iniciar auto-refresh cada 2 segundos
            this.startAutoRefresh();
        });

        onWillUnmount(() => {
            // Limpiar intervalo al destruir el componente
            this.stopAutoRefresh();
        });
    }

    startAutoRefresh() {
        // Cargar peso inicial
        this.refreshPeso();

        // Configurar intervalo para actualizar cada 2 segundos
        this.intervalId = setInterval(() => {
            this.refreshPeso();
        }, 2000);
    }

    stopAutoRefresh() {
        if (this.intervalId) {
            clearInterval(this.intervalId);
            this.intervalId = null;
        }
    }

    async refreshPeso() {
        const resId = this.props.record.resId;
        const state = this.props.record.data.state;

        // Solo actualizar si el pesaje está en borrador o en tránsito
        if (!resId || (state !== 'borrador' && state !== 'en_transito')) {
            this.stopAutoRefresh();
            return;
        }

        try {
            // Leer solo el campo peso_actual del servidor
            const result = await this.orm.read(
                "secadora.pesaje",
                [resId],
                ["peso_actual"]
            );

            if (result && result.length > 0) {
                const nuevoPeso = result[0].peso_actual;

                // Solo actualizar si el peso cambió
                if (this.state.peso !== nuevoPeso) {
                    this.state.peso = nuevoPeso;

                    // Actualizar también el campo en el formulario
                    this.props.record.update({
                        peso_actual: nuevoPeso,
                        escuchando_bascula: nuevoPeso > 0
                    });

                    // Actualizar timestamp
                    const now = new Date();
                    this.state.ultimaActualizacion = now.toLocaleTimeString('es-CO');
                }
            }
        } catch (error) {
            console.error("Error actualizando peso:", error);
        }
    }
}

PesoActualWidget.template = "bascula.PesoActualWidget";

registry.category("fields").add("peso_actual_widget", PesoActualWidget);
