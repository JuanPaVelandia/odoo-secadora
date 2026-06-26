# -*- coding: utf-8 -*-
"""
Modelo de Log para Nómina Electrónica DIAN.
Registra validaciones, envíos, respuestas y advertencias.
"""
from odoo import api, fields, models, _


# ================================================================
# CÓDIGOS DE RESPUESTA DEL PROVEEDOR Y DIAN
# Fuente: Anexo Técnico DIAN Resolución 000013 de 2021
# ================================================================

DIAN_RESPONSE_CODES = {
    # --- Respuestas exitosas ---
    '200': {
        'description': 'Documento recibido y aceptado/autorizado por la DIAN.',
        'state_dian': 'exitoso',
        'level': 'success',
        'action': 'Ninguna. El documento fue procesado exitosamente.',
    },
    '299': {
        'description': 'Documento recibido y aceptado/autorizado por la DIAN.',
        'state_dian': 'exitoso',
        'level': 'success',
        'action': 'Ninguna. El documento fue procesado exitosamente.',
    },
    '00': {
        'description': 'Procesado correctamente por DIAN.',
        'state_dian': 'exitoso',
        'level': 'success',
        'action': 'Ninguna. El documento fue procesado exitosamente.',
    },
    # --- Pendientes de validación ---
    '201': {
        'description': 'Documento recibido por el proveedor, se enviará más tarde a la DIAN.',
        'state_dian': 'por_validar',
        'level': 'info',
        'action': 'Esperar y consultar el estado del documento más tarde.',
    },
    '202': {
        'description': 'Documento recibido, entregado a DIAN pero con inconsistencia en la respuesta.',
        'state_dian': 'por_validar',
        'level': 'warning',
        'action': 'Consultar estado del documento directamente en DIAN. '
                  'Puede ser intermitencia del servicio.',
    },
    '203': {
        'description': 'Documento recibido, entregado a DIAN pero con inconsistencia en la respuesta.',
        'state_dian': 'por_validar',
        'level': 'warning',
        'action': 'Consultar estado del documento directamente en DIAN. '
                  'Puede ser intermitencia del servicio.',
    },
    '204': {
        'description': 'Documento recibido, entregado a DIAN pero con inconsistencia en la respuesta.',
        'state_dian': 'por_validar',
        'level': 'warning',
        'action': 'Consultar estado del documento directamente en DIAN. '
                  'Verificar CUNE en: https://catalogo-vpfe.dian.gov.co/document/searchqr?documentkey={CUNE}',
    },
    '208': {
        'description': 'Documento recibido, se enviará más tarde (comunicación en contingencia).',
        'state_dian': 'por_validar',
        'level': 'info',
        'action': 'El servicio DIAN está en contingencia. El proveedor reenviará automáticamente.',
    },
    '90': {
        'description': 'TrackId no encontrado en DIAN o documento procesado anteriormente.',
        'state_dian': 'por_validar',
        'level': 'warning',
        'action': 'En habilitación: el consecutivo ya fue usado bajo otro NIT de pruebas. '
                  'Crear nuevo secuencial con rango mayor. '
                  'En producción: verificar que el secuencial no fue creado en ambiente de habilitación.',
    },
    '66': {
        'description': 'NSU no encontrado en DIAN.',
        'state_dian': 'por_validar',
        'level': 'warning',
        'action': 'Reintentar la consulta de estado más tarde.',
    },
    # --- Errores del proveedor (Token/Formato) ---
    '101': {
        'description': 'El Token del Emisor es inválido.',
        'state_dian': 'error',
        'level': 'error',
        'action': 'Verificar Token Empresa y Token Contraseña en Odoo > Configuración > Compañía. '
                  'Los tokens deben estar en MINÚSCULAS y contener solo números y letras.',
    },
    '109': {
        'description': 'El Documento no superó las validaciones de formato del proveedor.',
        'state_dian': 'error',
        'level': 'error',
        'action': 'Revisar el XML generado. Verificar que todos los campos requeridos '
                  'tengan datos válidos (NIT, nombre, fechas, montos).',
    },
    '110': {
        'description': 'El Documento no superó las validaciones de formato del proveedor.',
        'state_dian': 'error',
        'level': 'error',
        'action': 'Revisar el XML generado. Verificar estructura del documento, '
                  'firma digital y campos obligatorios.',
    },
    '111': {
        'description': 'La longitud en campo de entrada no cumple con el rango permitido.',
        'state_dian': 'error',
        'level': 'error',
        'action': 'Verificar que la razón social no exceda el límite de caracteres. '
                  'Verificar formato de NIT (sin guiones ni DV). '
                  'Verificar que campos de texto no excedan longitudes máximas.',
    },
    # --- Rechazos DIAN ---
    '99': {
        'description': 'Documento rechazado por la DIAN.',
        'state_dian': 'rechazado',
        'level': 'error',
        'action': 'Revisar las reglas de rechazo específicas en el detalle del mensaje. '
                  'Corregir los datos y reenviar el documento.',
    },
    '2': {
        'description': 'Documento rechazado por la DIAN en set de pruebas (habilitación).',
        'state_dian': 'rechazado',
        'level': 'error',
        'action': 'Revisar las reglas de validación en el detalle. Corregir y reenviar. '
                  'En habilitación, las reglas 92 y NIE033 se superan al completar el proceso.',
    },
    '63': {
        'description': 'Documento rechazado por la DIAN.',
        'state_dian': 'rechazado',
        'level': 'error',
        'action': 'Revisar las reglas de rechazo en el detalle del mensaje de respuesta.',
    },
    # --- Errores de red/servidor ---
    '504': {
        'description': 'Timeout de conexión con DIAN. El servicio no responde.',
        'state_dian': 'error',
        'level': 'error',
        'action': 'La DIAN presenta intermitencia. Reintentar el envío más tarde.',
    },
}


