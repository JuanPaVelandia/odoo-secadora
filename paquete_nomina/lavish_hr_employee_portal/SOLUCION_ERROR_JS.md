# Solución a Errores de JavaScript en el Portal

## ❌ Errores Reportados

```javascript
TypeError: Cannot read properties of null (reading 'remove')
    at /web/assets/1/86ad510/web.assets_frontend_lazy.min.js:8636:2424

TypeError: Cannot set properties of null (setting 'textContent')
    at https://grupocdm.odoo.com/web/assets/1/86ad510/web.assets_frontend_lazy.min.js:8636:2095
```

## 🔍 Causa del Error

Estos errores ocurren cuando el JavaScript de Odoo/Bootstrap intenta acceder a elementos DOM que:
1. No existen en la página
2. Fueron eliminados o no se cargaron correctamente
3. Tienen IDs o clases incorrectas

## ✅ Soluciones Aplicadas

### 1. Integración Correcta de Templates

**Cambio realizado:**
- Los nuevos tabs (Mi Perfil y Chatter) ahora se llaman correctamente con `t-call`
- Insertados en las posiciones correctas del template principal

```xml
<!-- Después del Tab Resumen -->
<t t-call="lavish_hr_employee_portal.portal_tab_mi_perfil"/>

<!-- Después del Tab Préstamos -->
<t t-call="lavish_hr_employee_portal.portal_tab_chatter"/>
```

### 2. Verificación de Actualización

**Pasos para aplicar los cambios:**

```bash
# 1. Actualizar el módulo en Odoo
# Ir a: Aplicaciones > Portal de Empleados > Actualizar

# 2. Limpiar caché del navegador
# CTRL + SHIFT + R (Windows/Linux)
# CMD + SHIFT + R (Mac)

# 3. Reiniciar servidor Odoo (si es necesario)
sudo systemctl restart odoo
```

### 3. Verificación de Assets

El módulo ya tiene configurados los assets en el manifiesto:

```python
'assets': {
    'web.assets_frontend': [
        'lavish_hr_employee_portal/static/src/css/portal_employee.css',
    ],
}
```

## 🔧 Pasos de Diagnóstico

### Paso 1: Verificar que el módulo está actualizado

```bash
# En la consola de Odoo, verificar la versión del módulo
SELECT name, latest_version FROM ir_module_module
WHERE name = 'lavish_hr_employee_portal';
```

### Paso 2: Verificar que los templates existen

```bash
# En la consola de Odoo
SELECT key, name FROM ir_ui_view
WHERE key LIKE '%portal_tab%'
AND model = 'ir.ui.view';
```

Debe mostrar:
- `lavish_hr_employee_portal.portal_tab_mi_perfil`
- `lavish_hr_employee_portal.portal_tab_chatter`

### Paso 3: Verificar elementos DOM en el navegador

Abrir DevTools (F12) y ejecutar en la consola:

```javascript
// Verificar que existen los tabs
console.log('Tab Mi Perfil:', document.getElementById('mi_perfil'));
console.log('Tab Chatter:', document.getElementById('chatter'));

// Verificar nav-links
console.log('Nav links:', document.querySelectorAll('.nav-link'));
```

Todos deben retornar elementos, no `null`.

## 🐛 Si el Error Persiste

### Opción 1: Limpiar Cache de Odoo

```python
# En modo desarrollador, ir a:
# Configuración > Técnico > Vistas
# Buscar: portal_tab_mi_perfil
# Click en "Regenerar"
```

### Opción 2: Verificar Logs de Odoo

```bash
# Ver logs en tiempo real
tail -f /var/log/odoo/odoo.log | grep -i "portal\|template\|error"
```

Buscar errores como:
- `Template not found`
- `View does not exist`
- `QWeb error`

### Opción 3: Reinstalar el Módulo

**⚠️ Solo si las opciones anteriores no funcionan**

```bash
# 1. Hacer backup de la base de datos
# 2. Desinstalar el módulo
# 3. Actualizar lista de aplicaciones
# 4. Reinstalar el módulo
```

## 🎯 Errores Comunes y Soluciones

### Error: "Tab no aparece"

**Causa:** Template no se incluyó correctamente

**Solución:**
```xml
<!-- Verificar que existe esta línea en employee_portal_templates.xml -->
<t t-call="lavish_hr_employee_portal.portal_tab_mi_perfil"/>
```

### Error: "Contenido del tab no se muestra"

**Causa:** ID del tab no coincide con href del nav-link

**Solución:**
```xml
<!-- El nav-link debe tener: -->
<a href="#mi_perfil" data-bs-toggle="tab">...</a>

<!-- El tab debe tener: -->
<div id="mi_perfil" class="tab-pane fade">...</div>
```

### Error: "JavaScript de Bootstrap no funciona"

**Causa:** Assets no se cargan correctamente

**Solución:**
```bash
# Regenerar assets
./odoo-bin --update=lavish_hr_employee_portal --stop-after-init

# O en la interfaz:
# Modo desarrollador > Configuración > Técnico > Assets
# Buscar: web.assets_frontend
# Click en "Regenerar"
```

## ✅ Checklist de Verificación

Después de aplicar los cambios, verificar:

- [ ] Módulo actualizado en Odoo
- [ ] Cache del navegador limpiado
- [ ] Tab "Mi Perfil" visible en la navegación
- [ ] Tab "Mensajes" visible en la navegación
- [ ] Al hacer click en "Mi Perfil", se muestra el contrato
- [ ] Al hacer click en "Mensajes", se muestra el formulario del chatter
- [ ] No hay errores en la consola del navegador (F12)
- [ ] No hay errores en los logs de Odoo

## 📊 Información Técnica

### Templates Involucrados

1. **employee_portal_templates.xml** (Principal)
   - Línea 286: Llamada a portal_tab_mi_perfil
   - Línea 1482: Llamada a portal_tab_chatter

2. **portal_profile_chatter_tabs.xml** (Tabs nuevos)
   - Template: portal_tab_mi_perfil (línea 6)
   - Template: portal_tab_chatter (línea 254)

### Estructura del DOM

```html
<ul class="nav nav-tabs">
  <li><a href="#resumen">Resumen</a></li>
  <li><a href="#mi_perfil">Mi Perfil</a></li>  <!-- NUEVO -->
  <li><a href="#nomina">Nómina</a></li>
  ...
  <li><a href="#chatter">Mensajes</a></li>      <!-- NUEVO -->
</ul>

<div class="tab-content">
  <div id="resumen">...</div>
  <div id="mi_perfil">...</div>  <!-- NUEVO -->
  <div id="nomina">...</div>
  ...
  <div id="chatter">...</div>     <!-- NUEVO -->
</div>
```

## 🔄 Si Necesitas Revertir

Si los cambios causan problemas, puedes revertir temporalmente:

```bash
# 1. Comentar las líneas de t-call en employee_portal_templates.xml
# Línea 286: <!-- <t t-call="...portal_tab_mi_perfil"/> -->
# Línea 1482: <!-- <t t-call="...portal_tab_chatter"/> -->

# 2. Actualizar el módulo
# 3. Limpiar cache

# 4. Investigar el problema con más detalle
```

## 📞 Soporte

Si el error persiste después de aplicar todas las soluciones:

1. Verificar la versión de Odoo (debe ser 19.0)
2. Verificar que Bootstrap 5 está cargado
3. Revisar logs completos de Odoo
4. Contactar al equipo de desarrollo

---

**Nota:** Este documento se actualizará con nuevas soluciones según se identifiquen problemas adicionales.

**Última actualización:** 2025-10-27
