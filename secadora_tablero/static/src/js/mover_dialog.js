/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

/**
 * Diálogo para elegir una ubicación destino. Alternativa táctil al
 * arrastrar-y-soltar (iOS Safari no soporta drag-and-drop HTML5): funciona
 * con un toque en iPad, tablet y PC.
 *
 * props:
 *   - title: título del diálogo
 *   - sitios: [{id, name, capacidad_kg}] ubicaciones disponibles
 *   - sitioActualId: id de la ubicación actual (se marca y no se puede elegir)
 *   - onSelect: (sitioId) => void  callback al elegir destino
 *   - close: cerrar (lo inyecta el servicio dialog)
 */
export class MoverDialog extends Component {
    static template = "secadora_tablero.MoverDialog";
    static components = { Dialog };
    static props = {
        title: String,
        sitios: Array,
        sitioActualId: { type: [Number, Boolean], optional: true },
        onSelect: Function,
        close: Function,
    };

    setup() {
        this.state = useState({ busqueda: "" });
    }

    get sitiosFiltrados() {
        const q = this.state.busqueda.trim().toLowerCase();
        if (!q) {
            return this.props.sitios;
        }
        return this.props.sitios.filter((s) => s.name.toLowerCase().includes(q));
    }

    seleccionar(sitioId) {
        if (sitioId === this.props.sitioActualId) {
            return;
        }
        this.props.onSelect(sitioId);
        this.props.close();
    }
}
