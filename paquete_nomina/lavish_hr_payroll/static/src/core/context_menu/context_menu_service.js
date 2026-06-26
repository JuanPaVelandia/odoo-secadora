/** @odoo-module **/

import { registry } from "@web/core/registry";
import { EventBus } from "@odoo/owl";

/**
 * Context Menu Service
 * Ctrl + Right-click = Custom menu with form actions
 * Actions: Descartar, Guardar, Imprimir, Exportar, etc.
 */
export const contextMenuService = {
    dependencies: ["action", "orm", "notification"],

    start(env, { action, orm, notification }) {
        // Use EventBus for efficient component updates
        const bus = new EventBus();

        const state = {
            isOpen: false,
            position: { x: 0, y: 0 },
            items: [],
        };

        // Get current record info from URL
        const getCurrentRecord = () => {
            const hash = window.location.hash;
            const modelMatch = hash.match(/model=([^&]+)/);
            const idMatch = hash.match(/[&?]id=(\d+)/);
            const viewType = hash.match(/view_type=([^&]+)/);

            return {
                model: modelMatch ? modelMatch[1] : null,
                id: idMatch ? parseInt(idMatch[1]) : null,
                viewType: viewType ? viewType[1] : 'form',
                isFormView: !viewType || viewType[1] === 'form',
            };
        };

        // Get controller buttons state
        const getControllerState = () => {
            const saveBtn = document.querySelector('.o_form_button_save:not(.d-none)');
            const discardBtn = document.querySelector('.o_form_button_cancel:not(.d-none)');
            const editBtn = document.querySelector('.o_form_button_edit:not(.d-none)');

            return {
                canSave: saveBtn && !saveBtn.disabled,
                canDiscard: discardBtn && !discardBtn.disabled,
                canEdit: editBtn && !editBtn.disabled,
                isEditing: !!saveBtn && !saveBtn.classList.contains('d-none'),
            };
        };

        // Build menu items based on context
        const getItems = (target) => {
            const items = [];
            const record = getCurrentRecord();
            const ctrlState = getControllerState();

            // === FORM ACTIONS ===
            if (record.isFormView) {
                items.push({
                    id: 'form_header',
                    label: 'ACCIONES',
                    isHeader: true,
                    icon: 'fa-cogs',
                });

                // Save action
                if (ctrlState.canSave || ctrlState.isEditing) {
                    items.push({
                        id: 'save',
                        label: 'Guardar',
                        icon: 'fa-save',
                        shortcut: 'Ctrl+S',
                        action: () => {
                            const saveBtn = document.querySelector('.o_form_button_save');
                            if (saveBtn) saveBtn.click();
                        },
                    });
                }

                // Discard action
                if (ctrlState.canDiscard || ctrlState.isEditing) {
                    items.push({
                        id: 'discard',
                        label: 'Descartar',
                        icon: 'fa-times',
                        shortcut: 'Escape',
                        action: () => {
                            const discardBtn = document.querySelector('.o_form_button_cancel');
                            if (discardBtn) discardBtn.click();
                        },
                    });
                }

                // Edit action (if viewing)
                if (ctrlState.canEdit) {
                    items.push({
                        id: 'edit',
                        label: 'Editar',
                        icon: 'fa-pencil',
                        action: () => {
                            const editBtn = document.querySelector('.o_form_button_edit');
                            if (editBtn) editBtn.click();
                        },
                    });
                }

                items.push({ separator: true });
            }

            // === PRINT & EXPORT ===
            if (record.model && record.id) {
                items.push({
                    id: 'print_header',
                    label: 'IMPRIMIR / EXPORTAR',
                    isHeader: true,
                    icon: 'fa-print',
                });

                // Print action
                items.push({
                    id: 'print',
                    label: 'Imprimir',
                    icon: 'fa-print',
                    shortcut: 'Ctrl+P',
                    action: () => {
                        const printAction = document.querySelector('.o_cp_action_menus .dropdown-item[data-hotkey="p"]');
                        if (printAction) {
                            printAction.click();
                        } else {
                            window.print();
                        }
                    },
                });

                // Export to PDF
                items.push({
                    id: 'export_pdf',
                    label: 'Exportar PDF',
                    icon: 'fa-file-pdf-o',
                    action: () => window.print(),
                });

                // Export action
                items.push({
                    id: 'export',
                    label: 'Exportar datos',
                    icon: 'fa-download',
                    action: async () => {
                        const actionToggle = document.querySelector('.o_cp_action_menus .dropdown-toggle');
                        if (actionToggle) {
                            actionToggle.click();
                            setTimeout(() => {
                                const exportItem = document.querySelector('.o_cp_action_menus .dropdown-item:has(.fa-upload)');
                                if (exportItem) exportItem.click();
                            }, 100);
                        } else {
                            notification.add("Use el menú Acción para exportar", { type: "info" });
                        }
                    },
                });

                items.push({ separator: true });
            }

            // === SHARE & NAVIGATION ===
            items.push({
                id: 'nav_header',
                label: 'NAVEGACIÓN',
                isHeader: true,
                icon: 'fa-compass',
            });

            items.push({
                id: 'share',
                label: 'Copiar enlace',
                icon: 'fa-link',
                action: () => {
                    navigator.clipboard.writeText(window.location.href);
                    notification.add("Enlace copiado al portapapeles", { type: "success" });
                },
            });

            items.push({
                id: 'new_tab',
                label: 'Abrir en nueva pestaña',
                icon: 'fa-external-link',
                action: () => window.open(window.location.href, '_blank'),
            });

            items.push({
                id: 'refresh',
                label: 'Actualizar',
                icon: 'fa-refresh',
                shortcut: 'F5',
                action: () => window.location.reload(),
            });

            items.push({
                id: 'split_view',
                label: 'Vista dividida',
                icon: 'fa-columns',
                action: () => {
                    if (env.services.splitScreen) {
                        env.services.splitScreen.toggle();
                    } else {
                        window.open(window.location.href, '_blank', 'width=800,height=600,left=100,top=100');
                    }
                },
            });

            // === SELECTION ===
            const selection = window.getSelection();
            if (selection && selection.toString().trim()) {
                items.push({ separator: true });
                items.push({
                    id: 'copy_selection',
                    label: 'Copiar texto seleccionado',
                    icon: 'fa-copy',
                    action: () => {
                        navigator.clipboard.writeText(selection.toString());
                        notification.add("Texto copiado", { type: "success" });
                    },
                });
            }

            return items;
        };

        // Open menu
        const open = (ev) => {
            ev.preventDefault();
            ev.stopPropagation();

            state.position = { x: ev.clientX, y: ev.clientY };
            state.items = getItems(ev.target);
            state.isOpen = true;
            bus.trigger("state-changed", { ...state });
        };

        // Close menu
        const close = () => {
            if (state.isOpen) {
                state.isOpen = false;
                state.items = [];
                bus.trigger("state-changed", { ...state });
            }
        };

        // Event listener for Ctrl+Right-click only
        const handleContextMenu = (ev) => {
            if (ev.ctrlKey && !ev.target.closest('[contenteditable="true"]')) {
                open(ev);
            }
        };

        // Close on click outside
        const handleClick = (ev) => {
            if (state.isOpen && !ev.target.closest('.lavish-context-menu')) {
                close();
            }
        };

        // Close on Escape
        const handleKeydown = (ev) => {
            if (ev.key === 'Escape' && state.isOpen) {
                close();
            }
        };

        document.addEventListener('contextmenu', handleContextMenu);
        document.addEventListener('click', handleClick, { passive: true });
        document.addEventListener('keydown', handleKeydown, { passive: true });

        return {
            bus,
            state,
            open,
            close,
            getItems,
            getCurrentRecord,
        };
    },
};

registry.category("services").add("contextMenu", contextMenuService);
