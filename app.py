import os
import psycopg2
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, g

# -----------------------------------------------------------
# Configuração do Aplicativo e do Banco de Dados
# -----------------------------------------------------------

app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY", "dev")

# Lendo a variável de ambiente DATABASE_URL
DATABASE_URL = os.environ.get("DATABASE_URL")

# -----------------------------------------------------------
# Funções de Conexão com PostgreSQL
# -----------------------------------------------------------

def get_db():
    if 'db' not in g:
        if not DATABASE_URL:
            # Caso de erro no deploy
            print("ERRO: A variável de ambiente DATABASE_URL não está configurada!")
            g.db = None
        else:
            try:
                g.db = psycopg2.connect(DATABASE_URL)
            except psycopg2.Error as e:
                print(f"Erro ao conectar ao PostgreSQL: {e}")
                g.db = None
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

# -----------------------------------------------------------
# Inicialização do Banco de Dados (Cria a tabela se não existir)
# -----------------------------------------------------------

def init_db():
    conn = get_db()
    if conn is None:
        return
        
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rifas (
                numero INT PRIMARY KEY,
                nome VARCHAR(255) NOT NULL,
                status VARCHAR(50) NOT NULL,
                data_sorteio TIMESTAMP
            )
        """)
        conn.commit()
    except psycopg2.Error as e:
        print(f"Erro ao criar tabela: {e}")
    finally:
        cursor.close()

with app.app_context():
    init_db()

# -----------------------------------------------------------
# Funções de Dados
# -----------------------------------------------------------

def get_rifa_data():
    conn = get_db()
    if conn is None:
        return {}, [] 

    cursor = conn.cursor()
    
    mapa_rifa = {i: {'status': 'disponivel', 'nome': None, 'data_sorteio': None} for i in range(1, 101)}
    historico = []

    try:
        # 1. Busca todos os números
        cursor.execute("SELECT numero, nome, status, data_sorteio FROM rifas")
        vendidos = cursor.fetchall()
        
        for num, nome, status, data_sorteio in vendidos:
            mapa_rifa[num] = {'status': status, 'nome': nome, 'data_sorteio': data_sorteio}

        # 2. Busca o histórico de sorteios
        cursor.execute("SELECT numero, nome, data_sorteio FROM rifas WHERE status = 'sorteado' ORDER BY data_sorteio DESC")
        historico = cursor.fetchall()

    except psycopg2.Error as e:
        print(f"Erro ao buscar dados: {e}")
        
    finally:
        cursor.close()
        
    return mapa_rifa, historico

# -----------------------------------------------------------
# Rotas
# -----------------------------------------------------------

@app.route('/')
def index():
    mapa_rifa, historico = get_rifa_data()
    return render_template('index.html', mapa_rifa=mapa_rifa, historico=historico)

@app.route('/adicionar', methods=['POST'])
def adicionar():
    numero = request.form.get('numero')
    nome = request.form.get('nome').strip()
    conn = get_db()
    
    if not conn:
        flash('Erro de conexão com o banco de dados.', 'error')
        return redirect(url_for('index'))

    if not (nome and numero):
        flash('Nome e número são obrigatórios!', 'error')
        return redirect(url_for('index'))

    try:
        numero = int(numero)
        if not (1 <= numero <= 100):
            flash('Número da rifa deve ser entre 1 e 100.', 'error')
            return redirect(url_for('index'))
    except ValueError:
        flash('Número inválido.', 'error')
        return redirect(url_for('index'))

    cursor = conn.cursor()

    try:
        cursor.execute("SELECT status FROM rifas WHERE numero = %s", (numero,))
        
        if cursor.fetchone():
            flash(f'O número {numero} já está ocupado ou sorteado!', 'error')
        else:
            cursor.execute(
                "INSERT INTO rifas (numero, nome, status) VALUES (%s, %s, 'vendido')",
                (numero, nome)
            )
            conn.commit()
            flash(f'Número {numero} registrado para {nome}!', 'success')
            
    except psycopg2.Error as e:
        flash(f'Erro ao adicionar: {e}', 'error')
        
    finally:
        cursor.close()
    
    return redirect(url_for('index'))

@app.route('/sortear')
def sortear():
    conn = get_db()
    if not conn:
        flash('Erro de conexão com o banco de dados.', 'error')
        return redirect(url_for('index'))

    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT numero, nome FROM rifas WHERE status = 'vendido'")
        vendidos = cursor.fetchall()

        if not vendidos:
            flash('Não há números vendidos disponíveis para sortear!', 'error')
            return redirect(url_for('index'))

        import random
        num_sorteado, nome_ganhador = random.choice(vendidos)

        cursor.execute(
            "UPDATE rifas SET status = 'sorteado', data_sorteio = %s WHERE numero = %s",
            (datetime.now(), num_sorteado)
        )
        conn.commit()

        flash(f'🎉 O NÚMERO SORTEADO É: {num_sorteado}! Ganhador(a): <strong>{nome_ganhador}</strong>!', 'success')

    except psycopg2.Error as e:
        flash(f'Erro no sorteio: {e}', 'error')
    finally:
        cursor.close()

    return redirect(url_for('index'))

@app.route('/excluir/<int:numero>', methods=['POST'])
def excluir(numero):
    conn = get_db()
    if not conn:
        flash('Erro de conexão com o banco de dados.', 'error')
        return redirect(url_for('index'))
        
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT status, nome FROM rifas WHERE numero = %s", (numero,))
        resultado = cursor.fetchone()
        
        if not resultado:
            flash(f'Número {numero} não encontrado!', 'error')
        else:
            status, nome = resultado
            if status == 'sorteado':
                flash('Não é possível excluir um número que já foi sorteado!', 'error')
            else:
                cursor.execute("DELETE FROM rifas WHERE numero = %s", (numero,))
                conn.commit()
                flash(f'Número {numero} ({nome}) excluído com sucesso!', 'success')
                
    except psycopg2.Error as e:
        flash(f'Erro ao excluir: {e}', 'error')
    finally:
        cursor.close()
    
    return redirect(url_for('index'))

@app.route('/editar', methods=['POST'])
def editar():
    numero_antigo = request.form.get('numero_antigo')
    novo_nome = request.form.get('novo_nome').strip()
    novo_numero = request.form.get('novo_numero')
    conn = get_db()

    if not conn:
        flash('Erro de conexão com o banco de dados.', 'error')
        return redirect(url_for('index'))

    if not (novo_nome and novo_numero and numero_antigo):
        flash('Todos os campos de edição são obrigatórios.', 'error')
        return redirect(url_for('index'))
    
    try:
        numero_antigo = int(numero_antigo)
        novo_numero = int(novo_numero)
        if not (1 <= novo_numero <= 100):
            flash('O novo número da rifa deve ser entre 1 e 100.', 'error')
            return redirect(url_for('index'))
    except ValueError:
        flash('Número(s) inválido(s).', 'error')
        return redirect(url_for('index'))

    cursor = conn.cursor()
    
    try:
        if novo_numero != numero_antigo:
            cursor.execute("SELECT status FROM rifas WHERE numero = %s", (novo_numero,))
            if cursor.fetchone():
                flash(f'O novo número {novo_numero} já está ocupado!', 'error')
                return redirect(url_for('index'))

        if novo_numero == numero_antigo:
            cursor.execute(
                "UPDATE rifas SET nome = %s WHERE numero = %s",
                (novo_nome, numero_antigo)
            )
        else:
            cursor.execute(
                "INSERT INTO rifas (numero, nome, status) VALUES (%s, %s, 'vendido')",
                (novo_numero, novo_nome)
            )
            cursor.execute("DELETE FROM rifas WHERE numero = %s", (numero_antigo,))

        conn.commit()
        flash(f'Número {numero_antigo} alterado para {novo_numero} ({novo_nome}) com sucesso!', 'success')
        
    except psycopg2.Error as e:
        flash(f'Erro ao editar: {e}', 'error')
    finally:
        cursor.close()
    
    return redirect(url_for('index'))

@app.route('/reset')
def reset():
    conn = get_db()
    if not conn:
        flash('Erro de conexão com o banco de dados.', 'error')
        return redirect(url_for('index'))
        
    cursor = conn.cursor()
    
    try:
        cursor.execute("DELETE FROM rifas")
        conn.commit()
        flash('🚨 Rifa totalmente reiniciada! Todos os dados foram apagados.', 'success')
    except psycopg2.Error as e:
        flash(f'Erro ao reiniciar: {e}', 'error')
    finally:
        cursor.close()
        
    return redirect(url_for('index'))


