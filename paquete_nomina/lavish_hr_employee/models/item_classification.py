# -*- coding: utf-8 -*-
"""
Matriz de Clasificación de Ítems - Regla Madre
Define cómo cada concepto/ítem se comporta en los diferentes subsistemas
(IBC, PILA, ReteFuente, Provisiones, etc.)

Basado en análisis integral de lógica de nómina - Diciembre 2024
"""

from typing import Dict, Optional, Set
from odoo import models, fields, api, _


class ItemClassificationMatrix:
    """
    Matriz única de clasificación de ítems para nómina colombiana.
    
    Esta clase centraliza todas las reglas de clasificación de conceptos
    para evitar inconsistencias entre módulos.
    """
    
    # ══════════════════════════════════════════════════════════════════════════
    # MATRIZ BASE DE CLASIFICACIÓN
    # ══════════════════════════════════════════════════════════════════════════
    
    MATRIX = {
        # ══════════════════════════════════════════════════════════════════════
        # SALARIO BÁSICO Y VARIANTES
        # ══════════════════════════════════════════════════════════════════════
        'BASIC': {
            'es_salarial': True,
            'es_no_salarial': False,
            'entra_1393_total': True,
            'entra_ibc_salud': True,
            'entra_ibc_pension': True,
            'entra_ibc_arl': True,
            'entra_parafiscales': True,
            'entra_retefuente_bruto': True,
            'es_INCRGO': False,
            'es_deduccion_387': False,
            'es_renta_exenta': False,
            'entra_promedio_prestaciones': True,
            'entra_promedio_vacaciones': True,
            'base_prima': True,
            'base_cesantias': True,
            'base_vacaciones': True,
            'base_intereses_cesantias': False,
            'excluir_1393_ugpp': False,
            'novelty': None,
        },
        'BASIC002': {
            'es_salarial': True,
            'es_no_salarial': False,
            'entra_1393_total': True,
            'entra_ibc_salud': True,
            'entra_ibc_pension': True,
            'entra_ibc_arl': True,
            'entra_parafiscales': True,
            'entra_retefuente_bruto': True,
            'es_INCRGO': False,
            'base_prima': True,
            'base_cesantias': True,
            'base_vacaciones': True,
            'excluir_1393_ugpp': False,
        },
        
        # ══════════════════════════════════════════════════════════════════════
        # AUXILIOS
        # ══════════════════════════════════════════════════════════════════════
        'AUX000': {  # Auxilio de transporte
            'es_salarial': False,
            'es_no_salarial': True,
            'entra_1393_total': True,
            'entra_ibc_salud': False,
            'entra_ibc_pension': False,
            'entra_ibc_arl': False,
            'entra_parafiscales': False,
            'entra_retefuente_bruto': False,
            'es_INCRGO': False,
            'base_prima': True,
            'base_cesantias': True,
            'base_vacaciones': False,
            'excluir_1393_ugpp': False,
        },
        
        # ══════════════════════════════════════════════════════════════════════
        # HORAS EXTRAS Y RECARGOS
        # ══════════════════════════════════════════════════════════════════════
        'HE001': {  # Horas extras
            'es_salarial': True,
            'es_no_salarial': False,
            'entra_1393_total': True,
            'entra_ibc_salud': True,
            'entra_ibc_pension': True,
            'entra_ibc_arl': True,
            'entra_parafiscales': True,
            'entra_retefuente_bruto': True,
            'es_INCRGO': False,
            'base_prima': True,
            'base_cesantias': True,
            'base_vacaciones': True,
            'excluir_1393_ugpp': False,
        },
        
        # ══════════════════════════════════════════════════════════════════════
        # AUSENCIAS Y NOVEDADES
        # ══════════════════════════════════════════════════════════════════════
        'VAC': {  # Vacaciones disfrutadas
            'es_salarial': True,
            'es_no_salarial': False,
            'entra_1393_total': False,  # Según UGPP: NO participa en total remunerado
            'entra_ibc_salud': True,
            'entra_ibc_pension': True,
            'entra_ibc_arl': True,
            'entra_parafiscales': False,
            'entra_retefuente_bruto': True,
            'es_INCRGO': False,
            'base_prima': False,
            'base_cesantias': False,
            'base_vacaciones': False,
            'excluir_1393_ugpp': True,
            'novelty': 'vdi',
        },
        'IGE': {  # Incapacidad EPS
            'es_salarial': False,  # No constituye salario
            'es_no_salarial': False,
            'entra_1393_total': False,  # Según UGPP: NO participa
            'entra_ibc_salud': True,  # Solo empleador aporta
            'entra_ibc_pension': True,  # Solo empleador aporta
            'entra_ibc_arl': False,  # No hay ARL durante incapacidad
            'entra_parafiscales': False,
            'entra_retefuente_bruto': False,
            'es_INCRGO': False,
            'base_prima': False,
            'base_cesantias': False,
            'excluir_1393_ugpp': True,
            'novelty': 'ige',
        },
        'IRL': {  # Incapacidad ARL
            'es_salarial': False,
            'es_no_salarial': False,
            'entra_1393_total': False,
            'entra_ibc_salud': True,
            'entra_ibc_pension': True,
            'entra_ibc_arl': True,  # ARL paga durante incapacidad
            'entra_parafiscales': False,
            'entra_retefuente_bruto': False,
            'es_INCRGO': False,
            'base_prima': False,
            'base_cesantias': False,
            'excluir_1393_ugpp': True,
            'novelty': 'irl',
        },
        'LR': {  # Licencia remunerada
            'es_salarial': True,
            'es_no_salarial': False,
            'entra_1393_total': False,  # Según UGPP: NO participa
            'entra_ibc_salud': True,
            'entra_ibc_pension': True,
            'entra_ibc_arl': True,
            'entra_parafiscales': False,
            'entra_retefuente_bruto': True,
            'es_INCRGO': False,
            'base_prima': True,
            'base_cesantias': True,
            'excluir_1393_ugpp': True,
            'novelty': 'lr',
        },
        'LMA': {  # Licencia de maternidad
            'es_salarial': True,
            'es_no_salarial': False,
            'entra_1393_total': False,
            'entra_ibc_salud': True,
            'entra_ibc_pension': True,
            'entra_ibc_arl': True,
            'entra_parafiscales': False,
            'entra_retefuente_bruto': True,
            'es_INCRGO': False,
            'base_prima': True,
            'base_cesantias': True,
            'excluir_1393_ugpp': True,
            'novelty': 'lma',
        },
        'SLN': {  # Suspensión
            'es_salarial': False,
            'es_no_salarial': False,
            'entra_1393_total': False,
            'entra_ibc_salud': False,
            'entra_ibc_pension': False,
            'entra_ibc_arl': False,
            'entra_parafiscales': False,
            'entra_retefuente_bruto': False,
            'es_INCRGO': False,
            'base_prima': False,
            'base_cesantias': False,
            'excluir_1393_ugpp': False,
            'novelty': 'sln',
        },
        
        # ══════════════════════════════════════════════════════════════════════
        # APORTES SEGURIDAD SOCIAL
        # ══════════════════════════════════════════════════════════════════════
        'SSOCIAL001': {  # Aporte salud empleado
            'es_salarial': False,
            'es_no_salarial': False,
            'entra_1393_total': False,
            'entra_ibc_salud': False,
            'entra_ibc_pension': False,
            'entra_ibc_arl': False,
            'entra_parafiscales': False,
            'entra_retefuente_bruto': False,
            'es_INCRGO': True,  # Es aporte obligatorio
            'es_deduccion_387': False,
        },
        'SSOCIAL002': {  # Aporte pensión empleado
            'es_salarial': False,
            'es_no_salarial': False,
            'entra_1393_total': False,
            'entra_ibc_salud': False,
            'entra_ibc_pension': False,
            'entra_ibc_arl': False,
            'entra_parafiscales': False,
            'entra_retefuente_bruto': False,
            'es_INCRGO': True,
            'es_deduccion_387': False,
        },
        'SSOCIAL003': {  # Fondo de Subsistencia
            'es_salarial': False,
            'es_no_salarial': False,
            'entra_1393_total': False,
            'entra_ibc_salud': False,
            'entra_ibc_pension': False,
            'entra_ibc_arl': False,
            'entra_parafiscales': False,
            'entra_retefuente_bruto': False,
            'es_INCRGO': True,
            'es_deduccion_387': False,
        },
        'SSOCIAL004': {  # Fondo de Solidaridad
            'es_salarial': False,
            'es_no_salarial': False,
            'entra_1393_total': False,
            'entra_ibc_salud': False,
            'entra_ibc_pension': False,
            'entra_ibc_arl': False,
            'entra_parafiscales': False,
            'entra_retefuente_bruto': False,
            'es_INCRGO': True,
            'es_deduccion_387': False,
        },
        
        # ══════════════════════════════════════════════════════════════════════
        # PRESTACIONES SOCIALES
        # ══════════════════════════════════════════════════════════════════════
        'PRIMA': {
            'es_salarial': False,
            'es_no_salarial': True,
            'entra_1393_total': True,
            'entra_ibc_salud': False,
            'entra_ibc_pension': False,
            'entra_ibc_arl': False,
            'entra_parafiscales': False,
            'entra_retefuente_bruto': True,
            'es_item_prima': True,  # Para cálculo semestral retefuente
            'base_prima': False,
            'base_cesantias': False,
        },
        'CESANTIAS': {
            'es_salarial': False,
            'es_no_salarial': True,
            'entra_1393_total': True,
            'entra_ibc_salud': False,
            'entra_ibc_pension': False,
            'entra_ibc_arl': False,
            'entra_parafiscales': False,
            'entra_retefuente_bruto': True,
            'base_prima': False,
            'base_cesantias': False,
        },
        'INTCESANTIAS': {
            'es_salarial': False,
            'es_no_salarial': True,
            'entra_1393_total': True,
            'entra_ibc_salud': False,
            'entra_ibc_pension': False,
            'entra_ibc_arl': False,
            'entra_parafiscales': False,
            'entra_retefuente_bruto': True,
            'base_prima': False,
            'base_cesantias': False,
        },
        'VACCONTRATO': {
            'es_salarial': False,
            'es_no_salarial': True,
            'entra_1393_total': True,
            'entra_ibc_salud': False,
            'entra_ibc_pension': False,
            'entra_ibc_arl': False,
            'entra_parafiscales': False,
            'entra_retefuente_bruto': True,
            'base_prima': False,
            'base_cesantias': False,
        },
    }
    
    # ══════════════════════════════════════════════════════════════════════════
    # MÉTODOS DE CONSULTA
    # ══════════════════════════════════════════════════════════════════════════
    
    @classmethod
    def get_classification(cls, code: str, novelty: Optional[str] = None) -> Dict:
        """
        Obtiene la clasificación de un ítem por código.
        
        Args:
            code: Código de la regla salarial
            novelty: Código de novedad (opcional) para ausencias
            
        Returns:
            Dict con la clasificación del ítem o valores por defecto
        """
        # Si hay novelty, buscar primero por novelty
        if novelty:
            novelty_key = novelty.upper()
            if novelty_key in cls.MATRIX:
                return cls.MATRIX[novelty_key].copy()
        
        # Buscar por código
        if code in cls.MATRIX:
            return cls.MATRIX[code].copy()
        
        # Valores por defecto (conservador: no incluir en nada)
        return {
            'es_salarial': False,
            'es_no_salarial': False,
            'entra_1393_total': False,
            'entra_ibc_salud': False,
            'entra_ibc_pension': False,
            'entra_ibc_arl': False,
            'entra_parafiscales': False,
            'entra_retefuente_bruto': False,
            'es_INCRGO': False,
            'es_deduccion_387': False,
            'es_renta_exenta': False,
            'entra_promedio_prestaciones': False,
            'entra_promedio_vacaciones': False,
            'base_prima': False,
            'base_cesantias': False,
            'base_vacaciones': False,
            'base_intereses_cesantias': False,
            'excluir_1393_ugpp': False,
            'novelty': novelty,
        }
    
    @classmethod
    def is_salarial(cls, code: str, novelty: Optional[str] = None) -> bool:
        """Verifica si un ítem es salarial"""
        return cls.get_classification(code, novelty).get('es_salarial', False)
    
    @classmethod
    def is_no_salarial(cls, code: str, novelty: Optional[str] = None) -> bool:
        """Verifica si un ítem es no salarial"""
        return cls.get_classification(code, novelty).get('es_no_salarial', False)
    
    @classmethod
    def enters_ibc_salud(cls, code: str, novelty: Optional[str] = None) -> bool:
        """Verifica si un ítem entra al IBC de salud"""
        return cls.get_classification(code, novelty).get('entra_ibc_salud', False)
    
    @classmethod
    def enters_ibc_pension(cls, code: str, novelty: Optional[str] = None) -> bool:
        """Verifica si un ítem entra al IBC de pensión"""
        return cls.get_classification(code, novelty).get('entra_ibc_pension', False)
    
    @classmethod
    def enters_ibc_arl(cls, code: str, novelty: Optional[str] = None) -> bool:
        """Verifica si un ítem entra al IBC de ARL"""
        return cls.get_classification(code, novelty).get('entra_ibc_arl', False)
    
    @classmethod
    def enters_parafiscales(cls, code: str, novelty: Optional[str] = None) -> bool:
        """Verifica si un ítem entra a parafiscales (Caja, SENA, ICBF)"""
        return cls.get_classification(code, novelty).get('entra_parafiscales', False)
    
    @classmethod
    def enters_1393_total(cls, code: str, novelty: Optional[str] = None, 
                          include_absences_1393: bool = False) -> bool:
        """
        Verifica si un ítem participa en el total remunerado para Ley 1393.
        
        Args:
            code: Código de la regla
            novelty: Código de novedad
            include_absences_1393: Si True, incluye ausencias excluidas por UGPP
        """
        classification = cls.get_classification(code, novelty)
        
        # Si está excluido por UGPP y la configuración no incluye ausencias, retornar False
        if classification.get('excluir_1393_ugpp', False) and not include_absences_1393:
            return False
        
        return classification.get('entra_1393_total', False)
    
    @classmethod
    def is_INCRGO(cls, code: str) -> bool:
        """Verifica si un ítem es INCRGO (aporte obligatorio para retefuente)"""
        return cls.get_classification(code).get('es_INCRGO', False)
    
    @classmethod
    def is_base_prima(cls, code: str, novelty: Optional[str] = None) -> bool:
        """Verifica si un ítem es base para prima"""
        return cls.get_classification(code, novelty).get('base_prima', False)
    
    @classmethod
    def is_base_cesantias(cls, code: str, novelty: Optional[str] = None) -> bool:
        """Verifica si un ítem es base para cesantías"""
        return cls.get_classification(code, novelty).get('base_cesantias', False)
    
    @classmethod
    def is_base_vacaciones(cls, code: str, novelty: Optional[str] = None) -> bool:
        """Verifica si un ítem es base para vacaciones"""
        return cls.get_classification(code, novelty).get('base_vacaciones', False)
    
    @classmethod
    def get_novelty_excluded_from_1393(cls) -> Set[str]:
        """
        Retorna conjunto de novedades excluidas del cálculo Ley 1393 según UGPP.
        
        Returns:
            Set con códigos de novedades excluidas: {'VAC', 'IGE', 'IRL', 'LMA', 'LR'}
        """
        excluded = set()
        for code, classification in cls.MATRIX.items():
            if classification.get('excluir_1393_ugpp', False):
                novelty = classification.get('novelty')
                if novelty:
                    excluded.add(novelty)
        return excluded