# ================================================================
# GLOSARIO DE REGLAS DE RECHAZO DIAN
# Fuente: Anexo Técnico DIAN / Documentación proveedor
# Referencia: Anexo Técnico Resolución DIAN 000013 de 2021
# ================================================================

DIAN_REJECTION_GLOSSARY = {
    # --- Reglas de emisor/habilitación ---
    '92': {
        'rule': 'Regla 92',
        'message': 'El emisor del documento no se encuentra habilitado en la plataforma.',
        'solution': (
            'Verificar que la empresa esté habilitada como emisor de Nómina Electrónica ante DIAN. '
            'Ingresar al portal DIAN > Habilitación > Facturando Electrónicamente. '
            'Si está en ambiente de pruebas, activar habilitación en '
            'portal del proveedor: Configuración > Ambiente.'
        ),
        'category': 'habilitacion',
    },
    'NIE033': {
        'rule': 'Regla NIE033',
        'message': 'Debe ir el NIT del Empleador sin guiones ni DV.',
        'solution': (
            'Verificar que el campo NIT de la empresa no tenga guiones ni dígito de verificación. '
            'Ejemplo correcto: 900390126 (sin guión ni DV). '
            'Corregir en la configuración de la compañía en Odoo (res.company).'
        ),
        'category': 'datos_empresa',
    },
    'NIE024': {
        'rule': 'Regla NIE024',
        'message': 'Se debe indicar el CUNE según la definición establecida.',
        'solution': (
            'El cálculo del CUNE incluye valores con decimales. '
            'DIAN requiere usar solo 2 decimales en los valores totales del documento. '
            'Verificar que total_devengos, total_deducciones y total_paid tengan máximo 2 decimales.'
        ),
        'category': 'cune',
    },
    'NIE032': {
        'rule': 'Regla NIE032',
        'message': 'Debe corresponder al Nombre de la Razón Social del Empleador.',
        'solution': (
            'La razón social del empleador es muy extensa y DIAN tiene límite de caracteres. '
            'Configurar una razón social más corta en el portal del proveedor: '
            'Odoo > Configuración > Compañía (campos de nómina electrónica). '
            'También verificar que coincida exactamente con la registrada en DIAN.'
        ),
        'category': 'datos_empresa',
    },
    'NIAE010': {
        'rule': 'Regla NIAE010',
        'message': 'Debe corresponder a un prefijo elegido por el emisor del documento.',
        'solution': (
            'El prefijo debe ser de 4 caracteres solo ALFABÉTICOS en MAYÚSCULAS. '
            'Ejemplo válido: NOMI, HABB, HABC. '
            'Verificar secuenciales en Odoo > Configuración > Compañía > Secuencias. '
            'También en el portal del proveedor: Datos Fiscales > Secuenciales.'
        ),
        'category': 'secuencial',
    },
    'NIE107': {
        'rule': 'Regla NIE107',
        'message': 'Se debe colocar el Porcentaje que corresponda en horas extras.',
        'solution': (
            'Los porcentajes de horas extras según el anexo técnico DIAN son:\n'
            '  1 - Hora Extra Diurna: 25.00%\n'
            '  2 - Hora Extra Nocturna: 75.00%\n'
            '  3 - Hora Recargo Nocturno: 35.00%\n'
            '  4 - Hora Extra Diurna Dominical y Festivos: 100.00%\n'
            '  5 - Hora Recargo Diurno Dominical y Festivos: 75.00%\n'
            '  6 - Hora Extra Nocturna Dominical y Festivos: 150.00%\n'
            '  7 - Hora Recargo Nocturno Dominical y Festivos: 110.00%\n'
            'Verificar que las reglas salariales de horas extras usen estos porcentajes.'
        ),
        'category': 'devengos',
    },
    'NIAE191a': {
        'rule': 'Regla NIAE191a',
        'message': 'Documento a Reemplazar no se encuentra recibido en la Base de Datos de DIAN.',
        'solution': (
            'Al crear una nota de ajuste tipo "Reemplazar", verificar:\n'
            '  1. Que la nómina individual original esté aprobada (estado "Exitoso" en DIAN)\n'
            '  2. Que el CUNE de referencia (previous_cune) sea correcto\n'
            '  3. Que el número y fecha de emisión del documento original coincidan\n'
            'Puede validar el CUNE original en: '
            'https://catalogo-vpfe.dian.gov.co/document/searchqr?documentkey={CUNE}'
        ),
        'category': 'nota_ajuste',
    },
    'NIE111': {
        'rule': 'Regla NIE111',
        'message': 'Se debe colocar la cantidad de Días. Debe ser la diferencia entre FechaInicio y FechaFin.',
        'solution': (
            'Este rechazo aplica a vacaciones. La cantidad de días debe coincidir con '
            'la diferencia entre FechaInicio y FechaFin, y no puede ser mayor a 30 días. '
            'Si son más de 30 días, usar el concepto "Otros Conceptos de Carácter Salarial" '
            'en lugar de VacacionesComunes.'
        ),
        'category': 'vacaciones',
    },
    'NIE142': {
        'rule': 'Regla NIE142',
        'message': 'Valor Pagado por Auxilios No Salariales.',
        'solution': (
            'Al reportar auxilios no salariales, verificar que el monto del auxilio '
            'se esté colocando correctamente. El campo no reportado debe quedar en Blanco/vacío, '
            'no en cero.'
        ),
        'category': 'devengos',
    },
    # --- Errores de secuencial/ZipKey ---
    'ZipKey': {
        'rule': 'Error ZipKey',
        'message': 'Error al procesar batch. ZipKey inválido.',
        'solution': (
            'Verificar que el identificador del set de pruebas (TestSetID) sea el otorgado '
            'por DIAN y NO el ID Software del proveedor. Pasos:\n'
            '  1. Ingresar al portal de habilitación DIAN: www.dian.gov.co > Habilitación\n'
            '  2. Seleccionar Nómina Electrónica > Set de pruebas\n'
            '  3. Verificar el SetTestId correcto\n'
            '  4. En el portal del proveedor: Datos Fiscales > Secuenciales, '
            'desactivar secuenciales actuales y crear nuevos con rangos mayores.'
        ),
        'category': 'secuencial',
    },
    # --- Errores de servidor/conectividad ---
    'timeout': {
        'rule': 'Error de Timeout',
        'message': 'Error de conexión o timeout con el servicio DIAN.',
        'solution': (
            'La DIAN puede estar presentando intermitencia en su servicio. '
            'Reintentar el envío más tarde. Si persiste, verificar la conectividad del servidor.'
        ),
        'category': 'conectividad',
    },
    'batch_validacion': {
        'rule': 'Batch en proceso de validación',
        'message': 'El documento está en proceso de validación por DIAN.',
        'solution': (
            'Este mensaje indica que DIAN está procesando el documento. '
            'Puede ser por intermitencia del servicio. Esperar y consultar el estado más tarde.'
        ),
        'category': 'conectividad',
    },
    'municipio_vacio': {
        'rule': 'Municipio Ciudad no debe estar vacío',
        'message': 'El campo Municipio/Ciudad está vacío en los datos del empleador o establecimiento.',
        'solution': (
            'Verificar en Odoo > Configuración > Compañía que la dirección '
            'de la empresa tenga municipio/ciudad diligenciado. '
            'También verificar en el portal del proveedor los datos fiscales del establecimiento.'
        ),
        'category': 'datos_empresa',
    },
    'token_invalido': {
        'rule': 'Token Empresa/Password inválido',
        'message': 'El campo tokenEmpresa o tokenPassword no es válido.',
        'solution': (
            'Los tokens deben estar en MINÚSCULAS y contener solo números y letras. '
            'Verificar en Odoo > Configuración > Compañía los campos Token Empresa y Token Contraseña. '
            'Deben ser alfanuméricos en minúsculas. Si están en MAYÚSCULAS, reportar a soporte del proveedor.'
        ),
        'category': 'autenticacion',
    },
    'nit_no_registrado': {
        'rule': 'No muestra número de NIT de la empresa',
        'message': 'El NIT de la empresa no está registrado en el portal del proveedor.',
        'solution': (
            'Verificar que el NIT de la empresa está registrado en los portales:\n'
            'Verificar NIT en Odoo > Configuración > Compañía.\n'
            'Si el NIT no aparece en el proveedor, verificar también en el portal del proveedor.'
        ),
        'category': 'datos_empresa',
    },
    # --- Reglas de campos obligatorios del anexo técnico ---
    'NIE069': {
        'rule': 'Regla NIE069 - DiasTrabajados',
        'message': 'Se debe indicar la cantidad de días que el trabajador estuvo ejecutando sus labores.',
        'solution': (
            'Campo Básico > DiasTrabajados es obligatorio (1-1). '
            'Debe indicar los días laborados en el periodo de pago.'
        ),
        'category': 'basico',
    },
    'NIE070': {
        'rule': 'Regla NIE070 - SueldoTrabajado',
        'message': 'Se debe indicar el valor del sueldo trabajado.',
        'solution': (
            'Campo Básico > SueldoTrabajado es obligatorio (1-1). '
            'Corresponde al valor base o sueldo del trabajador por los días laborados.'
        ),
        'category': 'basico',
    },
    'NIE071': {
        'rule': 'Regla NIE071 - AuxilioTransporte',
        'message': 'Valor de auxilio de transporte incorrecto.',
        'solution': (
            'El auxilio de transporte aplica solo a trabajadores con ingresos hasta 2 SMMLV '
            'que se movilizan físicamente. No aplica para teletrabajo. '
            'No se paga durante vacaciones ni licencias. '
            'Verificar valor vigente en los parámetros anuales de Odoo (Nómina > Configuración).'
        ),
        'category': 'devengos',
    },
    'NIE115': {
        'rule': 'Regla NIE115 - VacacionesCompensadas Cantidad',
        'message': 'Cantidad de días de vacaciones no disfrutadas incorrecta.',
        'solution': (
            'Las vacaciones compensadas (no disfrutadas) deben tener la cantidad de días correcta. '
            'Si son menos de 30 días, usar VacacionesCompensadas. '
            'Si son más de 30 días, usar OtroConcepto (NIE146/NIE147) con descripción "Otros Conceptos de Carácter Salarial".'
        ),
        'category': 'vacaciones',
    },
    'NIE161': {
        'rule': 'Regla NIE161 - Porcentaje Salud',
        'message': 'El porcentaje de deducción de salud no corresponde.',
        'solution': (
            'La cotización de salud corresponde al 12.5% de la base. '
            'La empresa aporta 8.5% y el empleado 4%. '
            'En el XML se reporta el 4% del empleado como deducción. '
            'Campo Salud > Porcentaje (NIE161) es obligatorio (1-1).'
        ),
        'category': 'deducciones',
    },
    'NIE163': {
        'rule': 'Regla NIE163 - Deducción Salud',
        'message': 'El valor de deducción de salud es incorrecto.',
        'solution': (
            'El valor pagado correspondiente a Salud por parte del trabajador. '
            'Debe ser el 4% del total devengado (IBC salud). '
            'Campo Salud > Deducción (NIE163) es obligatorio (1-1).'
        ),
        'category': 'deducciones',
    },
    'NIE164': {
        'rule': 'Regla NIE164 - Porcentaje Pensión',
        'message': 'El porcentaje de deducción de pensión no corresponde.',
        'solution': (
            'La cotización de pensión corresponde al 16% de la base. '
            'La empresa aporta 12% y el empleado 4%. '
            'En el XML se reporta el 4% del empleado como deducción. '
            'Campo FondoPensión > Porcentaje (NIE164) es obligatorio (1-1).'
        ),
        'category': 'deducciones',
    },
    'NIE166': {
        'rule': 'Regla NIE166 - Deducción Pensión',
        'message': 'El valor de deducción de pensión es incorrecto.',
        'solution': (
            'El valor pagado correspondiente a Pensión por parte del trabajador. '
            'Debe ser el 4% del total devengado (IBC pensión). '
            'Campo FondoPensión > Deducción (NIE166) es obligatorio (1-1).'
        ),
        'category': 'deducciones',
    },
    'NIE117': {
        'rule': 'Regla NIE117 - Primas Cantidad',
        'message': 'La cantidad de días para cálculo de prima no es correcta.',
        'solution': (
            'Cuando se paga prima legal, se debe indicar la cantidad de días '
            'a los cuales corresponde el pago de la prima. '
            'La prima se paga en 2 cuotas: junio (max 30 jun) y diciembre (max 20 dic).'
        ),
        'category': 'devengos',
    },
    'NIE118': {
        'rule': 'Regla NIE118 - Primas Pago',
        'message': 'El valor pagado por prima legal es incorrecto.',
        'solution': (
            'Valor pagado por Prima Legal con respecto a la cantidad de días. '
            'Equivale a 15 días de salario por cada semestre trabajado.'
        ),
        'category': 'devengos',
    },
    'NIE120': {
        'rule': 'Regla NIE120 - Cesantías Pago',
        'message': 'El valor pagado por cesantías es incorrecto.',
        'solution': (
            'Cuando el pago de cesantías no se alcanzó a consignar en el fondo, '
            'se reporta como devengo en el concepto Cesantías. '
            'Fórmula: (Salario + Aux. Transporte) x Días trabajados / 360.'
        ),
        'category': 'devengos',
    },
    'NIE121': {
        'rule': 'Regla NIE121 - Porcentaje Intereses Cesantías',
        'message': 'El porcentaje de intereses de cesantías no corresponde.',
        'solution': (
            'Los intereses sobre cesantías son el 12% anual o proporcional. '
            'Se deben pagar directamente al empleado (no al fondo). '
            'Si se debe pagar intereses de cesantías, se reporta en concepto Cesantías.'
        ),
        'category': 'devengos',
    },
    'NIE122': {
        'rule': 'Regla NIE122 - PagoIntereses Cesantías',
        'message': 'El valor pagado por intereses de cesantías es incorrecto.',
        'solution': (
            'Valor pagado por intereses de cesantías otorgada por ley. '
            '12% anual sobre el monto de cesantías acumulado.'
        ),
        'category': 'devengos',
    },
    'NIE109': {
        'rule': 'Regla NIE109 - Vacaciones FechaInicio',
        'message': 'La fecha de inicio de vacaciones es incorrecta.',
        'solution': (
            'FechaInicio solo se diligencia en el mes que el trabajador inicia '
            'el disfrute de vacaciones. Formato: AAAA-MM-DD. '
            'Las vacaciones en Colombia son días hábiles (15 días por año).'
        ),
        'category': 'vacaciones',
    },
    'NIE110': {
        'rule': 'Regla NIE110 - Vacaciones FechaFin',
        'message': 'La fecha de fin de vacaciones es incorrecta.',
        'solution': (
            'FechaFin solo se diligencia en el mes que el trabajador regresa '
            'o termina el disfrute de vacaciones. Formato: AAAA-MM-DD.'
        ),
        'category': 'vacaciones',
    },
    'NIE146': {
        'rule': 'Regla NIE146 - OtroConcepto DescripcionConcepto',
        'message': 'Falta la descripción del otro concepto.',
        'solution': (
            'Al usar OtroConcepto (para vacaciones >30 días u otros pagos), '
            'el campo DescripcionConcepto (NIE146) es obligatorio (1-1). '
            'Debe ir la descripción del concepto.'
        ),
        'category': 'devengos',
    },
    'NIE147': {
        'rule': 'Regla NIE147 - OtroConcepto ConceptoS',
        'message': 'Falta el valor del otro concepto salarial.',
        'solution': (
            'Al usar OtroConcepto, el campo ConceptoS (NIE147) corresponde '
            'al valor de los pagos fijos o variables salariales.'
        ),
        'category': 'devengos',
    },
    # --- Reglas de dirección y datos del empleador ---
    'NIE035': {
        'rule': 'Regla NIE035 - País Empleador',
        'message': 'Se debe colocar el Código alfa-2 correspondiente del país del empleador.',
        'solution': (
            'Verificar en Odoo > Configuración > Compañía que el país tenga '
            'código alfa-2 (ej: CO).'
        ),
        'category': 'datos_empresa',
    },
    'NIE036': {
        'rule': 'Regla NIE036 - DepartamentoEstado Empleador',
        'message': 'Se debe colocar el Código DIAN del departamento del empleador.',
        'solution': (
            'Verificar en Odoo > Configuración > Compañía que el departamento '
            'tenga código DIAN configurado.'
        ),
        'category': 'datos_empresa',
    },
    'NIE037': {
        'rule': 'Regla NIE037 - MunicipioCiudad Empleador',
        'message': 'Se debe colocar el Código DIAN del municipio/ciudad del empleador.',
        'solution': (
            'Verificar en Odoo > Configuración > Compañía que la ciudad '
            'tenga código DIAN configurado.'
        ),
        'category': 'datos_empresa',
    },
    'NIE038': {
        'rule': 'Regla NIE038 - Dirección Empleador',
        'message': 'Debe ir la Dirección Física del Empleador.',
        'solution': (
            'Configurar la dirección física de la empresa en '
            'Odoo > Configuración > Compañía > Dirección.'
        ),
        'category': 'datos_empresa',
    },
    # --- Reglas de datos del trabajador ---
    'NIE044': {
        'rule': 'Regla NIE044 - TipoDocumento Trabajador',
        'message': 'Se debe colocar el Código de tipo de documento del trabajador.',
        'solution': (
            'Configurar el tipo de documento del empleado en '
            'Odoo > Empleados > Información privada > Tipo de documento.'
        ),
        'category': 'datos_trabajador',
    },
    'NIE046': {
        'rule': 'Regla NIE046 - PrimerApellido Trabajador',
        'message': 'Debe ir el Primer Apellido del trabajador.',
        'solution': (
            'Configurar el primer apellido del empleado en el contacto asociado.'
        ),
        'category': 'datos_trabajador',
    },
    'NIE048': {
        'rule': 'Regla NIE048 - PrimerNombre Trabajador',
        'message': 'Debe ir el Primer Nombre del trabajador.',
        'solution': (
            'Configurar el primer nombre del empleado en el contacto asociado.'
        ),
        'category': 'datos_trabajador',
    },
    'NIE050': {
        'rule': 'Regla NIE050 - LugarTrabajoPais',
        'message': 'Se debe colocar el Código alfa-2 del país del lugar de trabajo.',
        'solution': (
            'Verificar que el contacto del empleado tenga país configurado '
            'con código alfa-2.'
        ),
        'category': 'datos_trabajador',
    },
    'NIE051': {
        'rule': 'Regla NIE051 - LugarTrabajoDepartamentoEstado',
        'message': 'Se debe colocar el Código DIAN del departamento del lugar de trabajo.',
        'solution': (
            'Verificar que el departamento del contacto del empleado '
            'tenga código DIAN.'
        ),
        'category': 'datos_trabajador',
    },
    'NIE052': {
        'rule': 'Regla NIE052 - LugarTrabajoMunicipioCiudad',
        'message': 'Se debe colocar el Código DIAN del municipio/ciudad del lugar de trabajo.',
        'solution': (
            'Verificar que la ciudad del contacto del empleado '
            'tenga código DIAN.'
        ),
        'category': 'datos_trabajador',
    },
    'NIE053': {
        'rule': 'Regla NIE053 - LugarTrabajoDirección',
        'message': 'Debe ir la Dirección Física del Trabajador.',
        'solution': (
            'Configurar la dirección del empleado en el contacto asociado en Odoo.'
        ),
        'category': 'datos_trabajador',
    },
    # --- Reglas de contrato ---
    'NIE061': {
        'rule': 'Regla NIE061 - TipoContrato',
        'message': 'Se debe colocar el Código del tipo de contrato.',
        'solution': (
            'Configurar el tipo de contrato en Odoo > Contratos del empleado.'
        ),
        'category': 'datos_contrato',
    },
    'NIE062': {
        'rule': 'Regla NIE062 - Sueldo',
        'message': 'Se debe colocar el Sueldo Base que el Trabajador tiene en la empresa.',
        'solution': (
            'Verificar que el contrato del empleado tenga sueldo base '
            'configurado y mayor a cero.'
        ),
        'category': 'datos_contrato',
    },
    # --- Reglas de valores y totales ---
    'VLR01': {
        'rule': 'Regla VLR01 - Valores Positivos',
        'message': 'Los valores monetarios/porcentajes deben corresponder a valores positivos.',
        'solution': (
            'Verificar que los totales de devengados y deducciones sean positivos. '
            'DIAN no acepta valores negativos.'
        ),
        'category': 'totales',
    },
    'NIE010': {
        'rule': 'Regla NIE010 - Prefijo',
        'message': 'Debe corresponder a un Prefijo elegido por el Emisor del documento.',
        'solution': (
            'Configurar el prefijo en la secuencia de nómina electrónica. '
            'Debe ser letras mayúsculas.'
        ),
        'category': 'secuencial',
    },
    'NIE187': {
        'rule': 'Regla NIE187 - DevengadosTotal',
        'message': 'Debe ir el valor Total de Todos los Devengados del Trabajador.',
        'solution': (
            'Verificar que la suma de todos los devengados sea correcta.'
        ),
        'category': 'totales',
    },
    'NIE188': {
        'rule': 'Regla NIE188 - DeduccionesTotal',
        'message': 'Debe ir el valor Total de Todos las Deducciones del Trabajador.',
        'solution': (
            'Verificar que la suma de todas las deducciones sea correcta.'
        ),
        'category': 'totales',
    },
    'NIE189': {
        'rule': 'Regla NIE189 - ComprobanteTotal',
        'message': 'Debe ser la Diferencia entre DevengadosTotal - DeduccionesTotal.',
        'solution': (
            'El comprobante total debe ser exactamente DevengadosTotal '
            'menos DeduccionesTotal.'
        ),
        'category': 'totales',
    },
}


