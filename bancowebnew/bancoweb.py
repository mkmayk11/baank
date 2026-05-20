from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file, jsonify
import psycopg2, psycopg2.extras
import csv, random
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = "segredo_super_seguro"

# -------------------- Banco de dados --------------------
DB_URL = os.getenv("DATABASE_URL", "postgresql://neondb_owner:npg_DsJetaU27Llx@ep-orange-base-ahmxop1e-pooler.c-3.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require")


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

    # Adiciona colunas extras se ainda não existirem
    c.execute("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS email TEXT;")
    c.execute("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS telefone TEXT;")
    c.execute("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS chave_pix TEXT;")

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
    conn = psycopg2.connect(DB_URL)
    c = conn.cursor()

    # Verifica se o usuário existe
    c.execute("SELECT 1 FROM usuarios WHERE username = %s", (usuario,))
    if not c.fetchone():
        # Se não existir, cria com saldo inicial 0
        c.execute("INSERT INTO usuarios (username, saldo) VALUES (%s, %s)", (usuario, 0))

    # Agora insere a aposta
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
        email = request.form["email"]
        telefone = request.form["telefone"]
        chave_pix = request.form["chave_pix"]

        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO clientes (usuario, senha, email, telefone, chave_pix)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (usuario) DO NOTHING
        """, (usuario, senha, email, telefone, chave_pix))
        conn.commit()
        cur.close()
        conn.close()

        flash("Cadastro realizado com sucesso! Faça login.", "success")
        return redirect(url_for("login"))
    return render_template("cadastro.html")


@app.route("/dashboard")
def dashboard():
    if "usuario" not in session or session["usuario"] == "admin":
        return redirect(url_for("admin_dashboard"))
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

    # Registrar aposta (em produção: salvar em tabela de apostas)
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

    # conexão com o banco
    conn = get_connection()
    c = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    # pega o histórico do usuário, do mais recente para o mais antigo
    c.execute("SELECT * FROM historico WHERE usuario = %s ORDER BY id DESC", (usuario,))
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

    # 🟢 CORREÇÃO 3: SE FOR GET, VERIFICA QUAL JOGO DEVE EXIBIR NA TELA
    if request.method == "GET":
        jogo_escolhido = request.args.get("g") # Lê o ?g=linhas na URL
        if jogo_escolhido == "linhas":
            return render_template("caca_linhas.html", saldo=saldo)
        
        # Se não tiver '?g=linhas', abre o caça-níquel antigo normal
        return render_template("caca.html", saldo=saldo)

    # Símbolos do caça-níquel
    simbolos = ["🍒","🍋","🔔","⭐","💎","🍀","🍉","🥭","🍇","🍌","🍓","🍑","🍍","🥝","🥥","🍈","🌈",
                "🎲","🏺","💸","☀️","🚀","🌶️","🥕","🎃","🎅","👼","♻️","💲","☢️","👣","💣","🦜",
                "🍁","👹","☠️","🐮","🌍","👽","💡","🧛🏻","🔑","🔍","🎵","🐳","🐡","🍄","🎰","🧠","🍺","👑","🐧","🦄","🐁","🦉","🦅"]

    # SE FOR POST (Processamento das jogadas via JavaScript fetch)
    if request.method == "POST":
        data = request.get_json()
        tipo = data.get("tipo")

        # -------- CAÇA-NÍQUEL ANTIGO --------
        if tipo == "caca":
            try:
                aposta = float(data.get("aposta", 0))
                lote = int(data.get("lote", 1))
            except:
                return jsonify({"erro": "Aposta inválida"}), 400

            rodadas_gratis_usuario = dados["clientes"][usuario].get("rodadas_gratis", 0)
            saldo_real = saldo
            evento = None  

            if aposta <= 0 and rodadas_gratis_usuario <= 0:
                resultado = "Digite um valor válido de aposta!"
                rolos = ["❔"] * 5
            elif aposta > saldo_real and rodadas_gratis_usuario <= 0:
                resultado = "Saldo insuficiente!"
                rolos = ["❔"] * 5
            else:
                rolos = random.choices(simbolos, k=5)
                ganho = 0
                resultado = ""
                using_rodada_gratis = rodadas_gratis_usuario > 0

                if round(aposta, 2) == 13.33:
                    rolos = ["👼", "👹", random.choice(simbolos), random.choice(simbolos), random.choice(simbolos)]

                if "👼" in rolos and "👹" in rolos:
                    resultado = f"⚔️ Confronto celestial! {rolos} O Anjo e o Demônio estão em combate!"
                    registrar_historico(usuario, f"Luta Celestial {rolos}", 0)
                    evento = "luta_angel_demon"

                contagens = {simbolo: rolos.count(simbolo) for simbolo in set(rolos)}
                maior_combo = max(contagens.values())

                if evento != "luta_angel_demon":  
                    if rolos.count("💸") >= 2:
                        mult = {2:20, 3:160, 4:300, 5:600}[rolos.count("💸")]
                        ganho = aposta * mult
                        saldo_real += ganho
                        resultado = f"💸 Dinheiro em cascata! {rolos} Você ganhou R$ {ganho:.2f}!"
                        registrar_historico(usuario, f"Caça-níquel ({rolos.count('💸')} Dinheiros {rolos})", ganho)
                    elif rolos.count("🍀") >= 2:
                        bonus = 5 * rolos.count("🍀")
                        rodadas_gratis_usuario += bonus
                        resultado = f"🍀 Sorte tripla! {rolos} Você ganhou {bonus} rodadas grátis!"
                        registrar_historico(usuario, f"Caça-níquel ({rolos.count('🍀')} Trevos {rolos})", 0)
                    elif rolos.count("⭐") >= 2:
                        mult = {2:60, 3:250, 4:400, 5:800}[rolos.count("⭐")]
                        ganho = aposta * mult
                        saldo_real += ganho
                        resultado = f"🌟 JACKPOT SUPREMO! {rolos} Você ganhou R$ {ganho:.2f}!"
                        registrar_historico(usuario, f"Caça-níquel ({rolos.count('⭐')} Estrelas {rolos})", ganho)
                    elif rolos.count("🎲") >= 2:
                        mult = {2:30, 3:130, 4:200, 5:400}[rolos.count("🎲")]
                        ganho = aposta * mult
                        saldo_real += ganho
                        resultado = f"🎲 Dados da fortuna! {rolos} Você ganhou R$ {ganho:.2f}!"
                        registrar_historico(usuario, f"Caça-níquel ({rolos.count('🎲')} Dados {rolos})", ganho)
                    elif rolos.count("💲") >= 2:
                        mult_map = {2:50, 3:140, 4:600, 5:1000}
                        ganho = aposta * mult_map.get(rolos.count("💲"), 0)
                        saldo_real += ganho
                        resultado = f"💲 Riqueza! {rolos} Você ganhou R$ {ganho:.2f}!"
                        registrar_historico(usuario, f"Caça-níquel ({rolos.count('💲')} Cifrões {rolos})", ganho)
                    elif maior_combo == 5:
                        ganho = aposta * 200
                        saldo_real += ganho
                        resultado = f"🌟 QUINA! {rolos} Você ganhou R$ {ganho:.2f}!"
                        registrar_historico(usuario, f"Caça-níquel (5 iguais {rolos})", ganho)
                    elif maior_combo == 4:
                        ganho = aposta * 100
                        saldo_real += ganho
                        resultado = f"🌟 QUADRA! {rolos} Você ganhou R$ {ganho:.2f}!"
                        registrar_historico(usuario, f"Caça-níquel (4 iguais {rolos})", ganho)
                    elif maior_combo == 3:
                        ganho = aposta * 20
                        saldo_real += ganho
                        resultado = f"✅ TRINCA! {rolos} Você ganhou R$ {ganho:.2f}!"
                        registrar_historico(usuario, f"Caça-níquel (3 iguais {rolos})", ganho)
                    elif maior_combo == 2:
                        ganho = aposta * 3
                        saldo_real += ganho
                        resultado = f"✅ Par! {rolos} Você ganhou R$ {ganho:.2f}!"
                        registrar_historico(usuario, f"Caça-níquel (Par {rolos})", ganho)
                    else:
                        if rodadas_gratis_usuario > 0:
                            rodadas_gratis_usuario -= 1
                            resultado = f"❌ {rolos} Rodada grátis usada. Você ainda tem {rodadas_gratis_usuario}."
                            registrar_historico(usuario, f"Caça-níquel (Rodada grátis {rolos})", 0)
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
                "rodadas_gratis": rodadas_gratis_usuario,
                "evento": evento
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
                premio = aposta * 56
                saldo_real += premio
                resultado += f" 🎉 Acertou! Prêmio x56 = R$ {premio:.2f}"
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

        # 🟢 CORREÇÃO 1 e 2: NOVO JOGO IDENTADO CORRETAMENTE E COM VARIÁVEL CORRIGIDA
        elif tipo == "caca_linhas":
            try:
                aposta = float(data.get("aposta", 0))
            except:
                return jsonify({"erro": "Aposta inválida"}), 400

            if aposta <= 0 or aposta > saldo:
                return jsonify({"erro": "Aposta inválida ou saldo insuficiente"}), 400

            simbolos_jogo = ["🍒", "🍋", "🔔", "⭐", "💎", "🍀", "🍉", "🍇", "🎰"]
            quadrados = random.choices(simbolos_jogo, k=12)

            linha1 = quadrados[0:4]
            linha2 = quadrados[4:8]
            linha3 = quadrados[8:12]

            linhas_ganhas = 0
            for linha in [linha1, linha2, linha3]:
                contagem = {s: linha.count(s) for s in set(linha)}
                maior_combinacao = max(contagem.values())
                if maior_combinacao >= 3:
                    linhas_ganhas += 1

            saldo_real = saldo
            ganho = 0

            # Corrigido aqui de lines_ganhas para linhas_ganhas
            if linhas_ganhas > 0:
                mult_linhas = {1: 3, 2: 10, 3: 50}
                mult = mult_linhas.get(linhas_ganhas, 3)
                ganho = aposta * mult
                saldo_real += ganho
                resultado_txt = f"🎉 PARABÉNS! Você formou {linhas_ganhas} linha(s) premiada(s) e ganhou R$ {ganho:.2f}!"
                registrar_historico(usuario, f"Caça-Níquel Linhas: {linhas_ganhas} linha(s) ganha(s) - Grade: {quadrados}", ganho)
            else:
                saldo_real -= aposta
                resultado_txt = f"❌ Não foi dessa vez! Nenhuma linha formada. Você perdeu R$ {aposta:.2f}."
                registrar_historico(usuario, f"Caça-Níquel Linhas: Derrota - Grade: {quadrados}", -aposta)

            saldo = saldo_real
            salvar_cliente(usuario, saldo=saldo)

            return jsonify({
                "quadrados": quadrados,
                "resultado": resultado_txt,
                "saldo": saldo,
                "linhas_ganhas": linhas_ganhas
            })

    # Se por acaso passar por tudo sem retornar (o que não deve acontecer), volta padrão
    return render_template("caca.html", saldo=saldo)
    
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
import psycopg2.extras

@app.route("/admin_futebol")
def admin_futebol():
    if "usuario" not in session or session.get("usuario") != "admin":
        flash("Acesso restrito. Faça login como administrador.", "danger")
        return redirect(url_for("login"))

    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        # Buscar jogos cadastrados
        cur.execute("""
            SELECT id, time_casa, time_fora, odds_casa, odds_fora, odds_empate 
            FROM jogos_futebol
            ORDER BY id DESC
        """)
        jogos = cur.fetchall()

        # Buscar apostas vinculadas aos jogos
        cur.execute("""
            SELECT 
                a.id, a.usuario, a.valor, a.escolha, a.resultado, a.criado_em,
                j.time_casa, j.time_fora
            FROM apostas a
            JOIN jogos_futebol j ON a.jogo_id = j.id
            ORDER BY a.id DESC
        """)
        apostas = cur.fetchall()

        cur.close()
        conn.close()

        return render_template("admin_futebol.html", jogos=jogos, apostas=apostas)

    except Exception as e:
        print("Erro ao carregar admin_futebol:", e)
        flash("Erro ao carregar painel de administração de futebol.", "danger")
        return redirect(url_for("dashboard"))







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
    if "usuario" not in session:
        return redirect(url_for("login"))
    
    usuario = session["usuario"]
    dados = carregar_dados()
    cliente = dados["clientes"].get(usuario)
    saldo = float(cliente["saldo"]) if cliente else 0

    # Pega jogos ativos
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT * FROM jogos_futebol WHERE ativo = TRUE")
    jogos = cur.fetchall()
    conn.close()

    if request.method == "POST":
        jogo_id = int(request.form.get("jogo_id"))
        valor_aposta = float(request.form.get("valor_aposta", 0))
        resultado_aposta = request.form.get("resultado")  # time1, time2 ou empate

        if valor_aposta <= 0 or valor_aposta > saldo:
            flash("Valor inválido ou saldo insuficiente!", "danger")
            return redirect(url_for("futebol"))

        # Deduz saldo do cliente
        saldo -= valor_aposta
        salvar_cliente(usuario, saldo=saldo)  # atualizar saldo

        # Salva aposta no banco de dados
        registrar_aposta(usuario, jogo_id, valor_aposta, resultado_aposta)

        # Salva no histórico do cliente
        registrar_historico(usuario, f"Aposta em futebol: {resultado_aposta}", valor_aposta)

        flash(f"Aposta de R$ {valor_aposta:.2f} em '{resultado_aposta}' realizada!", "success")
        return redirect(url_for("futebol"))

    return render_template("futebol.html", usuario=usuario, saldo=saldo, jogos=jogos)

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




import os
import psycopg2

DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://neondb_owner:npg_DsJetaU27Llx@ep-orange-base-ahmxop1e-pooler.c-3.us-east-1.aws.neon.tech/neondb?sslmode=require"
)

conn = psycopg2.connect(DB_URL)

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

@app.route("/atualizar_resultado/<int:aposta_id>/<resultado>", methods=["GET"])
def atualizar_resultado(aposta_id, resultado):
    try:
        conn = psycopg2.connect(DB_URL)
        c = conn.cursor()

        # Pega os dados da aposta e do jogo
        c.execute("""
            SELECT a.valor, a.escolha, j.odds1, j.odds_empate, j.odds2, a.usuario
            FROM apostas a
            JOIN jogos_futebol j ON a.jogo_id = j.id
            WHERE a.id = %s
        """, (aposta_id,))
        aposta = c.fetchone()
        if not aposta:
            flash("Aposta não encontrada.", "danger")
            return redirect(url_for("admin_futebol"))

        valor, escolha, odds1, odds_empate, odds2, usuario = aposta

        # Converte para Decimal
        valor = Decimal(valor)
        odds1 = Decimal(odds1)
        odds_empate = Decimal(odds_empate)
        odds2 = Decimal(odds2)

        ganho = Decimal("0")
        if resultado == "vitoria":
            # Calcula ganho de acordo com a escolha
            if escolha == "time1":
                ganho = valor * odds1
            elif escolha == "empate":
                ganho = valor * odds_empate
            else:  # time2
                ganho = valor * odds2

            # Atualiza saldo do usuário: soma o valor total ganho
            c.execute("""
                UPDATE usuarios
                SET saldo = saldo + %s
                WHERE username = %s
            """, (float(ganho), usuario))  # converte para float antes de enviar para SQL

        # Atualiza resultado da aposta
        c.execute("""
            UPDATE apostas
            SET resultado = %s
            WHERE id = %s
        """, (resultado, aposta_id))

        conn.commit()
        flash(f"Aposta atualizada para '{resultado}'.", "success")
        return redirect(url_for("admin_futebol"))

    except Exception as e:
        print(e)
        flash("Erro ao atualizar a aposta.", "danger")
        return redirect(url_for("admin_futebol"))

    finally:
        conn.close()

@app.route("/deletar_jogo/<int:jogo_id>")
def deletar_jogo(jogo_id):
    cur = conn.cursor()
    cur.execute("DELETE FROM jogos WHERE id = %s", (jogo_id,))
    conn.commit()
    flash("Jogo deletado com sucesso!", "success")
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
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS apostas_futebol (
                id SERIAL PRIMARY KEY,
                usuario VARCHAR(100) NOT NULL,
                time1 VARCHAR(100) NOT NULL,
                time2 VARCHAR(100) NOT NULL,
                valor NUMERIC(10,2) NOT NULL,
                escolha VARCHAR(50) NOT NULL,
                resultado VARCHAR(20)
            );
        """)
        conn.commit()
        cur.close()
        conn.close()
        return "✅ Tabela 'apostas_futebol' criada com sucesso!"
    except Exception as e:
        return f"❌ Erro ao criar tabela: {e}"

@app.route("/admin_dashboard")
def admin_dashboard():
    if not session.get("usuario") or not session.get("admin"):
        return redirect(url_for("login"))
    
    conn = get_connection()
    c = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    c.execute("SELECT usuario, email, telefone, chave_pix, saldo FROM clientes ORDER BY usuario ASC;")
    clientes = c.fetchall()
    conn.close()
    
    return render_template("admin_dashboard.html", clientes=clientes)





























if __name__ == "__main__":
    app.run(debug=True)





































