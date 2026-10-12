import os
import sqlite3
import json
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, send_from_directory, session
from werkzeug.utils import secure_filename
from flask_cors import CORS
from flask_session import Session

app = Flask(__name__)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Pasta persistente (ex: volume do Railway montado em /data).
# Só é usada em sistemas POSIX (Linux/containers); no Windows (dev local) usa-se BASE_DIR,
# a menos que DATA_DIR seja definida explicitamente.
DATA_DIR = os.environ.get('DATA_DIR') or ('/data' if os.name == 'posix' else BASE_DIR)
try:
    os.makedirs(DATA_DIR, exist_ok=True)
except OSError:
    DATA_DIR = BASE_DIR
    os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "pedidos.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

FOTOS_MATERIAIS_FOLDER = os.path.join(BASE_DIR, "static", "fotos_materiais")
os.makedirs(FOTOS_MATERIAIS_FOLDER, exist_ok=True)
ALLOWED_FOTO_EXT = {'png', 'jpg', 'jpeg', 'webp'}
MAX_FOTO_SIZE = 2 * 1024 * 1024  # 2MB

EMOJI_POR_CATEGORIA = {
    'Impressão': '🖨️',
    'Resina': '💧',
    'Bases': '📦',
    'Consumíveis': '🧤',
}

def emoji_por_categoria(categoria):
    return EMOJI_POR_CATEGORIA.get(categoria, '📦')

# Sessão / autenticação
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'elements-troque-esta-chave-em-producao')
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = os.path.join(DATA_DIR, 'flask_session')
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)
Session(app)

CORS(app, supports_credentials=True)

APP_USERNAME = os.environ.get('APP_USERNAME', 'admin')
APP_PASSWORD = os.environ.get('APP_PASSWORD', 'admin')

PUBLIC_API_ROUTES = {'/api/login', '/api/check-auth'}

@app.before_request
def require_login():
    if request.path.startswith('/api/') and request.path not in PUBLIC_API_ROUTES:
        if not session.get('logged_in'):
            return jsonify({"error": "unauthorized"}), 401

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    username = data.get('username', '')
    password = data.get('password', '')
    if username == APP_USERNAME and password == APP_PASSWORD:
        session.permanent = True
        session['logged_in'] = True
        session['username'] = username
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Credenciais inválidas"}), 401

@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"success": True})

@app.route("/api/check-auth")
def api_check_auth():
    return jsonify({"authenticated": bool(session.get('logged_in'))})

def get_db():
    return sqlite3.connect(DB_PATH)

