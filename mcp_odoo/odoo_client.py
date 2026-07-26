"""Cliente XML-RPC de Odoo restringido a lectura.

Toda llamada al ORM pasa por `_execute`, que rechaza cualquier método que no
esté en METODOS_PERMITIDOS. Es una barrera de conveniencia: la barrera real
son los permisos del usuario de Odoo con el que se autentica (ver README).
"""

from __future__ import annotations

import os
import xmlrpc.client
from typing import Any

# Únicos métodos del ORM que este cliente puede invocar. Cualquier otro
# (create, write, unlink, los action_*, ...) se rechaza antes de salir a la red.
METODOS_PERMITIDOS = frozenset({
    "search_read",
    "search_count",
    "read",
    "read_group",
    "fields_get",
    "search",
})

# Modelos que nunca se exponen: contienen credenciales, tokens o trazas
# internas que no aportan a una consulta de negocio.
MODELOS_VETADOS = frozenset({
    "res.users.apikeys",
    "res.users.apikeys.description",
    "ir.config_parameter",
    "ir.logging",
    "ir.attachment",
    "auth.totp.device",
    "res.users.deletion",
    "iap.account",
    "ir.mail_server",
    "fetchmail.server",
})

# Campos que se recortan de cualquier resultado, vengan del modelo que vengan.
CAMPOS_VETADOS = frozenset({
    "password",
    "password_crypt",
    "new_password",
    "totp_secret",
    "api_key",
    "smtp_pass",
    "google_drive_refresh_token",
})


class OdooError(RuntimeError):
    """Fallo al hablar con Odoo, ya formateado para mostrar al usuario."""


