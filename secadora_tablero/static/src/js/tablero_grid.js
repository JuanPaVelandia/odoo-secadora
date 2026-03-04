/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

class TableroGrid extends Component {
    static template = "secadora_tablero.TableroGrid";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            sitios: [],
            posiciones: [],
            filas: [],
            columnas: [],
            en_transito: [],
            loading: true,
            bloqueado: localStorage.getItem('tablero_bloqueado') === 'true',
        });

        onWillStart(async () => {
            await this.loadData();
        });
    }

    async loadData() {
        this.state.loading = true;
        const data = await this.orm.call(
            "secadora.posicion.arroz",
            "get_tablero_grid_data",
            [],
        );
        this.state.sitios = data.sitios;
        this.state.posiciones = data.posiciones;
        this.state.filas = data.filas;
        this.state.columnas = data.columnas;
        this.state.en_transito = data.en_transito || [];
        this.state.loading = false;
    }

    getSitioAt(fila, columna) {
        return this.state.sitios.find(
            (s) => s.fila === fila && s.columna === columna
        );
    }

    getPosicionesForSitio(sitioId) {
        return this.state.posiciones.filter((p) => p.sitio_id === sitioId);
    }

    sitioTieneBultos(sitioId) {
        return this.getPosicionesForSitio(sitioId).some((p) => p.modalidad_salida_raw === "bultos");
    }

    getSinUbicar() {
        return this.state.posiciones.filter((p) => !p.sitio_id);
    }

    formatPeso(value) {
        return new Intl.NumberFormat("es-CO", {
            minimumFractionDigits: 0,
            maximumFractionDigits: 2,
        }).format(value);
    }

    hasPreasignados() {
        return this.state.posiciones.some((p) => p.es_preasignado);
    }

    getPesoTotalSitio(sitioId) {
        return this.state.posiciones
            .filter((p) => p.sitio_id === sitioId)
            .reduce((sum, p) => sum + p.peso_kg, 0);
    }

    getExcedente(sitioId, capacidad) {
        if (!capacidad) return 0;
        const total = this.getPesoTotalSitio(sitioId);
        return total > capacidad ? total - capacidad : 0;
    }

    getPorcentajeUso(sitioId, capacidad) {
        if (!capacidad) return 0;
        const total = this.getPesoTotalSitio(sitioId);
        return Math.min((total / capacidad) * 100, 100);
    }

    getCombinableCount(sitioId) {
        return this.state.posiciones.filter(
            (p) => p.sitio_id === sitioId && p.permite_combinar
        ).length;
    }

    /** Devuelve true si el sitio tiene ocultar_calidad marcado */
    sitioOcultaCalidad(sitioId) {
        const sitio = this.state.sitios.find((s) => s.id === sitioId);
        return sitio ? sitio.ocultar_calidad : false;
    }

    // --- Bloqueo ---
    onClickToggleBloqueo() {
        this.state.bloqueado = !this.state.bloqueado;
        localStorage.setItem('tablero_bloqueado', this.state.bloqueado);
    }

    // --- Drag tarjetas (posiciones) ---
    onDragStartCard(ev, posicionId) {
        if (this.state.bloqueado) {
            ev.preventDefault();
            return;
        }
        ev.stopPropagation();
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("application/x-card", String(posicionId));
    }

    // --- Drag tarjetas de tránsito ---
    onDragStartTransito(ev, pesajeId) {
        if (this.state.bloqueado) {
            ev.preventDefault();
            return;
        }
        ev.stopPropagation();
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("application/x-transito", String(pesajeId));
        this._draggedTransitoId = pesajeId;
        requestAnimationFrame(() => {
            ev.target.closest(".tablero-card-transito")?.classList.add("tablero-dragging");
        });
    }

    onDragEndTransito(ev) {
        this._draggedTransitoId = null;
        ev.currentTarget.classList.remove("tablero-dragging");
        // Limpiar todos los indicadores
        document.querySelectorAll(".tablero-drop-before, .tablero-drop-after").forEach((el) => {
            el.classList.remove("tablero-drop-before", "tablero-drop-after");
        });
    }

    onDragOverTransitoCard(ev) {
        if (this.state.bloqueado) return;
        if (!ev.dataTransfer.types.includes("application/x-transito")) return;
        ev.preventDefault();
        ev.dataTransfer.dropEffect = "move";

        const card = ev.currentTarget;
        const rect = card.getBoundingClientRect();
        const midX = rect.left + rect.width / 2;

        // Mostrar indicador en el lado izquierdo o derecho
        if (ev.clientX < midX) {
            card.classList.add("tablero-drop-before");
            card.classList.remove("tablero-drop-after");
        } else {
            card.classList.add("tablero-drop-after");
            card.classList.remove("tablero-drop-before");
        }
    }

    onDragLeaveTransitoCard(ev) {
        ev.currentTarget.classList.remove("tablero-drop-before", "tablero-drop-after");
    }

    onDropTransitoCard(ev) {
        if (this.state.bloqueado) return;
        ev.preventDefault();
        ev.stopPropagation();

        const card = ev.currentTarget;
        const rect = card.getBoundingClientRect();
        const dropAfter = ev.clientX >= rect.left + rect.width / 2;

        card.classList.remove("tablero-drop-before", "tablero-drop-after");

        const transitoId = ev.dataTransfer.getData("application/x-transito");
        if (!transitoId) return;
        const draggedId = parseInt(transitoId, 10);
        if (!draggedId) return;

        const targetIdx = parseInt(card.dataset.transitoIdx, 10);
        const list = this.state.en_transito;
        const fromIdx = list.findIndex((t) => t.id === draggedId);
        if (fromIdx < 0 || isNaN(targetIdx)) return;

        let toIdx = dropAfter ? targetIdx + 1 : targetIdx;

        // No hacer nada si queda en la misma posición
        if (fromIdx === toIdx || fromIdx === toIdx - 1 && dropAfter) return;

        const [item] = list.splice(fromIdx, 1);
        // Ajustar índice si venía de antes
        if (fromIdx < toIdx) toIdx--;
        list.splice(toIdx, 0, item);
    }

    // --- Drop en la sección de tránsito (devolver tarjeta pre-asignada) ---
    async onDropTransitoSection(ev) {
        if (this.state.bloqueado) return;
        ev.preventDefault();
        ev.currentTarget.classList.remove("tablero-transito-drag-over");

        const cardId = ev.dataTransfer.getData("application/x-card");
        if (!cardId) return;
        const posicionId = parseInt(cardId, 10);
        if (!posicionId) return;

        const pos = this.state.posiciones.find((p) => p.id === posicionId);
        if (!pos || !pos.es_preasignado) return;

        await this.orm.call(
            "secadora.posicion.arroz",
            "deshacer_preasignacion",
            [posicionId],
        );
        await this.loadData();
    }

    // --- Drag celdas (sitios) ---
    onDragStartCell(ev, sitioId) {
        if (this.state.bloqueado) {
            ev.preventDefault();
            return;
        }
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("application/x-cell", String(sitioId));
    }

    onDragOver(ev) {
        if (this.state.bloqueado) return;
        ev.preventDefault();
        ev.dataTransfer.dropEffect = "move";
    }

    onDragEnter(ev) {
        if (this.state.bloqueado) return;
        ev.currentTarget.classList.add("tablero-cell-drag-over");
    }

    onDragLeave(ev) {
        ev.currentTarget.classList.remove("tablero-cell-drag-over");
    }

    async onDrop(ev, targetSitioId, targetFila, targetCol) {
        if (this.state.bloqueado) return;
        ev.preventDefault();
        ev.currentTarget.classList.remove("tablero-cell-drag-over");

        // Caso 1: Se soltó una tarjeta
        const cardId = ev.dataTransfer.getData("application/x-card");
        if (cardId) {
            const posicionId = parseInt(cardId, 10);
            if (!posicionId || !targetSitioId) return;
            const pos = this.state.posiciones.find((p) => p.id === posicionId);
            if (pos && pos.sitio_id === targetSitioId) return;

            await this.orm.write("secadora.posicion.arroz", [posicionId], {
                sitio_id: targetSitioId,
            });
            await this.loadData();
            return;
        }

        // Caso 2: Se soltó una tarjeta de tránsito — pre-asignar ubicación
        const transitoId = ev.dataTransfer.getData("application/x-transito");
        if (transitoId) {
            const pesajeId = parseInt(transitoId, 10);
            if (!pesajeId || !targetSitioId) return;
            await this.orm.call(
                "secadora.posicion.arroz",
                "preasignar_transito",
                [pesajeId, targetSitioId],
            );
            await this.loadData();
            return;
        }

        // Caso 3: Se soltó una celda (sitio) — intercambiar posiciones en la grilla
        const cellId = ev.dataTransfer.getData("application/x-cell");
        if (cellId) {
            const draggedSitioId = parseInt(cellId, 10);
            if (!draggedSitioId || draggedSitioId === targetSitioId) return;

            const draggedSitio = this.state.sitios.find((s) => s.id === draggedSitioId);
            if (!draggedSitio) return;

            if (targetSitioId) {
                // Hay un sitio en la celda destino: intercambiar
                const targetSitio = this.state.sitios.find((s) => s.id === targetSitioId);
                await this.orm.write("secadora.sitio.muestra", [draggedSitioId], {
                    fila: targetSitio.fila,
                    columna: targetSitio.columna,
                });
                await this.orm.write("secadora.sitio.muestra", [targetSitioId], {
                    fila: draggedSitio.fila,
                    columna: draggedSitio.columna,
                });
            } else {
                // Celda vacía: mover ahí
                await this.orm.write("secadora.sitio.muestra", [draggedSitioId], {
                    fila: targetFila,
                    columna: targetCol,
                });
            }
            await this.loadData();
        }
    }

    async onClickPosicion(posicionId) {
        if (this.state.bloqueado) return;
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "secadora.posicion.arroz",
            res_id: posicionId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async onClickDespacharPosicion(posicionId) {
        if (this.state.bloqueado) return;
        const result = await this.orm.call(
            "secadora.posicion.arroz",
            "action_despachar",
            [posicionId],
        );
        if (!result.views) {
            result.views = [[false, "form"]];
        }
        await this.action.doAction(result, {
            onClose: async () => {
                await this.loadData();
            },
        });
    }

    async onClickDividir(posicionId) {
        if (this.state.bloqueado) return;
        const result = await this.orm.call(
            "secadora.posicion.arroz",
            "action_dividir",
            [posicionId],
        );
        if (!result.views) {
            result.views = [[false, "form"]];
        }
        await this.action.doAction(result, {
            onClose: async () => {
                await this.loadData();
            },
        });
    }

    async onClickRevertirDivision(posicionId) {
        if (this.state.bloqueado) return;
        if (!confirm("¿Revertir esta división? El peso se devolverá a la posición origen.")) return;
        await this.orm.call(
            "secadora.posicion.arroz",
            "action_revertir_division",
            [posicionId],
        );
        await this.loadData();
    }

    async onClickCombinar(sitioId) {
        if (this.state.bloqueado) return;
        await this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "secadora.combinar.posicion.wizard",
                view_mode: "form",
                views: [[false, "form"]],
                target: "new",
                context: {
                    default_sitio_id: sitioId,
                },
            },
            {
                onClose: async () => {
                    await this.loadData();
                },
            }
        );
    }

    async onClickDespachar(sitioId) {
        if (this.state.bloqueado) return;
        await this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "secadora.despachar.posicion.wizard",
                view_mode: "form",
                views: [[false, "form"]],
                target: "new",
                context: {
                    default_sitio_id: sitioId,
                },
            },
            {
                onClose: async () => {
                    await this.loadData();
                },
            }
        );
    }

    async onClickRefresh() {
        await this.loadData();
    }
}

registry.category("actions").add("secadora_tablero_grid", TableroGrid);