def column_exists(cursor, table, column):
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # Criar tabela se não existir (schema completo)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pedidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            clientName TEXT NOT NULL,
            clientPhone TEXT,
            product TEXT,
            size TEXT,
            quantity INTEGER DEFAULT 1,
            price REAL DEFAULT 0,
            deadline TEXT,
            address TEXT,
            notes TEXT,
            image TEXT,
            status TEXT DEFAULT 'Pendente',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            pdf TEXT
        )
    """)

    # Migração: adicionar colunas que faltem uma por uma
    colunas_necessarias = [
        ('clientName', 'TEXT NOT NULL DEFAULT ""'),
        ('clientPhone', 'TEXT'),
        ('product', 'TEXT'),
        ('size', 'TEXT'),
        ('quantity', 'INTEGER DEFAULT 1'),
        ('price', 'REAL DEFAULT 0'),
        ('deadline', 'TEXT'),
        ('address', 'TEXT'),
        ('notes', 'TEXT'),
        ('image', 'TEXT'),
        ('status', 'TEXT DEFAULT "Pendente"'),
        ('created_at', 'TEXT DEFAULT CURRENT_TIMESTAMP'),
        ('pdf', 'TEXT')
    ]

    for col, coltype in colunas_necessarias:
        if not column_exists(cursor, 'pedidos', col):
            try:
                cursor.execute(f"ALTER TABLE pedidos ADD COLUMN {col} {coltype}")
                print(f"[MIGRACAO] Coluna '{col}' adicionada a pedidos")
            except Exception as e:
                print(f"[MIGRACAO] Erro ao adicionar '{col}': {e}")

    # Tabela clientes
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            phone TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Tabela orcamentos
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orcamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            product TEXT,
            size TEXT,
            price REAL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Tabela materiais (stock)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS materiais (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            categoria TEXT,
            quantidade_atual REAL DEFAULT 0,
            quantidade_minima REAL DEFAULT 0,
            unidade TEXT,
            preco_unitario REAL DEFAULT 0,
            fornecedor TEXT,
            notas TEXT,
            data_atualizacao TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Tabela fornecedores
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fornecedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            telefone TEXT,
            email TEXT,
            website TEXT,
            categorias TEXT,
            notas TEXT,
            data_criacao TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Tabela compras (histórico de compras de materiais)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS compras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id INTEGER NOT NULL,
            fornecedor_id INTEGER,
            data_compra TEXT NOT NULL,
            quantidade REAL NOT NULL,
            unidade TEXT,
            preco_unitario REAL NOT NULL,
            preco_total REAL,
            notas TEXT,
            data_criacao TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (material_id) REFERENCES materiais(id),
            FOREIGN KEY (fornecedor_id) REFERENCES fornecedores(id)
        )
    """)

    # Tabela investimentos (máquinas e equipamentos a comprar)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS investimentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            descricao TEXT DEFAULT '',
            preco_est REAL DEFAULT 0,
            link TEXT DEFAULT '',
            prioridade TEXT DEFAULT 'Média',
            estado TEXT DEFAULT 'Em análise',
            notas TEXT DEFAULT '',
            criado_em TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Tabela sócios
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS socios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            ativo INTEGER DEFAULT 1,
            criado_em TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Tabela financas (entradas e saídas do negócio)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS financas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL,
            data TEXT NOT NULL,
            descricao TEXT DEFAULT '',
            categoria TEXT DEFAULT '',
            valor REAL NOT NULL,
            socio_id INTEGER,
            pedido_id INTEGER,
            compra_id INTEGER,
            metodo_pagamento TEXT DEFAULT '',
            notas TEXT DEFAULT '',
            criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (socio_id) REFERENCES socios(id),
            FOREIGN KEY (pedido_id) REFERENCES pedidos(id),
            FOREIGN KEY (compra_id) REFERENCES compras(id)
        )
    """)

    # Migração: adicionar colunas novas à tabela materiais (fornecedor associado, preço mais recente, foto)
    materiais_colunas_novas = [
        ('fornecedor_id', 'INTEGER REFERENCES fornecedores(id)'),
        ('preco_atual', 'REAL'),
        ('foto_path', 'TEXT')
    ]
    for col, coltype in materiais_colunas_novas:
        if not column_exists(cursor, 'materiais', col):
            try:
                cursor.execute(f"ALTER TABLE materiais ADD COLUMN {col} {coltype}")
                print(f"[MIGRACAO] Coluna '{col}' adicionada a materiais")
            except Exception as e:
                print(f"[MIGRACAO] Erro ao adicionar '{col}': {e}")

    conn.commit()
    conn.close()
    print("[DEBUG] Banco de dados inicializado com sucesso!")

def migrar_categorias():
    """
    Preenche a categoria dos materiais existentes com base no nome.
    Só corre se AINDA NÃO houver categorias reais na tabela (tudo NULL ou 'Consumíveis'),
    para nunca sobrescrever categorias que o utilizador já tenha ajustado manualmente.
    """
    conn = get_db()
    cursor = conn.cursor()

    valores_atuais = {row[0] for row in cursor.execute("SELECT DISTINCT categoria FROM materiais").fetchall()}
    if not valores_atuais.issubset({None, 'Consumíveis'}):
        conn.close()
        return

    regras = [
        ('%Papel fotográfico%', 'Impressão'),
        ('%Tinteiro%', 'Impressão'),
        ('%Resina%', 'Resina'),
        ('%Íman%', 'Bases'),
        ('%Iman%', 'Bases'),
        ('%Velcro%', 'Bases'),
        ('%pingente%', 'Bases'),
        ('%Argola%', 'Bases'),
        ('%corrente%', 'Bases'),
    ]
    for padrao, categoria in regras:
        cursor.execute("UPDATE materiais SET categoria = ? WHERE nome LIKE ?", (categoria, padrao))

    cursor.execute("UPDATE materiais SET categoria = 'Consumíveis' WHERE categoria IS NULL")
    conn.commit()
    conn.close()
    print("[MIGRACAO] Categorias de materiais atualizadas")

init_db()
migrar_categorias()

def sync_financa_pedido(conn, pedido_id, status, price, client_name, product):
    """
    Mantém uma entrada em 'financas' sincronizada com o estado do pedido:
    cria/atualiza a entrada quando o pedido passa a 'Entregue', remove-a se deixar de estar.
    Usa pedido_id + categoria='Venda de pedido' como chave para nunca duplicar.
    """
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM financas WHERE pedido_id = ? AND categoria = 'Venda de pedido'",
        (pedido_id,)
    )
    existente = cursor.fetchone()

    if status == 'Entregue':
        valor = float(price or 0)
        if valor <= 0:
            return
        descricao = f"Pedido #{pedido_id} — {client_name or 'Cliente'}"
        if product:
            descricao += f" ({product})"
        if existente:
            cursor.execute("UPDATE financas SET valor=?, descricao=? WHERE id=?", (valor, descricao, existente[0]))
        else:
            cursor.execute("""
                INSERT INTO financas (tipo, data, descricao, categoria, valor, pedido_id)
                VALUES ('entrada', ?, ?, 'Venda de pedido', ?, ?)
            """, (datetime.now().strftime('%Y-%m-%d'), descricao, valor, pedido_id))
    else:
        if existente:
            cursor.execute("DELETE FROM financas WHERE id = ?", (existente[0],))

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/pedidos", methods=["GET", "POST"])
def api_pedidos():
    conn = get_db()
    cursor = conn.cursor()

    if request.method == "POST":
        data = request.get_json()
        cursor.execute("""
            INSERT INTO pedidos (clientName, clientPhone, product, size, quantity, price, deadline, address, notes, image, status, pdf)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get('clientName', ''), data.get('clientPhone', ''), data.get('product', ''),
            data.get('size', ''), data.get('quantity', 1), data.get('price', 0),
            data.get('deadline', ''), data.get('address', ''), data.get('notes', ''),
            data.get('image', ''), data.get('status', 'Pendente'), data.get('pdf', '')
        ))
        conn.commit()
        pedido_id = cursor.lastrowid

        if data.get('clientName'):
            cursor.execute("SELECT id FROM clientes WHERE name = ?", (data.get('clientName'),))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO clientes (name, phone) VALUES (?, ?)",
                           (data.get('clientName'), data.get('clientPhone')))
            else:
                cursor.execute("UPDATE clientes SET phone = ? WHERE name = ?",
                           (data.get('clientPhone'), data.get('clientName')))
            conn.commit()

        sync_financa_pedido(conn, pedido_id, data.get('status', 'Pendente'), data.get('price', 0),
                            data.get('clientName', ''), data.get('product', ''))
        conn.commit()

        conn.close()
        return jsonify({"success": True, "id": pedido_id})

    status_filter = request.args.get('status')
    search = request.args.get('search')

    query = "SELECT * FROM pedidos WHERE 1=1"
    params = []

    if status_filter:
        query += " AND status = ?"
        params.append(status_filter)
    if search:
        query += " AND (clientName LIKE ? OR product LIKE ? OR clientPhone LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

    query += " ORDER BY deadline ASC, created_at DESC"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    pedidos = []
    for row in rows:
        pedidos.append({
            "id": row[0], "clientName": row[1], "clientPhone": row[2],
            "product": row[3], "size": row[4], "quantity": row[5],
            "price": row[6], "deadline": row[7], "address": row[8],
            "notes": row[9], "image": row[10], "status": row[11],
            "created_at": row[12], "pdf": row[13]
        })
    conn.close()
    return jsonify(pedidos)