# ================================================================
# GUÍA DE SITUACIONES - Qué hacer según el caso
# Fuente: Anexo Técnico DIAN / Normativa colombiana
# ================================================================

DIAN_SITUATION_GUIDE = {
    'liquidacion': {
        'title': 'Reporte Liquidación en Nómina Electrónica',
        'steps': [
            '1. Incluir días y sueldo trabajado en el mes (Básico: NIE069 + NIE070)',
            '2. Incluir auxilio de transporte si aplica (NIE071) - solo si <= 2 SMMLV',
            '3. Incluir otros devengos del periodo (horas extras, comisiones, etc)',
            '4. Incluir deducciones Salud (4%) y Pensión (4%) del trabajador',
            '5. Vacaciones no disfrutadas <= 30 días: VacacionesCompensadas',
            '5b. Vacaciones no disfrutadas > 30 días: usar OtroConcepto',
            '6. Prima legal: concepto Prima con días y valor',
            '7. Cesantías no consignadas a fondo: concepto Cesantías',
            '8. Intereses cesantías: se reportan en concepto Cesantías',
            '9. Indemnización por despido sin justa causa: concepto Indemnización',
            '10. Bonificación por retiro: concepto BonificaciónRetiro',
        ],
    },
    'nota_ajuste_reemplazar': {
        'title': 'Nota de Ajuste tipo Reemplazar',
        'steps': [
            '1. La nómina individual original debe estar aprobada (Exitoso en DIAN)',
            '2. El CUNE de referencia debe ser correcto (previous_cune)',
            '3. El documento de reemplazo contiene TODOS los conceptos (no solo los cambiados)',
            '4. Se debe generar y transmitir dentro de los 10 primeros días del mes siguiente',
            '5. Verificar en: https://catalogo-vpfe.dian.gov.co/document/searchqr?documentkey={CUNE}',
        ],
    },
    'nota_ajuste_eliminar': {
        'title': 'Nota de Ajuste tipo Eliminar',
        'steps': [
            '1. La nómina individual original debe estar aprobada (Exitoso en DIAN)',
            '2. Se usa cuando se requiere ELIMINAR completamente el documento',
            '3. El comprobante se emite con los valores en cero (0) y sin datos del empleado',
            '4. Aplica cuando hay errores contables o de procedimiento',
            '5. Se debe generar dentro de los 10 primeros días del mes siguiente',
        ],
    },
    'provisiones': {
        'title': 'Cómo reportar Provisiones en Nómina Electrónica',
        'steps': [
            '1. La nómina electrónica refleja la actualidad contable de la empresa',
            '2. Si se provisionan mensualmente Prima, Cesantías, Int.Cesantías, Vacaciones: reportarlas',
            '3. Obligados a llevar contabilidad: principio de Causación (reportar al causarse)',
            '4. No obligados a llevar contabilidad: principio de Caja (reportar al pagar)',
            '5. Usar los campos existentes del anexo técnico: Primas, Cesantías, VacacionesComunes',
            '6. Los parafiscales (Caja, ICBF, SENA) NO se reportan en nómina electrónica',
        ],
    },
    'aprendiz_sena': {
        'title': 'Nómina Electrónica para Aprendiz SENA (Ley 2466/2025)',
        'steps': [
            '1. A partir de Ley 2466 de 2025, los pagos a aprendices son naturaleza laboral',
            '2. Se DEBE emitir nómina electrónica para aprendices SENA',
            '3. Tipo de contrato: "Aprendizaje" (código 4)',
            '4. Tipo de trabajador: "Aprendices del SENA en etapa lectiva/productiva"',
            '5. Formación tradicional lectiva: 75% SMLMV, práctica: 100% SMLMV',
            '6. Formación dual primer año: 75% SMLMV, segundo año: 100% SMLMV',
            '7. Incluir aportes a salud, riesgos laborales y pensión si aplican',
        ],
    },
    'auxilio_transporte': {
        'title': 'Auxilio de Transporte en Nómina Electrónica',
        'steps': [
            '1. Aplica solo a trabajadores con ingresos hasta 2 SMMLV',
            '2. Verificar valor vigente en los parámetros anuales de Odoo (Nómina > Configuración)',
            '3. NO aplica para teletrabajo o trabajo remoto (usar Auxilio Conectividad)',
            '4. NO se incluye en cálculo de prestaciones sociales',
            '5. NO se paga durante vacaciones ni licencias',
            '6. Se reporta en el concepto Transporte (NIE071)',
        ],
    },
    'auxilio_conectividad': {
        'title': 'Auxilio de Conectividad en Nómina Electrónica',
        'steps': [
            '1. Aplica a trabajadores en teletrabajo o trabajo remoto',
            '2. Verificar valor vigente en los parámetros anuales de Odoo (Nómina > Configuración) (equivalente a auxilio transporte)',
            '3. Aplica si ingresos no superan 2 SMMLV',
            '4. Obligatorio desde 1 julio 2023 (Ley 2026 de 2020)',
            '5. NO se incluye en cálculo de prestaciones sociales',
            '6. NO se paga durante vacaciones ni licencias',
        ],
    },
    'fondo_solidaridad': {
        'title': 'Fondo de Solidaridad Pensional en Nómina Electrónica',
        'steps': [
            '1. Obligatorio para trabajadores con ingresos > 4 SMMLV',
            '2. Entre 4-16 SMMLV: 1% (solidaridad 1%, subsistencia 0%)',
            '3. Entre 16-17 SMMLV: 1.2% (solidaridad 1%, subsistencia 0.2%)',
            '4. Entre 17-18 SMMLV: 1.4% (solidaridad 1%, subsistencia 0.4%)',
            '5. Entre 18-19 SMMLV: 1.6% (solidaridad 1%, subsistencia 0.6%)',
            '6. Entre 19-20 SMMLV: 1.8% (solidaridad 1%, subsistencia 0.8%)',
            '7. Más de 20 SMMLV: 2% (solidaridad 1%, subsistencia 1%)',
        ],
    },
    'horas_extras': {
        'title': 'Porcentajes Horas Extras según DIAN',
        'steps': [
            '1. Hora Extra Diurna: 25% (código 1)',
            '2. Hora Extra Nocturna: 75% (código 2)',
            '3. Hora Recargo Nocturno: 35% (código 3)',
            '4. Hora Extra Diurna Dominical/Festivos: 100% (código 4)',
            '5. Hora Recargo Diurno Dominical/Festivos: 75% (código 5)',
            '6. Hora Extra Nocturna Dominical/Festivos: 150% (código 6)',
            '7. Hora Recargo Nocturno Dominical/Festivos: 110% (código 7)',
        ],
    },
}


