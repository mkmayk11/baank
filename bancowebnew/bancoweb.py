from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file, jsonify
import psycopg2, psycopg2.extras
import csv, random
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = "segredo_super_seguro"

# -------------------- Banco de dados --------------------
DB_URL = os.getenv("DATABASE_URL", "postgresql://savesite_user:5X70ctnMmv1jfWVuCQssRvmQUjW0D56p@dpg-d37hgjjuibrs7392ou1g-a/savesite")

def criar_tabelas():
    conn = psycopg2.connect(DB_URL)
    c = conn.cursor()

    # Tabela de usuários (se ainda não existir)
    c.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id SERIAL PRIMARY KEY,
        nome VARCHAR(100) UNIQUE NOT NULL,
        saldo NUMERIC(12,2) DEFAULT 0
    );
    """)

    # Tabela de jogos
    c.execute("""
    CREATE TABLE IF NOT EXISTS jogos (
        id SERIAL PRIMARY KEY,
        time1 VARCHAR(100) NOT NULL,
        time2 VARCHAR(100) NOT NULL,
        odds1 NUMERIC(10,2) NOT NULL,
        odds2 NUMERIC(10,2) NOT NULL,
        odds_empate NUMERIC(10,2) NOT NULL,
        ativo BOOLEAN DEFAULT TRUE
    );
    """)

    # Tabela de apostas
    c.execute("""
    CREATE TABLE IF NOT EXISTS apostas (
        id SERIAL PRIMARY KEY,
        usuario VARCHAR(100) REFERENCES usuarios(nome),
        jogo_id INT REFERENCES jogos(id),
        valor NUMERIC(12,2) NOT NULL,
        escolha VARCHAR(20) NOT NULL,
        resultado VARCHAR(20),  -- pendente, vitoria, derrota
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    conn.commit()
    c.close()
    conn.close()
    print("Tabelas criadas/verificadas com sucesso!")

# Chamar a função quando iniciar o Flask
criar_tabelas()



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

    # Tabela de jogos de futebol (admin define odds)
    c.execute("""
        CREATE TABLE IF NOT EXISTS jogos_futebol (
            id SERIAL PRIMARY KEY,
            time1 TEXT NOT NULL,
            time2 TEXT NOT NULL,
            odds1 REAL NOT NULL,
            odds_empate REAL NOT NULL,
            odds2 REAL NOT NULL
        )
    """)

    conn.commit()
    conn.close()

# Inicializa o banco
init_db()


# -------------------- Funções de persistência --------------------

def garantir_colunas_apostas():
    conn = psycopg2.connect(DB_URL)
    c = conn.cursor()
    # Coluna resultado
    c.execute("""
        ALTER TABLE apostas
        ADD COLUMN IF NOT EXISTS resultado TEXT DEFAULT 'pendente';
    """)
    # Coluna escolha (porque você tem erros com ela)
    c.execute("""
        ALTER TABLE apostas
        ADD COLUMN IF NOT EXISTS escolha TEXT;
    """)
    conn.commit()
    conn.close()



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

def carregar_cliente(usuario):
    dados = carregar_dados()
    return dados["clientes"].get(usuario)

def criar_coluna_resultado():
    conn = psycopg2.connect(DB_URL)
    c = conn.cursor()
    c.execute("""
        ALTER TABLE apostas
        ADD COLUMN IF NOT EXISTS resultado TEXT DEFAULT 'pendente';
    """)
    conn.commit()
    conn.close()


# Garante que o usuário exista na tabela usuarios
def garantir_usuario(usuario):
    conn = psycopg2.connect(DB_URL)
    c = conn.cursor()
    c.execute("SELECT usuario FROM usuarios WHERE usuario = %s", (usuario,))
    if not c.fetchone():
        c.execute("INSERT INTO usuarios (usuario) VALUES (%s)", (usuario,))
        conn.commit()
    conn.close()


# Registrar aposta (exemplo adaptado)
def registrar_aposta(usuario, jogo_id, valor, escolha):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO apostas (usuario, jogo_id, valor, escolha)
        VALUES (%s, %s, %s, %s)
    """, (usuario, jogo_id, valor, escolha))
    conn.commit()
    conn.close()






# Chame isso no início do seu app para garantir coluna
criar_coluna_resultado()

# Chame essa função uma vez no início do seu app
garantir_colunas_apostas()



# -------------------- Rotas básicas --------------------


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




# -------------------- Apostar Futebol --------------------
@app.route("/apostar_futebol", methods=["POST"])
def apostar_futebol():
    if "usuario" not in session or session["usuario"] == "admin":
        return jsonify({"success": False, "mensagem": "Não logado."})

    data = request.get_json()
    usuario = session["usuario"]
    jogo_id = int(data.get("jogo_id"))
    vencedor = data.get("vencedor")
    valor = float(data.get("valor"))

    # Busca saldo atual
    saldo = carregar_dados()["clientes"][usuario]["saldo"]
    if valor <= 0 or valor > saldo:
        return jsonify({"success": False, "mensagem": "Saldo insuficiente."})

    # Deduz saldo
    saldo -= valor
    salvar_cliente(usuario, saldo=saldo)

    # Busca o jogo e odds
    conn = get_connection()
    c = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    c.execute("SELECT * FROM jogos_futebol WHERE id = %s", (jogo_id,))
    jogo = c.fetchone()
    conn.close()
    if not jogo:
        return jsonify({"success": False, "mensagem": "Jogo não encontrado."})

    # Define a odd escolhida
    if vencedor == "time1":
        odds = jogo["odds1"]
    elif vencedor == "time2":
        odds = jogo["odds2"]
    elif vencedor == "empate":
        odds = jogo["odds_empate"]
    else:
        return jsonify({"success": False, "mensagem": "Seleção inválida."})

    # Registrar aposta
    registrar_aposta(usuario, jogo_id, valor, vencedor)
    registrar_historico(usuario, f"Aposta Futebol: {jogo['time1']} x {jogo['time2']} - Escolha: {vencedor}", valor)

    return jsonify({"success": True, "saldo": saldo, "mensagem": f"Aposta registrada! Odds: {odds}"})





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

def registrar_aposta(usuario, jogo_id, valor, escolha):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO apostas (usuario, jogo_id, valor, escolha)
        VALUES (%s, %s, %s, %s)
    """, (usuario, jogo_id, valor, escolha))
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

