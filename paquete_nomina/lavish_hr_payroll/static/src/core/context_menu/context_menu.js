/** @odoo-module **/

import { Component, useState, useRef, onMounted, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class ContextMenu extends Component {
    static template = "lavish_hr_payroll.ContextMenu";
    static props = {};

    setup() {
        this.contextMenuService = useService("contextMenu");
        this.menuRef = useRef("menu");

        // Local reactive state
        this.state = useState({
            isOpen: false,
            position: { x: 0, y: 0 },
            items: [],
        });

        this._onStateChanged = null;

        onMounted(() => {
            // Subscribe to service state changes
            this._onStateChanged = (ev) => {
                const newState = ev.detail;
                this.state.isOpen = newState.isOpen;
                this.state.position = { ...newState.position };
                this.state.items = [...newState.items];

                if (newState.isOpen) {
                    requestAnimationFrame(() => this.adjustPosition());
                }
            };
            this.contextMenuService.bus.addEventListener("state-changed", this._onStateChanged);
        });

        onWillUnmount(() => {
            if (this._onStateChanged) {
                this.contextMenuService.bus.removeEventListener("state-changed", this._onStateChanged);
            }
        });
    }

    adjustPosition() {
        const menu = this.menuRef.el;
        if (!menu) return;

        const rect = menu.getBoundingClientRect();
        const viewportWidth = window.innerWidth;
        const viewportHeight = window.innerHeight;

        let { x, y } = this.state.position;

        if (x + rect.width > viewportWidth) {
            x = viewportWidth - rect.width - 10;
        }
        if (y + rect.height > viewportHeight) {
            y = viewportHeight - rect.height - 10;
        }

        x = Math.max(10, x);
        y = Math.max(10, y);

        menu.style.left = `${x}px`;
        menu.style.top = `${y}px`;
    }

    get menuStyle() {
        return `position: fixed; left: ${this.state.position.x}px; top: ${this.state.position.y}px; z-index: 10000;`;
    }

    onItemClick(item) {
        if (item.action) {
            item.action();
        }
        this.contextMenuService.close();
    }
}
