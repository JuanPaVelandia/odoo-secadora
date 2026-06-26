/**
 * LordIcon Compatibility Layer
 *
 * Este archivo proporciona compatibilidad con el tag <lord-icon>
 * usando lottie-web en lugar de la libreria original de LordIcon.
 *
 * Permite que los templates existentes sigan funcionando sin cambios.
 *
 * Uso:
 *   <lord-icon
 *       src="/lavish_hr_payroll/static/src/lib/lottie/icons/qhviklyi.json"
 *       trigger="hover"
 *       colors="primary:#22c55e"
 *       style="width:48px;height:48px">
 *   </lord-icon>
 */

// Ruta base para iconos locales
const ICONS_LOCAL_PATH = "/lavish_hr_payroll/static/src/lib/lottie/icons/";

// Mapeo de URLs CDN a nombres de archivo local
function convertCdnToLocal(src) {
    if (!src) return null;

    // Si ya es una ruta local, retornarla
    if (src.startsWith('/')) {
        return src;
    }

    // Convertir URL de CDN a local
    if (src.includes('cdn.lordicon.com')) {
        const match = src.match(/\/([^\/]+)\.json$/);
        if (match) {
            return ICONS_LOCAL_PATH + match[1] + ".json";
        }
    }

    // Si es otra URL, intentar extraer el nombre del archivo
    const fileName = src.split('/').pop();
    if (fileName && fileName.endsWith('.json')) {
        return ICONS_LOCAL_PATH + fileName;
    }

    return src;
}

// Parsear el atributo colors
function parseColors(colorsStr) {
    if (!colorsStr) return {};

    const colors = {};
    const parts = colorsStr.split(',');
    parts.forEach(part => {
        const [key, value] = part.split(':');
        if (key && value) {
            colors[key.trim()] = value.trim();
        }
    });
    return colors;
}

// Definir el Custom Element <lord-icon>
class LordIconElement extends HTMLElement {
    constructor() {
        super();
        this.animation = null;
        this._observer = null;
    }

    static get observedAttributes() {
        return ['src', 'trigger', 'colors', 'state'];
    }

    connectedCallback() {
        // Esperar a que lottie este disponible
        if (typeof lottie === 'undefined') {
            console.warn('LordIconElement: lottie library not available');
            return;
        }

        this.initAnimation();

        // Observar cambios de atributos
        this._observer = new MutationObserver(() => this.initAnimation());
        this._observer.observe(this, { attributes: true });
    }

    disconnectedCallback() {
        this.destroyAnimation();
        if (this._observer) {
            this._observer.disconnect();
            this._observer = null;
        }
    }

    attributeChangedCallback(name, oldValue, newValue) {
        if (oldValue !== newValue && this.isConnected) {
            this.initAnimation();
        }
    }

    initAnimation() {
        this.destroyAnimation();

        const src = this.getAttribute('src');
        const localSrc = convertCdnToLocal(src);

        if (!localSrc) {
            console.warn('LordIconElement: No src attribute provided');
            return;
        }

        const trigger = this.getAttribute('trigger') || 'hover';
        const colors = parseColors(this.getAttribute('colors'));

        // Limpiar contenido previo
        this.innerHTML = '';

        // Crear contenedor interno
        const container = document.createElement('div');
        container.style.width = '100%';
        container.style.height = '100%';
        this.appendChild(container);

        try {
            this.animation = lottie.loadAnimation({
                container: container,
                renderer: 'svg',
                loop: trigger === 'loop',
                autoplay: trigger === 'loop',
                path: localSrc,
            });

            this.animation.addEventListener('DOMLoaded', () => {
                this.applyColors(colors);
            });

            this.animation.addEventListener('data_failed', () => {
                console.warn(`LordIconElement: Failed to load ${localSrc}`);
                this.showFallback();
            });

            // Configurar triggers
            this.setupTriggers(trigger);

        } catch (error) {
            console.error('LordIconElement: Error initializing animation', error);
            this.showFallback();
        }
    }

    setupTriggers(trigger) {
        // Limpiar event listeners previos
        this.onmouseenter = null;
        this.onmouseleave = null;
        this.onclick = null;

        switch (trigger) {
            case 'hover':
                this.onmouseenter = () => this.play();
                this.onmouseleave = () => this.stop();
                break;

            case 'click':
                this.onclick = () => this.playOnce();
                break;

            case 'morph':
            case 'boomerang':
                this.onmouseenter = () => this.play();
                this.onmouseleave = () => this.playReverse();
                break;

            case 'loop':
                // Ya configurado en loadAnimation
                break;

            case 'loop-on-hover':
                this.onmouseenter = () => {
                    if (this.animation) {
                        this.animation.loop = true;
                        this.animation.play();
                    }
                };
                this.onmouseleave = () => {
                    if (this.animation) {
                        this.animation.loop = false;
                    }
                };
                break;
        }
    }

    applyColors(colors) {
        if (!colors || Object.keys(colors).length === 0) return;

        const svg = this.querySelector('svg');
        if (!svg) return;

        // Aplicar color primario
        if (colors.primary) {
            const paths = svg.querySelectorAll('path, circle, rect, ellipse, polygon');
            paths.forEach(el => {
                const fill = el.getAttribute('fill');
                const stroke = el.getAttribute('stroke');

                if (fill && fill !== 'none' && fill !== 'transparent') {
                    el.style.fill = colors.primary;
                }
                if (stroke && stroke !== 'none' && stroke !== 'transparent') {
                    el.style.stroke = colors.primary;
                }
            });
        }

        // Aplicar color secundario
        if (colors.secondary) {
            // Buscar elementos con clases especificas o segundo grupo
            const groups = svg.querySelectorAll('g');
            if (groups.length > 1) {
                const secondGroup = groups[1];
                const paths = secondGroup.querySelectorAll('path, circle, rect');
                paths.forEach(el => {
                    const fill = el.getAttribute('fill');
                    if (fill && fill !== 'none') {
                        el.style.fill = colors.secondary;
                    }
                });
            }
        }
    }

    showFallback() {
        this.innerHTML = '<i class="fa fa-circle-o" style="font-size: 80%; opacity: 0.5;"></i>';
    }

    play() {
        if (this.animation) {
            this.animation.setDirection(1);
            this.animation.play();
        }
    }

    stop() {
        if (this.animation) {
            this.animation.stop();
        }
    }

    pause() {
        if (this.animation) {
            this.animation.pause();
        }
    }

    playOnce() {
        if (this.animation) {
            this.animation.goToAndPlay(0);
        }
    }

    playReverse() {
        if (this.animation) {
            this.animation.setDirection(-1);
            this.animation.play();
        }
    }

    destroyAnimation() {
        if (this.animation) {
            this.animation.destroy();
            this.animation = null;
        }
    }
}

// Registrar el Custom Element
if (!customElements.get('lord-icon')) {
    customElements.define('lord-icon', LordIconElement);
}

console.log('[Lottie] LordIcon compatibility layer loaded - Using local icons');