# -------------------- Jogos (Caça-níquel e Roleta) --------------------
# -------------------- Roleta e Caça-níquel --------------------
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

            rodadas_gratis_usuario = dados["clientes"][usuario].get("rodadas_gratis", 0)
            saldo_real = saldo

            if aposta <= 0 and rodadas_gratis_usuario <= 0:
                resultado = "Digite um valor válido de aposta!"
                rolos = ["❔","❔","❔"]
            elif aposta > saldo_real and rodadas_gratis_usuario <= 0:
                resultado = "Saldo insuficiente!"
                rolos = ["❔","❔","❔"]
            else:
                rolos = [random.choice(simbolos) for _ in range(3)]
                ganho = 0
                resultado = ""

                # --- novas regras especiais ---
                if rolos.count("💸") == 3:  # TRIO de dinheiro
                    ganho = aposta * 160
                    saldo_real += ganho
                    resultado = f"💸💸💸 TRIPLO DINHEIRO! {rolos} Você ganhou R$ {ganho:.2f}!"
                    registrar_historico(usuario, f"Caça-níquel (3 Dinheiro {rolos})", ganho)

                elif rolos.count("💸") == 2:  # PAR de dinheiro
                    ganho = aposta * 70
                    saldo_real += ganho
                    resultado = f"💸💸 Dois Dinheiros! {rolos} Você ganhou R$ {ganho:.2f}!"
                    registrar_historico(usuario, f"Caça-níquel (2 Dinheiro {rolos})", ganho)

                elif rolos.count("🍀") == 2:  # Dois trevos
                    rodadas_gratis_usuario += 10
                    resultado = f"🍀🍀 Sorte Grande! {rolos} Você ganhou 10 rodadas grátis!"
                    registrar_historico(usuario, f"Caça-níquel (2 Trevos {rolos})", 0)

                # --- regras padrão já existentes ---
                elif rolos.count("⭐") == 3:
                    ganho = aposta * 200
                    saldo_real += ganho
                    resultado = f"🌟🌟🌟 JACKPOT SUPREMO! {rolos} Você ganhou R$ {ganho:.2f}!"
                    registrar_historico(usuario, f"Caça-níquel (Jackpot Estrelas {rolos})", ganho)

                elif rolos.count("⭐") == 2:
                    ganho = aposta * 50
                    saldo_real += ganho
                    resultado = f"🌟 Duas estrelas! {rolos} Você ganhou R$ {ganho:.2f}!"
                    registrar_historico(usuario, f"Caça-níquel (2 Estrelas {rolos})", ganho)

                elif rolos.count("🎲") == 3:
                    ganho = aposta * 80
                    saldo_real += ganho
                    resultado = f"🎲🎲🎲 TRIPLO DADOS! {rolos} Você ganhou R$ {ganho:.2f}!"
                    registrar_historico(usuario, f"Caça-níquel (3 Dados {rolos})", ganho)

                elif rolos.count("🎲") == 2:
                    ganho = aposta * 20
                    saldo_real += ganho
                    resultado = f"🎲🎲 Dois dados! {rolos} Você ganhou R$ {ganho:.2f}!"
                    registrar_historico(usuario, f"Caça-níquel (2 Dados {rolos})", ganho)

                elif rolos[0] == rolos[1] == rolos[2]:
                    ganho = aposta * 30
                    saldo_real += ganho
                    resultado = f"🎉 Jackpot! {rolos} Você ganhou R$ {ganho:.2f}!"
                    registrar_historico(usuario, f"Caça-níquel (Jackpot {rolos})", ganho)

                elif rolos[0] == rolos[1] or rolos[1] == rolos[2] or rolos[0] == rolos[2]:
                    ganho = aposta * 6
                    saldo_real += ganho
                    resultado = f"✨ Par! {rolos} Você ganhou R$ {ganho:.2f}!"
                    registrar_historico(usuario, f"Caça-níquel (Par {rolos})", ganho)

                else:
                    if rodadas_gratis_usuario > 0:
                        rodadas_gratis_usuario -= 1
                        resultado = f"❌ {rolos} Você perdeu uma rodada grátis, saldo não foi descontado."
                    else:
                        saldo_real -= aposta
                        resultado = f"❌ {rolos} Você perdeu R$ {aposta:.2f}."
                        registrar_historico(usuario, f"Caça-níquel (Derrota {rolos})", -aposta)

            dados["clientes"][usuario]["rodadas_gratis"] = rodadas_gratis_usuario
            saldo = saldo_real
            salvar_cliente(usuario, saldo=saldo)

            return jsonify({
                "rolos": rolos,
                "resultado": resultado,
                "saldo": saldo,
                "rodadas_gratis": rodadas_gratis_usuario
            })
                  # -------- ROLETA --------
        elif tipo == "roleta":
            try:
                aposta = float(data.get("aposta", 0))
                numero = int(data.get("numero"))
            except:
                return jsonify({"erro": "Aposta ou número inválido"}), 400

            if aposta <= 0 or aposta > saldo:
                return jsonify({"erro": "Aposta inválida ou saldo insuficiente"}), 400

            numero_sorteado = random.randint(0, 20)
            saldo_real = saldo
            resultado = f"Caiu {numero_sorteado}."

            if numero == numero_sorteado:
                premio = aposta * 36
                saldo_real += premio
                resultado += f" 🎉 Acertou! Prêmio x36 = R$ {premio:.2f}"
                registrar_historico(usuario, f"Roleta acerto {numero_sorteado}", premio)
            else:
                saldo_real -= aposta
                registrar_historico(usuario, f"Roleta erro {numero_sorteado}", -aposta)

            saldo = saldo_real
            salvar_cliente(usuario, saldo=saldo)

            return jsonify({
                "numero": numero_sorteado,
                "resultado": resultado,
                "saldo": saldo
            })

    # -------- GET normal --------
    rodadas_gratis = dados["clientes"][usuario].get("rodadas_gratis", 0)
    return render_template(
        "jogos.html",
        saldo=saldo,
        last_aposta_caca="",
        last_aposta_roleta="",
        last_lote="",
        last_numero_aposta="",
        rodadas_gratis=rodadas_gratis
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

# -------------------- ADMIN FUTEBOL --------------------
@app.route("/admin_futebol", methods=["GET", "POST"])
def admin_futebol():
    # verifica sessão de admin
    if "usuario_id" not in session or not session.get("is_admin"):
        flash("Acesso negado! Você precisa estar logado como administrador.", "danger")
        return redirect(url_for("login"))

    conn = get_connection()
    cur = conn.cursor()

    try:
        # ---------- POST: inserir jogo e mercados ----------
        if request.method == "POST":
            time1 = request.form["time1"]
            time2 = request.form["time2"]
            odds1 = request.form["odds1"]
            odds_empate = request.form["odds_empate"]
            odds2 = request.form["odds2"]

            odd_resultado = request.form.get("odd_resultado") or None
            odd_gols = request.form.get("odd_gols") or None
            odd_cartoes = request.form.get("odd_cartoes") or None
            odd_expulsoes = request.form.get("odd_expulsoes") or None

            try:
                # insere jogo
                cur.execute(
                    "INSERT INTO jogos_futebol (time1, time2, odds1, odds_empate, odds2) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                    (time1, time2, odds1, odds_empate, odds2),
                )
                jogo_row = cur.fetchone()
                jogo_id = jogo_row["id"] if jogo_row else None
                if not jogo_id:
                    raise Exception("Não foi possível obter ID do jogo inserido.")

                # insere mercados básicos
                cur.execute("INSERT INTO mercados_jogo (jogo_id, nome, odd) VALUES (%s, %s, %s)", (jogo_id, "Time 1", odds1))
                cur.execute("INSERT INTO mercados_jogo (jogo_id, nome, odd) VALUES (%s, %s, %s)", (jogo_id, "Empate", odds_empate))
                cur.execute("INSERT INTO mercados_jogo (jogo_id, nome, odd) VALUES (%s, %s, %s)", (jogo_id, "Time 2", odds2))

                # insere mercados extras
                if odd_resultado:
                    cur.execute("INSERT INTO mercados_jogo (jogo_id, nome, odd) VALUES (%s, %s, %s)", (jogo_id, "Odd Resultado", odd_resultado))
                if odd_gols:
                    cur.execute("INSERT INTO mercados_jogo (jogo_id, nome, odd) VALUES (%s, %s, %s)", (jogo_id, "Gols", odd_gols))
                if odd_cartoes:
                    cur.execute("INSERT INTO mercados_jogo (jogo_id, nome, odd) VALUES (%s, %s, %s)", (jogo_id, "Cartões", odd_cartoes))
                if odd_expulsoes:
                    cur.execute("INSERT INTO mercados_jogo (jogo_id, nome, odd) VALUES (%s, %s, %s)", (jogo_id, "Expulsões", odd_expulsoes))

                conn.commit()
                flash("Jogo e mercados adicionados com sucesso!", "success")
            except Exception as e:
                conn.rollback()
                flash(f"Erro ao adicionar jogo: {e}", "danger")

            return redirect(url_for("admin_futebol"))

        # ---------- GET: buscar jogos e apostas ----------
        cur.execute("""
            SELECT j.id, j.time1, j.time2, j.ativo,
                   json_agg(json_build_object('id', m.id, 'nome', m.nome, 'odd', m.odd)) 
                   FILTER (WHERE m.id IS NOT NULL) AS mercados
            FROM jogos_futebol j
            LEFT JOIN mercados_jogo m ON j.id = m.jogo_id
            GROUP BY j.id
            ORDER BY j.id DESC
        """)
        jogos = cur.fetchall()

        cur.execute("""
            SELECT a.id, a.usuario_id AS usuario, a.valor, 
                   COALESCE(a.resultado, 'Pendente') AS resultado,
                   a.criado_em, aj.jogo_id, j.time1, j.time2, aj.escolha, aj.resultado AS resultado_jogo
            FROM apostas a
            JOIN apostas_jogos aj ON a.id = aj.aposta_id
            JOIN jogos_futebol j ON aj.jogo_id = j.id
            ORDER BY COALESCE(a.criado_em, NOW()) DESC
            LIMIT 500
        """)
        apostas = cur.fetchall()

    except Exception as e:
        flash(f"Erro ao carregar admin_futebol: {e}", "danger")
        jogos, apostas = [], []
    finally:
        cur.close()
        conn.close()

    return render_template("admin_futebol.html", jogos=jogos, apostas=apostas)















@app.route("/admin/futebol/toggle/<int:jogo_id>", methods=["POST"])
def toggle_jogo(jogo_id):
    if "usuario" not in session:
        return redirect(url_for("login"))

    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    cur.execute("UPDATE jogos_futebol SET ativo = NOT ativo WHERE id = %s", (jogo_id,))
    conn.commit()

    cur.close()
    conn.close()
    return redirect(url_for("admin_futebol"))


@app.route("/admin/futebol/delete/<int:jogo_id>", methods=["POST"])
def delete_jogo(jogo_id):
    if "usuario" not in session:
        return redirect(url_for("login"))

    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    cur.execute("DELETE FROM jogos_futebol WHERE id = %s", (jogo_id,))
    conn.commit()

    cur.close()
    conn.close()
    return redirect(url_for("admin_futebol"))


# ---------- Rota futebol ----------
@app.route("/futebol", methods=["GET", "POST"])
def futebol():
    # verifica sessão
    if "usuario_id" not in session:
        flash("Você precisa estar logado para apostar.", "warning")
        return redirect(url_for("login"))

    usuario_id = session["usuario_id"]

    # abre conexão
    conn = psycopg2.connect(DB_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    cur = conn.cursor()

    try:
        # ---------- POST: criar aposta ----------
        if request.method == "POST":
            jogo_id = request.form.get("jogo_id")
            mercado_id = request.form.get("mercado_id")
            valor = float(request.form.get("valor"))

            # Verifica saldo
            cur.execute("SELECT saldo FROM usuarios WHERE id = %s", (usuario_id,))
            usuario = cur.fetchone()
            saldo = usuario["saldo"] if usuario else 0
            if valor > saldo:
                flash("Saldo insuficiente!", "danger")
                return redirect(url_for("futebol"))

            # Insere aposta
            cur.execute(
                "INSERT INTO apostas (usuario_id, valor, criado_em) VALUES (%s, %s, NOW()) RETURNING id",
                (usuario_id, valor),
            )
            aposta_id = cur.fetchone()["id"]

            cur.execute(
                "INSERT INTO apostas_jogos (aposta_id, jogo_id, mercado_id, valor) VALUES (%s, %s, %s, %s)",
                (aposta_id, jogo_id, mercado_id, valor),
            )

            # Atualiza saldo
            novo_saldo = saldo - valor
            cur.execute("UPDATE usuarios SET saldo = %s WHERE id = %s", (novo_saldo, usuario_id))

            conn.commit()
            flash("Aposta registrada com sucesso!", "success")
            return redirect(url_for("futebol"))

        # ---------- GET: buscar jogos e mercados ----------
        cur.execute("""
            SELECT j.id, j.time1, j.time2, j.ativo,
                   json_agg(json_build_object('id', m.id, 'nome', m.nome, 'odd', m.odd)) 
                   FILTER (WHERE m.id IS NOT NULL) AS mercados
            FROM jogos_futebol j
            LEFT JOIN mercados_jogo m ON j.id = m.jogo_id
            WHERE j.ativo = TRUE
            GROUP BY j.id
            ORDER BY j.id DESC
        """)
        jogos = cur.fetchall()

        # Preenche apostas de cada usuário para mostrar no mesmo jogo
        for jogo in jogos:
            cur.execute("""
                SELECT aj.id, m.id AS mercado_id, m.nome, aj.valor, 
                       CASE WHEN a.resultado IS NULL THEN 'Pendente' ELSE a.resultado END AS resultado
                FROM apostas_jogos aj
                JOIN apostas a ON aj.aposta_id = a.id
                JOIN mercados_jogo m ON aj.mercado_id = m.id
                WHERE aj.jogo_id = %s AND a.usuario_id = %s
            """, (jogo["id"], usuario_id))
            apostas_usuario = cur.fetchall()
            # associa odds corretas
            for ap in apostas_usuario:
                ap['odd'] = next((m['odd'] for m in jogo['mercados'] if m['id'] == ap['mercado_id']), None)
            jogo["apostas_usuario"] = apostas_usuario if apostas_usuario else []

        # Busca saldo do usuário
        cur.execute("SELECT saldo FROM usuarios WHERE id = %s", (usuario_id,))
        usuario = cur.fetchone()
        saldo_usuario = usuario["saldo"] if usuario else 0

    except Exception as e:
        flash(f"Erro ao carregar jogos: {e}", "danger")
        jogos, saldo_usuario = [], 0
    finally:
        cur.close()
        conn.close()

    return render_template("futebol.html", jogos=jogos, saldo_usuario=saldo_usuario)




@app.route('/atualizar_aposta', methods=['POST'])
def atualizar_aposta():
    aposta_id = request.form.get('aposta_id')
    novo_status = request.form.get('resultado')  # "vitoria" ou "derrota"

    if not aposta_id or novo_status not in ['vitoria', 'derrota']:
        flash("Erro ao atualizar aposta.", "danger")
        return redirect(url_for('admin_futebol'))

    # Atualiza o status no banco
    try:
        conn = psycopg2.connect(DB_URL)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE apostas SET status = %s WHERE id = %s",
            (novo_status, aposta_id)
        )
        conn.commit()
        cursor.close()
        conn.close()
        flash(f"Aposta atualizada para '{resultado}'.", "success")
    except Exception as e:
        flash(f"Erro ao atualizar aposta: {str(e)}", "danger")

    return redirect(url_for('admin_futebol'))



import psycopg2

DB_URL = "postgresql://savesite_user:5X70ctnMmv1jfWVuCQssRvmQUjW0D56p@dpg-d37hgjjuibrs7392ou1g-a/savesite"

@app.route("/setup_db")
def setup_db():
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()

        # Cria tabela de usuários
        cur.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            username TEXT PRIMARY KEY,
            saldo NUMERIC DEFAULT 0
        );
        """)

        # Cria tabela de jogos de futebol
        cur.execute("""
        CREATE TABLE IF NOT EXISTS jogos_futebol (
            id SERIAL PRIMARY KEY,
            time1 TEXT NOT NULL,
            time2 TEXT NOT NULL,
            odds1 NUMERIC NOT NULL,
            odds2 NUMERIC NOT NULL,
            odds_empate NUMERIC NOT NULL,
            ativo BOOLEAN DEFAULT TRUE
        );
        """)

        # Cria tabela de apostas
        cur.execute("""
        CREATE TABLE IF NOT EXISTS apostas (
            id SERIAL PRIMARY KEY,
            usuario TEXT REFERENCES usuarios(username),
            jogo_id INT REFERENCES jogos_futebol(id),
            valor NUMERIC NOT NULL,
            data_aposta TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Insere usuário de teste (opcional)
        cur.execute("""
        INSERT INTO usuarios (username, saldo) 
        VALUES ('teste', 100) 
        ON CONFLICT (username) DO NOTHING;
        """)

        conn.commit()
        cur.close()
        conn.close()
        return "Tabelas criadas com sucesso! Usuário 'teste' com saldo 100 criado."
    except Exception as e:
        return f"Erro: {e}"


import psycopg2

conn = psycopg2.connect("postgresql://savesite_user:5X70ctnMmv1jfWVuCQssRvmQUjW0D56p@dpg-d37hgjjuibrs7392ou1g-a/savesite")
c = conn.cursor()
c.execute("""
CREATE TABLE IF NOT EXISTS apostas (
    id SERIAL PRIMARY KEY,
    usuario TEXT REFERENCES clientes(usuario),
    jogo_id INT REFERENCES jogos_futebol(id),
    valor NUMERIC NOT NULL,
    escolha TEXT NOT NULL,
    status TEXT DEFAULT 'pendente',
    data_aposta TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
""")
conn.commit()
conn.close()


# Chame essa função uma vez no seu Flask antes de começar a usar apostas
criar_coluna_resultado()

@app.route("/criar_usuario", methods=["GET", "POST"])
def criar_usuario():
    if request.method == "POST":
        username = request.form["username"]
        saldo_inicial = request.form.get("saldo", 0)

        conn = psycopg2.connect(DB_URL)
        c = conn.cursor()

        # Verifica se já existe
        c.execute("SELECT 1 FROM usuarios WHERE username = %s", (username,))
        if c.fetchone():
            conn.close()
            flash("Usuário já existe!", "warning")
            return redirect(url_for("criar_usuario"))

        # Cria novo usuário
        c.execute(
            "INSERT INTO usuarios (username, saldo) VALUES (%s, %s)",
            (username, saldo_inicial),
        )
        conn.commit()
        conn.close()

        flash(f"Usuário {username} criado com saldo {saldo_inicial}", "success")
        return redirect(url_for("criar_usuario"))

    # Form simples
    return """
    <h2>Criar Usuário</h2>
    <form method="post">
        <label>Nome:</label><br>
        <input type="text" name="username" required><br><br>
        <label>Saldo inicial:</label><br>
        <input type="number" step="0.01" name="saldo" value="0"><br><br>
        <button type="submit">Criar</button>
    </form>
    """
@app.route("/fixar_apostas")
def fixar_apostas():
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()

        # Adiciona coluna status (caso não exista)
        cur.execute("""
            ALTER TABLE apostas
            ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pendente';
        """)

        # Adiciona coluna resultado (caso não exista)
        cur.execute("""
            ALTER TABLE apostas
            ADD COLUMN IF NOT EXISTS resultado TEXT DEFAULT 'pendente';
        """)

        conn.commit()
        cur.close()
        conn.close()
        return "✅ Colunas 'status' e 'resultado' foram adicionadas (se não existiam)."

    except Exception as e:
        return f"❌ Erro: {str(e)}"

from decimal import Decimal

from flask import Flask, redirect, url_for, flash
import psycopg2
import psycopg2.extras
from decimal import Decimal

@app.route("/atualizar_resultado/<int:aposta_id>/<resultado>")
def atualizar_resultado(aposta_id, resultado):
    conn = psycopg2.connect(DB_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    cur = conn.cursor()
    try:
        # Buscar dados da aposta
        cur.execute("""
            SELECT a.usuario, a.valor, a.escolha, j.odds1, j.odds_empate, j.odds2
            FROM apostas a
            JOIN jogos_futebol j ON a.jogo_id = j.id
            WHERE a.id = %s
        """, (aposta_id,))
        aposta = cur.fetchone()

        if not aposta:
            flash("Aposta não encontrada.", "danger")
            return redirect(url_for("admin_futebol"))

        # Atualizar resultado da aposta
        cur.execute("UPDATE apostas SET resultado = %s WHERE id = %s", (resultado, aposta_id))

        # Se vitória, calcular lucro e atualizar saldo do usuário
        if resultado.lower() == "vitoria":
            valor = aposta['valor']  # já é Decimal
            escolha = aposta['escolha']
            # Determinar odds corretas e converter para Decimal
            if escolha.lower() == 'time1':
                odds = Decimal(aposta['odds1'])
            elif escolha.lower() == 'empate':
                odds = Decimal(aposta['odds_empate'])
            else:
                odds = Decimal(aposta['odds2'])

            lucro = valor * odds

            cur.execute("UPDATE clientes SET saldo = saldo + %s WHERE usuario = %s", (lucro, aposta['usuario']))

        conn.commit()
        flash("Resultado atualizado com sucesso!", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao atualizar resultado: {e}", "danger")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for("admin_futebol"))



@app.route("/deletar_jogo/<int:jogo_id>")
def deletar_jogo(jogo_id):
    conn = psycopg2.connect(DB_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    cur = conn.cursor()
    try:
        # Deletar todas as apostas ligadas a esse jogo
        cur.execute("DELETE FROM apostas WHERE jogo_id = %s", (jogo_id,))
        # Deletar o jogo
        cur.execute("DELETE FROM jogos_futebol WHERE id = %s", (jogo_id,))
        conn.commit()
        flash("Jogo e apostas associadas deletados com sucesso!", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao deletar jogo: {e}", "danger")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("admin_futebol"))




@app.route("/deletar_aposta/<int:aposta_id>")
def deletar_aposta(aposta_id):
    cur = conn.cursor()
    cur.execute("DELETE FROM apostas WHERE id = %s", (aposta_id,))
    conn.commit()
    flash("Aposta deletada com sucesso!", "success")
    return redirect(url_for("admin_futebol"))


# -------------------- Criar tabela pelo Flask --------------------
@app.route("/criar_tabela_apostas")
def criar_tabela_apostas():
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS apostas (
                id SERIAL PRIMARY KEY,
                usuario TEXT REFERENCES clientes(usuario),
                jogo_id INT REFERENCES jogos_futebol(id),
                valor NUMERIC(12,2) NOT NULL,
                escolha TEXT NOT NULL,
                resultado TEXT DEFAULT 'pendente',
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        cur.close()
        conn.close()
        return "✅ Tabela 'apostas' criada com sucesso!"
    except Exception as e:
        return f"❌ Erro ao criar tabela: {e}"

@app.route("/ajustar_apostas")
def ajustar_apostas():
    conn = psycopg2.connect(DB_URL, cursor_factory=psycopg2.extras.DictCursor)
    cur = conn.cursor()
    try:
        cur.execute("ALTER TABLE apostas ADD COLUMN jogo_id INT REFERENCES jogos_futebol(id);")
        conn.commit()
        msg = "Coluna 'jogo_id' adicionada na tabela 'apostas'."
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
        msg = "Coluna 'jogo_id' já existe em 'apostas'."
    cur.close()
    conn.close()
    return msg





@app.route("/migrar_apostas")
def migrar_apostas():
    conn = psycopg2.connect(DB_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    cur = conn.cursor()
    try:
        cur.execute("ALTER TABLE apostas ADD COLUMN IF NOT EXISTS jogo_id INT REFERENCES jogos_futebol(id);")
        conn.commit()
        return "✅ Coluna jogo_id adicionada na tabela apostas!"
    except Exception as e:
        conn.rollback()
        return f"❌ Erro na migração: {e}"
    finally:
        cur.close()
        conn.close()

    return msg



@app.route("/migrar_multijogos")
def migrar_multijogos():
    import psycopg2
    import psycopg2.extras

    conn = psycopg2.connect(DB_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    cur = conn.cursor()
    try:
        # Criar tabela de jogos de futebol
        cur.execute("""
            CREATE TABLE IF NOT EXISTS jogos_futebol (
                id SERIAL PRIMARY KEY,
                time1 TEXT NOT NULL,
                time2 TEXT NOT NULL,
                ativo BOOLEAN DEFAULT TRUE
            );
        """)

        # Criar tabela de mercados do jogo
        cur.execute("""
            CREATE TABLE IF NOT EXISTS mercados_jogo (
                id SERIAL PRIMARY KEY,
                jogo_id INT REFERENCES jogos_futebol(id) ON DELETE CASCADE,
                nome TEXT NOT NULL,
                odd NUMERIC(12,2) NOT NULL
            );
        """)

        # Criar tabela de apostas principal
        cur.execute("""
            CREATE TABLE IF NOT EXISTS apostas (
                id SERIAL PRIMARY KEY,
                usuario TEXT REFERENCES clientes(usuario),
                valor NUMERIC(12,2) NOT NULL,
                resultado TEXT DEFAULT 'pendente',
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Criar tabela de jogos dentro da aposta (apostas múltiplas)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS apostas_jogos (
                id SERIAL PRIMARY KEY,
                aposta_id INT REFERENCES apostas(id) ON DELETE CASCADE,
                jogo_id INT REFERENCES jogos_futebol(id),
                mercado_id INT REFERENCES mercados_jogo(id),
                escolha TEXT NOT NULL,
                resultado TEXT DEFAULT 'pendente'
            );
        """)

        conn.commit()
        return "✅ Tabelas de múltiplos jogos e mercados criadas com sucesso!"
    except Exception as e:
        conn.rollback()
        return f"❌ Erro ao criar tabelas: {e}"
    finally:
        cur.close()
        conn.close()






@app.route("/ajustar_tabela")
def ajustar_tabela():
    conn = psycopg2.connect(DB_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    cur = conn.cursor()
    try:
        # Permitir NULL nas odds da tabela original
        cur.execute("ALTER TABLE jogos_futebol ALTER COLUMN odds1 DROP NOT NULL;")
        cur.execute("ALTER TABLE jogos_futebol ALTER COLUMN odds2 DROP NOT NULL;")
        cur.execute("ALTER TABLE jogos_futebol ALTER COLUMN odds_empate DROP NOT NULL;")
        
        conn.commit()
        flash("Tabela ajustada com sucesso!", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao ajustar tabela: {e}", "danger")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("admin_futebol"))


@app.route("/apostar", methods=["POST"])
def apostar():
    # abre conexão
    conn = psycopg2.connect(DB_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    cur = conn.cursor()

    try:
        usuario = session.get("usuario")  # garante que o usuário está logado
        if not usuario:
            flash("Você precisa estar logado para apostar.", "warning")
            return redirect(url_for("login"))

        jogo_id = request.form.get("jogo_id")
        mercado_id = request.form.get("mercado_id")
        valor = request.form.get("valor")

        if not jogo_id or not mercado_id or not valor:
            flash("Dados incompletos para registrar a aposta.", "danger")
            return redirect(url_for("futebol"))

        # pega o nome do mercado para registrar
        cur.execute("SELECT nome, odd FROM mercados_jogo WHERE id=%s", (mercado_id,))
        mercado = cur.fetchone()
        if not mercado:
            flash("Mercado selecionado inválido.", "danger")
            return redirect(url_for("futebol"))

        # insere na tabela apostas
        cur.execute(
            "INSERT INTO apostas (usuario, valor, resultado) VALUES (%s, %s, %s) RETURNING id",
            (usuario, valor, "pendente")
        )
        aposta_row = cur.fetchone()
        aposta_id = aposta_row["id"] if aposta_row and "id" in aposta_row else None
        if not aposta_id:
            raise Exception("Erro ao obter ID da aposta.")

        # insere na tabela apostas_jogos
        cur.execute(
            "INSERT INTO apostas_jogos (aposta_id, jogo_id, mercado_id, escolha) VALUES (%s, %s, %s, %s)",
            (aposta_id, jogo_id, mercado_id, mercado["nome"])
        )

        conn.commit()
        flash(f"Aposta registrada com sucesso no mercado '{mercado['nome']}'!", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao registrar aposta: {e}", "danger")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for("futebol"))




if __name__ == "__main__":
    app.run(debug=True)




















































































































