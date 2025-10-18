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

@app.route("/deposito")
def deposito():
    # Aqui você renderiza a página de depósito
    return render_template("deposito.html")

@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if request.method == "POST":
        usuario = request.form["usuario"]
        senha = request.form["senha"]
        # insira no banco
        conn = psycopg2.connect(DB_URL, sslmode="require")
        cur = conn.cursor()
        cur.execute("INSERT INTO clientes (usuario, senha, saldo) VALUES (%s,%s,0)", (usuario, senha))
        conn.commit()
        cur.close()
        conn.close()
        return redirect(url_for("login"))
    return render_template("cadastro.html")

@app.route("/saque", methods=["GET", "POST"])
def saque():
    if "usuario" not in session:
        return redirect(url_for("login"))
    if request.method == "POST":
        valor = float(request.form["valor"])
        conn = psycopg2.connect(DB_URL, sslmode="require")
        cur = conn.cursor()
        # Atualiza saldo do usuário
        cur.execute("UPDATE clientes SET saldo = saldo - %s WHERE usuario = %s", (valor, session["usuario"]))
        conn.commit()
        cur.close()
        conn.close()
        return redirect(url_for("dashboard"))
    return render_template("saque.html")

@app.route("/alterar_senha", methods=["GET", "POST"])
def alterar_senha():
    if "usuario" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        senha_atual = request.form["senha_atual"]
        nova_senha = request.form["nova_senha"]

        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute("SELECT senha FROM usuarios WHERE usuario = ?", (session["usuario"],))
        senha_banco = cur.fetchone()

        if senha_banco and senha_banco[0] == senha_atual:
            cur.execute("UPDATE usuarios SET senha = ? WHERE usuario = ?", (nova_senha, session["usuario"]))
            conn.commit()
            conn.close()
            return render_template("mensagem.html", msg="Senha alterada com sucesso!")
        else:
            conn.close()
            return render_template("mensagem.html", msg="Senha atual incorreta!")

    return render_template("alterar_senha.html")




# -------------------- Main --------------------
if __name__ == "__main__":
    app.run(debug=True)





