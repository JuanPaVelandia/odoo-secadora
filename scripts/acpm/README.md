# Cruce del registro de ACPM (hoja "ACPM 2025") con las facturas de Odoo

- `hoja_acpm.tsv`: las 157 compras de la hoja de Google (seis pestañas por finca) al 13-oct-2026.
- `plan_acpm.json`: las 74 facturas de `secadora_2` que coinciden con 30 compras de la hoja
  (ids de factura y de línea, finca de destino).
- `aplicar_cruce_acpm.py`: script de `odoo shell` que marca esas líneas como ACPM de finca,
  crea la campaña 2025-2026 y muestra el resumen. `APLICAR = False` simula con rollback.

Claves del cruce: "Texaco Pore" = Distracom S.A.; "EDS Yopal" = Inversiones Alarcón Rojas.
Distracom factura cada tanque de 216 gal por separado. Las compras a nombre de Felipe Tibocha y
Luis Cubides no se facturan a las empresas. Faltan por cargar en Odoo las facturas de nov-2025 a
jun-2026 y de sep-2026 en adelante: **el cruce se vuelve a correr cuando estén cargadas**.

Informe: https://claude.ai/artifact/UaKfq6z4AXNE4CR5Uz496k

```bash
scp scripts/acpm/plan_acpm.json odoo-vps:/tmp/plan_acpm.json
scp scripts/acpm/aplicar_cruce_acpm.py odoo-vps:/tmp/aplicar_cruce_acpm.py
ssh odoo-vps "sudo -u odoo19 /opt/odoo19/odoo/odoo-venv/bin/python /opt/odoo19/odoo/odoo-bin shell -c /etc/odoo19.conf -d secadora_2 --no-http --log-level=error < /tmp/aplicar_cruce_acpm.py"
```
