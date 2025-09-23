from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
import psycopg2, psycopg2.extras
import csv, random
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = "segredo_super_seguro"

# -------------------- Banco de dados --------------------
DB_URL = os.getenv("DATABASE_URL", "postgresql://savesite_user:5X70ctnMmv1jfWVuCQssRvmQUjW0D56p@dpg-d37hgjjuibrs7392ou1g-a/savesite")

def get_connection():
    conn = psycopg2.connect(DB_URL, sslmode="require")
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()

    # Tabela de clientes
    c.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            usuario TEXT PRIMARY KEY,
            senha TEXT NOT NULL,
            saldo REAL DEFAULT 0
        )
    """)

    # Insere admin se não existir
    c.execute("INSERT INTO clientes (usuario, senha, saldo) VALUES (%s, %s, %s) ON CONFLICT (usuario) DO NOTHING",
              ("admin", "411269", 0))

    # Tabela de histórico
    c.execute("""
        CREATE TABLE IF NOT EXISTS historico (
            id SERIAL PRIMARY KEY,
            usuario TEXT,
            acao TEXT,
            valor REAL,
            destino TEXT,
            data TEXT
        )
    """)

    # Tabela de depósitos pendentes e notificações
    c.execute("""
        CREATE TABLE IF NOT EXISTS depositos_pendentes (
            id SERIAL PRIMARY KEY,
            usuario TEXT,
            valor REAL,
            data TEXT,
            aprovado INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()

# Inicializa o banco
init_db()

# -------------------- Funções de persistência --------------------
def carregar_dados():
    conn = get_connection()
    c = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    # Clientes
    c.execute("SELECT * FROM clientes")
    clientes = {row["usuario"]: {"senha": row["senha"], "saldo": row["saldo"]} for row in c.fetchall()}

    # Histórico
    c.execute("SELECT * FROM historico")
    historico = [dict(row) for row in c.fetchall()]

    conn.close()
    return {"clientes": clientes, "historico": historico}

def salvar_cliente(usuario, senha=None, saldo=None):
    conn = get_connection()
    c = conn.cursor()

    if senha is not None and saldo is not None:
        c.execute("""
            INSERT INTO clientes (usuario, senha, saldo) VALUES (%s, %s, %s)
            ON CONFLICT (usuario) DO UPDATE SET senha = EXCLUDED.senha, saldo = EXCLUDED.saldo
        """, (usuario, senha, saldo))
    elif saldo is not None:
        c.execute("UPDATE clientes SET saldo = %s WHERE usuario = %s", (saldo, usuario))
    elif senha is not None:
        c.execute("UPDATE clientes SET senha = %s WHERE usuario = %s", (senha, usuario))

    conn.commit()
    conn.close()

def registrar_historico(usuario, acao, valor=0, destino=None):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO historico (usuario, acao, valor, destino, data) VALUES (%s, %s, %s, %s, %s)",
              (usuario, acao, valor, destino, datetime.now().strftime("%d/%m/%Y %H:%M:%S")))
    conn.commit()
    conn.close()

# -------------------- Rotas --------------------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form["usuario"]
        senha = request.form["senha"]
        dados = carregar_dados()
        if usuario in dados["clientes"] and dados["clientes"][usuario]["senha"] == senha:
            session["usuario"] = usuario
            if usuario == "admin":
                return redirect(url_for("admin_depositos"))
            return redirect(url_for("dashboard"))
        flash("Login inválido")
    return render_template("login.html")

@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if request.method == "POST":
        usuario = request.form["usuario"]
        senha = request.form["senha"]
        dados = carregar_dados()
        if usuario in dados["clientes"]:
            flash("Usuário já existe!")
        else:
            salvar_cliente(usuario, senha=senha, saldo=0)
            flash("Cadastro realizado!")
            return redirect(url_for("login"))
    return render_template("cadastro.html")

@app.route("/dashboard")
def dashboard():
    if "usuario" not in session or session["usuario"] == "admin":
        return redirect(url_for("login"))
    usuario = session["usuario"]
    dados = carregar_dados()
    saldo = dados["clientes"][usuario]["saldo"]
    return render_template("dashboard.html", usuario=usuario, saldo=saldo, dados=dados)

# -------------------- Depósito pendente --------------------
@app.route("/deposito", methods=["GET", "POST"])
def deposito():
    if "usuario" not in session or session["usuario"] == "admin":
        return redirect(url_for("login"))
    usuario = session["usuario"]
    if request.method == "POST":
        valor = float(request.form["valor"])
        conn = get_connection()
        c = conn.cursor()
        c.execute("INSERT INTO depositos_pendentes (usuario, valor, data, aprovado) VALUES (%s, %s, %s, 0)",
                  (usuario, valor, datetime.now().strftime("%d/%m/%Y %H:%M:%S")))
        conn.commit()
        conn.close()
        flash("Depósito enviado para aprovação do admin!")
        return redirect(url_for("dashboard"))
    return render_template("deposito.html")