class HrPayslipEdiLog(models.Model):
    _name = 'hr.payslip.edi.log'
    _description = 'Log Nómina Electrónica'
    _order = 'create_date desc'

    payslip_edi_id = fields.Many2one(
        'hr.payslip.edi', string='Documento EDI',
        required=True, ondelete='cascade', index=True,
    )
    payslip_run_id = fields.Many2one(
        related='payslip_edi_id.payslip_run_id', store=True,
    )
    employee_id = fields.Many2one(
        related='payslip_edi_id.employee_id', store=True,
    )
    log_type = fields.Selection([
        ('validation', 'Validación'),
        ('send', 'Envío DIAN'),
        ('response', 'Respuesta DIAN'),
        ('status_check', 'Consulta Estado'),
        ('warning', 'Advertencia'),
        ('info', 'Información'),
    ], string='Tipo', required=True, index=True)
    level = fields.Selection([
        ('success', 'Éxito'),
        ('info', 'Info'),
        ('warning', 'Advertencia'),
        ('error', 'Error'),
    ], string='Nivel', required=True, default='info')
    dian_code = fields.Char(string='Código DIAN', index=True)
    summary = fields.Char(string='Resumen', required=True)
    detail = fields.Text(string='Detalle')
    state_dian_result = fields.Selection([
        ('por_notificar', 'Por Notificar'),
        ('error', 'Error'),
        ('por_validar', 'Por Validar'),
        ('exitoso', 'Exitoso'),
        ('rechazado', 'Rechazado'),
    ], string='Estado Resultante')

    @api.model
    def log_validation(self, payslip_edi, errors):
        """Registra errores de validación."""
        logs = []
        for error in errors:
            logs.append({
                'payslip_edi_id': payslip_edi.id,
                'log_type': 'validation',
                'level': 'error',
                'summary': error[:200],
                'detail': error,
            })
        if logs:
            self.create(logs)
        return logs

    @api.model
    def log_dian_response(self, payslip_edi, code, message, raw_response=None):
        """Registra respuesta DIAN con mapeo de código."""
        code_str = str(code).strip()
        code_info = DIAN_RESPONSE_CODES.get(code_str, {})

        vals = {
            'payslip_edi_id': payslip_edi.id,
            'log_type': 'response',
            'level': code_info.get('level', 'warning'),
            'dian_code': code_str,
            'summary': code_info.get('description', message[:200] if message else 'Código %s' % code_str),
            'detail': message or '',
            'state_dian_result': code_info.get('state_dian'),
        }
        if raw_response:
            vals['detail'] = '%s\n\n--- RAW ---\n%s' % (
                message or '', raw_response[:5000]
            )
        return self.create(vals)

    @api.model
    def log_send(self, payslip_edi, success, message):
        """Registra intento de envío."""
        return self.create({
            'payslip_edi_id': payslip_edi.id,
            'log_type': 'send',
            'level': 'success' if success else 'error',
            'summary': 'Envío exitoso' if success else 'Error en envío',
            'detail': message,
        })

    @api.model
    def log_warning(self, payslip_edi, message):
        """Registra advertencia."""
        return self.create({
            'payslip_edi_id': payslip_edi.id,
            'log_type': 'warning',
            'level': 'warning',
            'summary': message[:200],
            'detail': message,
        })

    @api.model
    def get_state_for_code(self, code):
        """Retorna el state_dian sugerido para un código DIAN."""
        code_str = str(code).strip()
        code_info = DIAN_RESPONSE_CODES.get(code_str)
        if code_info:
            return code_info['state_dian']
        return None

    @api.model
    def get_rejection_help(self, error_message):
        """Busca en el glosario de rechazos DIAN la ayuda para un mensaje de error.

        Busca primero en el modelo dian.rejection.glossary (BD) y si no
        encuentra nada, cae al diccionario hardcoded como respaldo.

        Returns: list of dicts con 'rule', 'message', 'solution', 'category'
        """
        if not error_message:
            return []
        msg_upper = error_message.upper()
        results = []

        # 1) Buscar en modelo BD (dian.rejection.glossary)
        try:
            glossary_records = self.env['dian.rejection.glossary'].search([('active', '=', True)])
            for rec in glossary_records:
                if (rec.code.upper() in msg_upper
                        or (rec.rule or '').upper() in msg_upper
                        or (rec.message or '').upper()[:30] in msg_upper):
                    results.append({
                        'rule': rec.rule,
                        'message': rec.message,
                        'solution': rec.solution,
                        'category': rec.category,
                    })
        except Exception:
            pass

        # 2) Fallback al diccionario hardcoded si no hubo resultados en BD
        if not results:
            for code, info in DIAN_REJECTION_GLOSSARY.items():
                if (code.upper() in msg_upper
                        or info.get('rule', '').upper() in msg_upper
                        or info.get('message', '').upper()[:30] in msg_upper):
                    results.append(info)
        return results

    @api.model
    def log_dian_response_with_help(self, payslip_edi, code, message, raw_response=None):
        """Registra respuesta DIAN con mapeo de código y agrega ayuda del glosario."""
        log = self.log_dian_response(payslip_edi, code, message, raw_response)

        # Buscar ayuda adicional del glosario de rechazos
        helps = self.get_rejection_help(message or '')
        if helps:
            help_texts = []
            for h in helps:
                help_texts.append(
                    '[%s] %s\nSolución: %s' % (
                        h.get('rule', ''), h.get('message', ''), h.get('solution', '')
                    )
                )
            help_detail = '\n\n'.join(help_texts)
            # Agregar la ayuda al detalle del log
            if log.detail:
                log.detail = '%s\n\n--- AYUDA ---\n%s' % (log.detail, help_detail)
            else:
                log.detail = help_detail

        return log
