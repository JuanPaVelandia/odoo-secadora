# Configurar la descarga de facturas desde Google Drive

Las facturas de proveedor se enlazan a Google Drive (campo `x_webviewlink`),
con los documentos **privados**. Para que el reporte "Viajes Facturados por
Pagar" pueda anexar el PDF de cada factura, el servidor de Odoo descarga el
archivo con una **cuenta de servicio** de Google a la que se le comparten los
documentos.

## 1. Google Cloud (una sola vez)

1. Entra a https://console.cloud.google.com con la cuenta dueña de los documentos.
2. Crea un proyecto (ej. "Odoo Secadora Drive").
3. **APIs y servicios → Biblioteca** → busca **Google Drive API** → **Habilitar**.
4. **APIs y servicios → Credenciales → Crear credenciales → Cuenta de servicio**.
   - Nombre: `odoo-drive-lector`. No necesita rol de proyecto.
5. Entra a la cuenta de servicio → **Claves → Agregar clave → Crear clave nueva → JSON**.
   Se descarga un archivo `.json`. Guárdalo bien; es la credencial.
6. Copia el `client_email` del JSON (ej. `odoo-drive-lector@proyecto.iam.gserviceaccount.com`).
7. En **Google Drive**, comparte la **carpeta** donde están las facturas con ese
   `client_email`, permiso **Lector**. Los documentos siguen privados para todos
   menos esa cuenta.

## 2. Subir la credencial al contenedor de Odoo (VPS)

Copiar el JSON al contenedor (ejemplo con el archivo en tu máquina/servidor):

```bash
# En la VPS, con el JSON en /root/drive-sa.json:
docker cp /root/drive-sa.json odoo_enterprise:/etc/odoo/drive-sa.json
docker exec odoo_enterprise chmod 600 /etc/odoo/drive-sa.json
```

> El JSON NO va al repositorio git (es un secreto). Se guarda solo en el servidor.
> Si el contenedor se recrea, hay que volver a copiarlo (o montarlo como volumen).

## 3. Configurar la ruta en Odoo

En Odoo, como administrador: **Ajustes → Técnico → Parámetros del sistema**,
crear/editar:

- Clave: `custom_webviewlink.drive_sa_json_path`
- Valor: `/etc/odoo/drive-sa.json`

O desde el shell de Odoo:

```python
env['ir.config_parameter'].sudo().set_param(
    'custom_webviewlink.drive_sa_json_path', '/etc/odoo/drive-sa.json')
env.cr.commit()
```

## 4. Instalar librerías (si el contenedor se recrea)

```bash
docker exec odoo_enterprise pip install --no-cache-dir --break-system-packages \
    google-api-python-client google-auth
```

## 5. Probar

En el shell de Odoo, con una factura que tenga enlace de Drive:

```python
f = env['account.move'].sudo().search([('x_webviewlink','!=',False)], limit=1)
data = env['custom_webviewlink.drive_downloader'].descargar_pdf(f.x_webviewlink)
print('Descargado' if data else 'FALLÓ', 'bytes:', len(data) if data else 0)
```

Si imprime "Descargado" con bytes > 0, la integración funciona y el reporte
anexará los PDF. Si "FALLÓ", revisar: credencial compartida con la carpeta,
ruta del parámetro correcta, y que el documento sea un PDF subido (no un Google
Doc nativo).
