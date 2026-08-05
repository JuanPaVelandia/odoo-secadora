# -*- coding: utf-8 -*-
from odoo import models, fields, api, _, Command
from odoo.exceptions import ValidationError, UserError
from odoo.tools.safe_eval import safe_eval

# Template HTML por defecto actualizado para Odoo 18
DEFAULT_HTML_TEMPLATE = '''
<div style="font-family: Arial, Helvetica, sans-serif; max-width: 900px; margin: 0 auto; font-size: 11px; color: #1a1a1a;">
    <!-- Encabezado DIAN -->
    <table style="width: 100%; border-collapse: collapse; border: 2px solid #003366;">
        <tr>
            <td style="width: 15%; padding: 4px; border: 1px solid #003366; text-align: center; vertical-align: middle;">
                <img src="{logo_dian}" style="max-height: 32px; max-width: 100%; display: inline-block;" alt="DIAN"/>
                <div style="font-size: 7px; color: #666; margin-top: 2px;">Formato 220</div>
            </td>
            <td style="width: 70%; padding: 8px; text-align: center; border: 1px solid #003366;">
                <div style="font-size: 13px; font-weight: bold; color: #003366;">
                    Certificado de Ingresos y Retenciones por Rentas de Trabajo<br/>y de Pensiones - Año Gravable {year}
                </div>
                <div style="font-size: 8px; color: #666; margin-top: 3px;">
                    Antes de diligenciar este formulario lea cuidadosamente las instrucciones
                </div>
            </td>
            <td style="width: 15%; padding: 6px; border: 1px solid #003366;">
                <div style="font-size: 8px; color: #003366; font-weight: bold;">4. No. Formulario</div>
                <div style="font-size: 11px; padding: 2px 0;">{val4}</div>
            </td>
        </tr>
    </table>

    <!-- Sección Retenedor -->
    <table style="width: 100%; border-collapse: collapse; border: 1px solid #003366; border-top: none;">
        <tr style="background-color: #003366; color: white;">
            <td colspan="12" style="padding: 3px 8px; font-weight: bold; font-size: 10px;">DATOS DEL RETENEDOR</td>
        </tr>
        <tr>
            <td style="width: 12%; padding: 3px 5px; border: 1px solid #99b3cc; background: #e8f0fe; font-size: 8px; font-weight: bold; color: #003366; vertical-align: top;">5. NIT</td>
            <td style="width: 15%; padding: 3px 5px; border: 1px solid #99b3cc; vertical-align: top;">{val5}</td>
            <td style="width: 6%; padding: 3px 5px; border: 1px solid #99b3cc; background: #e8f0fe; font-size: 8px; font-weight: bold; color: #003366; vertical-align: top;">6. DV</td>
            <td style="width: 5%; padding: 3px 5px; border: 1px solid #99b3cc; vertical-align: top;">{val6}</td>
            <td style="padding: 3px 5px; border: 1px solid #99b3cc; background: #e8f0fe; font-size: 8px; font-weight: bold; color: #003366; vertical-align: top;">7. Primer Apellido</td>
            <td style="padding: 3px 5px; border: 1px solid #99b3cc; vertical-align: top;">{val7}</td>
            <td style="padding: 3px 5px; border: 1px solid #99b3cc; background: #e8f0fe; font-size: 8px; font-weight: bold; color: #003366; vertical-align: top;">8. Segundo Apellido</td>
            <td style="padding: 3px 5px; border: 1px solid #99b3cc; vertical-align: top;">{val8}</td>
            <td style="padding: 3px 5px; border: 1px solid #99b3cc; background: #e8f0fe; font-size: 8px; font-weight: bold; color: #003366; vertical-align: top;">9. Primer Nombre</td>
            <td style="padding: 3px 5px; border: 1px solid #99b3cc; vertical-align: top;">{val9}</td>
            <td style="padding: 3px 5px; border: 1px solid #99b3cc; background: #e8f0fe; font-size: 8px; font-weight: bold; color: #003366; vertical-align: top;">10. Otros</td>
            <td style="padding: 3px 5px; border: 1px solid #99b3cc; vertical-align: top;">{val10}</td>
        </tr>
        <tr>
            <td style="padding: 3px 5px; border: 1px solid #99b3cc; background: #e8f0fe; font-size: 8px; font-weight: bold; color: #003366;">11. Razon Social</td>
            <td colspan="11" style="padding: 3px 5px; border: 1px solid #99b3cc;">{val11}</td>
        </tr>
        <tr>
            <td style="padding: 3px 5px; border: 1px solid #99b3cc; background: #e8f0fe; font-size: 8px; font-weight: bold; color: #003366;">12. Direccion</td>
            <td colspan="5" style="padding: 3px 5px; border: 1px solid #99b3cc;">{val12}</td>
            <td style="padding: 3px 5px; border: 1px solid #99b3cc; background: #e8f0fe; font-size: 8px; font-weight: bold; color: #003366;">13. Cod.Dpto</td>
            <td colspan="2" style="padding: 3px 5px; border: 1px solid #99b3cc;">{val13}</td>
            <td style="padding: 3px 5px; border: 1px solid #99b3cc; background: #e8f0fe; font-size: 8px; font-weight: bold; color: #003366;">14. Cod.Mpio</td>
            <td colspan="2" style="padding: 3px 5px; border: 1px solid #99b3cc;">{val14}</td>
        </tr>
    </table>

    <!-- Sección Empleado -->
    <table style="width: 100%; border-collapse: collapse; border: 1px solid #003366; border-top: none;">
        <tr style="background-color: #003366; color: white;">
            <td colspan="12" style="padding: 3px 8px; font-weight: bold; font-size: 10px;">DATOS DEL TRABAJADOR O PENSIONADO</td>
        </tr>
        <tr>
            <td style="padding: 3px 5px; border: 1px solid #99b3cc; background: #e8f0fe; font-size: 8px; font-weight: bold; color: #003366;">24. T.Doc</td>
            <td style="padding: 3px 5px; border: 1px solid #99b3cc;">{val24}</td>
            <td style="padding: 3px 5px; border: 1px solid #99b3cc; background: #e8f0fe; font-size: 8px; font-weight: bold; color: #003366;">25. No. Identificacion</td>
            <td colspan="2" style="padding: 3px 5px; border: 1px solid #99b3cc;">{val25}</td>
            <td style="padding: 3px 5px; border: 1px solid #99b3cc; background: #e8f0fe; font-size: 8px; font-weight: bold; color: #003366;">26. Primer Apellido</td>
            <td style="padding: 3px 5px; border: 1px solid #99b3cc;">{val26}</td>
            <td style="padding: 3px 5px; border: 1px solid #99b3cc; background: #e8f0fe; font-size: 8px; font-weight: bold; color: #003366;">27. Segundo Apellido</td>
            <td style="padding: 3px 5px; border: 1px solid #99b3cc;">{val27}</td>
            <td style="padding: 3px 5px; border: 1px solid #99b3cc; background: #e8f0fe; font-size: 8px; font-weight: bold; color: #003366;">28. Primer Nombre</td>
            <td style="padding: 3px 5px; border: 1px solid #99b3cc;">{val28}</td>
            <td style="padding: 3px 5px; border: 1px solid #99b3cc; background: #e8f0fe; font-size: 8px; font-weight: bold; color: #003366;">29. Otros</td>
        </tr>
    </table>

    <!-- Sección Periodo -->
    <table style="width: 100%; border-collapse: collapse; border: 1px solid #003366; border-top: none;">
        <tr style="background-color: #003366; color: white;">
            <td colspan="12" style="padding: 3px 8px; font-weight: bold; font-size: 10px;">PERIODO DE CERTIFICACION</td>
        </tr>
        <tr>
            <td style="padding: 3px 5px; border: 1px solid #99b3cc; background: #e8f0fe; font-size: 8px; font-weight: bold; color: #003366;">30. De</td>
            <td style="padding: 3px 5px; border: 1px solid #99b3cc;">{val30}</td>
            <td style="padding: 3px 5px; border: 1px solid #99b3cc; background: #e8f0fe; font-size: 8px; font-weight: bold; color: #003366;">31. A</td>
            <td style="padding: 3px 5px; border: 1px solid #99b3cc;">{val31}</td>
            <td style="padding: 3px 5px; border: 1px solid #99b3cc; background: #e8f0fe; font-size: 8px; font-weight: bold; color: #003366;">32. Fecha Exp.</td>
            <td style="padding: 3px 5px; border: 1px solid #99b3cc;">{val32}</td>
            <td style="padding: 3px 5px; border: 1px solid #99b3cc; background: #e8f0fe; font-size: 8px; font-weight: bold; color: #003366;">33. Lugar</td>
            <td colspan="2" style="padding: 3px 5px; border: 1px solid #99b3cc;">{val33}</td>
            <td style="padding: 3px 5px; border: 1px solid #99b3cc; background: #e8f0fe; font-size: 8px; font-weight: bold; color: #003366;">34. Dpto</td>
            <td style="padding: 3px 5px; border: 1px solid #99b3cc;">{val34}</td>
            <td style="padding: 3px 5px; border: 1px solid #99b3cc; background: #e8f0fe; font-size: 8px; font-weight: bold; color: #003366;">35. Ciudad</td>
        </tr>
    </table>

    <!-- Concepto de Ingresos -->
    <table style="width: 100%; border-collapse: collapse; border: 1px solid #003366; border-top: none;">
        <tr style="background-color: #003366; color: white;">
            <td colspan="3" style="padding: 3px 8px; font-weight: bold; font-size: 10px;">CONCEPTO DE LOS INGRESOS</td>
        </tr>
        <tr style="background-color: #336699; color: white; font-size: 9px;">
            <td style="padding: 3px 8px; border: 1px solid #003366; width: 70%;">Concepto</td>
            <td style="padding: 3px 8px; border: 1px solid #003366; width: 8%; text-align: center;">Reng.</td>
            <td style="padding: 3px 8px; border: 1px solid #003366; width: 22%; text-align: center;">Valor</td>
        </tr>
        <tr><td style="padding: 3px 8px; border: 1px solid #99b3cc;">Pagos por salarios o emolumentos eclesiasticos</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: center; background: #f0f4f8; color: #003366; font-weight: bold;">36</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: right;">{val36}</td></tr>
        <tr><td style="padding: 3px 8px; border: 1px solid #99b3cc; background: #fafcff;">Pagos realizados con bonos electronicos o de papel</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: center; background: #f0f4f8; color: #003366; font-weight: bold;">37</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: right; background: #fafcff;">{val37}</td></tr>
        <tr><td style="padding: 3px 8px; border: 1px solid #99b3cc;">Pagos por honorarios</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: center; background: #f0f4f8; color: #003366; font-weight: bold;">38</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: right;">{val38}</td></tr>
        <tr><td style="padding: 3px 8px; border: 1px solid #99b3cc; background: #fafcff;">Pagos por servicios</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: center; background: #f0f4f8; color: #003366; font-weight: bold;">39</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: right; background: #fafcff;">{val39}</td></tr>
        <tr><td style="padding: 3px 8px; border: 1px solid #99b3cc;">Pagos por comisiones</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: center; background: #f0f4f8; color: #003366; font-weight: bold;">40</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: right;">{val40}</td></tr>
        <tr><td style="padding: 3px 8px; border: 1px solid #99b3cc; background: #fafcff;">Pagos por prestaciones sociales</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: center; background: #f0f4f8; color: #003366; font-weight: bold;">41</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: right; background: #fafcff;">{val41}</td></tr>
        <tr><td style="padding: 3px 8px; border: 1px solid #99b3cc;">Pagos por viaticos</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: center; background: #f0f4f8; color: #003366; font-weight: bold;">42</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: right;">{val42}</td></tr>
        <tr><td style="padding: 3px 8px; border: 1px solid #99b3cc; background: #fafcff;">Pagos por gastos de representacion</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: center; background: #f0f4f8; color: #003366; font-weight: bold;">43</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: right; background: #fafcff;">{val43}</td></tr>
        <tr><td style="padding: 3px 8px; border: 1px solid #99b3cc;">Pagos por compensaciones trabajo asociado cooperativo</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: center; background: #f0f4f8; color: #003366; font-weight: bold;">44</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: right;">{val44}</td></tr>
        <tr><td style="padding: 3px 8px; border: 1px solid #99b3cc; background: #fafcff;">Otros pagos</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: center; background: #f0f4f8; color: #003366; font-weight: bold;">45</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: right; background: #fafcff;">{val45}</td></tr>
        <tr><td style="padding: 3px 8px; border: 1px solid #99b3cc;">Cesantias e intereses efectivamente pagadas</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: center; background: #f0f4f8; color: #003366; font-weight: bold;">46</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: right;">{val46}</td></tr>
        <tr><td style="padding: 3px 8px; border: 1px solid #99b3cc; background: #fafcff;">Cesantias consignadas al fondo</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: center; background: #f0f4f8; color: #003366; font-weight: bold;">47</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: right; background: #fafcff;">{val47}</td></tr>
        <tr><td style="padding: 3px 8px; border: 1px solid #99b3cc;">Pensiones de jubilacion, vejez o invalidez</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: center; background: #f0f4f8; color: #003366; font-weight: bold;">48</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: right;">{val48}</td></tr>
        <tr style="background-color: #ccdbe8; font-weight: bold;"><td style="padding: 4px 8px; border: 1px solid #003366;">Total ingresos brutos (Sume 36 a 48)</td><td style="padding: 4px 8px; border: 1px solid #003366; text-align: center; color: #003366;">49</td><td style="padding: 4px 8px; border: 1px solid #003366; text-align: right;">{val49}</td></tr>
    </table>

    <!-- Concepto de Aportes -->
    <table style="width: 100%; border-collapse: collapse; border: 1px solid #003366; border-top: none;">
        <tr style="background-color: #003366; color: white;">
            <td colspan="3" style="padding: 3px 8px; font-weight: bold; font-size: 10px;">CONCEPTO DE LOS APORTES</td>
        </tr>
        <tr><td style="padding: 3px 8px; border: 1px solid #99b3cc; width: 70%;">Aportes obligatorios por salud a cargo del trabajador</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; width: 8%; text-align: center; background: #f0f4f8; color: #003366; font-weight: bold;">50</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; width: 22%; text-align: right;">{val50}</td></tr>
        <tr><td style="padding: 3px 8px; border: 1px solid #99b3cc; background: #fafcff;">Aportes obligatorios a fondos de pensiones y solidaridad pensional</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: center; background: #f0f4f8; color: #003366; font-weight: bold;">51</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: right; background: #fafcff;">{val51}</td></tr>
        <tr><td style="padding: 3px 8px; border: 1px solid #99b3cc;">Cotizaciones voluntarias al RAIS</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: center; background: #f0f4f8; color: #003366; font-weight: bold;">52</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: right;">{val52}</td></tr>
        <tr><td style="padding: 3px 8px; border: 1px solid #99b3cc; background: #fafcff;">Aportes voluntarios a fondos de pensiones</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: center; background: #f0f4f8; color: #003366; font-weight: bold;">53</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: right; background: #fafcff;">{val53}</td></tr>
        <tr><td style="padding: 3px 8px; border: 1px solid #99b3cc;">Aportes a cuentas AFC</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: center; background: #f0f4f8; color: #003366; font-weight: bold;">54</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: right;">{val54}</td></tr>
        <tr style="background-color: #d4e6f1; font-weight: bold;"><td style="padding: 4px 8px; border: 1px solid #003366;">Retención en la fuente por ingresos laborales y pensiones</td><td style="padding: 4px 8px; border: 1px solid #003366; text-align: center; color: #003366;">55</td><td style="padding: 4px 8px; border: 1px solid #003366; text-align: right;">{val55}</td></tr>
    </table>

    <!-- Datos a cargo del trabajador -->
    <table style="width: 100%; border-collapse: collapse; border: 1px solid #003366; border-top: none;">
        <tr style="background-color: #003366; color: white;">
            <td colspan="6" style="padding: 3px 8px; font-weight: bold; font-size: 10px;">DATOS A CARGO DEL TRABAJADOR O PENSIONADO</td>
        </tr>
        <tr style="background-color: #336699; color: white; font-size: 9px;">
            <td style="padding: 3px 8px; border: 1px solid #003366; width: 42%;">Concepto de otros ingresos</td>
            <td style="padding: 3px 8px; border: 1px solid #003366; width: 5%; text-align: center;">Reng.</td>
            <td style="padding: 3px 8px; border: 1px solid #003366; width: 18%; text-align: center;">Valor Recibido</td>
            <td style="padding: 3px 8px; border: 1px solid #003366; width: 5%; text-align: center;">Reng.</td>
            <td style="padding: 3px 8px; border: 1px solid #003366; width: 18%; text-align: center;">Valor Retenido</td>
        </tr>
        <tr><td style="padding: 3px 8px; border: 1px solid #99b3cc;">Arrendamientos</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: center; background: #f0f4f8; color: #003366; font-weight: bold;">56</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: right;">{val56}</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: center; background: #f0f4f8; color: #003366; font-weight: bold;">63</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: right;">{val63}</td></tr>
        <tr><td style="padding: 3px 8px; border: 1px solid #99b3cc; background: #fafcff;">Honorarios, comisiones y servicios</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: center; background: #f0f4f8; color: #003366; font-weight: bold;">57</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: right; background: #fafcff;">{val57}</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: center; background: #f0f4f8; color: #003366; font-weight: bold;">64</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: right; background: #fafcff;">{val64}</td></tr>
        <tr><td style="padding: 3px 8px; border: 1px solid #99b3cc;">Intereses y rendimientos financieros</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: center; background: #f0f4f8; color: #003366; font-weight: bold;">58</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: right;">{val58}</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: center; background: #f0f4f8; color: #003366; font-weight: bold;">65</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: right;">{val65}</td></tr>
        <tr><td style="padding: 3px 8px; border: 1px solid #99b3cc; background: #fafcff;">Enajenacion de activos fijos</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: center; background: #f0f4f8; color: #003366; font-weight: bold;">59</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: right; background: #fafcff;">{val59}</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: center; background: #f0f4f8; color: #003366; font-weight: bold;">66</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: right; background: #fafcff;">{val66}</td></tr>
        <tr><td style="padding: 3px 8px; border: 1px solid #99b3cc;">Loterias, rifas, apuestas y similares</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: center; background: #f0f4f8; color: #003366; font-weight: bold;">60</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: right;">{val60}</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: center; background: #f0f4f8; color: #003366; font-weight: bold;">67</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: right;">{val67}</td></tr>
        <tr><td style="padding: 3px 8px; border: 1px solid #99b3cc; background: #fafcff;">Otros</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: center; background: #f0f4f8; color: #003366; font-weight: bold;">61</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: right; background: #fafcff;">{val61}</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: center; background: #f0f4f8; color: #003366; font-weight: bold;">68</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: right; background: #fafcff;">{val68}</td></tr>
        <tr style="background-color: #ccdbe8; font-weight: bold;"><td style="padding: 4px 8px; border: 1px solid #003366;">Totales</td><td style="padding: 4px 8px; border: 1px solid #003366; text-align: center; color: #003366;">62</td><td style="padding: 4px 8px; border: 1px solid #003366; text-align: right;">{val62}</td><td style="padding: 4px 8px; border: 1px solid #003366; text-align: center; color: #003366;">69</td><td style="padding: 4px 8px; border: 1px solid #003366; text-align: right;">{val69}</td></tr>
        <tr style="background-color: #fdf2d0; font-weight: bold;"><td colspan="3" style="padding: 4px 8px; border: 1px solid #003366;">Total retenciones año gravable {year} (Sume 55 + 69)</td><td style="padding: 4px 8px; border: 1px solid #003366; text-align: center; color: #003366;">70</td><td style="padding: 4px 8px; border: 1px solid #003366; text-align: right;">{val70}</td></tr>
    </table>

    <!-- Patrimonio -->
    <table style="width: 100%; border-collapse: collapse; border: 1px solid #003366; border-top: none;">
        <tr style="background-color: #003366; color: white;">
            <td colspan="3" style="padding: 3px 8px; font-weight: bold; font-size: 10px;">PATRIMONIO</td>
        </tr>
        <tr style="background-color: #336699; color: white; font-size: 9px;">
            <td style="padding: 3px 8px; border: 1px solid #003366; width: 5%; text-align: center;">Item</td>
            <td style="padding: 3px 8px; border: 1px solid #003366; width: 73%;">71. Identificacion de los bienes y derechos poseidos</td>
            <td style="padding: 3px 8px; border: 1px solid #003366; width: 22%; text-align: center;">72. Valor patrimonial</td>
        </tr>
        <tr><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: center;">1</td><td style="padding: 3px 8px; border: 1px solid #99b3cc;">{val71_1}</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: right;">{val72_1}</td></tr>
        <tr><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: center; background: #fafcff;">2</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; background: #fafcff;">{val71_2}</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: right; background: #fafcff;">{val72_2}</td></tr>
        <tr><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: center;">3</td><td style="padding: 3px 8px; border: 1px solid #99b3cc;">{val71_3}</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: right;">{val72_3}</td></tr>
        <tr><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: center; background: #fafcff;">4</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; background: #fafcff;">{val71_4}</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: right; background: #fafcff;">{val72_4}</td></tr>
        <tr><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: center;">5</td><td style="padding: 3px 8px; border: 1px solid #99b3cc;">{val71_5}</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: right;">{val72_5}</td></tr>
        <tr><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: center; background: #fafcff;">6</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; background: #fafcff;">{val71_6}</td><td style="padding: 3px 8px; border: 1px solid #99b3cc; text-align: right; background: #fafcff;">{val72_6}</td></tr>
        <tr style="background-color: #d4e6f1; font-weight: bold;"><td colspan="2" style="padding: 4px 8px; border: 1px solid #003366;">73. Deudas vigentes a 31 de diciembre de {year}</td><td style="padding: 4px 8px; border: 1px solid #003366; text-align: right;">{val73}</td></tr>
    </table>

    <!-- Dependientes -->
    <table style="width: 100%; border-collapse: collapse; border: 1px solid #003366; border-top: none;">
        <tr style="background-color: #003366; color: white;">
            <td colspan="4" style="padding: 3px 8px; font-weight: bold; font-size: 10px;">IDENTIFICACION DEL DEPENDIENTE ECONOMICO (Paragrafo 2 Art. 387 ET)</td>
        </tr>
        <tr>
            <td style="padding: 3px 5px; border: 1px solid #99b3cc; background: #e8f0fe; font-size: 8px; font-weight: bold; color: #003366; width: 15%;">74. Tipo Doc.<div style="font-weight: normal; font-size: 11px; color: #1a1a1a;">{val74}</div></td>
            <td style="padding: 3px 5px; border: 1px solid #99b3cc; background: #e8f0fe; font-size: 8px; font-weight: bold; color: #003366; width: 20%;">75. No. Documento<div style="font-weight: normal; font-size: 11px; color: #1a1a1a;">{val75}</div></td>
            <td style="padding: 3px 5px; border: 1px solid #99b3cc; background: #e8f0fe; font-size: 8px; font-weight: bold; color: #003366; width: 45%;">76. Apellidos y Nombres<div style="font-weight: normal; font-size: 11px; color: #1a1a1a;">{val76}</div></td>
            <td style="padding: 3px 5px; border: 1px solid #99b3cc; background: #e8f0fe; font-size: 8px; font-weight: bold; color: #003366; width: 20%;">77. Parentesco<div style="font-weight: normal; font-size: 11px; color: #1a1a1a;">{val77}</div></td>
        </tr>
    </table>

    <!-- Certificación UVT -->
    <table style="width: 100%; border-collapse: collapse; border: 1px solid #003366; border-top: none;">
        <tr>
            <td style="padding: 8px; border: 1px solid #99b3cc; font-size: 10px; line-height: 1.5;">
                <strong style="color: #003366;">Certifico que durante el año gravable {year}:</strong><br/>
                1. Mi patrimonio bruto no excedio de 4.500 UVT ({uvt_4500})<br/>
                2. Mis ingresos brutos fueron inferiores a 1.400 UVT ({uvt_1400})<br/>
                3. No fui responsable del impuesto sobre las ventas<br/>
                4. Mis consumos mediante tarjeta de credito no excedieron 1.400 UVT ({uvt_1400})<br/>
                5. Total de compras y consumos no superaron 1.400 UVT ({uvt_1400})<br/>
                6. Consignaciones bancarias, depositos o inversiones no excedieron 1.400 UVT ({uvt_1400})<br/>
                <br/>
                Por lo tanto, manifiesto que no estoy obligado a presentar declaracion de renta por el año gravable {year}
            </td>
            <td style="padding: 8px; border: 1px solid #99b3cc; text-align: center; vertical-align: bottom; width: 30%;">
                <div style="border-top: 1px solid #003366; margin: 0 20px; padding-top: 4px; font-size: 9px; color: #003366; font-weight: bold;">
                    Firma del Trabajador o Pensionado
                </div>
                <div style="height: 40px;"></div>
            </td>
        </tr>
    </table>

    <p style="font-size: 8px; color: #666; margin-top: 4px; line-height: 1.3;">
        <strong>Nota:</strong> Este certificado sustituye para todos los efectos legales la declaracion de Renta y Complementario
        para el trabajador o pensionado que lo firme.
    </p>
</div>
'''