class ItemClassificationService(models.AbstractModel):
    """
    Servicio para consultar clasificación de ítems desde modelos de Odoo.
    """
    _name = 'item.classification.service'
    _description = 'Servicio de Clasificación de Ítems'
    
    def get_classification(self, rule_code: str, novelty: Optional[str] = None) -> Dict:
        """
        Obtiene la clasificación de un ítem.
        
        Args:
            rule_code: Código de la regla salarial
            novelty: Código de novedad (opcional)
            
        Returns:
            Dict con la clasificación
        """
        return ItemClassificationMatrix.get_classification(rule_code, novelty)
    
    def filter_rules_by_classification(self, rules: Dict, 
                                      classification_key: str, 
                                      value: bool = True) -> Dict:
        """
        Filtra reglas según una clasificación específica.
        
        Args:
            rules: Diccionario de reglas (localdict['rules'])
            classification_key: Clave de clasificación (ej: 'entra_ibc_salud')
            value: Valor esperado (default: True)
            
        Returns:
            Dict filtrado con solo las reglas que cumplen la clasificación
        """
        filtered = {}
        for code, rule_data in rules.items():
            rule = rule_data.rule if hasattr(rule_data, 'rule') else None
            if not rule:
                continue
            
            # Obtener novelty si existe
            novelty = None
            if hasattr(rule_data, 'leave') and rule_data.leave:
                novelty = getattr(rule_data.leave, 'novelty', None)
            
            classification = ItemClassificationMatrix.get_classification(code, novelty)
            if classification.get(classification_key, False) == value:
                filtered[code] = rule_data
        
        return filtered

