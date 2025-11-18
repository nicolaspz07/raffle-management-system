from flask import Flask, render_template, request, redirect, flash
import mysql.connector
import random
from datetime import datetime
import os 
import sys 

# A. Configuração explícita do template folder (necessário para alguns ambientes)
try:
    template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
    app = Flask(__name__, template_folder=template_dir)
except NameError:
    app = Flask(__name__)
    print("Aviso: Usando a configuração padrão do Flask para a pasta 'templates'.")


# Chave secreta necessária para usar 'flash' (mensagens de erro/sucesso)
app.secret_key = 'sua_chave_secreta_aqui' 

# B. Configuração do Banco de Dados
# ATENÇÃO: Verifique se 'user' e 'password' estão corretos para o seu MySQL
DB_CONFIG = {
    "host": "localhost",
    "user": "root",        
    "password": "",        
    "database": "rifa"
}

def get_db_connection():
    """Cria e retorna uma nova conexão com o banco de dados."""
    return mysql.connector.connect(**DB_CONFIG)
@app.route('/')
def index():
    try:
        db = get_db_connection()
        cursor = db.cursor()
        
        # 1. Obter todos os participantes
        cursor.execute("SELECT numero, nome FROM participantes ORDER BY numero ASC")
        participantes = cursor.fetchall()
        
        # 2. Obter o histórico de sorteios
        cursor.execute("SELECT numero_sorteado, nome_ganhador, data_hora FROM historico_sorteios ORDER BY data_hora DESC")
        historico = cursor.fetchall()
        
        # 3. Criar o mapa da rifa (1 a 100) para a grade visual
        mapa_rifa = {i: {'nome': '', 'status': 'disponivel'} for i in range(1, 101)}
        
        # Atualizar status para números vendidos
        for numero, nome in participantes:
            mapa_rifa[numero]['nome'] = nome if nome is not None else '' 
            mapa_rifa[numero]['status'] = 'vendido'
            
        # Atualizar status para números sorteados
        numeros_sorteados = [row[0] for row in historico]
        for numero in numeros_sorteados:
            if numero in mapa_rifa:
                mapa_rifa[numero]['status'] = 'sorteado'
                # Garante que o nome do ganhador é mostrado
                for num_sorteado, nome_ganhador, _ in historico:
                    if num_sorteado == numero:
                        mapa_rifa[numero]['nome'] = nome_ganhador
                        break
                
        db.close()
        
        return render_template('index.html', mapa_rifa=mapa_rifa, historico=historico)
    
    except mysql.connector.Error as err:
        print(f"❌ ERRO CRÍTICO NO BANCO DE DADOS: {err}", file=sys.stderr)
        flash(f"Erro de conexão: Verifique o MySQL e o DB 'rifa'. Detalhes no console.", 'error')
        return render_template('index.html', mapa_rifa={i: {'nome': '', 'status': 'disponivel'} for i in range(1, 101)}, historico=[])

@app.route('/adicionar', methods=['POST'])
def adicionar():
    nome = request.form['nome'].strip()
    try:
        numero = int(request.form['numero'])
    except ValueError:
        flash("O número deve ser um valor inteiro.", 'error')
        return redirect('/')

    if not (1 <= numero <= 100):
        flash("O número deve estar entre 1 e 100.", 'error')
        return redirect('/')

    db = get_db_connection()
    cursor = db.cursor()
    
    try:
        # A. Verificar se o número já está vendido
        cursor.execute("SELECT nome FROM participantes WHERE numero = %s", (numero,))
        if cursor.fetchone():
            flash(f"O número {numero} já está reservado!", 'error')
            return redirect('/')
        
        # B. Verificar se o número já foi sorteado
        cursor.execute("SELECT id FROM historico_sorteios WHERE numero_sorteado = %s", (numero,))
        if cursor.fetchone():
            flash(f"O número {numero} já foi sorteado!", 'error')
            return redirect('/')

        # C. Inserir novo participante
        cursor.execute("INSERT INTO participantes (nome, numero) VALUES (%s, %s)", (nome, numero))
        db.commit()
        flash(f"Participante '{nome}' adicionado com o número {numero}.", 'success')
    
    except mysql.connector.Error as err:
        flash(f"Erro no banco de dados: {err}", 'error')
    finally:
        db.close()
        
    return redirect('/')

