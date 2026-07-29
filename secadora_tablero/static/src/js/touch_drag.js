/** @odoo-module **/

/**
 * Arrastrar-y-soltar táctil para el tablero.
 *
 * El tablero usa drag-and-drop HTML5 (draggable/dragstart/drop), que SOLO
 * funciona con ratón: ningún navegador móvil genera esos eventos a partir de
 * un gesto táctil. En Android el deslizamiento se interpreta como scroll y en
 * iOS Safari no hay soporte en absoluto. Esta capa traduce gestos de puntero
 * a las mismas acciones de soltar que ya usa el escritorio, para no duplicar
 * la lógica de negocio ni tocar el camino del ratón.
 *
 * Gesto: mantener pulsado LONG_PRESS_MS sobre una tarjeta y arrastrar. Se
 * exige la pulsación larga porque un deslizamiento inmediato debe seguir
 * haciendo scroll — el tablero es más alto que la pantalla de una tablet y
 * capturar todo gesto lo dejaría inmóvil.
 *
 * Durante el arrastre se clona la tarjeta como "fantasma" que sigue al dedo,
 * ya que el elemento original permanece en su sitio (a diferencia del arrastre
 * nativo, que pinta la vista previa por nosotros).
 */

// Pulsación antes de que el gesto pase de "scroll" a "arrastre".
const LONG_PRESS_MS = 350;
// Margen de movimiento tolerado durante la pulsación larga: por encima de esto
// se entiende que el usuario quería hacer scroll y se cancela el arrastre.
const MOVE_TOLERANCE_PX = 10;
// Franja desde el borde de la ventana en la que se auto-desplaza el tablero
// al arrastrar cerca del límite, para poder soltar en zonas fuera de pantalla.
const EDGE_SCROLL_PX = 60;
const EDGE_SCROLL_SPEED = 12;

/**
 * Activa el arrastre táctil dentro de `root`.
 *
 * @param {HTMLElement} root contenedor del tablero
 * @param {Object} handlers
 *   - onDropCard(posicionId, sitioId, fila, col)
 *   - onDropTransito(pesajeId, sitioId)
 *   - onDropCardEnTransito(posicionId)
 *   - onDropCell(sitioIdArrastrado, sitioIdDestino, fila, col)
 *   - isBloqueado() => boolean
 * @returns {Function} para desactivar los listeners
 */