@app.route("/api/pedidos/<int:id>", methods=["PUT", "DELETE"])
def api_pedido(id):
    conn = get_db()
    cursor = conn.cursor()

    if request.method == "PUT":
        data = request.get_json()
        cursor.execute("""
            UPDATE pedidos SET clientName=?, clientPhone=?, product=?, size=?, quantity=?,
            price=?, deadline=?, address=?, notes=?, image=?, status=?, pdf=?
            WHERE id=?
        """, (
            data.get('clientName'), data.get('clientPhone'), data.get('product'),
            data.get('size'), data.get('quantity'), data.get('price'),
            data.get('deadline'), data.get('address'), data.get('notes'),
            data.get('image'), data.get('status'), data.get('pdf'), id
        ))
        sync_financa_pedido(conn, id, data.get('status'), data.get('price', 0),
                            data.get('clientName', ''), data.get('product', ''))
        conn.commit()
        conn.close()
        return jsonify({"success": True})

    elif request.method == "DELETE":
        cursor.execute("DELETE FROM pedidos WHERE id = ?", (id,))
        cursor.execute("DELETE FROM financas WHERE pedido_id = ? AND categoria = 'Venda de pedido'", (id,))
        conn.commit()
        conn.close()
        return jsonify({"success": True})

@app.route("/api/clientes", methods=["GET", "POST"])
def api_clientes():
    conn = get_db()
    cursor = conn.cursor()

    if request.method == "POST":
        data = request.get_json()
        cursor.execute("INSERT OR REPLACE INTO clientes (name, phone) VALUES (?, ?)",
                   (data.get('name'), data.get('phone')))
        conn.commit()
        conn.close()
        return jsonify({"success": True})

    cursor.execute("SELECT * FROM clientes ORDER BY name")
    rows = cursor.fetchall()
    clientes = []
    for row in rows:
        cursor.execute("SELECT COUNT(*) FROM pedidos WHERE clientName = ?", (row[1],))
        count = cursor.fetchone()[0]
        clientes.append({
            "id": row[0], "name": row[1], "phone": row[2],
            "created_at": row[3], "pedidos_count": count
        })
    conn.close()
    return jsonify(clientes)

@app.route("/api/clientes/<int:id>", methods=["PUT", "DELETE"])
def api_cliente(id):
    conn = get_db()
    cursor = conn.cursor()

    if request.method == "PUT":
        data = request.get_json()
        # Buscar nome antigo para atualizar pedidos
        cursor.execute("SELECT name FROM clientes WHERE id = ?", (id,))
        old = cursor.fetchone()
        old_name = old[0] if old else None
        new_name = data.get('name')
        new_phone = data.get('phone')

        # Atualizar cliente
        cursor.execute("UPDATE clientes SET name = ?, phone = ? WHERE id = ?",
                       (new_name, new_phone, id))

        # Se o nome mudou, atualizar todos os pedidos desse cliente
        if old_name and old_name != new_name:
            cursor.execute("UPDATE pedidos SET clientName = ? WHERE clientName = ?",
                           (new_name, old_name))

        conn.commit()
        conn.close()
        return jsonify({"success": True})

    elif request.method == "DELETE":
        cursor.execute("SELECT name FROM clientes WHERE id = ?", (id,))
        cliente = cursor.fetchone()
        if cliente:
            # Opcional: remover ou manter pedidos? Vamos manter pedidos mas desvincular
            cursor.execute("UPDATE pedidos SET clientName = '' WHERE clientName = ?", (cliente[0],))
            cursor.execute("DELETE FROM clientes WHERE id = ?", (id,))
            conn.commit()
        conn.close()
        return jsonify({"success": True})

