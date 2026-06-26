# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

"""
Pruebas básicas para verificar la funcionalidad del módulo de libros contables Colombia.
"""

def test_module_structure():
    """Verifica que la estructura del módulo sea correcta."""
    import os
    
    base_path = '/home/ubuntu/libros_contables_colombia'
    
    # Verificar archivos principales
    required_files = [
        '__manifest__.py',
        '__init__.py',
        'README.md',
        'models/__init__.py',
        'models/account_inventory_book.py',
        'models/account_journal_book.py',
        'models/account_ledger_book.py',
        'models/account_capital_difference.py',
        'models/account_auxiliary_book.py',
        'views/account_report_view.xml',
        'views/menu_view.xml',
        'security/ir.model.access.csv',
    ]
    
    missing_files = []
    for file_path in required_files:
        full_path = os.path.join(base_path, file_path)
        if not os.path.exists(full_path):
            missing_files.append(file_path)
    
    if missing_files:
        print(f"Archivos faltantes: {missing_files}")
        return False
    
    print("✓ Estructura del módulo correcta")
    return True

def test_manifest_syntax():
    """Verifica que el archivo __manifest__.py tenga sintaxis correcta."""
    try:
        import sys
        sys.path.insert(0, '/home/ubuntu/libros_contables_colombia')
        
        with open('/home/ubuntu/libros_contables_colombia/__manifest__.py', 'r') as f:
            manifest_content = f.read()
        
        # Verificar que sea un diccionario válido
        manifest_dict = eval(manifest_content)
        
        # Verificar campos requeridos
        required_fields = ['name', 'version', 'depends', 'data']
        for field in required_fields:
            if field not in manifest_dict:
                print(f"Campo faltante en __manifest__.py: {field}")
                return False
        
        print("✓ Archivo __manifest__.py válido")
        return True
        
    except Exception as e:
        print(f"Error en __manifest__.py: {e}")
        return False

def test_python_syntax():
    """Verifica que los archivos Python tengan sintaxis correcta."""
    import ast
    import os
    
    python_files = [
        'models/account_inventory_book.py',
        'models/account_journal_book.py',
        'models/account_ledger_book.py',
        'models/account_capital_difference.py',
        'models/account_auxiliary_book.py',
    ]
    
    base_path = '/home/ubuntu/libros_contables_colombia'
    
    for file_path in python_files:
        full_path = os.path.join(base_path, file_path)
        try:
            with open(full_path, 'r') as f:
                content = f.read()
            
            # Verificar sintaxis Python
            ast.parse(content)
            print(f"✓ {file_path} - sintaxis correcta")
            
        except SyntaxError as e:
            print(f"✗ {file_path} - error de sintaxis: {e}")
            return False
        except Exception as e:
            print(f"✗ {file_path} - error: {e}")
            return False
    
    return True

def test_xml_syntax():
    """Verifica que los archivos XML tengan sintaxis correcta."""
    import xml.etree.ElementTree as ET
    import os
    
    xml_files = [
        'views/account_report_view.xml',
        'views/menu_view.xml',
    ]
    
    base_path = '/home/ubuntu/libros_contables_colombia'
    
    for file_path in xml_files:
        full_path = os.path.join(base_path, file_path)
        try:
            ET.parse(full_path)
            print(f"✓ {file_path} - XML válido")
            
        except ET.ParseError as e:
            print(f"✗ {file_path} - error XML: {e}")
            return False
        except Exception as e:
            print(f"✗ {file_path} - error: {e}")
            return False
    
    return True

def run_all_tests():
    """Ejecuta todas las pruebas."""
    print("=== Ejecutando pruebas del módulo Libros Contables Colombia ===\n")
    
    tests = [
        ("Estructura del módulo", test_module_structure),
        ("Sintaxis del manifiesto", test_manifest_syntax),
        ("Sintaxis Python", test_python_syntax),
        ("Sintaxis XML", test_xml_syntax),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"Ejecutando: {test_name}")
        if test_func():
            passed += 1
        print()
    
    print(f"=== Resultados: {passed}/{total} pruebas pasaron ===")
    
    if passed == total:
        print("✓ Todas las pruebas pasaron. El módulo está listo para usar.")
        return True
    else:
        print("✗ Algunas pruebas fallaron. Revisar los errores arriba.")
        return False

if __name__ == "__main__":
    run_all_tests()

