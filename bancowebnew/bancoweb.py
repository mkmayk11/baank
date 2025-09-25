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
from flask import jsonify

@app.route("/jogos", methods=["GET", "POST"])
def jogos():
    if "usuario" not in session or session["usuario"] == "admin":
        return redirect(url_for("login"))

    usuario = session["usuario"]
    dados = carregar_dados()
    saldo = dados["clientes"][usuario]["saldo"]

    # símbolos do caça-níquel
    simbolos = ["🍒","🍋","🔔","⭐","💎","🍀","🍉","🥭","🍇","🍌","🍓","🍑","🍍","🥝","🥥","🍈","🌈","🎲","🏺","💸"]

    if request.method == "POST":
        data = request.get_json()
        tipo = data.get("tipo")

        # -------- CAÇA-NÍQUEL --------
        if tipo == "caca":
            try:
                aposta = float(data.get("aposta", 0))
                lote = int(data.get("lote", 1))
            except:
                return jsonify({"erro":"Aposta inválida"}), 400

            if aposta <= 0 and dados["clientes"][usuario].get("rodadas_gratis", 0) <= 0:
                resultado = "Digite um valor válido de aposta!"
                rolos = ["❔","❔","❔"]
            elif aposta > saldo:
                resultado = "Saldo insuficiente!"
                rolos = ["❔","❔","❔"]
            else:
                rolos = [random.choice(simbolos) for _ in range(3)]
                ganho = 0
                resultado = ""

                # --- novas regras especiais ---
                if rolos.count("💸") == 3:  # TRIO de dinheiro
                    ganho = aposta * 160
                    saldo += ganho
                    resultado = f"💸💸💸 TRIPLO DINHEIRO! {rolos} Você ganhou R$ {ganho:.2f}!"
                    registrar_historico(usuario, f"Caça-níquel (3 Dinheiro {rolos})", ganho)

                elif rolos.count("💸") == 2:  # PAR de dinheiro
                    ganho = aposta * 70
                    saldo += ganho
                    resultado = f"💸💸 Dois Dinheiros! {rolos} Você ganhou R$ {ganho:.2f}!"
                    registrar_historico(usuario, f"Caça-níquel (2 Dinheiro {rolos})", ganho)

                elif rolos.count("🍀") == 2:  # Dois trevos
                    rodadas = 10
                    dados["clientes"][usuario]["rodadas_gratis"] = dados["clientes"][usuario].get("rodadas_gratis", 0) + rodadas
                    resultado = f"🍀🍀 Sorte Grande! {rolos} Você ganhou {rodadas} rodadas grátis!"
                    registrar_historico(usuario, f"Caça-níquel (2 Trevos {rolos})", 0)

                # --- regras especiais já existentes ---
                elif rolos.count("⭐") == 3:
                    ganho = aposta * 200
                    saldo += ganho
                    resultado = f"🌟🌟🌟 JACKPOT SUPREMO! {rolos} Você ganhou R$ {ganho:.2f}!"
                    registrar_historico(usuario, f"Caça-níquel (Jackpot Estrelas {rolos})", ganho)

                elif rolos.count("⭐") == 2:
                    ganho = aposta * 50
                    saldo += ganho
                    resultado = f"🌟 Duas estrelas! {rolos} Você ganhou R$ {ganho:.2f}!"
                    registrar_historico(usuario, f"Caça-níquel (2 Estrelas {rolos})", ganho)

                elif rolos.count("🎲") == 3:
                    ganho = aposta * 80
                    saldo += ganho
                    resultado = f"🎲🎲🎲 TRIPLO DADOS! {rolos} Você ganhou R$ {ganho:.2f}!"
                    registrar_historico(usuario, f"Caça-níquel (3 Dados {rolos})", ganho)

                elif rolos.count("🎲") == 2:
                    ganho = aposta * 20
                    saldo += ganho
                    resultado = f"🎲🎲 Dois dados! {rolos} Você ganhou R$ {ganho:.2f}!"
                    registrar_historico(usuario, f"Caça-níquel (2 Dados {rolos})", ganho)

                # --- regras padrão ---
                elif rolos[0] == rolos[1] == rolos[2]:
                    ganho = aposta * 30
                    saldo += ganho
                    resultado = f"🎉 Jackpot! {rolos} Você ganhou R$ {ganho:.2f}!"
                    registrar_historico(usuario, f"Caça-níquel (Jackpot {rolos})", ganho)

                elif rolos[0] == rolos[1] or rolos[1] == rolos[2] or rolos[0] == rolos[2]:
                    ganho = aposta * 6
                    saldo += ganho
                    resultado = f"✨ Par! {rolos} Você ganhou R$ {ganho:.2f}!"
                    registrar_historico(usuario, f"Caça-níquel (Par {rolos})", ganho)

                else:
                    if dados["clientes"][usuario].get("rodadas_gratis", 0) > 0:
                        dados["clientes"][usuario]["rodadas_gratis"] -= 1
                        resultado = f"❌ {rolos} Você perdeu uma rodada grátis, saldo não foi descontado."
                    else:
                        saldo -= aposta
                        resultado = f"❌ {rolos} Você perdeu R$ {aposta:.2f}."
                        registrar_historico(usuario, f"Caça-níquel (Derrota {rolos})", -aposta)

            salvar_cliente(usuario, saldo)

            return jsonify({
                "rolos": rolos,
                "resultado": resultado,
                "saldo": saldo,
                "rodadas_gratis": dados["clientes"][usuario].get("rodadas_gratis", 0)
            })

    # GET normal
    return render_template(
        "jogos.html",
        saldo=saldo,
        last_aposta_caca="",
        last_aposta_roleta="",
        last_lote="",
        last_numero_aposta="",
        dados=dados
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

# -------------------- Saques (admin) --------------------
@app.route("/admin/aprovar_saque/<int:id>")
def aprovar_saque(id):
    if "usuario" not in session or session["usuario"] != "admin":
        return redirect(url_for("login"))
    conn = get_connection()
    c = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    c.execute("SELECT * FROM depositos_pendentes WHERE id = %s", (id,))
    saque = c.fetchone()
    if saque and saque["aprovado"] == -1:
        # Só marca como aprovado, já foi debitado no pedido de saque
        c.execute("UPDATE depositos_pendentes SET aprovado = 1 WHERE id = %s", (id,))
        c.execute("INSERT INTO historico (usuario, acao, valor, destino, data) VALUES (%s,%s,%s,%s,%s)",
                  (saque["usuario"], "Saque Aprovado", saque["valor"], None,
                   datetime.now().strftime("%d/%m/%Y %H:%M:%S")))
        conn.commit()

    conn.close()
    flash("Saque aprovado!")
    return redirect(url_for("admin_depositos"))

@app.route("/admin/recusar_saque/<int:id>")
def recusar_saque(id):
    if "usuario" not in session or session["usuario"] != "admin":
        return redirect(url_for("login"))
    conn = get_connection()
    c = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    c.execute("SELECT * FROM depositos_pendentes WHERE id = %s", (id,))
    saque = c.fetchone()
    if saque and saque["aprovado"] == -1:
        # Devolve o valor para o saldo do usuário
        c.execute("UPDATE clientes SET saldo = saldo + %s WHERE usuario = %s",
                  (saque["valor"], saque["usuario"]))
        c.execute("UPDATE depositos_pendentes SET aprovado = 2 WHERE id = %s", (id,))
        c.execute("INSERT INTO historico (usuario, acao, valor, destino, data) VALUES (%s,%s,%s,%s,%s)",
                  (saque["usuario"], "Saque Recusado (valor devolvido)", saque["valor"], None,
                   datetime.now().strftime("%d/%m/%Y %H:%M:%S")))
        conn.commit()

    conn.close()
    flash("Saque recusado! Valor devolvido ao usuário.")
    return redirect(url_for("admin_depositos"))


# -------------------- Deletar histórico de depósitos/saques --------------------
@app.route("/admin/deletar_historico")
def deletar_historico():
    if "usuario" not in session or session["usuario"] != "admin":
        return redirect(url_for("login"))

    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM depositos_pendentes")
    conn.commit()
    conn.close()

    flash("Histórico de depósitos/saques deletado!")
    return redirect(url_for("admin_depositos"))

# -------------------- Histórico - deletar tudo --------------------
@app.route("/admin/deletar_todo_historico")
def deletar_todo_historico():
    if "usuario" not in session:
        return redirect(url_for("login"))

    if session["usuario"] == "admin":
        # Admin apaga geral
        conn = get_connection()
        c = conn.cursor()
        c.execute("DELETE FROM historico")
        conn.commit()
        conn.close()
        flash("Todo o histórico foi deletado pelo Admin!")
    else:
        # Usuário comum apaga só o dele
        usuario = session["usuario"]
        conn = get_connection()
        c = conn.cursor()
        c.execute("DELETE FROM historico WHERE usuario = %s", (usuario,))
        conn.commit()
        conn.close()
        flash("Seu histórico foi deletado.")

    return redirect(url_for("historico"))


# -------------------- Histórico - deletar selecionados --------------------
@app.route("/admin/deletar_historico_selecionados", methods=["POST"])
def deletar_historico_selecionados():
    if "usuario" not in session:
        return redirect(url_for("login"))

    ids = request.form.getlist("ids")
    if not ids:
        flash("Nenhum item selecionado para deletar.")
        return redirect(url_for("historico"))

    conn = get_connection()
    c = conn.cursor()

    if session["usuario"] == "admin":
        # Admin pode apagar qualquer id
        query = "DELETE FROM historico WHERE id = ANY(%s)"
        c.execute(query, (ids,))
        flash(f"{len(ids)} registros foram deletados pelo Admin!")
    else:
        # Usuário só pode apagar IDs que pertencem a ele
        usuario = session["usuario"]
        query = "DELETE FROM historico WHERE id = ANY(%s) AND usuario = %s"
        c.execute(query, (ids, usuario))
        flash("Seus registros selecionados foram deletados.")

    conn.commit()
    conn.close()
    return redirect(url_for("historico"))





if __name__ == "__main__":
    app.run(debug=True)




























