# ⚠️ Error al Actualizar: AttributeError 'Char' object has no attribute 'ondelete'

## 🔍 ¿Por qué pasa este error?

Este error ocurre porque cambiamos un campo de **Selection** a **Char computed**:

```python
# ANTES (Selection - columna de BD)
tipo_servicio = fields.Selection([...])

# AHORA (Char computed - sin columna de BD)
tipo_servicio = fields.Char(compute='_compute_tipo_servicio_legacy')
```

Cuando intentas **Actualizar** el módulo, Odoo:
1. Ve que `tipo_servicio` cambió de tipo
2. Intenta eliminarlo de la base de datos
3. Se confunde porque ahora es Char computed (no Selection)
4. 💥 ERROR: `AttributeError: 'Char' object has no attribute 'ondelete'`

## ✅ Solución: Desinstalar primero

**NO** uses el botón "Actualizar". Debes **desinstalar** y luego **reinstalar**.

### Pasos correctos:

#### 1️⃣ Desinstalar
1. Ve a **Apps** (Aplicaciones)
2. Quita el filtro que dice "Apps" (arriba a la izquierda)
3. Busca: **"Báscula"**
4. Haz click en los **tres puntos verticales** (⋮) del módulo "Báscula Secadora La Gran Colombia"
5. Selecciona **Desinstalar**
6. Confirma la desinstalación

⚠️ **Esto borrará todos los datos de prueba** (pesajes, órdenes, vehículos, etc.)

#### 2️⃣ Actualizar lista
1. Estando en **Apps**
2. Click en el botón **↻ Actualizar Lista de Aplicaciones** (arriba a la derecha)
3. Confirma
4. Espera que termine

#### 3️⃣ Reinstalar
1. Busca nuevamente: **"Báscula"**
2. Click en **Instalar**
3. Espera que termine la instalación

#### 4️⃣ Verificar
1. Ve a **Báscula** → **Órdenes de Servicio**
2. Click en **Crear**
3. Verifica que el campo **"Tipo de Servicio"** sea un selector desplegable
4. Debe mostrar: "Servicio de Secamiento", "Servicio de Prelimpieza", etc.

## 🎯 ¿Por qué no migración automática?

Como estás en **fase de pruebas** y los datos no son importantes, es más rápido y limpio desinstalar/reinstalar que hacer una migración compleja.

Cuando llegue el momento de **producción** (con datos reales), ahí sí crearemos un script de migración que preserve todo.

## 💡 Tip para el futuro

**Siempre que cambies la estructura de campos** (tipo, relación, etc.) durante desarrollo:
- 🔴 **NO** uses "Actualizar"
- 🟢 **SÍ** usa "Desinstalar → Reinstalar"

Es más rápido y evita errores como este.