# Mapeo de secuencias del certificado a códigos de reglas salariales por defecto
DEFAULT_SALARY_RULE_MAP = {
    36: [  # Pagos por salarios o emolumentos eclesiásticos
        'BASIC', 'BASIC002', 'BASIC003', 'BASIC004', 'BASIC005',
        'HEYREC001', 'HEYREC002', 'HEYREC003', 'HEYREC004', 'HEYREC005',
        'HEYREC006', 'HEYREC007', 'HEYREC008', 'HEYREC009',
        'BONIF', 'COMISIONES', 'RETRO',
        'INCAPACIDAD001', 'INCAPACIDAD002', 'INCAPACIDAD007', 'EGH',
        'LICENCIA001', 'LUTO',
        'AT', 'EP', 'MAT', 'PAT',
    ],
    37: ['BONOPRI', 'BONNS'],  # Bonos electrónicos o de papel
    41: [  # Prestaciones sociales
        'PRIMA',
        'VACDISFRUTADAS', 'VACANOVE', 'VACATIONS_MONEY', 'VACCONTRATO',
        'CONS_VAC',
    ],
    42: ['VIATICOS'],  # Viáticos
    45: [  # Otros pagos
        'AUX128', 'AUX000', 'AUX00C', 'INDEM', 'PREAVISO',
        'AUX110', 'AUX111', 'AUX112', 'AUX120',
        'INTVIV',
    ],
    46: ['CESANTIAS', 'INTCESANTIAS'],  # Cesantías pagadas al empleado
    47: [  # Cesantías consignadas al fondo
        'CESANTIAS', 'CES_YEAR', 'INTCESANTIAS', 'INTCES_YEAR',
        'CONS_CES', 'CONS_INT',
    ],
    50: ['SSOCIAL001'],  # Aportes obligatorios salud
    51: ['SSOCIAL002', 'SSOCIAL003', 'SSOCIAL004'],  # Pensiones + fondo solidaridad
    53: ['AVP'],  # Aportes voluntarios pensión
    54: ['AFC'],  # Aportes cuentas AFC
    55: ['RT_MET_01', 'RET_PRIMA', 'RTF_INDEM'],  # Retención en la fuente
}

