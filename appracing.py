from flask import Flask, render_template, request
import pyodbc

app = Flask(__name__)

# Configuração da conexão com o SQL Server no Azure
server = os.getenv('APP_SERVER','hornet.database.windows.net') 
database = os.getenv('APP_DATABASE','vfbgroup')
username = os.getenv('APP_USER','proficio')
password = os.getenv('APP_PWD','$Fortuna')
port = os.getenv('APP_PORT','1433')
driver = '{ODBC Driver 18 for SQL Server}'

# Conectar ao banco de dados

conn = pyodbc.connect(
    f'DRIVER={driver};SERVER={server};PORT={port};DATABASE={database};UID={username};PWD={password}'
)
cursor = conn.cursor()

# Página inicial (exibe o formulário)
@app.route('/')
def index():
    return render_template('racing.html')

# Rota para inserir dados no banco
@app.route('/inserir-dados', methods=['GET', 'POST'])
def inserir_dados():
    try:    
        # Captura os dados do formulário
        ticket = request.form.get['Ticket']
        data = request.form.get['Data']
        racing = request.form.get['Racing']
        time = request.form.get['Time']
        horse = request.form.get['Horse']
        bet = request.form.get['Bet']
        gain = request.form.get['Gain']

        # Query para inserir no banco (corrigida)
        query = "INSERT INTO [dbo].[racing] (Ticket, Data, Racing, Time, Bet, Gain) VALUES (?, ?, ?, ?, ?, ?)"
        cursor.execute(query, (ticket, data, racing, time, bet, gain))
        conn.commit()  # Confirma a inserção

        return 'Dados inseridos com sucesso!'
    except Exception as e:
        return f"Erro ao inserir os dados: {str(e)}"

# Rodando o Flask
if __name__ == "__main__":
    app.run(host="0.0.0.0", port={port})


# python -m venv venv

# venv\Scripts\activate     # Windows

# Isso vai subir seu código automaticamente para o Azure

# az webapp up --name appracing --resource-group vfbgroup --runtime "PYTHON|3.11"

# #{APP_DATABASE:vfbgroup};
# {:1433},
# {APP_PWD:APP_PORT$Fortuna},
# {APP_SERVER:hornet.database.windows.net},
# {APP_USER:proficio}