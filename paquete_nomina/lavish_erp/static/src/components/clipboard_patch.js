import { ErrorDialog } from "@web/core/errors/error_dialogs";
import { patch } from "@web/core/utils/patch";

/**
 * Patch para soportar entornos HTTP (sin HTTPS) donde navigator.clipboard
 * no está disponible. Usa execCommand como fallback.
 */
patch(ErrorDialog.prototype, {
    onClickClipboard() {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            return super.onClickClipboard(...arguments);
        }
        // Fallback para HTTP (clipboard API no disponible sin HTTPS)
        const text = `${this.props.name}\n\n${this.props.message}\n\n${this.contextDetails}\n\n${this.props.traceback}`;
        const textarea = document.createElement("textarea");
        textarea.value = text;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.focus();
        textarea.select();
        try {
            document.execCommand("copy");
        } finally {
            document.body.removeChild(textarea);
        }
        this.showTooltip?.();
    },
});
