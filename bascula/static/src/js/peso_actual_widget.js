/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useService } from "@web/core/utils/hooks";

export class PesoActualWidget extends Component {
    static template = "bascula.PesoActualWidget";
    static props = {
        ...standardFieldProps,
    };

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            peso: this.props.record.data.peso_actual || 0,
            ultimaActualizacion: "",
        });

        this.intervalId = null;

        onMounted(() => {
            this.startAutoRefresh();
        });

        onWillUnmount(() => {
            this.stopAutoRefresh();
        });
    }

    startAutoRefresh() {
        this.refreshPeso();
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

        if (!resId || (state !== "borrador" && state !== "en_transito")) {
            this.stopAutoRefresh();
            return;
        }

        try {
            const result = await this.orm.read(
                "secadora.pesaje",
                [resId],
                ["peso_actual"]
            );

            if (result && result.length > 0) {
                const nuevoPeso = result[0].peso_actual;

                if (this.state.peso !== nuevoPeso) {
                    this.state.peso = nuevoPeso;

                    await this.props.record.update({
                        peso_actual: nuevoPeso,
                        escuchando_bascula: nuevoPeso > 0
                    });

                    const now = new Date();
                    this.state.ultimaActualizacion = now.toLocaleTimeString("es-CO");
                }
            }
        } catch (error) {
            console.error("Error actualizando peso:", error);
        }
    }
}

registry.category("fields").add("peso_actual_widget", PesoActualWidget);
