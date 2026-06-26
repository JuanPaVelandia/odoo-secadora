/** @odoo-module **/
/**
 * LottieIcon - Componente OWL para iconos animados con Lottie
 *
 * Uso:
 *   <LottieIcon name="'qhviklyi'" size="48" color="'#22c55e'" trigger="'hover'"/>
 *
 * Props:
 *   - name: Nombre del archivo JSON (sin extension) ej: 'qhviklyi'
 *   - src: URL completa del JSON (alternativa a name)
 *   - size: Tamano en pixels (default: 48)
 *   - color: Color primario (default: currentColor)
 *   - trigger: 'hover' | 'click' | 'loop' | 'none' (default: 'hover')
 *   - speed: Velocidad de animacion (default: 1)
 */

import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";

// Ruta base para iconos locales
const ICONS_BASE_PATH = "/lavish_hr_payroll/static/src/lib/lottie/icons/";

// Mapeo de nombres amigables a archivos
const ICON_ALIASES = {
    // Dinero / Finanzas
    'money': 'qhviklyi',
    'dollar': 'qhviklyi',
    'dinero': 'qhviklyi',

    // Documentos
    'document': 'abfverha',
    'file': 'abfverha',
    'documento': 'abfverha',
    'receipt': 'iltqorsz',
    'recibo': 'iltqorsz',
    'nomina': 'iltqorsz',

    // Calendario / Tiempo
    'calendar': 'kbtmbyzy',
    'calendario': 'kbtmbyzy',
    'clock': 'nizfqlnq',
    'reloj': 'nizfqlnq',
    'time': 'nizfqlnq',

    // Personas
    'user': 'tdrtiskw',
    'person': 'tdrtiskw',
    'usuario': 'tdrtiskw',
    'team': 'lomfljuq',
    'users': 'lomfljuq',
    'equipo': 'lomfljuq',
    'licencias': 'hrqwmutt',

    // Graficos / Analytics
    'chart': 'dxoycpzg',
    'analytics': 'dxoycpzg',
    'grafico': 'dxoycpzg',
    'trending-up': 'vduvxizq',
    'subida': 'vduvxizq',
    'trending-down': 'yeallgsa',
    'bajada': 'yeallgsa',

    // Estado
    'check': 'wyqtxzeh',
    'success': 'wyqtxzeh',
    'exito': 'wyqtxzeh',
    'alert': 'nocovwne',
    'warning': 'nocovwne',
    'alerta': 'nocovwne',
    'info': 'zmkotitn',
    'informacion': 'zmkotitn',

    // Edificios / Organizacion
    'building': 'rmkpgtpt',
    'edificio': 'rmkpgtpt',
    'empresa': 'rmkpgtpt',
    'folder': 'kdduutaw',
    'carpeta': 'kdduutaw',
    'list': 'jmkrnisz',
    'lista': 'jmkrnisz',

    // Configuracion
    'settings': 'yrxnwkni',
    'gear': 'yrxnwkni',
    'config': 'yrxnwkni',
    'configuracion': 'yrxnwkni',

    // Busqueda / Vacio
    'search': 'msoeawqm',
    'empty': 'msoeawqm',
    'vacio': 'msoeawqm',
    'buscar': 'msoeawqm',

    // Retencion
    'retencion': 'nizfqlnq',
    'percent': 'nizfqlnq',
};

export class LottieIcon extends Component {
    static template = "lavish_hr_payroll.LottieIcon";
    static props = {
        name: { type: String, optional: true },
        src: { type: String, optional: true },
        size: { type: Number, optional: true },
        color: { type: String, optional: true },
        trigger: { type: String, optional: true },
        speed: { type: Number, optional: true },
        className: { type: String, optional: true },
        style: { type: String, optional: true },
    };

    setup() {
        this.containerRef = useRef("container");
        this.state = useState({
            loaded: false,
            error: false,
        });
        this.animation = null;

        onMounted(() => {
            this.initLottie();
        });

        onWillUnmount(() => {
            this.destroyAnimation();
        });
    }

    get iconPath() {
        // Si se proporciona src completo, usarlo
        if (this.props.src) {
            // Si es una URL de CDN, convertir a local
            if (this.props.src.includes('cdn.lordicon.com')) {
                const match = this.props.src.match(/\/([^\/]+)\.json$/);
                if (match) {
                    return ICONS_BASE_PATH + match[1] + ".json";
                }
            }
            return this.props.src;
        }

        // Si se proporciona name, buscar en aliases o usar directamente
        if (this.props.name) {
            const fileName = ICON_ALIASES[this.props.name] || this.props.name;
            return ICONS_BASE_PATH + fileName + ".json";
        }

        return null;
    }

    get size() {
        return this.props.size || 48;
    }

    get trigger() {
        return this.props.trigger || 'hover';
    }

    get speed() {
        return this.props.speed || 1;
    }

    async initLottie() {
        const container = this.containerRef.el;
        if (!container || !this.iconPath) return;

        // Verificar que lottie esta disponible globalmente
        if (typeof lottie === 'undefined') {
            console.error("LottieIcon: lottie library not loaded");
            this.state.error = true;
            return;
        }

        try {
            this.animation = lottie.loadAnimation({
                container: container,
                renderer: 'svg',
                loop: this.trigger === 'loop',
                autoplay: this.trigger === 'loop',
                path: this.iconPath,
            });

            this.animation.setSpeed(this.speed);

            this.animation.addEventListener('DOMLoaded', () => {
                this.state.loaded = true;
                this.applyColor();
            });

            this.animation.addEventListener('data_failed', () => {
                this.state.error = true;
                console.warn(`LottieIcon: Failed to load ${this.iconPath}`);
            });

            // Configurar triggers
            if (this.trigger === 'hover') {
                container.addEventListener('mouseenter', () => this.play());
                container.addEventListener('mouseleave', () => this.stop());
            } else if (this.trigger === 'click') {
                container.addEventListener('click', () => this.playOnce());
            }

        } catch (error) {
            console.error("LottieIcon: Error initializing", error);
            this.state.error = true;
        }
    }

    applyColor() {
        if (!this.props.color || !this.containerRef.el) return;

        // Aplicar color a los elementos SVG
        const svg = this.containerRef.el.querySelector('svg');
        if (svg) {
            svg.style.color = this.props.color;
            // Para paths que usan fill
            const paths = svg.querySelectorAll('path[fill]');
            paths.forEach(path => {
                const fill = path.getAttribute('fill');
                if (fill && fill !== 'none' && fill !== 'transparent') {
                    path.style.fill = this.props.color;
                }
            });
            // Para paths que usan stroke
            const strokes = svg.querySelectorAll('path[stroke]');
            strokes.forEach(path => {
                const stroke = path.getAttribute('stroke');
                if (stroke && stroke !== 'none' && stroke !== 'transparent') {
                    path.style.stroke = this.props.color;
                }
            });
        }
    }

    play() {
        if (this.animation) {
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

    destroyAnimation() {
        if (this.animation) {
            this.animation.destroy();
            this.animation = null;
        }
    }
}

// Template inline para el componente
LottieIcon.template = owl.xml`
    <div t-ref="container"
         t-att-class="'lottie-icon ' + (props.className || '')"
         t-att-style="'width:' + size + 'px; height:' + size + 'px; display:inline-block; ' + (props.style || '')">
        <t t-if="state.error">
            <i class="fa fa-circle-o" t-att-style="'font-size:' + (size * 0.8) + 'px; color:' + (props.color || '#6B7280') + ';'"/>
        </t>
    </div>
`;

export default LottieIcon;