@app.route('/sortear')
def sortear():
    db = get_db_connection()
    cursor = db.cursor()
    
    try:
        # 1. Encontrar todos os números vendidos que AINDA NÃO foram sorteados
        cursor.execute("""
            SELECT p.numero, p.nome 
            FROM participantes p 
            LEFT JOIN historico_sorteios h ON p.numero = h.numero_sorteado
            WHERE h.numero_sorteado IS NULL
        """)
        
        candidatos = cursor.fetchall()
        
        if not candidatos:
            flash("Não há números vendidos disponíveis para sortear!", 'warning')
            return redirect('/')
        
        # 2. Sortear um candidato aleatório
        sorteado_data = random.choice(candidatos)
        sorteado_numero = sorteado_data[0]
        sorteado_nome = sorteado_data[1]
        
        # 3. Inserir o resultado no histórico
        query = "INSERT INTO historico_sorteios (numero_sorteado, nome_ganhador) VALUES (%s, %s)"
        cursor.execute(query, (sorteado_numero, sorteado_nome))
        db.commit()
        
        flash(f"🥳 GANHADOR! Número {sorteado_numero} para {sorteado_nome} foi sorteado e adicionado ao histórico.", 'success')

    except mysql.connector.Error as err:
        flash(f"Erro no sorteio: {err}", 'error')
    finally:
        db.close()
        
    return redirect('/')
# --- ROTAS DE ADMINISTRAÇÃO ---

@app.route('/excluir/<int:numero>', methods=['POST'])
def excluir(numero):
    """Exclui um número da tabela 'participantes'."""
    db = get_db_connection()
    cursor = db.cursor()
    
    try:
        # A. Verifica se o número já foi sorteado antes de excluir
        cursor.execute("SELECT id FROM historico_sorteios WHERE numero_sorteado = %s", (numero,))
        if cursor.fetchone():
            flash(f"O número {numero} já foi sorteado e não pode ser excluído do registro.", 'error')
            return redirect('/')
            
        # B. Exclui o participante
        cursor.execute("DELETE FROM participantes WHERE numero = %s", (numero,))
        if cursor.rowcount == 0:
            flash(f"O número {numero} não foi encontrado para exclusão.", 'error')
        else:
            db.commit()
            flash(f"Número {numero} excluído com sucesso do registro de vendas.", 'success')
            
    except mysql.connector.Error as err:
        flash(f"Erro no banco de dados ao excluir: {err}", 'error')
    finally:
        db.close()
        
    return redirect('/')


@app.route('/editar', methods=['POST'])
def editar():
    """Edita o nome e/ou número de um participante existente."""
    try:
        # Pega os dados do formulário
        numero_antigo = int(request.form['numero_antigo'])
        novo_nome = request.form['novo_nome'].strip()
        novo_numero = int(request.form['novo_numero'])
    except ValueError:
        flash("Erro: Os números devem ser inteiros.", 'error')
        return redirect('/')

    db = get_db_connection()
    cursor = db.cursor()
    
    try:
        # 1. Validação do novo número (1 a 100)
        if not (1 <= novo_numero <= 100):
            flash("O novo número deve estar entre 1 e 100.", 'error')
            return redirect('/')
            
        # 2. Se o número mudou, verificar se o novo número já está ocupado por outro
        if numero_antigo != novo_numero:
            cursor.execute("SELECT nome FROM participantes WHERE numero = %s", (novo_numero,))
            if cursor.fetchone():
                flash(f"O número {novo_numero} já está ocupado por outro participante.", 'error')
                return redirect('/')
        
        # 3. Atualizar o registro
        query = "UPDATE participantes SET nome = %s, numero = %s WHERE numero = %s"
        cursor.execute(query, (novo_nome, novo_numero, numero_antigo))
        
        if cursor.rowcount > 0:
            db.commit()
            flash(f"Registro do número {numero_antigo} atualizado para {novo_nome} ({novo_numero}).", 'success')
        else:
            flash("Erro ao editar: Participante original não encontrado.", 'error')
            
    except mysql.connector.Error as err:
        flash(f"Erro no banco de dados ao editar: {err}", 'error')
    finally:
        db.close()
        
    return redirect('/')


@app.route('/reset')
def reset_rifa():
    """Apaga todos os dados das tabelas de participantes e histórico."""
    db = get_db_connection()
    cursor = db.cursor()
    
    try:
        # TRUNCATE TABLE apaga todos os dados e reinicia os contadores (AUTO_INCREMENT)
        cursor.execute("TRUNCATE TABLE participantes")
        cursor.execute("TRUNCATE TABLE historico_sorteios")
        db.commit()
        
        flash("🎉 REINÍCIO COMPLETO! Todos os números vendidos e o histórico de sorteios foram apagados. A rifa está pronta para recomeçar.", 'success')
        
    except mysql.connector.Error as err:
        flash(f"Erro crítico ao reiniciar a rifa: {err}", 'error')
    finally:
        db.close()
        
    return redirect('/')


if __name__ == '__main__':
    # Use debug=True apenas em desenvolvimento
    app.run(debug=True)