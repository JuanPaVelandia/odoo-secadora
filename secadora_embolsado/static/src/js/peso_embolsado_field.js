/** @odoo-module **/

import { registry } from "@web/core/registry";
import { PesoActualField } from "@bascula/js/peso_actual_field";

/**
 * Variante del widget de peso en vivo para el embolsado (wizard de viajes y
 * taras). Reutiliza toda la lectura Web Serial del widget de báscula, pero
 * SIEMPRE envía el peso como global (pesaje_id=false): el resId aquí sería el
 * id de un wizard, que puede coincidir con el id de un pesaje real en curso y
 * contaminarle su peso_actual.
 */
export class PesoEmbolsadoField extends PesoActualField {
    async _enviarPeso(peso) {
        const ahora = Date.now();
        const cambio =
            this._ultimoEnviado === null || Math.abs(this._ultimoEnviado - peso) > 0.01;
        const heartbeat = ahora - this._ultimoEnvioTs > 2000;
        if (!cambio && !heartbeat) return;

        this._ultimoEnviado = peso;
        this._ultimoEnvioTs = ahora;
        try {
            await this.orm.call("secadora.pesaje", "recibir_peso_web_serial", [
                peso,
                false,
            ]);
        } catch (e) {
            console.warn("[EMBOLSADO] Error enviando peso:", e);
        }
    }
}

PesoEmbolsadoField.template = "bascula.PesoActualField";

registry.category("fields").add("peso_embolsado_field", {
    component: PesoEmbolsadoField,
});