class OdooReadOnlyClient:
    """Conexión perezosa a Odoo por XML-RPC, limitada a operaciones de lectura."""

    def __init__(
        self,
        url: str | None = None,
        db: str | None = None,
        user: str | None = None,
        password: str | None = None,
        timeout: int = 60,
    ) -> None:
        self.url = (url or os.environ.get("ODOO_URL", "")).rstrip("/")
        self.db = db or os.environ.get("ODOO_DB", "")
        self.user = user or os.environ.get("ODOO_USER", "")
        self.password = password or os.environ.get("ODOO_PASSWORD", "")
        self.timeout = timeout

        faltantes = [
            nombre
            for nombre, valor in (
                ("ODOO_URL", self.url),
                ("ODOO_DB", self.db),
                ("ODOO_USER", self.user),
                ("ODOO_PASSWORD", self.password),
            )
            if not valor
        ]
        if faltantes:
            raise OdooError(
                "Faltan variables de entorno: " + ", ".join(faltantes)
            )

        self._uid: int | None = None
        self._models: xmlrpc.client.ServerProxy | None = None

    # -- conexión --------------------------------------------------------

    def _proxy(self, endpoint: str) -> xmlrpc.client.ServerProxy:
        # allow_none: Odoo devuelve None en campos vacíos.
        return xmlrpc.client.ServerProxy(
            f"{self.url}/xmlrpc/2/{endpoint}", allow_none=True
        )

    @property
    def uid(self) -> int:
        if self._uid is None:
            try:
                uid = self._proxy("common").authenticate(
                    self.db, self.user, self.password, {}
                )
            except Exception as exc:  # red, DNS, TLS, XML mal formado...
                raise OdooError(f"No se pudo contactar con Odoo: {exc}") from exc
            if not uid:
                raise OdooError(
                    "Odoo rechazó las credenciales "
                    f"(usuario {self.user!r}, base {self.db!r})."
                )
            self._uid = uid
        return self._uid

    # -- ejecución -------------------------------------------------------

    def _execute(self, modelo: str, metodo: str, *args: Any, **kwargs: Any) -> Any:
        if metodo not in METODOS_PERMITIDOS:
            raise OdooError(
                f"Método {metodo!r} bloqueado: este conector es de solo lectura."
            )
        if modelo in MODELOS_VETADOS:
            raise OdooError(f"El modelo {modelo!r} no está disponible por seguridad.")

        if self._models is None:
            self._models = self._proxy("object")

        try:
            return self._models.execute_kw(
                self.db, self.uid, self.password, modelo, metodo, list(args), kwargs
            )
        except xmlrpc.client.Fault as fault:
            raise OdooError(_mensaje_de_fault(fault, modelo)) from fault
        except OdooError:
            raise
        except Exception as exc:
            raise OdooError(f"Error consultando {modelo}: {exc}") from exc

    # -- operaciones públicas -------------------------------------------

    def search_read(
        self,
        modelo: str,
        dominio: list | None = None,
        campos: list[str] | None = None,
        limite: int = 50,
        offset: int = 0,
        orden: str | None = None,
    ) -> list[dict]:
        kwargs: dict[str, Any] = {"limit": limite, "offset": offset}
        if campos:
            kwargs["fields"] = [c for c in campos if c not in CAMPOS_VETADOS]
        if orden:
            kwargs["order"] = orden
        filas = self._execute(modelo, "search_read", dominio or [], **kwargs)
        return [_limpiar(fila) for fila in filas]

    def search_count(self, modelo: str, dominio: list | None = None) -> int:
        return self._execute(modelo, "search_count", dominio or [])

    def read_group(
        self,
        modelo: str,
        dominio: list | None = None,
        campos: list[str] | None = None,
        agrupar_por: list[str] | None = None,
        limite: int = 100,
        orden: str | None = None,
    ) -> list[dict]:
        kwargs: dict[str, Any] = {"limit": limite, "lazy": False}
        if orden:
            kwargs["orderby"] = orden
        filas = self._execute(
            modelo,
            "read_group",
            dominio or [],
            campos or [],
            agrupar_por or [],
            **kwargs,
        )
        return [_limpiar(fila) for fila in filas]

    def fields_get(self, modelo: str) -> dict:
        campos = self._execute(
            modelo,
            "fields_get",
            [],
            attributes=["string", "type", "relation", "selection", "help", "required"],
        )
        return {k: v for k, v in campos.items() if k not in CAMPOS_VETADOS}

    def listar_modelos(self, filtro: str | None = None, limite: int = 100) -> list[dict]:
        dominio: list = [("transient", "=", False)]
        if filtro:
            dominio += [
                "|",
                ("model", "ilike", filtro),
                ("name", "ilike", filtro),
            ]
        modelos = self.search_read(
            "ir.model",
            dominio,
            ["model", "name"],
            limite=limite,
            orden="model asc",
        )
        return [m for m in modelos if m.get("model") not in MODELOS_VETADOS]


def _limpiar(fila: dict) -> dict:
    """Quita campos sensibles y normaliza los Many2one a algo legible."""
    salida = {}
    for clave, valor in fila.items():
        if clave in CAMPOS_VETADOS:
            continue
        # Odoo devuelve Many2one como [id, "nombre"]; el nombre es lo útil.
        if isinstance(valor, list) and len(valor) == 2 and isinstance(valor[0], int) \
                and isinstance(valor[1], str):
            salida[clave] = {"id": valor[0], "nombre": valor[1]}
        elif valor is False and clave != "active":
            # False es el "vacío" de Odoo en casi todos los tipos; None es más claro.
            salida[clave] = None
        else:
            salida[clave] = valor
    return salida


def _mensaje_de_fault(fault: xmlrpc.client.Fault, modelo: str) -> str:
    """Traduce los errores más comunes de Odoo a algo accionable."""
    detalle = (fault.faultString or "").strip()
    ultima_linea = detalle.splitlines()[-1] if detalle else str(fault)

    if "Object" in detalle and "doesn't exist" in detalle:
        return f"El modelo {modelo!r} no existe en esta base de datos."
    if "AccessError" in detalle or "not allowed to access" in detalle:
        return (
            f"El usuario no tiene permiso de lectura sobre {modelo!r}. "
            "Añade el grupo correspondiente en Odoo."
        )
    if "Invalid field" in detalle:
        return (
            f"{ultima_linea} — usa odoo_describir_modelo('{modelo}') "
            "para ver los campos válidos."
        )
    return f"Odoo devolvió un error en {modelo}: {ultima_linea}"