# -------------------- Saque --------------------
@app.route("/saque", methods=["GET", "POST"])
def saque():
    if "usuario" not in session or session["usuario"] == "admin":
        return redirect(url_for("login"))
    usuario = session["usuario"]
    dados = carregar_dados()
    if request.method == "POST":
        valor = float(request.form["valor"])
        if valor <= dados["clientes"][usuario]["saldo"]:
            saldo_atual = dados["clientes"][usuario]["saldo"] - valor
            salvar_cliente(usuario, saldo=saldo_atual)
            registrar_historico(usuario, "Saque", valor)

            conn = get_connection()
            c = conn.cursor()
            c.execute("INSERT INTO depositos_pendentes (usuario, valor, data, aprovado) VALUES (%s, %s, %s, -1)",
                      (usuario, valor, datetime.now().strftime("%d/%m/%Y %H:%M:%S")))
            conn.commit()
            conn.close()

            flash("Saque realizado! O admin foi notificado.")
        else:
            flash("Saldo insuficiente!")
        return redirect(url_for("dashboard"))
    return render_template("saque.html")

# -------------------- Transferência --------------------
@app.route("/transferencia", methods=["GET", "POST"])
def transferencia():
    if "usuario" not in session or session["usuario"] == "admin":
        return redirect(url_for("login"))
    usuario = session["usuario"]
    dados = carregar_dados()
    if request.method == "POST":
        destino = request.form["destino"]
        valor = float(request.form["valor"])
        if destino in dados["clientes"] and valor <= dados["clientes"][usuario]["saldo"]:
            saldo_origem = dados["clientes"][usuario]["saldo"] - valor
            saldo_destino = dados["clientes"][destino]["saldo"] + valor
            salvar_cliente(usuario, saldo=saldo_origem)
            salvar_cliente(destino, saldo=saldo_destino)
            registrar_historico(usuario, "Transferência", valor, destino)
            flash("Transferência realizada!", "success")
        else:
            flash("Erro na transferência!", "danger")
        return redirect(url_for("dashboard"))
    return render_template("transferencia.html", dados=dados)

# -------------------- Alterar senha --------------------
@app.route("/alterar_senha", methods=["GET", "POST"])
def alterar_senha():
    if "usuario" not in session or session["usuario"] == "admin":
        return redirect(url_for("login"))
    usuario = session["usuario"]
    if request.method == "POST":
        nova_senha = request.form["senha"]
        salvar_cliente(usuario, senha=nova_senha)
        flash("Senha alterada com sucesso!", "success")
        return redirect(url_for("dashboard"))
    return render_template("alterar_senha.html", usuario=usuario)

# -------------------- Histórico --------------------
@app.route("/historico")
def historico():
    if "usuario" not in session or session["usuario"] == "admin":
        return redirect(url_for("login"))
    usuario = session["usuario"]
    conn = get_connection()
    c = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    c.execute("SELECT * FROM historico WHERE usuario = %s", (usuario,))
    historico_user = [dict(row) for row in c.fetchall()]
    conn.close()
    return render_template("historico.html", historico=historico_user)

@app.route("/exportar_csv")
def exportar_csv():
    if "usuario" not in session or session["usuario"] == "admin":
        return redirect(url_for("login"))
    usuario = session["usuario"]
    conn = get_connection()
    c = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    c.execute("SELECT * FROM historico WHERE usuario = %s", (usuario,))
    historico_user = [dict(row) for row in c.fetchall()]
    conn.close()

    filename = f"historico_{usuario}.csv"
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["usuario","acao","valor","destino","data"])
        writer.writeheader()
        writer.writerows(historico_user)
    return send_file(filename, as_attachment=True)

