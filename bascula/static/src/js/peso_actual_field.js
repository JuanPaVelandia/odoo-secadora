/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onMounted, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

/**
 * Widget de peso en vivo desde la báscula, leído DIRECTAMENTE por el navegador
 * con la Web Serial API (Chrome/Edge, requiere HTTPS). No necesita bridge
 * Python ni nada instalado en el PC: el navegador abre el puerto serial, lee
 * las tramas del indicador y envía el peso a Odoo por RPC (usuario autenticado).
 *
 * El puerto se autoriza UNA vez por PC (botón "Conectar báscula"); Chrome lo
 * recuerda y reconecta solo en las siguientes visitas.
 */
export class PesoActualField extends Component {
    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        // El peso arranca en 0 (esperando lectura fresca del serial). NO se
        // muestra el peso_actual guardado en el registro: sería un valor viejo
        // de una lectura anterior de ese pesaje, no lo que hay en la báscula
        // ahora — confundía al reabrir un pesaje en tránsito.
        this.state = useState({
            peso: 0.0,
            recibido: false, // ¿ya llegó al menos una lectura del serial?
            timestamp: new Date().toLocaleTimeString("es-CO"),
            conectado: false,
            soportado: "serial" in navigator, // Web Serial disponible
        });

        this._port = null;
        this._reader = null;
        this._keepReading = false;
        this._ultimoEnviado = null;
        this._ultimoEnvioTs = 0;

        onMounted(async () => {
            if (this.state.soportado) {
                // Reconexión automática: si ya se autorizó un puerto antes,
                // Chrome lo devuelve en getPorts() sin volver a preguntar.
                try {
                    const puertos = await navigator.serial.getPorts();
                    if (puertos.length > 0) {
                        await this._abrirPuerto(puertos[0]);
                    }
                } catch (e) {
                    /* getPorts puede no estar disponible; sin ruido */
                }
            }
        });

        onWillUnmount(async () => {
            await this._cerrarPuerto();
        });
    }

    /** Botón "Conectar báscula": pide el puerto al usuario (1 clic/PC). */
    async conectar() {
        if (!this.state.soportado) {
            this.notification.add(
                "Este navegador no soporta lectura de báscula. Usa Chrome o Edge.",
                { type: "danger" }
            );
            return;
        }
        try {
            const port = await navigator.serial.requestPort();
            await this._abrirPuerto(port);
        } catch (e) {
            // El usuario canceló el selector: no es error.
            if (e && e.name !== "NotFoundError") {
                this.notification.add("No se pudo abrir el puerto: " + e.message, {
                    type: "danger",
                });
            }
        }
    }

    async _abrirPuerto(port) {
        try {
            await port.open({
                baudRate: 9600,
                dataBits: 8,
                parity: "none",
                stopBits: 1,
            });
        } catch (e) {
            if (e && e.name === "InvalidStateError") {
                // El puerto ya estaba abierto (otra pestaña, o esta misma):
                // se puede leer sin volver a abrir.
                this.notification.add("La báscula ya estaba abierta, reutilizando.", {
                    type: "info",
                });
            } else if (e && e.name === "NetworkError") {
                // Causa típica: el puerto está ocupado por otro programa
                // (el bridge/simulador Python, u otro software de báscula).
                this.notification.add(
                    "El puerto de la báscula está ocupado por otro programa. " +
                        "Cierra el simulador/bridge de Python u otras pestañas y reintenta.",
                    { type: "danger", sticky: true }
                );
                return;
            } else {
                this.notification.add(
                    "No se pudo abrir la báscula: " + (e ? e.message : "error desconocido"),
                    { type: "danger", sticky: true }
                );
                return;
            }
        }
        this._port = port;
        this.state.conectado = true;
        this.notification.add("Báscula conectada", { type: "success" });
        this._leerLoop();
    }

    async _leerLoop() {
        this._keepReading = true;
        const decoder = new TextDecoder();
        let buffer = "";
        while (this._keepReading && this._port && this._port.readable) {
            this._reader = this._port.readable.getReader();
            try {
                while (this._keepReading) {
                    const { value, done } = await this._reader.read();
                    if (done) break;
                    buffer += decoder.decode(value, { stream: true });
                    // Procesar por líneas completas (el indicador termina en \n o \r)
                    let idx;
                    while ((idx = buffer.search(/[\r\n]/)) >= 0) {
                        const linea = buffer.slice(0, idx).trim();
                        buffer = buffer.slice(idx + 1);
                        if (linea) {
                            this._procesarTrama(linea);
                        }
                    }
                }
            } catch (e) {
                // Error de lectura (desconexión física): salimos del loop.
                break;
            } finally {
                try {
                    this._reader.releaseLock();
                } catch (e) {
                    /* noop */
                }
            }
        }
    }

    /**
     * Parseo del indicador Prometálicos (misma lógica que el bridge Python):
     * la trama trae el número, ej "  12345.50 kg". Extraer el número y validar
     * el rango 0..100000 kg.
     */
    _procesarTrama(linea) {
        const match = linea.match(/([\d.]+)/);
        if (!match) return;
        const peso = parseFloat(match[1]);
        if (isNaN(peso) || peso < 0 || peso > 100000) return;

        this.state.recibido = true;
        if (Math.abs(this.state.peso - peso) > 0.01) {
            this.state.peso = peso;
            this.state.timestamp = new Date().toLocaleTimeString("es-CO");
        }
        this._enviarPeso(peso);
    }

    /**
     * Envía el peso a Odoo. Antirebote: solo si cambió o pasaron >2s
     * (heartbeat), para no saturar con lecturas idénticas.
     */
    async _enviarPeso(peso) {
        const ahora = Date.now();
        const cambio =
            this._ultimoEnviado === null || Math.abs(this._ultimoEnviado - peso) > 0.01;
        const heartbeat = ahora - this._ultimoEnvioTs > 2000;
        if (!cambio && !heartbeat) return;

        this._ultimoEnviado = peso;
        this._ultimoEnvioTs = ahora;
        const resId = this.props.record && this.props.record.resId;
        try {
            await this.orm.call("secadora.pesaje", "recibir_peso_web_serial", [
                peso,
                resId || false,
            ]);
        } catch (e) {
            console.warn("[BASCULA] Error enviando peso:", e);
        }
    }

    async _cerrarPuerto() {
        this._keepReading = false;
        try {
            if (this._reader) {
                await this._reader.cancel();
            }
        } catch (e) {
            /* noop */
        }
        try {
            if (this._port) {
                await this._port.close();
            }
        } catch (e) {
            /* noop */
        }
        this._port = null;
        this.state.conectado = false;
    }

    get formattedPeso() {
        const peso = this.state.peso;
        if (peso % 1 === 0) {
            return peso.toLocaleString("es-CO", { maximumFractionDigits: 0 });
        }
        return peso.toLocaleString("es-CO", {
            minimumFractionDigits: 1,
            maximumFractionDigits: 2,
        });
    }
}

PesoActualField.template = "bascula.PesoActualField";

registry.category("fields").add("peso_actual_field", {
    component: PesoActualField,
});
