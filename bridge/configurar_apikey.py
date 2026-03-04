import xmlrpc.client

ODOO_URL = "https://srv1360477.hstgr.cloud"
DB = "odoo_col"
USER = "admin"
PASSWORD = "admin"
API_KEY = "L_-xkDG2JoS8ldx4A0abyaiuxDzdWRy-MLbwtTObkSk"

print("Conectando a Odoo...")
common = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/common')
uid = common.authenticate(DB, USER, PASSWORD, {})
print(f"UID: {uid}")

if uid:
    models = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/object')
    models.execute_kw(DB, uid, PASSWORD, 'ir.config_parameter', 'set_param', ['bascula.api_key', API_KEY])
    print("API Key configurada!")

    # Verificar
    valor = models.execute_kw(DB, uid, PASSWORD, 'ir.config_parameter', 'get_param', ['bascula.api_key'])
    print(f"Verificacion - API Key guardada: {valor}")
else:
    print("Error: No se pudo autenticar")