# -------------------- Roleta --------------------
# -------------------- Roleta --------------------
# -------------------- ROLETA --------------------
@app.route("/jogos", methods=["GET", "POST"])
def jogos():
    if "usuario" not in session or session["usuario"] == "admin":
        return redirect(url_for("login"))

    usuario = session["usuario"]
    dados = carregar_dados()
    saldo = dados["clientes"][usuario]["saldo"]

    resultado_roleta = None
    resultado_caca = None
    rolos = []

    # Variáveis para lembrar as últimas apostas (para preencher os campos)
    last_aposta_caca = ""
    last_aposta_roleta = ""
    last_lote = ""

    # símbolos do caça-níquel (inclui estrelas e dados)
    simbolos = [
        "🍒", "🍋", "🔔", "⭐", "💎", "🍀", "🍉", "🥭",
        "🍇", "🍌", "🍓", "🍑", "🍍", "🥝", "🥥", "🍈", "🌈", "🎲"
    ]

    if request.method == "POST":
        # guarda últimos valores enviados (úteis para manter no input)
        last_aposta_caca = request.form.get("aposta_caca", "") or ""
        last_aposta_roleta = request.form.get("aposta_roleta", "") or ""
        last_lote = request.form.get("lote", "") or ""

        # -------- CAÇA-NÍQUEL --------
        if "aposta_caca" in request.form:
            try:
                aposta = float(request.form.get("aposta_caca", 0))
            except (ValueError, TypeError):
                flash("Aposta inválida!", "danger")
                return redirect(url_for("jogos"))

            if aposta <= 0:
                resultado_caca = "Digite um valor válido de aposta!"
            elif aposta > saldo:
                resultado_caca = "Saldo insuficiente!"
            else:
                # sorteio dos 3 rolos
                rolos = [random.choice(simbolos) for _ in range(3)]

                # --- Regras especiais (prioridade alta) ---
                if rolos.count("⭐") == 3:
                    ganho = aposta * 200
                    saldo += ganho
                    resultado_caca = f"🌟🌟🌟 JACKPOT SUPREMO! {rolos} Você ganhou R$ {ganho:.2f}!"
                    registrar_historico(usuario, f"Caça-níquel (Jackpot Estrelas {rolos})", ganho)
                elif rolos.count("⭐") == 2:
                    ganho = aposta * 50
                    saldo += ganho
                    resultado_caca = f"🌟 Duas estrelas! {rolos} Você ganhou R$ {ganho:.2f}!"
                    registrar_historico(usuario, f"Caça-níquel (2 Estrelas {rolos})", ganho)
                elif rolos.count("🎲") == 3:
                    ganho = aposta * 80
                    saldo += ganho
                    resultado_caca = f"🎲🎲🎲 TRIPLO DADOS! {rolos} Você ganhou R$ {ganho:.2f}!"
                    registrar_historico(usuario, f"Caça-níquel (3 Dados {rolos})", ganho)
                elif rolos.count("🎲") == 2:
                    ganho = aposta * 20
                    saldo += ganho
                    resultado_caca = f"🎲🎲 Dois dados! {rolos} Você ganhou R$ {ganho:.2f}!"
                    registrar_historico(usuario, f"Caça-níquel (2 Dados {rolos})", ganho)

                # --- Regras padrão ---
                elif rolos[0] == rolos[1] == rolos[2]:
                    ganho = aposta * 30
                    saldo += ganho
                    resultado_caca = f"🎉 Jackpot! {rolos} Você ganhou R$ {ganho:.2f}!"
                    registrar_historico(usuario, f"Caça-níquel (Jackpot {rolos})", ganho)
                elif rolos[0] == rolos[1] or rolos[1] == rolos[2] or rolos[0] == rolos[2]:
                    ganho = aposta * 6
                    saldo += ganho
                    resultado_caca = f"✨ Par! {rolos} Você ganhou R$ {ganho:.2f}!"
                    registrar_historico(usuario, f"Caça-níquel (Par {rolos})", ganho)
                else:
                    saldo -= aposta
                    resultado_caca = f"❌ {rolos} Você perdeu R$ {aposta:.2f}."
                    registrar_historico(usuario, f"Caça-níquel (Derrota {rolos})", -aposta)

                # salva saldo atualizado no banco
                salvar_cliente(usuario, saldo=saldo)

        # -------- ROLETA --------
        elif "aposta_roleta" in request.form:
            try:
                aposta = float(request.form.get("aposta_roleta", 0))
            except (ValueError, TypeError):
                flash("Aposta inválida!", "danger")
                return redirect(url_for("jogos"))

            if aposta <= 0:
                resultado_roleta = "Digite um valor válido de aposta!"
            elif aposta > saldo:
                resultado_roleta = "Saldo insuficiente!"
            else:
                # número sorteado (0-36)
                numero_sorteado = random.randint(0, 36)

                # se usuário apostou num número específico (numero_roleta)
                if "numero_roleta" in request.form and request.form.get("numero_roleta", "") != "":
                    try:
                        escolhido = int(request.form.get("numero_roleta"))
                    except (ValueError, TypeError):
                        escolhido = None

                    if escolhido is not None and escolhido == numero_sorteado:
                        ganho = aposta * 36  # pagamento por número (ex: 35:1 + stake)
                        saldo += ganho
                        resultado_roleta = f"🎉 Número {numero_sorteado}! Você ganhou R$ {ganho:.2f}!"
                        registrar_historico(usuario, f"Roleta (Vitória no número {numero_sorteado})", ganho)
                    else:
                        saldo -= aposta
                        resultado_roleta = f"❌ Caiu {numero_sorteado}. Você perdeu R$ {aposta:.2f}."
                        registrar_historico(usuario, f"Roleta (Derrota no número {numero_sorteado})", -aposta)

                # senão, aposta por cor (cor_roleta)
                else:
                    cor_aposta = (request.form.get("cor_roleta") or "").lower()
                    # definição simplificada: 0 = casa (verde), números pares = vermelho, ímpares = preto
                    if numero_sorteado == 0:
                        cor_real = "verde"
                    else:
                        cor_real = "vermelho" if numero_sorteado % 2 == 0 else "preto"

                    if cor_aposta == cor_real:
                        ganho = aposta * 2
                        saldo += ganho
                        resultado_roleta = f"🎉 Número {numero_sorteado} ({cor_real})! Você ganhou R$ {ganho:.2f}!"
                        registrar_historico(usuario, f"Roleta (Vitória {numero_sorteado} {cor_real})", ganho)
                    else:
                        saldo -= aposta
                        resultado_roleta = f"❌ Número {numero_sorteado} ({cor_real}). Você perdeu R$ {aposta:.2f}."
                        registrar_historico(usuario, f"Roleta (Derrota {numero_sorteado} {cor_real})", -aposta)

                # salva saldo atualizado
                salvar_cliente(usuario, saldo=saldo)

    # renderiza a página (mantendo últimos valores para preencher inputs)
    return render_template(
        "jogos.html",
        saldo=saldo,
        resultado_caca=resultado_caca,
        resultado_roleta=resultado_roleta,
        rolos=rolos,
        last_aposta_caca=last_aposta_caca,
        last_aposta_roleta=last_aposta_roleta,
        last_lote=last_lote
    )