# Mapeo de secuencias de información a campos de modelo
DEFAULT_INFO_FIELDS_MAP = {
    5: {'model': 'res.partner', 'field': 'vat', 'type_partner': 'company'},
    11: {'model': 'res.partner', 'field': 'name', 'type_partner': 'company'},
    25: {'model': 'res.partner', 'field': 'vat', 'type_partner': 'employee'},
    26: {'model': 'res.partner', 'field': 'first_lastname', 'type_partner': 'employee'},
    27: {'model': 'res.partner', 'field': 'second_lastname', 'type_partner': 'employee'},
    28: {'model': 'res.partner', 'field': 'first_name', 'type_partner': 'employee'},
    29: {'model': 'res.partner', 'field': 'second_name', 'type_partner': 'employee'},
}

# Nombres descriptivos para los renglones del certificado DIAN
RENGLON_NAMES = {
    36: 'Pagos por salarios o emolumentos eclesiásticos',
    37: 'Pagos realizados con bonos electrónicos o de papel',
    38: 'Pagos por honorarios',
    39: 'Pagos por servicios',
    40: 'Pagos por comisiones',
    41: 'Pagos por prestaciones sociales',
    42: 'Pagos por viáticos',
    43: 'Pagos por gastos de representación',
    44: 'Pagos por compensaciones trabajo asociado cooperativo',
    45: 'Otros pagos',
    46: 'Cesantías e intereses efectivamente pagadas',
    47: 'Cesantías consignadas al fondo',
    48: 'Pensiones de jubilación, vejez o invalidez',
    49: 'Total ingresos brutos (Sume 36 a 48)',
    50: 'Aportes obligatorios por salud',
    51: 'Aportes obligatorios a fondos de pensiones y solidaridad pensional',
    52: 'Cotizaciones voluntarias al RAIS',
    53: 'Aportes voluntarios a fondos de pensiones',
    54: 'Aportes a cuentas AFC',
    55: 'Retención en la fuente por ingresos laborales y pensiones',
    56: 'Arrendamientos',
    57: 'Honorarios, comisiones y servicios',
    58: 'Intereses y rendimientos financieros',
    59: 'Enajenación de activos fijos',
    60: 'Loterías, rifas, apuestas y similares',
    61: 'Otros',
    62: 'Totales valor recibido',
    63: 'Ret. Arrendamientos',
    64: 'Ret. Honorarios, comisiones y servicios',
    65: 'Ret. Intereses y rendimientos financieros',
    66: 'Ret. Enajenación de activos fijos',
    67: 'Ret. Loterías, rifas, apuestas y similares',
    68: 'Ret. Otros',
    69: 'Totales valor retenido',
    70: 'Total retenciones año gravable (55 + 69)',
    73: 'Deudas vigentes a 31 de diciembre',
}


