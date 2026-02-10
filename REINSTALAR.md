# Cómo Reinstalar el Módulo (Para Desarrollo/Pruebas)

Cuando haces cambios estructurales en los modelos (nuevos campos, cambios de tipo, etc.) y los datos actuales NO son importantes, la forma más rápida es **desinstalar y reinstalar**.

## 🔧 Pasos en CloudPepper

### 1. Desinstalar el módulo
1. Ve a **Apps** (Aplicaciones)
2. Quita el filtro "Apps" para ver todos los módulos
3. Busca "Báscula Secadora"
4. Click en **Desinstalar**
5. Confirma la desinstalación

⚠️ **IMPORTANTE**: Esto borrará todos los datos (pesajes, órdenes, vehículos, etc.)

### 2. Actualizar el código
El código ya está actualizado en GitHub, CloudPepper lo sincroniza automáticamente.

### 3. Reinstalar el módulo
1. Ve a **Apps** (Aplicaciones)
2. Click en **Actualizar Lista de Aplicaciones**
3. Busca "Báscula Secadora"
4. Click en **Instalar**

### 4. Verificar que funciona
- Crea una nueva orden de servicio
- Verifica que el campo "Tipo de Servicio" sea un selector desplegable (con opciones del catálogo)
- Crea un pesaje y genera el PDF
- Verifica las reglas automáticas (que permita seleccionar múltiples tipos)

## 📋 Alternativa: Solo actualizar

Si prefieres solo actualizar (aunque puede dar errores por cambios de estructura):

1. Ve a **Apps**
2. Busca "Báscula Secadora"
3. Click en **Actualizar**

Si da error de columna, entonces usa el método de Desinstalar/Reinstalar.

## 🎯 Para cuando sí importe los datos (Producción)

Cuando ya tengas datos reales en producción y necesites actualizar sin perder nada, ahí sí crearemos el script de migración. Por ahora, para desarrollo, desinstalar/reinstalar es más rápido y limpio.