export function habilitarArrastreTactil(root, handlers) {
    let timerPulsacion = null;
    let arrastrando = false;
    let origen = null; // {tipo, id, el}
    let fantasma = null;
    let inicioX = 0;
    let inicioY = 0;
    let ultimoDestino = null;
    let rafScroll = null;
    let ultimoX = 0;
    let ultimoY = 0;

    function limpiarResaltado() {
        root.querySelectorAll(
            ".tablero-cell-drag-over, .tablero-transito-drag-over"
        ).forEach((el) => {
            el.classList.remove("tablero-cell-drag-over", "tablero-transito-drag-over");
        });
    }

    function cancelar() {
        clearTimeout(timerPulsacion);
        timerPulsacion = null;
        if (rafScroll) {
            cancelAnimationFrame(rafScroll);
            rafScroll = null;
        }
        if (fantasma) {
            fantasma.remove();
            fantasma = null;
        }
        if (origen?.el) {
            origen.el.classList.remove("tablero-dragging");
        }
        limpiarResaltado();
        // El <html> recupera la selección de texto y el menú contextual.
        document.body.classList.remove("tablero-arrastrando");
        arrastrando = false;
        origen = null;
        ultimoDestino = null;
    }

    /** Identifica qué se está arrastrando a partir del elemento tocado. */
    function detectarOrigen(target) {
        const cardTransito = target.closest(".tablero-card-transito");
        if (cardTransito && root.contains(cardTransito)) {
            const id = cardTransito.dataset.transitoId;
            if (id) {
                return { tipo: "transito", id: parseInt(id, 10), el: cardTransito };
            }
        }
        const card = target.closest(".tablero-card");
        if (card && root.contains(card)) {
            const id = card.dataset.posicionId;
            if (id) {
                return { tipo: "card", id: parseInt(id, 10), el: card };
            }
        }
        // La celda solo se arrastra desde su cabecera: agarrarla por cualquier
        // punto haría imposible arrastrar las tarjetas que contiene.
        const header = target.closest(".tablero-cell-header");
        if (header && root.contains(header)) {
            const celda = header.closest(".tablero-grid-cell");
            const id = celda?.dataset.sitioId;
            if (id) {
                return { tipo: "cell", id: parseInt(id, 10), el: celda };
            }
        }
        return null;
    }

    function crearFantasma(el, x, y) {
        const rect = el.getBoundingClientRect();
        const clon = el.cloneNode(true);
        clon.classList.add("tablero-fantasma");
        // Los botones del clon no deben ser interactivos ni recibir el puntero.
        clon.querySelectorAll("button").forEach((b) => b.remove());
        clon.style.width = `${rect.width}px`;
        clon.style.height = `${rect.height}px`;
        document.body.appendChild(clon);
        fantasma = clon;
        // Desplazamiento del dedo respecto a la esquina, para que la tarjeta no
        // salte al empezar a mover.
        fantasma._offsetX = x - rect.left;
        fantasma._offsetY = y - rect.top;
        moverFantasma(x, y);
    }

    function moverFantasma(x, y) {
        if (!fantasma) return;
        fantasma.style.left = `${x - fantasma._offsetX}px`;
        fantasma.style.top = `${y - fantasma._offsetY}px`;
    }

    /** Elemento del tablero bajo el dedo, ignorando el fantasma. */
    function destinoEn(x, y) {
        if (fantasma) {
            fantasma.style.display = "none";
        }
        const el = document.elementFromPoint(x, y);
        if (fantasma) {
            fantasma.style.display = "";
        }
        return el;
    }

    function resaltarDestino(x, y) {
        const el = destinoEn(x, y);
        limpiarResaltado();
        ultimoDestino = null;
        if (!el || !root.contains(el)) {
            return;
        }
        const seccionTransito = el.closest(".tablero-transito-section");
        if (seccionTransito && origen.tipo === "card") {
            seccionTransito.classList.add("tablero-transito-drag-over");
            ultimoDestino = { tipo: "transito-section" };
            return;
        }
        const celda = el.closest(".tablero-grid-cell");
        if (celda) {
            celda.classList.add("tablero-cell-drag-over");
            ultimoDestino = {
                tipo: "celda",
                sitioId: celda.dataset.sitioId ? parseInt(celda.dataset.sitioId, 10) : false,
                fila: parseInt(celda.dataset.fila, 10),
                col: parseInt(celda.dataset.col, 10),
            };
        }
    }

    /** Desplaza la ventana cuando el dedo se acerca a un borde. */
    function autoScroll() {
        if (!arrastrando) {
            rafScroll = null;
            return;
        }
        if (ultimoY < EDGE_SCROLL_PX) {
            window.scrollBy(0, -EDGE_SCROLL_SPEED);
        } else if (ultimoY > window.innerHeight - EDGE_SCROLL_PX) {
            window.scrollBy(0, EDGE_SCROLL_SPEED);
        }
        rafScroll = requestAnimationFrame(autoScroll);
    }

    function onPointerDown(ev) {
        // Solo gestos táctiles o de lápiz: con ratón manda el arrastre nativo.
        if (ev.pointerType === "mouse") return;
        if (handlers.isBloqueado()) return;
        // Un toque sobre un botón es una acción, no un arrastre.
        if (ev.target.closest("button")) return;

        const detectado = detectarOrigen(ev.target);
        if (!detectado) return;

        inicioX = ev.clientX;
        inicioY = ev.clientY;
        ultimoX = ev.clientX;
        ultimoY = ev.clientY;

        timerPulsacion = setTimeout(() => {
            arrastrando = true;
            origen = detectado;
            origen.el.classList.add("tablero-dragging");
            document.body.classList.add("tablero-arrastrando");
            crearFantasma(origen.el, ultimoX, ultimoY);
            // Aviso háptico de que el gesto pasó a modo arrastre.
            if (navigator.vibrate) {
                navigator.vibrate(30);
            }
            rafScroll = requestAnimationFrame(autoScroll);
        }, LONG_PRESS_MS);
    }

    function onPointerMove(ev) {
        if (ev.pointerType === "mouse") return;
        ultimoX = ev.clientX;
        ultimoY = ev.clientY;

        if (!arrastrando) {
            // Todavía en la ventana de pulsación larga: si el dedo se mueve, el
            // gesto era scroll.
            if (timerPulsacion) {
                const dx = Math.abs(ev.clientX - inicioX);
                const dy = Math.abs(ev.clientY - inicioY);
                if (dx > MOVE_TOLERANCE_PX || dy > MOVE_TOLERANCE_PX) {
                    clearTimeout(timerPulsacion);
                    timerPulsacion = null;
                }
            }
            return;
        }
        // Ya arrastrando: este gesto es nuestro, no de la página.
        ev.preventDefault();
        moverFantasma(ev.clientX, ev.clientY);
        resaltarDestino(ev.clientX, ev.clientY);
    }

    async function onPointerUp(ev) {
        if (ev.pointerType === "mouse") return;
        if (!arrastrando) {
            clearTimeout(timerPulsacion);
            timerPulsacion = null;
            return;
        }
        const destino = ultimoDestino;
        const tipoOrigen = origen.tipo;
        const idOrigen = origen.id;
        cancelar();

        if (!destino) return;

        if (destino.tipo === "transito-section") {
            if (tipoOrigen === "card") {
                await handlers.onDropCardEnTransito(idOrigen);
            }
            return;
        }
        if (destino.tipo === "celda") {
            if (tipoOrigen === "card") {
                await handlers.onDropCard(idOrigen, destino.sitioId, destino.fila, destino.col);
            } else if (tipoOrigen === "transito") {
                await handlers.onDropTransito(idOrigen, destino.sitioId);
            } else if (tipoOrigen === "cell") {
                await handlers.onDropCell(idOrigen, destino.sitioId, destino.fila, destino.col);
            }
        }
    }

    root.addEventListener("pointerdown", onPointerDown);
    // En window para no perder el gesto si el dedo sale del tablero, y no
    // pasivo porque onPointerMove necesita preventDefault para frenar el scroll.
    window.addEventListener("pointermove", onPointerMove, { passive: false });
    window.addEventListener("pointerup", onPointerUp);
    window.addEventListener("pointercancel", cancelar);

    return function desactivar() {
        cancelar();
        root.removeEventListener("pointerdown", onPointerDown);
        window.removeEventListener("pointermove", onPointerMove);
        window.removeEventListener("pointerup", onPointerUp);
        window.removeEventListener("pointercancel", cancelar);
    };
}