@app.route("/api/clientes/<name>/historico")
def api_cliente_historico(name):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM pedidos WHERE clientName = ? ORDER BY created_at DESC", (name,))
    rows = cursor.fetchall()
    pedidos = []
    for row in rows:
        pedidos.append({
            "id": row[0], "clientName": row[1], "clientPhone": row[2],
            "product": row[3], "size": row[4], "quantity": row[5],
            "price": row[6], "deadline": row[7], "address": row[8],
            "notes": row[9], "image": row[10], "status": row[11],
            "created_at": row[12], "pdf": row[13]
        })

    total_pedidos = len(pedidos)
    total_gasto = sum(p['price'] for p in pedidos if p['price'])

    produtos = {}
    for p in pedidos:
        prod = p['product'] or 'Outro'
        produtos[prod] = produtos.get(prod, 0) + 1
    produto_favorito = max(produtos, key=produtos.get) if produtos else "N/A"

    datas = [p['created_at'] for p in pedidos if p['created_at']]
    primeiro = min(datas) if datas else "N/A"
    ultimo = max(datas) if datas else "N/A"

    if datas and len(datas) > 1:
        try:
            primeira_data = datetime.strptime(datas[-1], "%Y-%m-%d %H:%M:%S")
            ultima_data = datetime.strptime(datas[0], "%Y-%m-%d %H:%M:%S")
            diferenca = (ultima_data - primeira_data).days or 1
            meses = diferenca / 30
            media_mensal = round(total_pedidos / meses, 1) if meses > 0 else total_pedidos
        except:
            media_mensal = total_pedidos
    else:
        media_mensal = total_pedidos

    conn.close()
    return jsonify({
        "cliente": name,
        "total_pedidos": total_pedidos,
        "total_gasto": round(total_gasto, 2),
        "produto_favorito": produto_favorito,
        "primeiro_pedido": primeiro,
        "ultimo_pedido": ultimo,
        "media_mensal": media_mensal,
        "pedidos": pedidos
    })

@app.route("/api/orcamentos", methods=["GET", "POST", "DELETE"])
def api_orcamentos():
    conn = get_db()
    cursor = conn.cursor()

    if request.method == "POST":
        data = request.get_json()
        cursor.execute("INSERT INTO orcamentos (title, product, size, price) VALUES (?, ?, ?, ?)",
                   (data.get('title'), data.get('product'), data.get('size'), data.get('price')))
        conn.commit()
        conn.close()
        return jsonify({"success": True})

    elif request.method == "DELETE":
        id = request.args.get('id')
        if id:
            cursor.execute("DELETE FROM orcamentos WHERE id = ?", (id,))
            conn.commit()
        conn.close()
        return jsonify({"success": True})

    cursor.execute("SELECT * FROM orcamentos ORDER BY title")
    rows = cursor.fetchall()
    orcamentos = [{"id": r[0], "title": r[1], "product": r[2], "size": r[3], "price": r[4]} for r in rows]
    conn.close()
    return jsonify(orcamentos)

def row_to_material(row):
    quantidade_atual = row[3] or 0
    quantidade_minima = row[4] or 0
    categoria = row[2]
    foto_path = row[12]
    return {
        "id": row[0], "nome": row[1], "categoria": categoria,
        "quantidade_atual": quantidade_atual, "quantidade_minima": quantidade_minima,
        "unidade": row[5], "preco_unitario": row[6], "fornecedor": row[7],
        "notas": row[8], "data_atualizacao": row[9],
        "fornecedor_id": row[10], "preco_atual": row[11],
        "foto_path": foto_path, "foto_url": f"/static/{foto_path}" if foto_path else None,
        "emoji": emoji_por_categoria(categoria),
        "fornecedor_nome": row[13],
        "stock_baixo": quantidade_atual <= quantidade_minima
    }

@app.route("/api/materiais", methods=["GET", "POST"])
def api_materiais():
    conn = get_db()
    cursor = conn.cursor()

    if request.method == "POST":
        data = request.get_json()
        cursor.execute("""
            INSERT INTO materiais (nome, categoria, quantidade_atual, quantidade_minima, unidade, preco_unitario, fornecedor, notas, fornecedor_id, preco_atual, data_atualizacao)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            data.get('nome', ''), data.get('categoria') or 'Consumíveis',
            data.get('quantidade_atual', 0), data.get('quantidade_minima', 0),
            data.get('unidade', ''), data.get('preco_unitario', 0),
            data.get('fornecedor', ''), data.get('notas', ''),
            data.get('fornecedor_id'), data.get('preco_atual')
        ))
        conn.commit()
        material_id = cursor.lastrowid
        conn.close()
        return jsonify({"success": True, "id": material_id})

    categoria_filter = request.args.get('categoria')

    query = """
        SELECT m.id, m.nome, m.categoria, m.quantidade_atual, m.quantidade_minima, m.unidade,
               m.preco_unitario, m.fornecedor, m.notas, m.data_atualizacao, m.fornecedor_id, m.preco_atual,
               m.foto_path, f.nome as fornecedor_nome
        FROM materiais m
        LEFT JOIN fornecedores f ON m.fornecedor_id = f.id
        WHERE 1=1
    """
    params = []
    if categoria_filter:
        query += " AND m.categoria = ?"
        params.append(categoria_filter)
    query += " ORDER BY m.categoria, m.nome ASC"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    materiais = [row_to_material(row) for row in rows]
    conn.close()
    return jsonify(materiais)

@app.route("/api/materiais/<int:id>", methods=["PUT", "DELETE"])
def api_material(id):
    conn = get_db()
    cursor = conn.cursor()

    if request.method == "PUT":
        data = request.get_json()
        cursor.execute("""
            UPDATE materiais SET nome=?, categoria=?, quantidade_atual=?, quantidade_minima=?,
            unidade=?, preco_unitario=?, fornecedor=?, notas=?, fornecedor_id=?, preco_atual=?, data_atualizacao=CURRENT_TIMESTAMP
            WHERE id=?
        """, (
            data.get('nome'), data.get('categoria') or 'Consumíveis',
            data.get('quantidade_atual', 0), data.get('quantidade_minima', 0),
            data.get('unidade'), data.get('preco_unitario', 0),
            data.get('fornecedor'), data.get('notas'),
            data.get('fornecedor_id'), data.get('preco_atual'), id
        ))
        conn.commit()
        conn.close()
        return jsonify({"success": True})

    elif request.method == "DELETE":
        cursor.execute("DELETE FROM materiais WHERE id = ?", (id,))
        conn.commit()
        conn.close()
        return jsonify({"success": True})

@app.route("/api/fornecedores", methods=["GET", "POST"])
def api_fornecedores():
    conn = get_db()
    cursor = conn.cursor()

    if request.method == "POST":
        data = request.get_json()
        cursor.execute("""
            INSERT INTO fornecedores (nome, telefone, email, website, categorias, notas)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            data.get('nome', ''), data.get('telefone', ''), data.get('email', ''),
            data.get('website', ''), data.get('categorias', ''), data.get('notas', '')
        ))
        conn.commit()
        fornecedor_id = cursor.lastrowid
        conn.close()
        return jsonify({"success": True, "id": fornecedor_id})

    cursor.execute("SELECT id, nome, telefone, email, website, categorias, notas, data_criacao FROM fornecedores ORDER BY nome")
    rows = cursor.fetchall()
    fornecedores = [{
        "id": r[0], "nome": r[1], "telefone": r[2], "email": r[3],
        "website": r[4], "categorias": r[5], "notas": r[6], "data_criacao": r[7]
    } for r in rows]
    conn.close()
    return jsonify(fornecedores)

