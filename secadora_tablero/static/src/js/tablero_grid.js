/** @odoo-module **/

import { Component, useState, onWillStart, onWillUnmount } from "@odoo/owl";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { MoverDialog } from "./mover_dialog";

export class TableroGrid extends Component {
    static template = "secadora_tablero.TableroGrid";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.state = useState({
            sitios: [],
            posiciones: [],
            filas: [],
            columnas: [],
            en_transito: [],
            loading: true,
            bloqueado: localStorage.getItem('tablero_bloqueado') === 'true',
        });

        // Se marca al desmontar para no escribir el estado tras un await si
        // el componente ya se destruyó (p. ej. loadData disparado desde el
        // onClose de un wizard cuando el tablero ya no está montado).
        this._destruido = false;
        onWillUnmount(() => {
            this._destruido = true;
        });

        onWillStart(async () => {
            await this.loadData();
        });
    }

    async loadData() {
        // Si el componente ya se destruyó, NO llamar al ORM: el orm de OWL
        // está ligado al ciclo de vida del componente y rechaza con
        // "Component is destroyed" al resolver la promesa. Esto pasa cuando
        // loadData se dispara desde el onClose de un wizard tras el cual el
        // tablero ya no está montado.
        if (this._destruido) {
            return;
        }
        this.state.loading = true;
        let data;
        try {
            data = await this.orm.call(
                "secadora.posicion.arroz",
                "get_tablero_grid_data",
                [],
            );
        } catch (e) {
            // El propio orm.call rechaza si el componente murió durante la
            // llamada. No es un error real: se ignora silenciosamente.
            if (this._destruido) {
                return;
            }
            throw e;
        }
        if (this._destruido) {
            return;
        }
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
        const combinables = this.state.posiciones.filter(
            (p) => p.sitio_id === sitioId && p.permite_combinar
        );
        // Para semilla solo se permite combinar si todas las combinables son del
        // mismo viaje (pesaje) que fue dividido antes; nunca se mezclan viajes.
        if (combinables.some((p) => p.es_semilla)) {
            const pesajes = new Set(combinables.map((p) => p.pesaje_id));
            if (pesajes.size > 1) {
                return 0;
            }
        }
        return combinables.length;
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

    // En iPad, las tarjetas son draggable y iOS Safari no soporta HTML5
    // drag-and-drop: el gesto táctil sobre un botón hijo se traga el "click",
    // por eso los botones del footer no responden. Escuchamos touchend y
    // disparamos la acción desde ahí.
    //
    // Safari puede emitir igual un "click" sintético después del touchend, así
    // que en vez de cancelar el gesto (preventDefault bloquearía cualquier
    // diálogo nativo y rompe el scroll) marcamos el toque como ya atendido y
    // dejamos que el click posterior se descarte solo.
    onTouchAction(ev, handler) {
        ev.stopPropagation();
        this._touchHandled = true;
        // Si Safari no llega a emitir el click sintético, el flag no debe
        // quedar activo y tragarse el siguiente click legítimo.
        clearTimeout(this._touchHandledTimer);
        this._touchHandledTimer = setTimeout(() => {
            this._touchHandled = false;
        }, 700);
        handler();
    }

    // Ejecuta la acción de un click de mouse, salvo que un touchend inmediato
    // anterior ya la haya disparado (click sintético de iOS).
    onClickAction(handler) {
        if (this._touchHandled) {
            this._touchHandled = false;
            clearTimeout(this._touchHandledTimer);
            return;
        }
        handler();
    }

    // Mover una tarjeta a otra ubicación vía diálogo (alternativa táctil al
    // arrastrar-y-soltar, que iOS Safari no soporta en iPad).
    onClickMover(posicionId) {
        if (this.state.bloqueado) return;
        const pos = this.state.posiciones.find((p) => p.id === posicionId);
        this.dialog.add(MoverDialog, {
            title: "Mover tarjeta a...",
            sitios: this.state.sitios,
            sitioActualId: pos ? pos.sitio_id : false,
            onSelect: async (sitioId) => {
                await this.orm.write("secadora.posicion.arroz", [posicionId], {
                    sitio_id: sitioId,
                });
                await this.loadData();
            },
        });
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

    // Se usa ConfirmationDialog (DOM) y no el confirm() nativo: WebKit suprime
    // los modales nativos invocados desde un handler táctil, y el botón quedaba
    // muerto en iPad.
    onClickRevertirDivision(posicionId) {
        if (this.state.bloqueado) return;
        this.dialog.add(ConfirmationDialog, {
            title: "Revertir división",
            body: "¿Revertir esta división? El peso se devolverá a la posición origen.",
            confirmLabel: "Revertir",
            cancelLabel: "Cancelar",
            confirm: async () => {
                await this.orm.call(
                    "secadora.posicion.arroz",
                    "action_revertir_division",
                    [posicionId],
                );
                await this.loadData();
            },
            cancel: () => {},
        });
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
