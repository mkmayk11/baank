from flask import Flask, render_template, request, redirect, url_for, flash, session
import psycopg2, psycopg2.extras
import os

app = Flask(__name__)
app.secret_key = "segredo_super_seguro"

DB_URL = os.getenv("DATABASE_URL", "postgresql://savesite_user:5X70ctnMmv1jfWVuCQssRvmQUjW0D56p@dpg-d37hgjjuibrs7392ou1g-a/savesite")

# -------------------- Banco de dados --------------------
def init_db():
    conn = psycopg2.connect(DB_URL, sslmode="require")
    c = conn.cursor()
    
    # Tabela de clientes
    c.execute("""
    CREATE TABLE IF NOT EXISTS clientes (
        usuario TEXT PRIMARY KEY,
        senha TEXT NOT NULL,
        saldo NUMERIC DEFAULT 0,
        rodadas_gratis INT DEFAULT 0,
        admin BOOLEAN DEFAULT FALSE
    );
    """)
    
    # Histórico simples
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

def carregar_clientes():
    conn = get_connection()
    c = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    c.execute("SELECT * FROM clientes")
    clientes = [dict(row) for row in c.fetchall()]
    conn.close()
    return clientes

def salvar_cliente(usuario, senha, saldo=0, rodadas_gratis=0, admin=False):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
    INSERT INTO clientes (usuario, senha, saldo, rodadas_gratis, admin)
    VALUES (%s,%s,%s,%s,%s)
    ON CONFLICT (usuario) DO NOTHING
    """, (usuario, senha, saldo, rodadas_gratis, admin))
    conn.commit()
    conn.close()

# -------------------- Rotas --------------------
@app.route("/", methods=["GET","POST"])
def login():
    if request.method == "POST":
        usuario = request.form["usuario"]
        senha = request.form["senha"]
        conn = get_connection()
        c = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        c.execute("SELECT * FROM clientes WHERE usuario=%s AND senha=%s", (usuario, senha))
        user = c.fetchone()
        conn.close()
        if user:
            session["usuario"] = usuario
            session["admin"] = user["admin"]
            if user["admin"]:
                return redirect(url_for("admin_dashboard"))
            return redirect(url_for("dashboard"))
        flash("Login inválido", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("usuario", None)
    session.pop("admin", None)
    return redirect(url_for("login"))

@app.route("/cadastro", methods=["GET","POST"])
def cadastro():
    if request.method == "POST":
        usuario = request.form["usuario"]
        senha = request.form["senha"]
        salvar_cliente(usuario, senha)
        flash("Cadastro realizado com sucesso!", "success")
        return redirect(url_for("login"))
    return render_template("cadastro.html")

@app.route("/dashboard")
def dashboard():
    if "usuario" not in session or session.get("admin"):
        return redirect(url_for("login"))
    usuario = session["usuario"]
    return render_template("dashboard.html", usuario=usuario)

@app.route("/admin_dashboard")
def admin_dashboard():
    if not session.get("usuario") or not session.get("admin"):
        return redirect(url_for("login"))
    clientes = carregar_clientes()
    return render_template("admin_dashboard.html", clientes=clientes)

# -------------------- Main --------------------
if __name__ == "__main__":
    app.run(debug=True)

