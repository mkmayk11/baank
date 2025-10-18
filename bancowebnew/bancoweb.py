from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import psycopg2, psycopg2.extras
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = "segredo_super_seguro"

DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://savesite_user:5X70ctnMmv1jfWVuCQssRvmQUjW0D56p@dpg-d37hgjjuibrs7392ou1g-a/savesite"
)

# -------------------- Banco de dados --------------------
def init_db():
    conn = psycopg2.connect(DB_URL, sslmode="require")
    c = conn.cursor()
    
    # Tabelas básicas
    c.execute("""
    CREATE TABLE IF NOT EXISTS clientes (
        usuario TEXT PRIMARY KEY,
        senha TEXT NOT NULL,
        saldo NUMERIC DEFAULT 0,
        rodadas_gratis INT DEFAULT 0,
        admin BOOLEAN DEFAULT FALSE
    );
    """)
    
    c.execute("""
    CREATE TABLE IF NOT EXISTS historico (
        id SERIAL PRIMARY KEY,
        usuario TEXT,
        acao TEXT,
        valor NUMERIC DEFAULT 0,
        destino TEXT,
        data TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    
    c.execute("""
    CREATE TABLE IF NOT EXISTS depositos_pendentes (
        id SERIAL PRIMARY KEY,
        usuario TEXT,
        valor NUMERIC,
        data TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        aprovado INT DEFAULT 0
    );
    """)
    
    # Insere admin se não existir
    c.execute("""
    INSERT INTO clientes (usuario, senha, saldo, admin) 
    VALUES ('admin','411269',0,TRUE) ON CONFLICT (usuario) DO NOTHING;
    """)
    
    conn.commit()
    conn.close()

init_db()

# -------------------- Funções auxiliares --------------------
def get_connection():
    return psycopg2.connect(DB_URL, sslmode="require")

def carregar_dados():
    conn = get_connection()
    c = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    c.execute("SELECT * FROM clientes")
    clientes = {
        row["usuario"]: {
            "senha": row["senha"],
            "saldo": float(row["saldo"]),
            "rodadas_gratis": row["rodadas_gratis"],
            "admin": row["admin"]
        }
        for row in c.fetchall()
    }
    
    c.execute("SELECT * FROM historico ORDER BY data DESC")
    historico = [dict(row) for row in c.fetchall()]
    
    c.execute("SELECT * FROM depositos_pendentes ORDER BY data DESC")
    depositos = [dict(row) for row in c.fetchall()]
    
    conn.close()
    return {"clientes": clientes, "historico": historico, "depositos": depositos}

def salvar_cliente(usuario, senha=None, saldo=None, rodadas_gratis=None):
    conn = get_connection()
    c = conn.cursor()
    
    updates = []
    params = []
    if saldo is not None:
        updates.append("saldo=%s")
        params.append(saldo)
    if senha is not None:
        updates.append("senha=%s")
        params.append(senha)
    if rodadas_gratis is not None:
        updates.append("rodadas_gratis=%s")
        params.append(rodadas_gratis)
    
    if updates:
        query = f"""
        INSERT INTO clientes (usuario, senha, saldo, rodadas_gratis) 
        VALUES (%s,%s,%s,%s) 
        ON CONFLICT (usuario) DO UPDATE SET {','.join(updates)}
        """
        params = [usuario, senha or '', saldo or 0, rodadas_gratis or 0] + params
        c.execute(query, params)
    
    conn.commit()
    conn.close()

def registrar_historico(usuario, acao, valor=0, destino=None):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO historico (usuario, acao, valor, destino) VALUES (%s,%s,%s,%s)",
        (usuario, acao, valor, destino)
    )
    conn.commit()
    conn.close()

def registrar_deposito(usuario, valor):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO depositos_pendentes (usuario, valor) VALUES (%s,%s)",
        (usuario, valor)
    )
    conn.commit()
    conn.close()
    registrar_historico(usuario, "Depósito solicitado", valor)

# -------------------- Decorators --------------------
def login_required(func):
    from functools import wraps
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "usuario" not in session:
            flash("Faça login para continuar","warning")
            return redirect(url_for("login"))
        return func(*args, **kwargs)
    return wrapper

def admin_required(func):
    from functools import wraps
    @wraps(func)
    def wrapper(*args, **kwargs):
        usuario = session.get("usuario")
        dados = carregar_dados()
        if not usuario or not dados["clientes"].get(usuario, {}).get("admin"):
            flash("Acesso negado!","danger")
            return redirect(url_for("login"))
        return func(*args, **kwargs)
    return wrapper

# -------------------- Rotas --------------------
@app.route("/", methods=["GET","POST"])
def login():
    if request.method=="POST":
        usuario = request.form["usuario"]
        senha = request.form["senha"]
        dados = carregar_dados()
        cliente = dados["clientes"].get(usuario)
        if cliente and cliente["senha"]==senha:
            session["usuario"] = usuario
            if cliente["admin"]:
                return redirect(url_for("admin_dashboard"))
            return redirect(url_for("dashboard"))
        flash("Login inválido","danger")
    return render_template("login.html")

@app.route("/dashboard")
@login_required
def dashboard():
    usuario = session["usuario"]
    dados = carregar_dados()
    cliente = dados["clientes"][usuario]
    return render_template("dashboard.html", usuario=usuario, saldo=cliente["saldo"], rodadas_gratis=cliente["rodadas_gratis"], historico=dados["historico"])

@app.route("/depositar", methods=["POST"])
@login_required
def depositar():
    usuario = session["usuario"]
    valor = float(request.form.get("valor",0))
    if valor <= 0:
        flash("Valor inválido","danger")
    else:
        registrar_deposito(usuario, valor)
        flash(f"Depósito de R$ {valor:.2f} solicitado com sucesso!","success")
    return redirect(url_for("dashboard"))

@app.route("/admin")
@admin_required
def admin_dashboard():
    dados = carregar_dados()
    return render_template("admin_dashboard.html", depositos=dados["depositos"], clientes=dados["clientes"])

@app.route("/admin/aprovar_deposito/<int:id>")
@admin_required
def aprovar_deposito(id):
    conn = get_connection()
    c = conn.cursor()
    # Pega depósito
    c.execute("SELECT * FROM depositos_pendentes WHERE id=%s", (id,))
    dep = c.fetchone()
    if dep and dep[4]==0:  # aprovado=0
        # Atualiza saldo do cliente
        salvar_cliente(dep[1], saldo=float(carregar_dados()["clientes"][dep[1]]["saldo"]) + float(dep[2]))
        # Marca como aprovado
        c.execute("UPDATE depositos_pendentes SET aprovado=1 WHERE id=%s", (id,))
        conn.commit()
        flash(f"Depósito de R$ {dep[2]:.2f} aprovado para {dep[1]}","success")
    conn.close()
    return redirect(url_for("admin_dashboard"))

@app.route("/logout")
def logout():
    session.pop("usuario",None)
    flash("Você saiu do sistema","info")
    return redirect(url_for("login"))

# -------------------- Inicialização --------------------
if __name__=="__main__":
    app.run(debug=True)
