/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { TableroGrid } from "@secadora_tablero/js/tablero_grid";

/**
 * En contenedores de arroz seco, el total del sitio (texto "N / capacidad",
 * barra de uso y excedente) se calcula sobre el seco estimado de las tarjetas,
 * igual que el peso que muestra cada tarjeta.
 */
patch(TableroGrid.prototype, {
    getPesoTotalSitio(sitioId) {
        const sitio = this.state.sitios.find((s) => s.id === sitioId);
        if (sitio && sitio.mostrar_estimacion_seco) {
            return this.getPosicionesForSitio(sitioId).reduce(
                (sum, p) => sum + (p.peso_estimado_seco || p.peso_kg || 0),
                0
            );
        }
        return super.getPesoTotalSitio(sitioId);
    },
});
