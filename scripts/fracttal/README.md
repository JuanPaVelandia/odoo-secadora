# Migración Fracttal → Mantenimiento Odoo

Carga el historial de mantenimiento de Fracttal (el software que se usaba
antes) en el módulo de mantenimiento de Odoo v19.

## Qué se migra

| Origen (Excel) | Destino en Odoo | Volumen |
|---|---|---|
| `ACTIVOS.xlsx` | `maintenance.equipment` | 265 (195 raíz + 70 componentes) |
| `UBICACIONES.xlsx` | `secadora.lugar` / `secadora.origen.muestra` | 24 → se reusan las existentes |
| Fuentes de recurso | (solo texto en el costo) | no se crean contactos |
| `OT-RECURSOS.xlsx` | `maintenance.request` + `maintenance.historic.cost` | 1.171 OT / 5.861 líneas |
| `Horómetros/*.xlsx` | `maintenance.horometro.reading` | 833 lecturas en 21 tractores |
| `MEDIDORES_HOY.xlsx` | `horometro_last_maintenance` del equipo | 21 medidores |

Costo histórico total: **$1.744.781.022,41** (cuadra al peso con el origen).

## Decisiones de mapeo

Todas viven en `mapeo.py`; si algo hay que reclasificar, se toca ese archivo
y se vuelve a correr (es idempotente).

**Ubicaciones — sin duplicar.** Las fincas ya existen como `secadora.lugar` y
se reusan (ojo: Fracttal dice `FINCA ALIANZA`, Odoo `FINCA LA ALIANZA`). Las
áreas internas de planta (Prelimpieza, Secamiento, Almacenamiento) **no** se
crean como lugar: se reusa el catálogo `secadora.origen.muestra` de
`secadora_calidad` mediante el campo `origen_muestra_id`. Solo se crean los
lugares que realmente falten (La Milagrosa, Don Ruperto) y las dos áreas que
no estaban (Laboratorio, Subestación).

**Talleres.** No son ubicación de maquinaria sino quien presta el servicio. La
migración **no da de alta contactos**: el catálogo se comparte con contabilidad
y el campo "Fuente del Recurso" de Fracttal es texto libre (mezcla talleres
reales con descripciones del trabajo: "MOTOR NUEVO", "TAPIZADO", "-"). El
nombre del taller queda siempre en el costo (`source_name`); si además existe
ya como contacto en Odoo, se enlaza.

**Compañías**, por el sufijo del nombre del activo:
`FT` → Felipe Tibocha · `JPV` → Juan Pablo Velandia · `JV`, `LC` y sin
sufijo → José Velandia. Los combinados (`FT/JPV`) van al primero.

**Costos.** `maintenance.equipment.cost.line` exige una línea de factura y el
histórico no la tiene, así que va a `maintenance.historic.cost`: suma en el
total del equipo y de la OT, sin tocar contabilidad. Desde el corte del
1-ago-2026 los costos nuevos siguen entrando por factura como hasta ahora.

**Historial de ubicación.** `lugar_id` guarda dónde está el equipo hoy;
`maintenance.equipment.location.history` conserva de dónde viene.

**OT contra la finca completa.** 13 órdenes no apuntaban a una máquina sino a
la finca (vías, cercas). Van a un equipo genérico `<FINCA> - INFRAESTRUCTURA`
en vez de perderse.

## Cómo se corre

Requisito: el módulo `maintenance_purchase_link` **≥ 19.0.4.0.0** actualizado
en el servidor (trae los campos y modelos nuevos):

```bash
sudo -u odoo19 git -C /opt/odoo19/custom_addons/odoo-secadora pull origin secadora-19
systemctl stop odoo19
sudo -u odoo19 /opt/odoo19/odoo/odoo-venv/bin/python /opt/odoo19/odoo/odoo-bin \
    -c /etc/odoo19.conf -d odoo_prueba_4 -u maintenance_purchase_link --stop-after-init
systemctl start odoo19
```

Luego, desde `scripts/fracttal/`:

```bash
python3 migrar.py --db=odoo_prueba_4              # simulacro: no escribe nada
python3 migrar.py --db=odoo_prueba_4 --aplicar    # carga real
python3 verificar.py --db=odoo_prueba_4           # contrasta contra los Excel
```

Por defecto **simula**: sin `--aplicar` no escribe. Para cargar por etapas:
`--paso=catalogos,activos,horometros,ordenes` (en ese orden; cada una depende
de la anterior).

Volver a correrlo no duplica: los equipos se emparejan por `external_ref` y
las OT por su id de Fracttal, así que una segunda pasada solo carga lo que
falte. Útil si algo se interrumpe a medias.

Cuando esté validado en `odoo_prueba_4`, se repite con `--db=secadora_2`.