class HrCertificateIncomeHeader(models.Model):
    """Configuración principal del certificado de ingresos y retenciones"""
    _name = 'l10n_co.exogenous_income_cert_config'
    _description = 'Configuración de Certificado de Ingresos y Retenciones'
    _check_company_auto = True
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'year desc, name'

    # Información básica
    name = fields.Char(
        string='Nombre',
        required=True,
        tracking=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
        tracking=True
    )
    year = fields.Integer(
        string='Año',
        required=True,
        tracking=True,
        default=lambda self: fields.Date.today().year
    )
    active = fields.Boolean(
        string='Activo',
        default=True,
        tracking=True
    )
    description = fields.Text(
        string='Descripción'
    )

    # Datos del formulario
    form_number = fields.Char(
        string='Número de Formulario',
        tracking=True
    )
    issue_date = fields.Date(
        string='Fecha de Expedición',
        tracking=True,
        default=fields.Date.today
    )

    # Valores UVT
    uvt_value = fields.Float(
        string='Valor UVT',
        compute='_compute_uvt_from_annual_params',
        store=True,
        readonly=False,
        tracking=True,
        help='Valor de la UVT obtenido desde Parametros Anuales. Editable manualmente.'
    )
    patrimony_uvt = fields.Float(
        string='UVT Patrimonio',
        default=4500,
        tracking=True,
        help='UVT para límite de patrimonio bruto (típicamente 4.500 UVT)'
    )
    income_uvt = fields.Float(
        string='UVT Ingresos',
        default=1400,
        tracking=True,
        help='UVT para límite de ingresos brutos (típicamente 1.400 UVT)'
    )

    # Valores computados en COP
    patrimony_cop = fields.Monetary(
        string='Patrimonio en COP',
        compute='_compute_cop_values',
        store=True,
        currency_field='currency_id',
        help='Patrimonio bruto en COP (UVT Patrimonio * Valor UVT)'
    )
    income_cop = fields.Monetary(
        string='Ingresos en COP',
        compute='_compute_cop_values',
        store=True,
        currency_field='currency_id',
        help='Ingresos brutos en COP (UVT Ingresos * Valor UVT)'
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        default=lambda self: self.env.company.currency_id
    )

    # Configuración de cuentas contables
    account_ids = fields.Many2many(
        'account.account',
        'l10n_co_exo_income_cert_account_rel',
        'config_id',
        'account_id',
        string='Cuentas Contables',
        check_company=True,
        help="Cuentas contables a considerar en el cálculo"
    )
    excluded_journal_ids = fields.Many2many(
        'account.journal',
        'l10n_co_exo_income_cert_journal_rel',
        'config_id',
        'journal_id',
        string='Diarios Excluidos',
        check_company=True,
        help="Diarios que se excluirán del cálculo"
    )

    # Líneas de configuración
    line_ids = fields.One2many(
        'l10n_co.exogenous_income_cert_line',
        'header_id',
        string='Líneas de Configuración',
        copy=True
    )

    # Template HTML
    report_template = fields.Html(
        string='Plantilla del Certificado',
        default=DEFAULT_HTML_TEMPLATE,
        sanitize=False,
        help='Plantilla HTML del certificado. Use {valNN} para valores dinámicos'
    )

    # Control de completitud
    configuration_complete = fields.Boolean(
        string='Configuración Completa',
        compute='_compute_configuration_status',
        store=True
    )
    missing_items_count = fields.Integer(
        string='Items Faltantes',
        compute='_compute_configuration_status',
        store=True
    )

    # Constraints
    _unique_year_company = models.Constraint(
        'UNIQUE(year, company_id)',
        'Ya existe una configuración para este año y compañía')

    @api.model_create_multi
    def create(self, vals_list):
        """
        Override para auto-llenar desde parámetros anuales y asociar líneas al crear
        SIEMPRE crea con todas las líneas de configuración
        """
        records = super().create(vals_list)
        for record in records:
            # Asociar lineas de configuracion si no existen
            if not record.line_ids:
                # Buscar líneas XML sin encabezado
                orphan_lines = self.env['l10n_co.exogenous_income_cert_line'].search([
                    ('header_id', '=', False),
                    ('annual_parameters_id', '=', False)
                ])

                if orphan_lines:
                    # Asociar líneas huérfanas con este encabezado
                    orphan_lines.write({'header_id': record.id})
                else:
                    # Si no hay líneas huérfanas, crear estructura básica
                    record._create_default_lines()

        return records

    def _create_default_lines(self):
        """
        Crea las líneas de configuración por defecto si no existen
        Define las 30+ líneas estándar del certificado
        """
        self.ensure_one()

        # Definir líneas básicas (las mismas del XML data)
        default_lines = [
            # Líneas de Ingresos (36-49)
            {'sequence': 36, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            {'sequence': 37, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            {'sequence': 38, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            {'sequence': 39, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            {'sequence': 40, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            {'sequence': 41, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            {'sequence': 42, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            {'sequence': 43, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            {'sequence': 44, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            {'sequence': 45, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            {'sequence': 46, 'calculation': 'sum_rule', 'type_partner': 'employee', 'origin_severance_pay': 'employee'},
            {'sequence': 47, 'calculation': 'sum_rule', 'type_partner': 'employee', 'origin_severance_pay': 'fund'},
            {'sequence': 48, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            {'sequence': 49, 'calculation': 'sum_sequence', 'sequence_list_sum': '36,37,38,39,40,41,42,43,44,45,46,47,48'},
            # Líneas de Aportes (50-54)
            {'sequence': 50, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            {'sequence': 51, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            {'sequence': 52, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            {'sequence': 53, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            {'sequence': 54, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            # Línea de Retención (55)
            {'sequence': 55, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            # Datos a cargo del trabajador - Valor Recibido (56-62)
            {'sequence': 56, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            {'sequence': 57, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            {'sequence': 58, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            {'sequence': 59, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            {'sequence': 60, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            {'sequence': 61, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            {'sequence': 62, 'calculation': 'sum_sequence', 'sequence_list_sum': '56,57,58,59,60,61'},
            # Datos a cargo del trabajador - Valor Retenido (63-69)
            {'sequence': 63, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            {'sequence': 64, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            {'sequence': 65, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            {'sequence': 66, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            {'sequence': 67, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            {'sequence': 68, 'calculation': 'sum_rule', 'type_partner': 'employee'},
            {'sequence': 69, 'calculation': 'sum_sequence', 'sequence_list_sum': '63,64,65,66,67,68'},
            # Total retenciones año gravable (70 = 55 + 69)
            {'sequence': 70, 'calculation': 'sum_sequence', 'sequence_list_sum': '55,69'},
            # Líneas de Información del Retenedor (5, 11)
            {'sequence': 5, 'calculation': 'info', 'type_partner': 'company'},
            {'sequence': 11, 'calculation': 'info', 'type_partner': 'company'},
            # Líneas de Información del Empleado (24-29)
            {'sequence': 24, 'calculation': 'info', 'type_partner': 'employee'},
            {'sequence': 25, 'calculation': 'info', 'type_partner': 'employee'},
            {'sequence': 26, 'calculation': 'info', 'type_partner': 'employee'},
            {'sequence': 27, 'calculation': 'info', 'type_partner': 'employee'},
            {'sequence': 28, 'calculation': 'info', 'type_partner': 'employee'},
            {'sequence': 29, 'calculation': 'info', 'type_partner': 'employee'},
            # Líneas de Fechas (30-32)
            {'sequence': 30, 'calculation': 'start_date_year'},
            {'sequence': 31, 'calculation': 'end_date_year'},
            {'sequence': 32, 'calculation': 'date_issue'},
            # Dependientes (74-77)
            {'sequence': 74, 'calculation': 'dependents_type_vat'},
            {'sequence': 75, 'calculation': 'dependents_vat'},
            {'sequence': 76, 'calculation': 'dependents_name'},
            {'sequence': 77, 'calculation': 'dependents_type'},
        ]

        # Crear líneas
        for line_vals in default_lines:
            line_vals['header_id'] = self.id
            self.env['l10n_co.exogenous_income_cert_line'].create(line_vals)

    @api.depends('year', 'company_id')
    def _compute_uvt_from_annual_params(self):
        """Obtiene el valor UVT desde hr.annual.parameters.

        Busca primero el año configurado; si no existe, usa el año anterior como fallback.
        """
        AnnualParams = self.env['hr.annual.parameters']
        for record in self:
            uvt = 0.0
            if record.year:
                annual_params = AnnualParams.search([('year', '=', record.year)], limit=1)
                if not annual_params or not annual_params.value_uvt:
                    annual_params = AnnualParams.search([('year', '=', record.year - 1)], limit=1)
                if annual_params and annual_params.value_uvt:
                    uvt = annual_params.value_uvt
            record.uvt_value = uvt

    @api.depends('uvt_value', 'patrimony_uvt', 'income_uvt')
    def _compute_cop_values(self):
        """Calcula los valores en COP basados en UVT"""
        for record in self:
            record.patrimony_cop = record.uvt_value * record.patrimony_uvt
            record.income_cop = record.uvt_value * record.income_uvt

    @api.depends('line_ids', 'line_ids.salary_rule_id', 'line_ids.information_fields_id')
    def _compute_configuration_status(self):
        """Determina si la configuración está completa"""
        for record in self:
            # Verificar que existan líneas
            if not record.line_ids:
                record.configuration_complete = False
                record.missing_items_count = 100
                continue

            # Contar líneas sin configuración completa
            incomplete = record.line_ids.filtered(
                lambda l: l.calculation in ['sum_rule', 'info'] and
                not (l.salary_rule_id or l.information_fields_id)
            )

            record.missing_items_count = len(incomplete)
            record.configuration_complete = len(incomplete) == 0

    @api.constrains('year')
    def _check_year(self):
        """Valida que el año esté en un rango razonable"""
        for record in self:
            current_year = fields.Date.today().year
            if record.year < 2000 or record.year > current_year + 2:
                raise ValidationError(
                    f'El año debe estar entre 2000 y {current_year + 2}'
                )

    @api.depends('year', 'company_id', 'company_id.name')
    def _compute_display_name(self):
        """Retorna nombre descriptivo"""
        for record in self:
            company_name = record.company_id.name if record.company_id else ''
            record.display_name = f"Certificado {record.year} - {company_name}"

    def copy(self, default=None):
        """Copia la configuración incrementando el año"""
        default = dict(default or {})
        default.update({
            'name': f"{self.name} (Copia)",
            'year': self.year + 1,
        })
        return super().copy(default)

    def action_open_wizard(self):
        """Abre el formulario de Solicitud de Certificado para generar.

        Originalmente abría el wizard `hr.certificate.income.wizard` (definido
        en lavish_hr_employee, no disponible en este sistema). Aquí abrimos
        directamente el form del modelo de Solicitud de Certificado de
        Ingresos (l10n_co.exogenous_income_cert_request), que tiene
        action_generate() para producir el PDF/Excel.
        """
        self.ensure_one()
        return {
            'name': _('Generar Certificado de Ingresos y Retenciones'),
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_co.exogenous_income_cert_request',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_header_id': self.id,
                'default_year': self.year,
                'default_date_from': '%s-01-01' % self.year,
                'default_date_to': '%s-12-31' % self.year,
            }
        }

    def action_compute_from_parameters(self):
        """Fuerza recalculo del UVT desde los parametros anuales"""
        self.ensure_one()
        annual_params = self.env['hr.annual.parameters'].search(
            [('year', '=', self.year)], limit=1)
        if not annual_params:
            raise UserError(_(
                'No se encontraron parametros anuales para el año %(year)s. '
                'Por favor creelos primero.',
                year=self.year,
            ))
        if annual_params.value_uvt:
            self.uvt_value = annual_params.value_uvt

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Valores Actualizados'),
                'message': _('UVT actualizado desde parametros anuales: %s') % self.uvt_value,
                'sticky': False,
                'type': 'success',
            }
        }

    def action_load_default_configuration(self):
        """Carga configuración por defecto: asocia líneas huérfanas o crea estructura completa"""
        self.ensure_one()

        # Buscar líneas de data XML huérfanas y asociarlas
        orphan_lines = self.env['l10n_co.exogenous_income_cert_line'].search([
            ('header_id', '=', False),
            ('annual_parameters_id', '=', False)
        ])

        if orphan_lines:
            orphan_lines.write({'header_id': self.id})

        # Si aún no hay líneas, crear estructura completa
        if not self.line_ids:
            self._create_default_lines()

        total_lines = len(self.line_ids)
        unconfigured = len(self.line_ids.filtered(
            lambda l: l.calculation in ('sum_rule', 'info') and
            not (l.salary_rule_id or l.information_fields_id)
        ))

        msg = _(
            'Configuración cargada: %(total)s líneas creadas. '
            '%(pending)s líneas pendientes de asignar reglas salariales.',
            total=total_lines,
            pending=unconfigured,
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Configuración Cargada'),
                'message': msg,
                'sticky': False,
                'type': 'success' if unconfigured == 0 else 'warning',
            }
        }

    def action_auto_configure_rules(self):
        """Auto-configura reglas salariales y campos de información en las líneas.

        Busca hr.salary.rule por código y las asigna a las líneas según el mapeo
        DEFAULT_SALARY_RULE_MAP. También asigna campos de ir.model.fields para
        las líneas de tipo 'info' según DEFAULT_INFO_FIELDS_MAP.
        """
        self.ensure_one()

        if not self.line_ids:
            raise UserError(_(
                'Primero debe crear las líneas de configuración '
                '(use el botón "Configuración por Defecto").'
            ))

        SalaryRule = self.env['hr.salary.rule']
        ModelFields = self.env['ir.model.fields']

        configured_rules = 0
        configured_info = 0

        # Configurar reglas salariales
        for line in self.line_ids.filtered(lambda l: l.calculation == 'sum_rule'):
            rule_codes = DEFAULT_SALARY_RULE_MAP.get(line.sequence)
            if not rule_codes:
                continue

            rules = SalaryRule.search([('code', 'in', rule_codes)])
            if rules:
                line.salary_rule_id = [Command.set(rules.ids)]
                configured_rules += 1

        # Configurar campos de información
        for line in self.line_ids.filtered(lambda l: l.calculation == 'info'):
            info_spec = DEFAULT_INFO_FIELDS_MAP.get(line.sequence)
            if not info_spec:
                continue

            field = ModelFields.search([
                ('model', '=', info_spec['model']),
                ('name', '=', info_spec['field']),
            ], limit=1)

            if field:
                line.write({
                    'information_fields_id': field.id,
                    'type_partner': info_spec.get('type_partner', 'employee'),
                })
                configured_info += 1

        total = configured_rules + configured_info
        pending = len(self.line_ids.filtered(
            lambda l: l.calculation in ('sum_rule', 'info') and
            not (l.salary_rule_id or l.information_fields_id)
        ))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Configuración Automática'),
                'message': _(
                    '%(total)s líneas configuradas (%(rules)s reglas, %(info)s info). '
                    '%(pending)s líneas pendientes de ajuste manual.',
                    total=total,
                    rules=configured_rules,
                    info=configured_info,
                    pending=pending,
                ),
                'type': 'success' if pending == 0 else 'warning',
                'sticky': False,
            }
        }

    def action_view_configuration_status(self):
        """Muestra el estado de la configuración"""
        self.ensure_one()
        incomplete_lines = self.line_ids.filtered(
            lambda l: l.calculation in ['sum_rule', 'info'] and
            not (l.salary_rule_id or l.information_fields_id)
        )

        return {
            'name': _('Estado de Configuración'),
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_co.exogenous_income_cert_line',
            'view_mode': 'list,form',
            'domain': [('id', 'in', incomplete_lines.ids)],
            'context': {'create': False}
        }


class HrConfCertificateIncome(models.Model):
    """Líneas de configuración para el certificado de ingresos"""
    _name = 'l10n_co.exogenous_income_cert_line'
    _description = 'Líneas de Configuración para Certificado de Ingresos'
    _order = 'header_id, sequence'

    # Relaciones principales
    header_id = fields.Many2one('l10n_co.exogenous_income_cert_config',
        string='Configuración',
        ondelete='cascade',
        index=True,
        check_company=True)
    annual_parameters_id = fields.Many2one(
        'hr.annual.parameters',
        string='Parámetro Anual',
        ondelete='cascade',
        index=True
    )

    # Secuencia y nombre
    sequence = fields.Integer(
        string='Secuencia',
        required=True,
        help='Número de campo en el certificado (ej: 36, 37, etc.)'
    )
    name = fields.Char(
        string='Nombre',
        compute='_compute_name',
        store=True
    )

    # Tipo de cálculo
    calculation = fields.Selection([
        ('info', 'Información'),
        ('sum_rule', 'Sumatoria de Reglas Salariales'),
        ('sum_accounting', 'Sumatoria Contable (account.move.line)'),
        ('sum_rule_accounting', 'Reglas Salariales + Contabilidad'),
        ('average_rule', 'Promedio de Reglas Salariales'),
        ('sum_sequence', 'Sumatoria de Secuencias Anteriores'),
        ('date_issue', 'Fecha de Expedición'),
        ('start_date_year', 'Fecha Inicial de Certificación'),
        ('end_date_year', 'Fecha Final de Certificación'),
        ('dependents_type_vat', 'Dependiente - Tipo Documento'),
        ('dependents_vat', 'Dependiente - Número Documento'),
        ('dependents_name', 'Dependiente - Apellidos y Nombres'),
        ('dependents_type', 'Dependiente - Parentesco'),
    ], string='Tipo de Cálculo', default='info', required=True)

    # Origen de información
    type_partner = fields.Selection([
        ('employee', 'Empleado'),
        ('company', 'Compañía')
    ], string='Origen de Información')

    # Campo de información
    information_fields_id = fields.Many2one(
        'ir.model.fields',
        string="Campo de Información",
        domain="[('model_id.model', 'in', ['hr.employee','res.partner','hr.contract'])]"
    )
    information_fields_relation = fields.Char(
        related='information_fields_id.relation',
        string='Relación del Campo',
        store=True
    )
    related_field_id = fields.Many2one(
        'ir.model.fields',
        string='Campo Relacionado',
        domain="[('model_id.model', '=', information_fields_relation)]"
    )

    # Reglas salariales
    salary_rule_id = fields.Many2many(
        'hr.salary.rule',
        'l10n_co_exo_income_cert_line_salary_rule_rel',
        'line_id',
        'rule_id',
        string='Reglas Salariales'
    )

    # Configuración para cesantías
    origin_severance_pay = fields.Selection([
        ('employee', 'Pagado al Empleado'),
        ('fund', 'Consignado a Fondo')
    ], string='Origen Pago de Cesantías')

    # Configuración para acumulados
    accumulated_previous_year = fields.Boolean(
        string='Incluir Año Anterior',
        help='Incluye valores acumulados del año anterior'
    )
    sequence_list_sum = fields.Char(
        string='Secuencias a Sumar',
        help='Números de secuencia separados por coma (ej: 36,37,38)'
    )

    # Configuración para cesantías pagadas año anterior
    severance_paid_previous_year = fields.Boolean(
        string='Cesantías Pagadas Año Anterior',
        default=False,
        help='Marca si las cesantías fueron pagadas en el año anterior'
    )

    # Configuración contable específica
    account_ids = fields.Many2many(
        'account.account',
        'l10n_co_exo_income_cert_line_account_rel',
        'line_id',
        'account_id',
        string='Cuentas Contables Específicas',
        help="Cuentas contables específicas para esta línea (opcional)"
    )

    # Tipo de movimiento contable
    account_move_type = fields.Selection([
        ('debit', 'Débito'),
        ('credit', 'Crédito'),
        ('both', 'Ambos (Débito + Crédito)')
    ], string='Tipo de Movimiento',
       default='both',
       help='Define si se toman movimientos de débito, crédito o ambos')

    # Diarios excluidos
    excluded_journal_ids = fields.Many2many(
        'account.journal',
        'l10n_co_exo_income_cert_line_journal_rel',
        'line_id',
        'journal_id',
        string='Diarios Excluidos Específicos',
        help="Diarios excluidos específicos para esta línea (opcional)"
    )

    # Filtros adicionales de movimientos contables
    move_state_filter = fields.Selection([
        ('posted', 'Solo Publicados'),
        ('all', 'Todos'),
        ('draft', 'Solo Borradores')
    ], string='Estado de Movimientos',
       default='posted',
       help='Estado de los movimientos contables a incluir')

    exclude_payroll_entries = fields.Boolean(
        string='Excluir Asientos de Nómina',
        default=True,
        help='Excluye automáticamente los asientos contables generados por nómina para evitar duplicados'
    )

    # Categorías de reglas salariales alternativas
    salary_rule_category_ids = fields.Many2many(
        'hr.salary.rule.category',
        'l10n_co_exo_income_cert_line_category_rel',
        'line_id',
        'category_id',
        string='Categorías de Reglas Salariales',
        help='Categorías de reglas salariales asociadas a esta configuración'
    )

    # Dominio personalizado para movimientos contables
    account_move_domain = fields.Char(
        string='Dominio Adicional',
        help='Dominio Odoo adicional para filtrar movimientos contables (ej: [(\'ref\', \'like\', \'ING\')])'
    )

    # Limites y topes
    limit_uvt_factor = fields.Float(
        string='Factor UVT Limite',
        help='Multiplicador de UVT para tope maximo (ej: 41 UVT). Si > 0, el resultado no puede superar este valor * UVT'
    )
    limit_uvt_cop = fields.Float(
        string='Límite UVT en COP',
        compute='_compute_limit_uvt_cop',
        store=True,
        help='Valor equivalente en COP del Factor UVT (Factor * UVT del año)'
    )
    limit_fixed_value = fields.Float(
        string='Limite Fijo (COP)',
        help='Valor maximo fijo en pesos. Si > 0, el resultado no puede superar este valor'
    )

    # Referencia cruzada entre lineas
    reference_sequence = fields.Char(
        string='Secuencias de Referencia',
        help='Secuencias de otras lineas para referencia cruzada, separadas por coma (ej: 49,55)'
    )
    operation_mode = fields.Selection([
        ('none', 'Sin operacion'),
        ('subtract', 'Restar referencia al resultado'),
        ('compare_min', 'Menor entre resultado y referencia'),
        ('compare_max', 'Mayor entre resultado y referencia'),
        ('carry_difference', 'Saldo de diferencia (referencia - resultado)'),
    ], string='Modo de Operacion', default='none',
       help='Define como se aplica la referencia cruzada sobre el valor calculado')

    # Condicion Python
    python_condition = fields.Text(
        string='Condicion Python',
        help='Expresion Python para post-procesamiento. '
             'Variables disponibles: result (valor calculado), uvt (valor UVT), '
             'lines (dict {secuencia: valor}), abs, min, max, round. '
             'Ejemplo: max(result - lines.get(49, 0) * 0.25, 0)'
    )

    # Estado de configuración
    is_configured = fields.Boolean(
        string='Configurado',
        compute='_compute_is_configured',
        store=True
    )

    # Constraints
    _unique_sequence_header = models.Constraint(
        'UNIQUE(header_id, sequence)',
        'Ya existe esta secuencia en la configuración')

    @api.depends('sequence', 'calculation')
    def _compute_name(self):
        """Genera nombre descriptivo"""
        for record in self:
            record.name = f"Campo {record.sequence} - {dict(record._fields['calculation'].selection).get(record.calculation, '')}"

    @api.depends('calculation', 'salary_rule_id', 'information_fields_id',
                 'account_ids', 'sequence_list_sum', 'reference_sequence', 'operation_mode')
    def _compute_is_configured(self):
        """Determina si la línea está correctamente configurada"""
        for record in self:
            if record.calculation == 'sum_rule':
                record.is_configured = bool(record.salary_rule_id)
            elif record.calculation == 'sum_accounting':
                record.is_configured = bool(record.account_ids)
            elif record.calculation == 'sum_rule_accounting':
                record.is_configured = bool(record.salary_rule_id or record.account_ids)
            elif record.calculation == 'average_rule':
                record.is_configured = bool(record.salary_rule_id)
            elif record.calculation == 'info':
                record.is_configured = bool(record.information_fields_id)
            elif record.calculation == 'sum_sequence':
                record.is_configured = bool(record.sequence_list_sum)
            else:
                record.is_configured = True
            # Validar referencia cruzada si tiene operation_mode activo
            if record.operation_mode and record.operation_mode != 'none':
                if not record.reference_sequence:
                    record.is_configured = False

    @api.depends('limit_uvt_factor', 'header_id.uvt_value')
    def _compute_limit_uvt_cop(self):
        """Calcula el equivalente en COP del factor UVT según el valor UVT del año"""
        for record in self:
            if record.limit_uvt_factor and record.header_id and record.header_id.uvt_value:
                record.limit_uvt_cop = record.limit_uvt_factor * record.header_id.uvt_value
            else:
                record.limit_uvt_cop = 0.0

    @api.onchange('header_id')
    def _onchange_header(self):
        """Hereda configuración del encabezado si está vacío"""
        if self.header_id and not self.account_ids:
            self.account_ids = self.header_id.account_ids
        if self.header_id and not self.excluded_journal_ids:
            self.excluded_journal_ids = self.header_id.excluded_journal_ids

    def _get_accounting_value(self, employee, date_from, date_to):
        """
        Calcula el valor desde movimientos contables usando ORM optimizado (_read_group)

        :param employee: Registro de hr.employee
        :param date_from: Fecha inicial del periodo
        :param date_to: Fecha final del periodo
        :return: float con el valor calculado
        """
        self.ensure_one()

        if not self.account_ids:
            return 0.0

        # Construir dominio base
        domain = [
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('account_id', 'in', self.account_ids.ids),
        ]

        # Filtro de estado de movimientos
        if self.move_state_filter == 'posted':
            domain.append(('move_id.state', '=', 'posted'))
        elif self.move_state_filter == 'draft':
            domain.append(('move_id.state', '=', 'draft'))

        # Excluir diarios específicos
        if self.excluded_journal_ids:
            domain.append(('journal_id', 'not in', self.excluded_journal_ids.ids))

        # Excluir asientos de nómina: account.move.payslip_run_id es el campo
        # creado por hr_payroll_extended para enlazar el asiento con la corrida
        # de nómina. Es la forma confiable de identificar movimientos generados
        # por nómina sin depender del nombre del diario o el ref.
        if self.exclude_payroll_entries:
            domain.append(('move_id.payslip_run_id', '=', False))

        # Filtrar por empleado (si la cuenta tiene partner asociado).
        # En Odoo 19 no existe address_home_id: el tercero del empleado es
        # partner_encab_id (lavish_hr_employee) o work_contact_id (core hr).
        partner = employee.partner_encab_id or employee.work_contact_id
        if partner:
            domain.append(('partner_id', '=', partner.id))

        # Dominio adicional personalizado
        if self.account_move_domain:
            try:
                additional_domain = eval(self.account_move_domain)
                if isinstance(additional_domain, list):
                    domain.extend(additional_domain)
            except:
                pass

        MoveLine = self.env['account.move.line']

        if self.account_move_type == 'debit':
            result = MoveLine.read_group(domain, fields=['debit:sum'], groupby=[], lazy=False)
            return float(result[0].get('debit', 0.0)) if result else 0.0

        elif self.account_move_type == 'credit':
            result = MoveLine.read_group(domain, fields=['credit:sum'], groupby=[], lazy=False)
            return float(result[0].get('credit', 0.0)) if result else 0.0

        elif self.account_move_type == 'both':
            result = MoveLine.read_group(domain, fields=['debit:sum', 'credit:sum'], groupby=[], lazy=False)
            if result:
                return float(result[0].get('debit', 0.0)) + float(result[0].get('credit', 0.0))
            return 0.0

        return 0.0

    def _get_payslip_value_by_categories(self, employee, date_from, date_to):
        """
        Calcula el valor desde líneas de nómina usando ORM optimizado (_read_group)

        :param employee: Registro de hr.employee
        :param date_from: Fecha inicial del periodo
        :param date_to: Fecha final del periodo
        :return: float con el valor calculado
        """
        self.ensure_one()

        if not self.salary_rule_category_ids:
            return 0.0

        # Incluir nominas que se solapen con el periodo del certificado
        domain = [
            ('employee_id', '=', employee.id),
            ('date_from', '<=', date_to),
            ('date_to', '>=', date_from),
            ('state_slip', 'in', ['done', 'paid']),
            ('category_id', 'in', self.salary_rule_category_ids.ids)
        ]

        PayslipLine = self.env['hr.payslip.line']
        result = PayslipLine.read_group(domain, fields=['total:sum'], groupby=[], lazy=False)
        return float(result[0].get('total') or 0.0) if result else 0.0

    def _get_payslip_value_by_rules(self, employee, date_from, date_to):
        """
        Calcula el valor desde líneas de nómina usando reglas salariales directamente

        :param employee: Registro de hr.employee
        :param date_from: Fecha inicial del periodo
        :param date_to: Fecha final del periodo
        :return: float con el valor calculado
        """
        self.ensure_one()

        if not self.salary_rule_id:
            return 0.0

        # Incluir nominas que se solapen con el periodo del certificado
        # Una nomina entra si su date_from O date_to caen dentro del rango
        domain = [
            ('employee_id', '=', employee.id),
            ('date_from', '<=', date_to),
            ('date_to', '>=', date_from),
            ('state_slip', 'in', ['done', 'paid']),
            ('salary_rule_id', 'in', self.salary_rule_id.ids)
        ]

        # Filtro por origen de cesantias (pagadas al empleado vs consignadas al fondo)
        if self.origin_severance_pay:
            if self.origin_severance_pay == 'employee':
                domain.append(('slip_id.employee_severance_pay', '=', True))
            elif self.origin_severance_pay == 'fund':
                domain.append(('slip_id.employee_severance_pay', '=', False))

        PayslipLine = self.env['hr.payslip.line']
        result = PayslipLine.read_group(domain, fields=['total:sum'], groupby=[], lazy=False)
        return float(result[0].get('total') or 0.0) if result else 0.0

    def _get_average_payslip_value(self, employee, date_from, date_to):
        """
        Calcula el promedio mensual de reglas salariales en el periodo.
        Usado para el renglon 59 del formulario 220 DIAN:
        'Ingreso laboral promedio de los ultimos seis meses anteriores'

        :param employee: Registro de hr.employee
        :param date_from: Fecha inicial del periodo
        :param date_to: Fecha final del periodo
        :return: float con el promedio mensual
        """
        self.ensure_one()

        if not self.salary_rule_id:
            return 0.0

        # Incluir nominas que se solapen con el periodo
        domain = [
            ('employee_id', '=', employee.id),
            ('date_from', '<=', date_to),
            ('date_to', '>=', date_from),
            ('state_slip', 'in', ['done', 'paid']),
            ('salary_rule_id', 'in', self.salary_rule_id.ids)
        ]

        PayslipLine = self.env['hr.payslip.line']
        result = PayslipLine.read_group(domain, fields=['total:sum'], groupby=[], lazy=False)
        total = float(result[0].get('total') or 0.0) if result else 0.0

        if total == 0.0:
            return 0.0

        # Contar meses unicos de nominas en el periodo
        slip_domain = [
            ('employee_id', '=', employee.id),
            ('date_from', '<=', date_to),
            ('date_to', '>=', date_from),
            ('state', 'in', ['done', 'paid']),
        ]
        slips = self.env['hr.payslip'].search(slip_domain)
        if not slips:
            return 0.0

        # Contar meses unicos
        months = set()
        for slip in slips:
            months.add((slip.date_from.year, slip.date_from.month))
        num_months = len(months) or 1

        return total / num_months

    def _get_sum_from_sequences(self, lines_results, sequence_list):
        """Suma valores de secuencias previamente calculadas

        :param lines_results: dict {secuencia: valor} con resultados anteriores
        :param sequence_list: string con secuencias separadas por coma (ej: '36,37,38')
        :return: float con la suma total
        """
        if not sequence_list or not lines_results:
            return 0.0
        total = 0.0
        for seq_str in sequence_list.split(','):
            try:
                seq = int(seq_str.strip())
                total += lines_results.get(seq, 0.0)
            except (ValueError, TypeError):
                pass
        return total

    def _apply_post_processing(self, value, lines_results=None):
        """Aplica límites, referencias cruzadas y condiciones Python al valor calculado

        Orden de aplicación:
        1. Límites UVT y fijos (tope máximo)
        2. Operaciones de referencia cruzada
        3. Condición Python personalizada

        :param value: Valor bruto calculado
        :param lines_results: dict {secuencia: valor} con resultados de otras líneas
        :return: float con el valor post-procesado
        """
        if lines_results is None:
            lines_results = {}

        # 1. Limites/topes
        if self.limit_uvt_factor and self.limit_uvt_factor > 0:
            uvt_value = self.header_id.uvt_value if self.header_id else 0
            if uvt_value > 0:
                max_uvt = self.limit_uvt_factor * uvt_value
                value = min(value, max_uvt)

        if self.limit_fixed_value and self.limit_fixed_value > 0:
            value = min(value, self.limit_fixed_value)

        # 2. Referencia cruzada
        if self.reference_sequence and self.operation_mode and self.operation_mode != 'none':
            ref_total = self._get_sum_from_sequences(lines_results, self.reference_sequence)
            if self.operation_mode == 'subtract':
                value = value - ref_total
            elif self.operation_mode == 'compare_min':
                value = min(value, ref_total)
            elif self.operation_mode == 'compare_max':
                value = max(value, ref_total)
            elif self.operation_mode == 'carry_difference':
                value = ref_total - value

        # 3. Condicion Python
        if self.python_condition:
            try:
                local_vars = {
                    'result': value,
                    'uvt': self.header_id.uvt_value if self.header_id else 0,
                    'lines': lines_results,
                    'abs': abs,
                    'min': min,
                    'max': max,
                    'round': round,
                }
                evaluated = safe_eval(self.python_condition, local_vars)
                if isinstance(evaluated, (int, float)):
                    value = float(evaluated)
            except Exception:
                pass

        return value

    def compute_line_value(self, employee, date_from, date_to, lines_results=None):
        """Calcula el valor de la linea segun su tipo y aplica post-procesamiento.

        Tipos soportados:
        - sum_rule: Sumatoria desde reglas salariales o categorias
        - sum_accounting: Sumatoria desde movimientos contables (account.move.line)
        - sum_rule_accounting: Combinado reglas salariales + contabilidad
        - average_rule: Promedio mensual de reglas salariales
        - sum_sequence: Sumatoria de secuencias anteriores

        Post-procesamiento (aplicado a todos los tipos):
        - Limites UVT y fijos
        - Operaciones de referencia cruzada
        - Condicion Python personalizada

        :param employee: Registro de hr.employee
        :param date_from: Fecha inicial del periodo
        :param date_to: Fecha final del periodo
        :param lines_results: dict {secuencia: valor} con resultados previos
        :return: float con el valor calculado y post-procesado
        """
        self.ensure_one()
        if lines_results is None:
            lines_results = {}

        raw_value = 0.0

        if self.calculation == 'sum_rule':
            if self.salary_rule_id:
                raw_value = self._get_payslip_value_by_rules(employee, date_from, date_to)
            elif self.salary_rule_category_ids:
                raw_value = self._get_payslip_value_by_categories(employee, date_from, date_to)

        elif self.calculation == 'sum_accounting':
            if self.account_ids:
                raw_value = self._get_accounting_value(employee, date_from, date_to)

        elif self.calculation == 'sum_rule_accounting':
            if self.salary_rule_id:
                raw_value += self._get_payslip_value_by_rules(employee, date_from, date_to)
            elif self.salary_rule_category_ids:
                raw_value += self._get_payslip_value_by_categories(employee, date_from, date_to)
            if self.account_ids:
                raw_value += self._get_accounting_value(employee, date_from, date_to)

        elif self.calculation == 'average_rule':
            raw_value = self._get_average_payslip_value(employee, date_from, date_to)

        elif self.calculation == 'sum_sequence':
            raw_value = self._get_sum_from_sequences(lines_results, self.sequence_list_sum)

        return self._apply_post_processing(raw_value, lines_results)