# -------------------- Logout --------------------
@app.route("/logout")
def logout():
    session.pop("usuario", None)
    return redirect(url_for("login"))

# -------------------- Admin --------------------
@app.route("/admin/depositos")
def admin_depositos():
    if "usuario" not in session or session["usuario"] != "admin":
        return redirect(url_for("login"))
    conn = get_connection()
    c = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    c.execute("SELECT * FROM depositos_pendentes ORDER BY aprovado ASC, data DESC")
    depositos = [dict(row) for row in c.fetchall()]
    conn.close()
    return render_template("admin_depositos.html", depositos=depositos)

@app.route("/admin/aprovar/<int:id>")
def aprovar_deposito(id):
    if "usuario" not in session or session["usuario"] != "admin":
        return redirect(url_for("login"))
    conn = get_connection()
    c = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    c.execute("SELECT * FROM depositos_pendentes WHERE id = %s", (id,))
    dep = c.fetchone()
    if dep and dep["aprovado"] == 0:
        c.execute("UPDATE clientes SET saldo = saldo + %s WHERE usuario = %s", (dep["valor"], dep["usuario"]))
        c.execute("UPDATE depositos_pendentes SET aprovado = 1 WHERE id = %s", (id,))
        c.execute("INSERT INTO historico (usuario, acao, valor, destino, data) VALUES (%s, %s, %s, %s, %s)",
                  (dep["usuario"], "Depósito Aprovado", dep["valor"], None, datetime.now().strftime("%d/%m/%Y %H:%M:%S")))
        conn.commit()

    conn.close()
    flash("Depósito aprovado!")
    return redirect(url_for("admin_depositos"))

@app.route("/admin/recusar/<int:id>")
def recusar_deposito(id):
    if "usuario" not in session or session["usuario"] != "admin":
        return redirect(url_for("login"))
    conn = get_connection()
    c = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    c.execute("SELECT * FROM depositos_pendentes WHERE id = %s", (id,))
    dep = c.fetchone()
    if dep and dep["aprovado"] == 0:
        c.execute("UPDATE depositos_pendentes SET aprovado = 2 WHERE id = %s", (id,))
        c.execute("INSERT INTO historico (usuario, acao, valor, destino, data) VALUES (%s, %s, %s, %s, %s)",
                  (dep["usuario"], "Depósito Recusado", dep["valor"], None, datetime.now().strftime("%d/%m/%Y %H:%M:%S")))
        conn.commit()

    conn.close()
    flash("Depósito recusado!")
    return redirect(url_for("admin_depositos"))




if __name__ == "__main__":
    app.run(debug=True)

















