from flask import Flask, render_template, request, redirect, url_for, flash, session
import psycopg2, psycopg2.extras
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = "segredo_super_seguro"

DB_URL = os.getenv("DATABASE_URL", "postgresql://savesite_user:5X70ctnMmv1jfWVuCQssRvmQUjW0D56p@dpg-d37hgjjuibrs7392ou1g-a/savesite")

# -------------------- Banco de dados --------------------
def init_db():
    conn = psycopg2.connect(DB_URL, sslmode="require")
    c = conn.cursor()
    
    # Cria tabela clientes
    c.execute("""
    CREATE TABLE IF NOT EXISTS clientes (
        usuario TEXT PRIMARY KEY,
        senha TEXT NOT NULL,
        saldo NUMERIC DEFAULT 0,
        rodadas_gratis INT DEFAULT 0
    );
    """)
    
    # Adiciona coluna admin se não existir
    c.execute("""
    ALTER TABLE clientes
    ADD COLUMN IF NOT EXISTS admin BOOLEAN DEFAULT FALSE;
    """)
    
    # Cria tabela historico
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
    
    # Cria tabela depositos_pendentes
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
    VALUES ('admin','411269',0,TRUE) 
    ON CONFLICT (usuario) DO NOTHING;
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
    clientes = {row["usuario"]: {"senha": row["senha"], "saldo": float(row["saldo"]), "rodadas_gratis": row["rodadas_gratis"], "admin": row["admin"]} for row in c.fetchall()}
    
    c.execute("SELECT * FROM historico ORDER BY data DESC")
    historico = [dict(row) for row in c.fetchall()]
    
    conn.close()
    return {"clientes": clientes, "historico": historico}

def salvar_cliente(usuario, senha=None, saldo=None, rodadas_gratis=None, admin=None):
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
    if admin is not None:
        updates.append("admin=%s")
        params.append(admin)
    
    if updates:
        query = f"INSERT INTO clientes (usuario, senha, saldo, rodadas_gratis, admin) VALUES (%s,%s,%s,%s,%s) ON CONFLICT (usuario) DO UPDATE SET {','.join(updates)}"
        params = [usuario, senha or '', saldo or 0, rodadas_gratis or 0, admin or False] + params
        c.execute(query, params)
    
    conn.commit()
    conn.close()

def registrar_historico(usuario, acao, valor=0, destino=None):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO historico (usuario, acao, valor, destino) VALUES (%s,%s,%s,%s)", (usuario, acao, valor, destino))
    conn.commit()
    conn.close()

# -------------------- Rotas principais --------------------
@app.route("/", methods=["GET","POST"])
def login():
    if request.method == "POST":
        usuario = request.form["usuario"]
        senha = request.form["senha"]
        dados = carregar_dados()
        if usuario in dados["clientes"] and dados["clientes"][usuario]["senha"] == senha:
            session["usuario"] = usuario
            if dados["clientes"][usuario]["admin"]:
                return redirect(url_for("admin_dashboard"))
            return redirect(url_for("dashboard"))
        flash("Login inválido", "danger")
    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    if "usuario" not in session or session["usuario"]=="admin":
        return redirect(url_for("login"))
    usuario = session["usuario"]
    dados = carregar_dados()
    saldo = dados["clientes"][usuario]["saldo"]
    return render_template("dashboard.html", usuario=usuario, saldo=saldo, dados=dados)

# -------------------- Admin --------------------
@app.route("/admin_dashboard")
def admin_dashboard():
    if "usuario" not in session:
        return redirect(url_for("login"))
    dados = carregar_dados()
    usuario = session["usuario"]
    if not dados["clientes"][usuario]["admin"]:
        return redirect(url_for("dashboard"))
    return render_template("admin_dashboard.html", usuario=usuario, dados=dados)

# -------------------- Logout --------------------
@app.route("/logout")
def logout():
    session.pop("usuario", None)
    return redirect(url_for("login"))

# -------------------- Run --------------------
if __name__ == "__main__":
    app.run(debug=True)