@app.route("/api/fornecedores/<int:id>", methods=["PUT", "DELETE"])
def api_fornecedor(id):
    conn = get_db()
    cursor = conn.cursor()

    if request.method == "PUT":
        data = request.get_json()
        cursor.execute("""
            UPDATE fornecedores SET nome=?, telefone=?, email=?, website=?, categorias=?, notas=?
            WHERE id=?
        """, (
            data.get('nome', ''), data.get('telefone', ''), data.get('email', ''),
            data.get('website', ''), data.get('categorias', ''), data.get('notas', ''), id
        ))
        conn.commit()
        conn.close()
        return jsonify({"success": True})

    elif request.method == "DELETE":
        cursor.execute("DELETE FROM fornecedores WHERE id = ?", (id,))
        conn.commit()
        conn.close()
        return jsonify({"success": True})

@app.route("/api/compras", methods=["GET", "POST"])
def api_compras():
    conn = get_db()
    cursor = conn.cursor()

    if request.method == "POST":
        data = request.get_json()
        quantidade = float(data.get('quantidade', 0) or 0)
        preco_unitario = float(data.get('preco_unitario', 0) or 0)
        preco_total = quantidade * preco_unitario
        cursor.execute("""
            INSERT INTO compras (material_id, fornecedor_id, data_compra, quantidade, unidade, preco_unitario, preco_total, notas)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get('material_id'), data.get('fornecedor_id'), data.get('data_compra'),
            quantidade, data.get('unidade', ''), preco_unitario, preco_total, data.get('notas', '')
        ))
        # Actualiza o preço actual e o fornecedor do material com os dados desta compra
        cursor.execute("UPDATE materiais SET preco_atual=?, fornecedor_id=? WHERE id=?",
                       (preco_unitario, data.get('fornecedor_id'), data.get('material_id')))
        conn.commit()
        compra_id = cursor.lastrowid
        conn.close()
        return jsonify({"success": True, "id": compra_id})

    material_id = request.args.get('material_id')
    fornecedor_id = request.args.get('fornecedor_id')

    query = """
        SELECT c.id, c.material_id, c.fornecedor_id, c.data_compra, c.quantidade, c.unidade,
               c.preco_unitario, c.preco_total, c.notas, c.data_criacao,
               m.nome as material_nome, m.unidade as material_unidade, f.nome as fornecedor_nome
        FROM compras c
        LEFT JOIN materiais m ON c.material_id = m.id
        LEFT JOIN fornecedores f ON c.fornecedor_id = f.id
        WHERE 1=1
    """
    params = []
    if material_id:
        query += " AND c.material_id = ?"
        params.append(material_id)
    if fornecedor_id:
        query += " AND c.fornecedor_id = ?"
        params.append(fornecedor_id)
    query += " ORDER BY c.data_compra DESC, c.id DESC"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    compras = [{
        "id": r[0], "material_id": r[1], "fornecedor_id": r[2], "data_compra": r[3],
        "quantidade": r[4], "unidade": r[5], "preco_unitario": r[6], "preco_total": r[7],
        "notas": r[8], "data_criacao": r[9], "material_nome": r[10], "material_unidade": r[11],
        "fornecedor_nome": r[12]
    } for r in rows]
    conn.close()
    return jsonify(compras)

@app.route("/api/compras/<int:id>", methods=["DELETE"])
def api_compra(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM compras WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

def row_to_investimento(row):
    return {
        "id": row[0], "nome": row[1], "descricao": row[2], "preco_est": row[3],
        "link": row[4], "prioridade": row[5], "estado": row[6], "notas": row[7],
        "criado_em": row[8]
    }

@app.route("/api/investimentos", methods=["GET", "POST"])
def api_investimentos():
    conn = get_db()
    cursor = conn.cursor()

    if request.method == "POST":
        data = request.get_json()
        nome = (data.get('nome') or '').strip()
        if not nome:
            conn.close()
            return jsonify({"success": False, "error": "Nome obrigatório"}), 400
        cursor.execute("""
            INSERT INTO investimentos (nome, descricao, preco_est, link, prioridade, estado, notas)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            nome, data.get('descricao', ''), data.get('preco_est') or 0,
            data.get('link', ''), data.get('prioridade', 'Média'),
            data.get('estado', 'Em análise'), data.get('notas', '')
        ))
        conn.commit()
        investimento_id = cursor.lastrowid
        conn.close()
        return jsonify({"success": True, "id": investimento_id})

    cursor.execute("""
        SELECT id, nome, descricao, preco_est, link, prioridade, estado, notas, criado_em
        FROM investimentos
        ORDER BY CASE prioridade WHEN 'Alta' THEN 0 WHEN 'Média' THEN 1 WHEN 'Baixa' THEN 2 ELSE 3 END, criado_em DESC
    """)
    rows = cursor.fetchall()
    investimentos = [row_to_investimento(row) for row in rows]
    conn.close()
    return jsonify(investimentos)

