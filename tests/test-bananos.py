#!/usr/bin/env python3

import json
import sys
import time
import urllib.request
import urllib.error
import subprocess
from datetime import datetime

BASE = "http://127.0.0.1:8001"

ADMIN_USER = "admin"
ADMIN_PASS = "admin123"

SELLERS = [
    ("TEST_AUTO_V1", "Test1171"),
    ("TEST_AUTO_V2", "Test1172"),
    ("TEST_AUTO_V3", "Test1173"),
]

PASS = 0
FAIL = 0
RESULTS = []

def result(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        mark = "✅"
    else:
        FAIL += 1
        mark = "❌"

    RESULTS.append((name, ok, detail))
    print(f"{mark} {name}")
    if detail:
        print(f"   {detail}")

def request(method, path, token=None, data=None, expected=None):
    headers = {}

    if token:
        headers["Authorization"] = f"Bearer {token}"

    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(
        BASE + path,
        data=body,
        headers=headers,
        method=method
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read()
            ct = r.headers.get("Content-Type", "")

            if "application/json" in ct:
                content = json.loads(raw.decode())
            else:
                content = raw

            return r.status, content, dict(r.headers)

    except urllib.error.HTTPError as e:
        raw = e.read()

        try:
            content = json.loads(raw.decode())
        except:
            content = raw.decode(errors="replace")

        return e.code, content, dict(e.headers)

    except Exception as e:
        return 0, {"error": str(e)}, {}

def login(username, password):
    status, body, _ = request(
        "POST",
        "/api/login",
        data={
            "username": username,
            "password": password
        }
    )

    if status != 200:
        return None

    return body.get("token")

def docker_sql(sql):
    p = subprocess.run(
        [
            "docker", "exec", "bananos-manager",
            "python", "-c",
            f"""
import sqlite3
c=sqlite3.connect('/app/database/bananos_pos.db')
r=c.execute({sql!r}).fetchall()
print(repr(r))
c.close()
"""
        ],
        capture_output=True,
        text=True
    )

    return p.stdout.strip()

print()
print("╔══════════════════════════════════════════════════════╗")
print("║       BANANOS MANAGER V3.4 — FULL TEST SUITE       ║")
print("╚══════════════════════════════════════════════════════╝")
print()

# =====================================================
# 1. SERVIDOR
# =====================================================

status, body, _ = request("GET", "/api/status")

result(
    "API disponible",
    status == 200 and body.get("ok") is True,
    str(body)
)

# =====================================================
# 2. LOGIN ADMIN
# =====================================================

admin = login(ADMIN_USER, ADMIN_PASS)

result(
    "Login administrador",
    bool(admin)
)

if not admin:
    print()
    print("❌ No pude iniciar sesión como admin/admin123.")
    print("Si cambiaste la contraseña del administrador, edita ADMIN_PASS.")
    sys.exit(1)

status, me, _ = request("GET", "/api/me", admin)

result(
    "Identidad administrador",
    status == 200 and me.get("role") == "admin",
    str(me)
)

# =====================================================
# 3. CREAR VENDEDORES
# =====================================================

seller_tokens = {}

for username, password in SELLERS:

    status, users, _ = request("GET", "/api/users", admin)

    existing = next(
        (x for x in users if x["username"] == username),
        None
    )

    if existing:
        request(
            "PATCH",
            f"/api/users/{existing['id']}",
            admin,
            {
                "active": True,
                "password": password
            }
        )

        result(
            f"Preparar vendedor {username}",
            True,
            "Ya existía; contraseña reiniciada."
        )

    else:
        status, body, _ = request(
            "POST",
            "/api/users",
            admin,
            {
                "username": username,
                "password": password
            }
        )

        result(
            f"Crear vendedor {username}",
            status == 200,
            str(body)
        )

    token = login(username, password)

    seller_tokens[username] = token

    result(
        f"Login {username}",
        bool(token)
    )

# =====================================================
# 4. PRODUCTOS DE PRUEBA
# =====================================================

print()
print("── PRODUCTOS ───────────────────────────────────────")

# Producto vía multipart usando curl porque FastAPI espera Form()
def create_product(name, category, price, stock, beer=False):

    cmd = [
        "curl", "-s",
        "-w", "\\n%{http_code}",
        "-X", "POST",
        BASE + "/api/products",
        "-H", f"Authorization: Bearer {admin}",
        "-F", f"name={name}",
        "-F", f"category={category}",
        "-F", f"price={price}",
        "-F", f"stock={stock}",
        "-F", "min_stock=5",
        "-F", "description=Producto generado por test automático",
        "-F", f"beer_selectable={'true' if beer else 'false'}"
    ]

    p = subprocess.run(cmd, capture_output=True, text=True)

    parts = p.stdout.rsplit("\n", 1)

    try:
        body = json.loads(parts[0])
        code = int(parts[1])
    except:
        return 0, {}

    return code, body


status, products, _ = request("GET", "/api/products", admin)

test_names = [
    "TEST_AUTO_CORONA",
    "TEST_AUTO_REFRESCO",
    "TEST_AUTO_PAPAS"
]

# reutilizamos si una ejecución anterior dejó productos
product_ids = {}

for p in products:
    if p["name"] in test_names:
        product_ids[p["name"]] = p["id"]

        request(
            "PATCH",
            f"/api/products/{p['id']}",
            admin,
            {
                "stock": 100,
                "price":
                    50 if p["name"] == "TEST_AUTO_CORONA"
                    else 30 if p["name"] == "TEST_AUTO_REFRESCO"
                    else 25,
                "beer_selectable":
                    p["name"] == "TEST_AUTO_CORONA"
            }
        )

products_to_create = [
    ("TEST_AUTO_CORONA", "CERVEZAS", 50, 100, True),
    ("TEST_AUTO_REFRESCO", "BEBIDAS", 30, 100, False),
    ("TEST_AUTO_PAPAS", "SNACKS", 25, 100, False),
]

for name, cat, price, stock, beer in products_to_create:

    if name not in product_ids:

        code, body = create_product(
            name, cat, price, stock, beer
        )

        result(
            f"Crear {name}",
            code == 200,
            str(body)
        )

        if code == 200:
            product_ids[name] = body["id"]

    else:
        result(
            f"Preparar {name}",
            True,
            "Producto existente reutilizado."
        )

CORONA = product_ids["TEST_AUTO_CORONA"]
REFRESCO = product_ids["TEST_AUTO_REFRESCO"]
PAPAS = product_ids["TEST_AUTO_PAPAS"]

# =====================================================
# 5. PREPARACIONES
# =====================================================

status, preparations, _ = request(
    "GET",
    "/api/preparations",
    admin
)

prep_names = {
    p["name"]: p["extra_price"]
    for p in preparations
}

result(
    "Preparación Normal disponible",
    prep_names.get("Normal") == 0
)

result(
    "Preparación Michelada disponible",
    prep_names.get("Michelada") == 25
)

# =====================================================
# 6. CAJA OBLIGATORIA
# =====================================================

print()
print("── CAJA OBLIGATORIA ───────────────────────────────")

v1 = seller_tokens["TEST_AUTO_V1"]
v2 = seller_tokens["TEST_AUTO_V2"]
v3 = seller_tokens["TEST_AUTO_V3"]

# cerrar cajas viejas si quedó alguna de test anterior
for token in [v1, v2, v3]:
    st, cash, _ = request("GET", "/api/cash", token)

    if st == 200 and cash.get("open"):
        request("POST", "/api/cash/close", token, {})

# venta SIN caja
status, body, _ = request(
    "POST",
    "/api/sales",
    v1,
    {
        "items": [
            {
                "product_id": REFRESCO,
                "qty": 1
            }
        ],
        "payment_method": "cash"
    }
)

result(
    "Bloquear venta con caja cerrada",
    status == 403,
    f"HTTP {status} {body}"
)

# mesa SIN caja
status, body, _ = request(
    "PUT",
    "/api/tables/10",
    v1,
    {
        "items": [
            {
                "product_id": PAPAS,
                "qty": 1
            }
        ]
    }
)

result(
    "Bloquear mesa con caja cerrada",
    status == 403,
    f"HTTP {status}"
)

# =====================================================
# 7. ABRIR CAJAS
# =====================================================

for username in ["TEST_AUTO_V1", "TEST_AUTO_V2", "TEST_AUTO_V3"]:

    token = seller_tokens[username]

    status, body, _ = request(
        "POST",
        "/api/cash/open",
        token,
        {}
    )

    result(
        f"Abrir caja {username}",
        status == 200,
        str(body)
    )

    status, cash, _ = request(
        "GET",
        "/api/cash",
        token
    )

    result(
        f"Confirmar caja abierta {username}",
        status == 200 and cash.get("open") is True
    )

# =====================================================
# 8. VENTAS RÁPIDAS
# =====================================================

print()
print("── VENTAS ─────────────────────────────────────────")

# V1
# 2 refrescos = 60
status, sale1, _ = request(
    "POST",
    "/api/sales",
    v1,
    {
        "items": [
            {
                "product_id": REFRESCO,
                "qty": 2
            }
        ],
        "payment_method": "cash"
    }
)

result(
    "Venta V1: 2 refrescos",
    status == 200 and sale1.get("total") == 60,
    str(sale1)
)

# V2
# Corona normal = 50
status, sale2, _ = request(
    "POST",
    "/api/sales",
    v2,
    {
        "items": [
            {
                "product_id": CORONA,
                "qty": 1,
                "preparation": "Normal"
            }
        ],
        "payment_method": "card"
    }
)

result(
    "Venta V2: cerveza Normal",
    status == 200 and sale2.get("total") == 50,
    str(sale2)
)

# V3
# Corona Michelada = 50 + 25 = 75
status, sale3, _ = request(
    "POST",
    "/api/sales",
    v3,
    {
        "items": [
            {
                "product_id": CORONA,
                "qty": 1,
                "preparation": "Michelada"
            }
        ],
        "payment_method": "transfer"
    }
)

result(
    "Venta V3: cerveza Michelada +$25",
    status == 200 and sale3.get("total") == 75,
    str(sale3)
)

# V1 multiproducto
# 1 refresco 30 + 2 papas 50 = 80
status, sale4, _ = request(
    "POST",
    "/api/sales",
    v1,
    {
        "items": [
            {
                "product_id": REFRESCO,
                "qty": 1
            },
            {
                "product_id": PAPAS,
                "qty": 2
            }
        ],
        "payment_method": "cash"
    }
)

result(
    "Venta multiproducto V1",
    status == 200 and sale4.get("total") == 80,
    str(sale4)
)

# =====================================================
# 9. STOCK DESPUÉS DE VENTAS
# =====================================================

status, products, _ = request(
    "GET",
    "/api/products",
    admin
)

stocks = {
    p["id"]: p["stock"]
    for p in products
}

result(
    "Stock refresco después de ventas = 97",
    stocks.get(REFRESCO) == 97,
    f"stock={stocks.get(REFRESCO)}"
)

result(
    "Stock papas después de ventas = 98",
    stocks.get(PAPAS) == 98,
    f"stock={stocks.get(PAPAS)}"
)

result(
    "Stock cerveza después de ventas = 98",
    stocks.get(CORONA) == 98,
    f"stock={stocks.get(CORONA)}"
)

# =====================================================
# 10. MESAS
# =====================================================

print()
print("── MESAS ──────────────────────────────────────────")

# Mesa 1:
# 2 refrescos = 60
# 1 Michelada = 75
# total = 135

status, body, _ = request(
    "PUT",
    "/api/tables/1",
    v1,
    {
        "items": [
            {
                "product_id": REFRESCO,
                "qty": 2
            },
            {
                "product_id": CORONA,
                "qty": 1,
                "preparation": "Michelada"
            }
        ]
    }
)

result(
    "Guardar consumo Mesa 1",
    status == 200,
    str(body)
)

status, tables, _ = request(
    "GET",
    "/api/tables",
    v1
)

mesa1 = next(
    x for x in tables
    if x["table"] == 1
)

result(
    "Mesa 1 abierta",
    mesa1["open"] is True
)

result(
    "Mesa 1 total = $135",
    mesa1["total"] == 135,
    f"${mesa1['total']}"
)

result(
    "Mesa 1 contiene 3 unidades",
    mesa1["count"] == 3,
    f"count={mesa1['count']}"
)

# Mesa 2
# 3 papas = 75
status, body, _ = request(
    "PUT",
    "/api/tables/2",
    v2,
    {
        "items": [
            {
                "product_id": PAPAS,
                "qty": 3
            }
        ]
    }
)

result(
    "Guardar Mesa 2",
    status == 200
)

# Mesa 5
# Corona Chelada = 65
status, body, _ = request(
    "PUT",
    "/api/tables/5",
    v3,
    {
        "items": [
            {
                "product_id": CORONA,
                "qty": 1,
                "preparation": "Chelada"
            }
        ]
    }
)

result(
    "Guardar Mesa 5 con Chelada",
    status == 200
)

# IMPORTANTE:
# Guardar mesa NO debe descontar stock.
status, products, _ = request(
    "GET",
    "/api/products",
    admin
)

stocks_before_checkout = {
    p["id"]: p["stock"]
    for p in products
}

result(
    "Guardar mesa NO descuenta cerveza",
    stocks_before_checkout[CORONA] == 98
)

result(
    "Guardar mesa NO descuenta papas",
    stocks_before_checkout[PAPAS] == 98
)

# =====================================================
# 11. COBRAR MESAS
# =====================================================

status, checkout1, _ = request(
    "POST",
    "/api/tables/1/checkout",
    v1,
    {"payment_method": "cash"}
)

result(
    "Cobrar Mesa 1",
    status == 200 and checkout1.get("total") == 135,
    str(checkout1)
)

status, checkout2, _ = request(
    "POST",
    "/api/tables/2/checkout",
    v2,
    {"payment_method": "card"}
)

result(
    "Cobrar Mesa 2",
    status == 200 and checkout2.get("total") == 75,
    str(checkout2)
)

status, checkout5, _ = request(
    "POST",
    "/api/tables/5/checkout",
    v3,
    {"payment_method": "transfer"}
)

result(
    "Cobrar Mesa 5",
    status == 200 and checkout5.get("total") == 65,
    str(checkout5)
)

# =====================================================
# 12. MESAS LIBERADAS
# =====================================================

status, tables, _ = request(
    "GET",
    "/api/tables",
    v1
)

for n in [1,2,5]:

    t = next(
        x for x in tables
        if x["table"] == n
    )

    result(
        f"Mesa {n} liberada después del cobro",
        t["open"] is False and t["total"] == 0
    )

# =====================================================
# 13. STOCK FINAL
# =====================================================

status, products, _ = request(
    "GET",
    "/api/products",
    admin
)

stocks = {
    p["id"]: p["stock"]
    for p in products
}

# REFRESCO:
# inicial 100
# ventas rápidas 3
# mesa1 2
# final 95

result(
    "Stock final refresco = 95",
    stocks[REFRESCO] == 95,
    f"stock={stocks[REFRESCO]}"
)

# PAPAS:
# inicial 100
# venta rápida 2
# mesa2 3
# final 95

result(
    "Stock final papas = 95",
    stocks[PAPAS] == 95,
    f"stock={stocks[PAPAS]}"
)

# CORONA:
# inicial 100
# normal 1
# michelada 1
# mesa1 1
# mesa5 1
# final 96

result(
    "Stock final cerveza = 96",
    stocks[CORONA] == 96,
    f"stock={stocks[CORONA]}"
)

# =====================================================
# 14. VENDEDORES NO VEN STOCK
# =====================================================

status, seller_products, _ = request(
    "GET",
    "/api/products",
    v1
)

sp = next(
    p for p in seller_products
    if p["id"] == REFRESCO
)

result(
    "Vendedor NO puede ver stock",
    sp.get("stock") is None
)

result(
    "Vendedor NO puede ver stock mínimo",
    sp.get("min_stock") is None
)

# =====================================================
# 15. PERMISOS
# =====================================================

print()
print("── SEGURIDAD / ROLES ──────────────────────────────")

status, body, _ = request(
    "GET",
    "/api/dashboard",
    v1
)

result(
    "Vendedor bloqueado del Dashboard admin",
    status == 403,
    f"HTTP {status}"
)

status, body, _ = request(
    "GET",
    "/api/users",
    v1
)

result(
    "Vendedor bloqueado de administración de usuarios",
    status == 403,
    f"HTTP {status}"
)

status, body, _ = request(
    "GET",
    "/api/sales",
    v1
)

result(
    "Vendedor bloqueado del historial global",
    status == 403,
    f"HTTP {status}"
)

status, body, _ = request(
    "POST",
    "/api/preparations",
    v1,
    {
        "name": "TEST_HACK",
        "extra_price": 999
    }
)

result(
    "Vendedor no puede crear preparaciones",
    status == 403,
    f"HTTP {status}"
)

# =====================================================
# 16. HISTORIAL ADMIN
# =====================================================

print()
print("── HISTORIAL ──────────────────────────────────────")

status, sales, _ = request(
    "GET",
    "/api/sales",
    admin
)

test_sales = [
    x for x in sales
    if x["seller"].startswith("TEST_AUTO_")
]

result(
    "Historial contiene ventas de prueba",
    len(test_sales) >= 7,
    f"{len(test_sales)} tickets encontrados"
)

micheladas = []

for sale in test_sales:
    for item in sale["items"]:
        if (
            item["name"] == "TEST_AUTO_CORONA"
            and item["preparation"] == "Michelada"
        ):
            micheladas.append(item)

result(
    "Historial conserva preparación Michelada",
    len(micheladas) >= 1
)

result(
    "Precio Michelada almacenado = $75",
    any(x["unit_price"] == 75 for x in micheladas)
)

# =====================================================
# 17. DASHBOARD
# =====================================================

status, dashboard, _ = request(
    "GET",
    "/api/dashboard",
    admin
)

result(
    "Dashboard administrador responde",
    status == 200
)

names = [
    x["name"]
    for x in dashboard.get("sellers", [])
]

result(
    "Dashboard registra vendedores TEST",
    any(x.startswith("TEST_AUTO_") for x in names),
    str(names)
)

result(
    "Dashboard tiene gráfica de 7 días",
    len(dashboard.get("chart", [])) == 7
)

# =====================================================
# 18. CAJAS ANTES DE CERRAR
# =====================================================

expected = {
    "TEST_AUTO_V1": 275, # 60 + 80 + mesa1 135
    "TEST_AUTO_V2": 125, # 50 + mesa2 75
    "TEST_AUTO_V3": 140, # 75 + mesa5 65
}

for username in expected:

    token = seller_tokens[username]

    status, cash, _ = request(
        "GET",
        "/api/cash",
        token
    )

    result(
        f"Total sesión {username} = ${expected[username]}",
        cash.get("session_total") == expected[username],
        f"${cash.get('session_total')}"
    )

# =====================================================
# 19. CERRAR CAJAS
# =====================================================

print()
print("── CIERRE DE CAJAS ────────────────────────────────")

for username in expected:

    token = seller_tokens[username]

    status, close, _ = request(
        "POST",
        "/api/cash/close",
        token,
        {}
    )

    result(
        f"Cerrar caja {username}",
        status == 200,
        str(close)
    )

    result(
        f"Corte {username} matemáticamente correcto",
        close.get("session_total") == expected[username],
        f"${close.get('session_total')}"
    )

    status, cash, _ = request(
        "GET",
        "/api/cash",
        token
    )

    result(
        f"Caja {username} quedó cerrada",
        cash.get("open") is False
    )

# =====================================================
# 20. HISTORIAL DE CORTES
# =====================================================

status, history, _ = request(
    "GET",
    "/api/cash/history",
    admin
)

test_history = [
    x for x in history
    if x["seller"].startswith("TEST_AUTO_")
]

result(
    "Admin ve los 3 cortes",
    len(test_history) >= 3,
    f"{len(test_history)} cortes"
)

# =====================================================
# 21. PDF
# =====================================================

status, pdf, headers = request(
    "GET",
    "/api/report/pdf",
    admin
)

result(
    "Reporte PDF responde",
    status == 200
)

result(
    "Reporte comienza con firma PDF",
    isinstance(pdf, bytes) and pdf.startswith(b"%PDF"),
    f"{len(pdf) if isinstance(pdf,bytes) else 0} bytes"
)

# =====================================================
# 22. SQLITE
# =====================================================

print()
print("── BASE DE DATOS ──────────────────────────────────")

sql_sales = docker_sql(
    """
SELECT COUNT(*)
FROM sales s
JOIN users u ON u.id=s.seller_id
WHERE u.username LIKE 'TEST_AUTO_%'
"""
)

result(
    "SQLite contiene tickets TEST",
    sql_sales and sql_sales != "[(0,)]",
    sql_sales
)

sql_items = docker_sql(
    """
SELECT COUNT(*)
FROM sale_items si
JOIN sales s ON s.id=si.sale_id
JOIN users u ON u.id=s.seller_id
WHERE u.username LIKE 'TEST_AUTO_%'
"""
)

result(
    "SQLite contiene detalle de ventas",
    sql_items and sql_items != "[(0,)]",
    sql_items
)

sql_tables = docker_sql(
    """
SELECT table_number,items_json
FROM table_accounts
WHERE table_number IN (1,2,5)
ORDER BY table_number
"""
)

result(
    "SQLite tiene Mesas 1,2,5 vacías tras cobro",
    "'[]'" in sql_tables,
    sql_tables
)

# =====================================================
# 23. PERSISTENCIA DOCKER
# =====================================================

print()
print("── PERSISTENCIA DOCKER ────────────────────────────")

before = docker_sql(
    """
SELECT COUNT(*)
FROM sales s
JOIN users u ON u.id=s.seller_id
WHERE u.username LIKE 'TEST_AUTO_%'
"""
)

print("   Destruyendo contenedor...")
subprocess.run(
    ["docker", "compose", "down"],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL
)

print("   Recreando contenedor...")
subprocess.run(
    ["docker", "compose", "up", "-d"],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL
)

print("   Esperando FastAPI...")
time.sleep(5)

status, body, _ = request(
    "GET",
    "/api/status"
)

result(
    "API vuelve después de docker compose down/up",
    status == 200 and body.get("ok") is True
)

after = docker_sql(
    """
SELECT COUNT(*)
FROM sales s
JOIN users u ON u.id=s.seller_id
WHERE u.username LIKE 'TEST_AUTO_%'
"""
)

result(
    "Ventas sobreviven recreación del contenedor",
    before == after and before != "[(0,)]",
    f"antes={before} después={after}"
)

# =====================================================
# RESULTADO
# =====================================================

TOTAL = PASS + FAIL

print()
print("╔══════════════════════════════════════════════════════╗")
print("║                    RESULTADOS                        ║")
print("╠══════════════════════════════════════════════════════╣")

for name, ok, detail in RESULTS:
    mark = "PASS" if ok else "FAIL"
    print(f"║ {mark:4}  {name[:43]:43} ║")

print("╠══════════════════════════════════════════════════════╣")
print(f"║ TOTAL: {TOTAL:<4}   PASS: {PASS:<4}   FAIL: {FAIL:<4}               ║")

if FAIL == 0:
    print("║              ✅ SISTEMA APROBADO                    ║")
else:
    print("║              ❌ REVISAR FALLOS                      ║")

print("╚══════════════════════════════════════════════════════╝")

report = f"tests/resultado-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"

with open(report, "w") as f:
    for name, ok, detail in RESULTS:
        f.write(
            f"{'PASS' if ok else 'FAIL'} | {name} | {detail}\n"
        )

    f.write(
        f"\nTOTAL={TOTAL} PASS={PASS} FAIL={FAIL}\n"
    )

print()
print("Reporte guardado en:", report)
print()

sys.exit(0 if FAIL == 0 else 1)