@app.route("/api/investimentos/<int:id>", methods=["PUT", "DELETE"])
def api_investimento(id):
    conn = get_db()
    cursor = conn.cursor()

    if request.method == "PUT":
        data = request.get_json()
        nome = (data.get('nome') or '').strip()
        if not nome:
            conn.close()
            return jsonify({"success": False, "error": "Nome obrigatório"}), 400
        cursor.execute("""
            UPDATE investimentos SET nome=?, descricao=?, preco_est=?, link=?, prioridade=?, estado=?, notas=?
            WHERE id=?
        """, (
            nome, data.get('descricao', ''), data.get('preco_est') or 0,
            data.get('link', ''), data.get('prioridade', 'Média'),
            data.get('estado', 'Em análise'), data.get('notas', ''), id
        ))
        conn.commit()
        conn.close()
        return jsonify({"success": True})

    elif request.method == "DELETE":
        cursor.execute("DELETE FROM investimentos WHERE id = ?", (id,))
        conn.commit()
        conn.close()
        return jsonify({"success": True})

def row_to_socio(row):
    return {"id": row[0], "nome": row[1], "ativo": bool(row[2]), "criado_em": row[3]}

@app.route("/api/socios", methods=["GET", "POST"])
def api_socios():
    conn = get_db()
    cursor = conn.cursor()

    if request.method == "POST":
        data = request.get_json()
        nome = (data.get('nome') or '').strip()
        if not nome:
            conn.close()
            return jsonify({"success": False, "error": "Nome obrigatório"}), 400
        cursor.execute("INSERT INTO socios (nome, ativo) VALUES (?, 1)", (nome,))
        conn.commit()
        socio_id = cursor.lastrowid
        conn.close()
        return jsonify({"success": True, "id": socio_id})

    query = "SELECT id, nome, ativo, criado_em FROM socios WHERE 1=1"
    params = []
    if request.args.get('ativo') == '1':
        query += " AND ativo = 1"
    query += " ORDER BY ativo DESC, nome ASC"
    cursor.execute(query, params)
    socios = [row_to_socio(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify(socios)

@app.route("/api/socios/<int:id>", methods=["PUT"])
def api_socio(id):
    data = request.get_json()
    conn = get_db()
    cursor = conn.cursor()

    campos = []
    valores = []
    if 'nome' in data:
        nome = (data.get('nome') or '').strip()
        if not nome:
            conn.close()
            return jsonify({"success": False, "error": "Nome obrigatório"}), 400
        campos.append("nome=?")
        valores.append(nome)
    if 'ativo' in data:
        campos.append("ativo=?")
        valores.append(1 if data.get('ativo') else 0)

    if not campos:
        conn.close()
        return jsonify({"success": False, "error": "Nada para atualizar"}), 400

    valores.append(id)
    cursor.execute(f"UPDATE socios SET {', '.join(campos)} WHERE id=?", valores)
    conn.commit()
    conn.close()
    return jsonify({"success": True})

VALID_TIPOS_FINANCA = {'entrada', 'saida'}

def validar_data_financa(data_str):
    try:
        datetime.strptime(data_str, '%Y-%m-%d')
        return True
    except (ValueError, TypeError):
        return False

def row_to_financa(row):
    return {
        "id": row[0], "tipo": row[1], "data": row[2], "descricao": row[3],
        "categoria": row[4], "valor": row[5], "socio_id": row[6], "socio_nome": row[7],
        "pedido_id": row[8], "compra_id": row[9], "metodo_pagamento": row[10],
        "notas": row[11], "criado_em": row[12]
    }

def validar_financa(data):
    tipo = data.get('tipo')
    if tipo not in VALID_TIPOS_FINANCA:
        return None, "Tipo inválido (use 'entrada' ou 'saida')"
    try:
        valor = float(data.get('valor'))
    except (TypeError, ValueError):
        return None, "Valor inválido"
    if valor <= 0:
        return None, "Valor deve ser maior que zero"
    data_mov = data.get('data') or ''
    if not validar_data_financa(data_mov):
        return None, "Data inválida (use AAAA-MM-DD)"
    return {
        "tipo": tipo, "valor": valor, "data": data_mov,
        "descricao": data.get('descricao', ''), "categoria": data.get('categoria', ''),
        "socio_id": data.get('socio_id') or None, "pedido_id": data.get('pedido_id') or None,
        "compra_id": data.get('compra_id') or None, "metodo_pagamento": data.get('metodo_pagamento', ''),
        "notas": data.get('notas', '')
    }, None

@app.route("/api/financas", methods=["GET", "POST"])
def api_financas():
    conn = get_db()
    cursor = conn.cursor()

    if request.method == "POST":
        data = request.get_json()
        f, erro = validar_financa(data)
        if erro:
            conn.close()
            return jsonify({"success": False, "error": erro}), 400
        cursor.execute("""
            INSERT INTO financas (tipo, data, descricao, categoria, valor, socio_id, pedido_id, compra_id, metodo_pagamento, notas)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            f["tipo"], f["data"], f["descricao"], f["categoria"], f["valor"],
            f["socio_id"], f["pedido_id"], f["compra_id"], f["metodo_pagamento"], f["notas"]
        ))
        conn.commit()
        financa_id = cursor.lastrowid
        conn.close()
        return jsonify({"success": True, "id": financa_id})

    de = request.args.get('de')
    ate = request.args.get('ate')
    tipo_filter = request.args.get('tipo')
    categoria_filter = request.args.get('categoria')
    socio_filter = request.args.get('socio_id')

    query = """
        SELECT f.id, f.tipo, f.data, f.descricao, f.categoria, f.valor, f.socio_id, s.nome,
               f.pedido_id, f.compra_id, f.metodo_pagamento, f.notas, f.criado_em
        FROM financas f
        LEFT JOIN socios s ON f.socio_id = s.id
        WHERE 1=1
    """
    params = []
    if de:
        query += " AND f.data >= ?"
        params.append(de)
    if ate:
        query += " AND f.data <= ?"
        params.append(ate)
    if tipo_filter:
        query += " AND f.tipo = ?"
        params.append(tipo_filter)
    if categoria_filter:
        query += " AND f.categoria = ?"
        params.append(categoria_filter)
    if socio_filter == 'sem_socio':
        query += " AND f.socio_id IS NULL"
    elif socio_filter:
        query += " AND f.socio_id = ?"
        params.append(socio_filter)
    query += " ORDER BY f.data DESC, f.id DESC"

    cursor.execute(query, params)
    financas = [row_to_financa(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify(financas)

@app.route("/api/financas/<int:id>", methods=["PUT", "DELETE"])
def api_financa(id):
    conn = get_db()
    cursor = conn.cursor()

    if request.method == "PUT":
        data = request.get_json()
        f, erro = validar_financa(data)
        if erro:
            conn.close()
            return jsonify({"success": False, "error": erro}), 400
        cursor.execute("""
            UPDATE financas SET tipo=?, data=?, descricao=?, categoria=?, valor=?, socio_id=?,
            pedido_id=?, compra_id=?, metodo_pagamento=?, notas=? WHERE id=?
        """, (
            f["tipo"], f["data"], f["descricao"], f["categoria"], f["valor"],
            f["socio_id"], f["pedido_id"], f["compra_id"], f["metodo_pagamento"], f["notas"], id
        ))
        conn.commit()
        conn.close()
        return jsonify({"success": True})

    elif request.method == "DELETE":
        cursor.execute("DELETE FROM financas WHERE id = ?", (id,))
        conn.commit()
        conn.close()
        return jsonify({"success": True})

@app.route("/api/financas/resumo")
def api_financas_resumo():
    de = request.args.get('de')
    ate = request.args.get('ate')
    socio_filter = request.args.get('socio_id')

    conn = get_db()
    cursor = conn.cursor()

    where = "WHERE 1=1"
    params = []
    if de:
        where += " AND f.data >= ?"
        params.append(de)
    if ate:
        where += " AND f.data <= ?"
        params.append(ate)
    if socio_filter == 'sem_socio':
        where += " AND f.socio_id IS NULL"
    elif socio_filter:
        where += " AND f.socio_id = ?"
        params.append(socio_filter)

    cursor.execute(f"""
        SELECT f.tipo, f.socio_id, s.nome, f.categoria, f.valor, f.data
        FROM financas f LEFT JOIN socios s ON f.socio_id = s.id
        {where}
    """, params)
    rows = cursor.fetchall()
    conn.close()

    total_entradas = 0.0
    total_saidas = 0.0
    por_socio = {}
    por_categoria_entradas = {}
    por_categoria_saidas = {}
    por_mes = {}

    for tipo, socio_id, socio_nome, categoria, valor, data_mov in rows:
        valor = float(valor or 0)
        chave_socio = socio_id if socio_id is not None else 'sem_socio'
        nome_socio = socio_nome if socio_id is not None else 'Empresa / sem sócio'
        if chave_socio not in por_socio:
            por_socio[chave_socio] = {"socio_id": socio_id, "socio": nome_socio, "entradas": 0.0, "saidas": 0.0}

        mes = (data_mov or '')[:7] or 'sem-data'
        if mes not in por_mes:
            por_mes[mes] = {"mes": mes, "entradas": 0.0, "saidas": 0.0}

        categoria_chave = categoria or 'Sem categoria'
        if tipo == 'entrada':
            total_entradas += valor
            por_socio[chave_socio]["entradas"] += valor
            por_categoria_entradas[categoria_chave] = por_categoria_entradas.get(categoria_chave, 0.0) + valor
            por_mes[mes]["entradas"] += valor
        else:
            total_saidas += valor
            por_socio[chave_socio]["saidas"] += valor
            por_categoria_saidas[categoria_chave] = por_categoria_saidas.get(categoria_chave, 0.0) + valor
            por_mes[mes]["saidas"] += valor

    por_socio_lista = []
    for v in por_socio.values():
        v["saldo"] = v["entradas"] - v["saidas"]
        por_socio_lista.append(v)
    por_socio_lista.sort(key=lambda x: x["saidas"], reverse=True)

    por_mes_lista = sorted(por_mes.values(), key=lambda x: x["mes"])
    for m in por_mes_lista:
        m["saldo"] = m["entradas"] - m["saidas"]

    return jsonify({
        "total_entradas": total_entradas,
        "total_saidas": total_saidas,
        "saldo": total_entradas - total_saidas,
        "por_socio": por_socio_lista,
        "por_categoria": {
            "entradas": [{"categoria": k, "valor": v} for k, v in sorted(por_categoria_entradas.items(), key=lambda x: -x[1])],
            "saidas": [{"categoria": k, "valor": v} for k, v in sorted(por_categoria_saidas.items(), key=lambda x: -x[1])]
        },
        "por_mes": por_mes_lista
    })

@app.route("/api/upload", methods=["POST"])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No filename"}), 400
    filename = secure_filename(file.filename)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_")
    filename = timestamp + filename
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    return jsonify({"success": True, "filename": filename, "url": f"/static/uploads/{filename}"})

@app.route("/static/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route("/material/<int:mid>/foto", methods=["POST"])
def upload_foto_material(mid):
    if 'foto' not in request.files:
        return jsonify({"ok": False, "error": "Nenhum ficheiro enviado"}), 400

    file = request.files['foto']
    if file.filename == '':
        return jsonify({"ok": False, "error": "Nenhum ficheiro selecionado"}), 400

    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_FOTO_EXT:
        return jsonify({"ok": False, "error": "Formato inválido. Use PNG, JPG ou WEBP."}), 400

    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    if size > MAX_FOTO_SIZE:
        return jsonify({"ok": False, "error": "Ficheiro demasiado grande (máx. 2MB)."}), 400

    conn = get_db()
    cursor = conn.cursor()
    existe = cursor.execute("SELECT id FROM materiais WHERE id = ?", (mid,)).fetchone()
    if not existe:
        conn.close()
        return jsonify({"ok": False, "error": "Material não encontrado"}), 404

    # Remove fotos antigas deste material com outra extensão
    for old_ext in ALLOWED_FOTO_EXT:
        old_path = os.path.join(FOTOS_MATERIAIS_FOLDER, f"{mid}.{old_ext}")
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
            except OSError:
                pass

    filename = f"{mid}.{ext}"
    file.save(os.path.join(FOTOS_MATERIAIS_FOLDER, filename))

    foto_path = f"fotos_materiais/{filename}"
    cursor.execute("UPDATE materiais SET foto_path=? WHERE id=?", (foto_path, mid))
    conn.commit()
    conn.close()

    return jsonify({"ok": True, "url": f"/static/{foto_path}"})

@app.route("/api/export")
def export_data():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM pedidos")
    pedidos = [dict(zip([c[0] for c in cursor.description], row)) for row in cursor.fetchall()]

    cursor.execute("SELECT * FROM clientes")
    clientes = [dict(zip([c[0] for c in cursor.description], row)) for row in cursor.fetchall()]

    cursor.execute("SELECT * FROM orcamentos")
    orcamentos = [dict(zip([c[0] for c in cursor.description], row)) for row in cursor.fetchall()]

    conn.close()

    return jsonify({
        "pedidos": pedidos,
        "clientes": clientes,
        "orcamentos": orcamentos,
        "exported_at": datetime.now().isoformat()
    })

@app.route("/api/import", methods=["POST"])
def import_data():
    data = request.get_json()
    conn = get_db()
    cursor = conn.cursor()

    if 'pedidos' in data:
        for p in data['pedidos']:
            cursor.execute("""
                INSERT INTO pedidos (id, clientName, clientPhone, product, size, quantity, price, deadline, address, notes, image, status, created_at, pdf)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                clientName=excluded.clientName, clientPhone=excluded.clientPhone,
                product=excluded.product, size=excluded.size, quantity=excluded.quantity,
                price=excluded.price, deadline=excluded.deadline, address=excluded.address,
                notes=excluded.notes, image=excluded.image, status=excluded.status, pdf=excluded.pdf
            """, (
                p.get('id'), p.get('clientName'), p.get('clientPhone'), p.get('product'),
                p.get('size'), p.get('quantity'), p.get('price'), p.get('deadline'),
                p.get('address'), p.get('notes'), p.get('image'), p.get('status'), p.get('created_at'),
                p.get('pdf')
            ))

    if 'clientes' in data:
        for c in data['clientes']:
            cursor.execute("INSERT OR REPLACE INTO clientes (id, name, phone, created_at) VALUES (?, ?, ?, ?)",
                       (c.get('id'), c.get('name'), c.get('phone'), c.get('created_at')))

    if 'orcamentos' in data:
        for o in data['orcamentos']:
            cursor.execute("INSERT OR REPLACE INTO orcamentos (id, title, product, size, price, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                       (o.get('id'), o.get('title'), o.get('product'), o.get('size'), o.get('price'), o.get('created_at')))

    conn.commit()
    conn.close()
    return jsonify({"success": True})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("="*60)
    print("SERVIDOR ELEMENTS PEDIDOS INICIADO!")
    print(f"Acesse no seu navegador: http://localhost:{port}")
    print("Para acessar de outro PC na mesma rede, use o IP deste computador")
    print(f"Exemplo: http://192.168.1.116:{port}")
    print("="*60)
    app.run(host='0.0.0.0', port=port, debug=False)
