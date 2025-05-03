import streamlit as st
import numpy as np
import requests
import base64
import json
import joblib
import os
import plotly.express as px
import plotly.graph_objects as go
import matplotlib.pyplot as plt
import logging
from datetime import datetime, timedelta
import pandas as pd

# Configurar Pandas para aceitar futuras mudanças no tratamento de objetos
pd.set_option('future.no_silent_downcasting', True)

# Configuração do GitHub
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_OWNER = "vbautistacode"
REPO_NAME = "app"
BRANCH = "main"

# Diretório do repositório no GitHub
diretorio_base = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/{BRANCH}/"

# Função para carregar dados direto do GitHub
def load_data():
    arquivos = ["horse_data.json", "team_data.json", "bet_data.json"]
    
    for arquivo in arquivos:
        url_arquivo = diretorio_base + arquivo
        try:
            response = requests.get(url_arquivo)
            response.raise_for_status()  # Verifica erros na requisição
            st.session_state[arquivo.replace(".json", "")] = response.json()
        except requests.exceptions.RequestException:
            st.session_state[arquivo.replace(".json", "")] = []  # Retorna lista vazia em caso de erro

# Função para salvar dados no GitHub
def salvar_csv_no_github(dataframe, nome_arquivo):
    try:
        if dataframe.empty:
            st.warning(f"⚠️ O arquivo '{nome_arquivo}' está vazio! Não será salvo.")
            return
        
        csv_content = dataframe.to_csv(index=False, encoding="utf-8")
        encoded_content = base64.b64encode(csv_content.encode()).decode()
        github_api_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{nome_arquivo}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        
        response = requests.get(github_api_url, headers=headers)
        sha = response.json().get("sha", None)

        payload = {
            "message": f"Atualizando {nome_arquivo} via API",
            "content": encoded_content,
            "branch": BRANCH
        }
        if sha:
            payload["sha"] = sha  # Atualiza arquivo existente

        response = requests.put(github_api_url, json=payload, headers=headers)
        if response.status_code in [200, 201]:
            st.success(f"✅ {nome_arquivo} salvo no GitHub com sucesso!")
        else:
            st.error(f"❌ Erro ao salvar {nome_arquivo}: {response.json()}")

    except Exception as e:
        st.error(f"❌ Erro inesperado: {e}")

# Inicialização dos dados no session_state
if "initialized" not in st.session_state:
    load_data()
    st.session_state["initialized"] = True

# Inicializa os dados no session_state
if "horse_data" not in st.session_state:
    st.session_state["horse_data"] = []
if "team_data" not in st.session_state:
    st.session_state["team_data"] = []
if "going_conditions" not in st.session_state:  # 🔹 Evita erro de chave não definida
    st.session_state["going_conditions"] = ["Firm", "Good to Firm", "Good", "Good to Soft", "Soft", "Heavy", 
                                            "Yielding", "Standard", "Standard to Slow", "Slow", "All-Weather"]

if not st.session_state.get("initialized", False):
    load_data()
    st.session_state["initialized"] = True

if "Nome" not in st.session_state:
    st.session_state["Nome"] = "Cavalo_Default"  # Nome padrão ou escolha inicial

# --- Funções de cálculo ---
def kelly_criterion(odds, probability, bankroll):
#Calcula a fração de Kelly para apostas estratégicas.
    b = odds - 1
    kelly_fraction = (b * probability - (1 - probability)) / b
    return max(0, round(bankroll * kelly_fraction, 2))

def calculate_dutching(odds, bankroll):
#Distribui aposta usando Dutching com ajuste para odds e desempenho da equipe.
    probabilities = [1 / odd for odd in odds]
    total_probability = sum(probabilities)
    if total_probability > 1:
        probabilities = [p / total_probability for p in probabilities]
    apostas = [round(bankroll * p, 2) for p in probabilities]
    return apostas

# --- Interface Streamlit ---
st.title("Apostas | Estratégias Dutching")

# Abas para organização
tab1, tab2, tab3, tab4, = st.tabs(["Locais", "Dados dos Cavalos", "Dados das Equipes", "Análises"])

# --- Aba 1: Escolha ou Registro do Local de Prova ---   
with tab1:
    def carregar_locais():
        url_arquivo = diretorio_base + "locais_prova.json"
        try:
            response = requests.get(url_arquivo)
            response.raise_for_status()
            data = response.json()
            return data.get("Locais de Prova", [])
        except requests.exceptions.RequestException:
            return []

    locais_prova = carregar_locais()

    # Dropdown para selecionar um local existente
    local_selecionado = st.selectbox("Selecione um local de prova:", locais_prova, key="select_local")
    st.session_state["local_atual"] = local_selecionado

    # Registrar um novo local
    novo_local = st.text_input("Ou registre um novo local de prova:")
    if st.button("Salvar Novo Local"):
        if novo_local and novo_local not in locais_prova:
            locais_prova.append(novo_local)
            st.session_state["local_atual"] = novo_local
            st.success(f"Novo local '{novo_local}' adicionado com sucesso!")
        elif novo_local in locais_prova:
            st.warning("Este local já está registrado.")

    # Lista de opções de "Going"
    tipo_pista = st.selectbox("Escolha o tipo de pista (Going):", st.session_state["going_conditions"], key="select_going_1")

    # Salvar o tipo de pista selecionado no `session_state`
    st.session_state["tipo_pista_atual"] = tipo_pista
    st.session_state["distance"] = st.number_input("Distância da Pista", min_value=0.00, step=0.01)

# --- Aba 2: Dados dos Cavalos ---
with tab2:
    st.subheader("Dados Históricos | Cavalos")
# ✅ Verifica se 'horse_data' já foi inicializado
    if "horse_data" not in st.session_state:
        st.session_state["horse_data"] = []
    if "local_atual" in st.session_state and st.session_state["local_atual"]:
        st.write(f"Registrando para o local: **{st.session_state['local_atual']}**")
# ✅ Inicializa a variável de controle de registro
    if "horse_data_started" not in st.session_state:
        st.session_state["horse_data_started"] = False
    if st.button("Cadastro de Dados dos Cavalos"):
        st.session_state["horse_data_started"] = True
    if st.session_state["horse_data_started"]:
# ✅ Ajusta a seleção de cavalos existentes
        cavalo_selecionado = st.selectbox(
            "Selecione o Cavalo para Editar ou Adicionar Novo",
            ["Adicionar Novo"] + [horse["Nome"] for horse in st.session_state["horse_data"]],
            key="select_horse_edit"
        )
        cavalo_dados = next(
            (horse for horse in st.session_state["horse_data"] if horse["Nome"] == cavalo_selecionado),
            None
        ) if cavalo_selecionado != "Adicionar Novo" else None
# ✅ Divisão em colunas para melhor organização
        col1, col2 = st.columns(2)
        with col1:
            local_atual = st.session_state.get("local_atual", "Não definido")
            Nome = st.text_input("Nome do Cavalo", cavalo_dados["Nome"] if cavalo_dados else "")
            idade = st.number_input("Idade", min_value=0, max_value=30, step=1, value=cavalo_dados["Idade"] if cavalo_dados else 0)
            runs = st.number_input("Runs (Corridas)", min_value=0, step=1, value=cavalo_dados["Runs"] if cavalo_dados else 0)
            wins = st.number_input("Wins (Vitórias)", min_value=0, step=1, value=cavalo_dados["Wins"] if cavalo_dados else 0)
            seconds = st.number_input("2nds (Segundos Lugares)", min_value=0, step=1, value=cavalo_dados["2nds"] if cavalo_dados else 0)
            thirds = st.number_input("3rds (Terceiros Lugares)", min_value=0, step=1, value=cavalo_dados["3rds"] if cavalo_dados else 0)
        with col2:
            odds = st.number_input("Odds (Probabilidades)", min_value=0.01, step=0.01, value=cavalo_dados["Odds"] if cavalo_dados else 0.01)
# ✅ Ajuste de cálculo de intervalo de dias
            data_anterior = st.date_input("Data Última Corrida", value=datetime.today().date())
            data_anterior = datetime.combine(data_anterior, datetime.min.time())
            data_atual = datetime.now()
            diferenca_dias = (data_atual - data_anterior).days
            st.session_state["diferenca_dias"] = diferenca_dias
            intervalo_corridas = st.number_input("Intervalo", min_value=0, step=1, value=diferenca_dias)
            Ranking = st.number_input("Ranking (Colocação)", min_value=0, step=1, value=cavalo_dados["Ranking"] if cavalo_dados else 0)
# ✅ Corrige o acesso ao tipo de pista
            going = st.selectbox("Going", st.session_state.get("going_conditions", 
                ["Firm", "Good to Firm", "Good", "Good to Soft", "Soft", "Heavy", "Yielding", "Standard", "Slow", "All-Weather"]), 
                key="select_going_2"
            )
            distancia = st.number_input("Distancia", min_value=0.00, step=0.01, value=cavalo_dados["Distancia"] if cavalo_dados else 0.00)
# ✅ Botão para salvar dados do cavalo
        if st.button("Salvar Dados do Cavalo"):
            novo_cavalo = {
                "Local": local_atual,
                "Nome": Nome,
                "Idade": idade,
                "Runs": runs,
                "Wins": wins,
                "2nds": seconds,
                "3rds": thirds,
                "Odds": odds,
                "Intervalo": diferenca_dias,
                "Going": going,
                "Ranking": Ranking,
                "Distancia": distancia,
            }
            if cavalo_selecionado == "Adicionar Novo":
                st.session_state["horse_data"].append(novo_cavalo)
                st.success(f"Novo cavalo '{Nome}' adicionado com sucesso no local '{local_atual}'!")
            else:
                for horse in st.session_state["horse_data"]:
                    if horse["Nome"] == cavalo_selecionado:
                        horse.update(novo_cavalo)
                        st.success(f"Alterações no cavalo '{Nome}' salvas com sucesso!")
# ✅ Exibição de cavalos cadastrados
    if st.session_state["horse_data"]:
        st.write("### Cavalos Registrados")
        df_horses = pd.DataFrame(st.session_state["horse_data"])
        st.dataframe(df_horses)       
# ✅ Correção da função de salvamento no GitHub
def salvar_csv_no_github(dataframe):
    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
    REPO_OWNER = "vbautistacode"
    REPO_NAME = "app"
    BRANCH = "main"
    FILE_PATH = "dados_corridas.csv"
    GITHUB_API_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{FILE_PATH}"
    try:
        if dataframe.empty:
            st.warning("⚠️ O arquivo CSV está vazio! Não será salvo.")
            return
        csv_content = dataframe.to_csv(index=False, encoding="utf-8")
        encoded_content = base64.b64encode(csv_content.encode()).decode()
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        response = requests.get(GITHUB_API_URL, headers=headers)
        sha = response.json().get("sha", None)
        payload = {
            "message": "Atualizando dados_corridas.csv via API",
            "content": encoded_content,
            "branch": BRANCH
        }
        if sha:
            payload["sha"] = sha
        response = requests.put(GITHUB_API_URL, json=payload, headers=headers)
        if response.status_code in [200, 201]:
            st.success("✅ CSV salvo no GitHub com sucesso!")
        else:
            st.error(f"❌ Erro ao salvar no GitHub: {response.json()}")
    except Exception as e:
        st.error(f"❌ Erro inesperado: {e}")
with tab2:
# ✅ Botão para salvar no GitHub
    if st.button("Salvar em CSV", key="unique_key_1"):
        salvar_csv_no_github(df_horses)
    else:
        st.warning("Ainda não há cavalos registrados.")

# --- Aba 3: Dados das Equipes ---
with tab3:
    st.subheader("Dados Históricos | Equipes")
# Inicializa o estado das equipes
    if "team_data" not in st.session_state:
        st.session_state["team_data"] = []
    if "reset_team_fields" not in st.session_state:
        st.session_state["reset_team_fields"] = False  # Indica se os campos devem ser limpos
# Botão para iniciar o cadastro
    if st.button("Cadastro de Dados das Equipes"):
        st.session_state["team_data_started"] = True
        st.session_state["reset_team_fields"] = True  # Limpar campos quando o botão é clicado
    if st.session_state.get("team_data_started", False):
        if st.session_state["reset_team_fields"]:# Limpar variáveis (deixa vazio ou zero)
            if st.session_state["team_data"]:# Dropdown para selecionar equipe ou adicionar nova
                equipe_selecionada = st.selectbox(
                    "Selecione a Equipe para Editar ou Adicionar Nova",
                    ["Adicionar Nova"] + [team["Nome da Equipe"] for team in st.session_state["team_data"]],
                    key="select_team_edit"
                )
                if equipe_selecionada == "Adicionar Nova":
                    equipe_dados = None
                else:
                    equipe_dados = next(
                        (team for team in st.session_state["team_data"] if team["Nome da Equipe"] == equipe_selecionada),
                        None
                    )
            else:
                st.warning("Ainda não há equipes cadastradas. Preencha os dados para adicionar uma nova equipe.")
                equipe_selecionada = "Adicionar Nova"
                equipe_dados = None
# Divisão em duas colunas
        col1, col2 = st.columns(2)
# Campos na primeira coluna
        with col1:
# Extrair os nomes dos cavalos para usar como opções no selectbox
            nomes_cavalos = [horse["Nome"] for horse in st.session_state["horse_data"]] if "horse_data" in st.session_state else []
            nome_equipe = st.selectbox("Nome do Cavalo Associado", nomes_cavalos, key="select_horse_team")  # Vincula Nome do Cavalo
            treinador = st.text_input("Treinador", equipe_dados["Treinador"] if equipe_dados else "")
            treinador_wins = st.number_input("Treinador Wins", min_value=0, step=1, value=equipe_dados["Treinador Wins"] if equipe_dados else 0)
            treinador_runs = st.number_input("Treinador Runs", min_value=0, step=1, value=equipe_dados["Treinador Runs"] if equipe_dados else 0)
            treinador_placed = st.number_input("Treinador Placed (Colocações)", min_value=0, step=1, value=equipe_dados["Treinador Placed"] if equipe_dados else 0)
        with col2:
            jockey = st.text_input("Jockey", equipe_dados["Jockey"] if equipe_dados else "")
            jockey_wins = st.number_input("Jockey Wins", min_value=0, step=1, value=equipe_dados["Jockey Wins"] if equipe_dados else 0)
            jockey_rides = st.number_input("Jockey Rides", min_value=0, step=1, value=equipe_dados["Jockey Rides"] if equipe_dados else 0)
            jockey_seconds = st.number_input("Jockey 2nds", min_value=0, step=1, value=equipe_dados["Jockey 2nds"] if equipe_dados else 0)
            jockey_thirds = st.number_input("Jockey 3rds", min_value=0, step=1, value=equipe_dados["Jockey 3rds"] if equipe_dados else 0)
#Botão para salvar dados
            if st.button("Salvar Dados da Equipe"):
# Verificar se já existe uma equipe com o mesmo nome
                nomes_equipes_existentes = [team["Nome da Equipe"] for team in st.session_state["team_data"]]
                if equipe_selecionada == "Adicionar Nova":
                    if nome_equipe in nomes_equipes_existentes:
                        st.error(f"A equipe '{nome_equipe}' já foi registrada. Insira um nome único!")
                    else:
# Adiciona nova equipe
                            nova_equipe = {
                        "Nome da Equipe": nome_equipe,
                        "Treinador": treinador,
                        "Treinador Wins": treinador_wins,
                        "Treinador Runs": treinador_runs,
                        "Treinador Placed": treinador_placed,
                        "Jockey": jockey,
                        "Jockey Wins": jockey_wins,
                        "Jockey Rides": jockey_rides,
                        "Jockey 2nds": jockey_seconds,
                        "Jockey 3rds": jockey_thirds,
                    }
                    st.session_state["team_data"].append(nova_equipe)  # Salva no session_state
                    st.success(f"Nova equipe '{nome_equipe}' adicionada com sucesso!")
                else:
#Atualiza equipe existente
                    for team in st.session_state["team_data"]:
                        if team["Nome da Equipe"] == equipe_selecionada:
                            team.update({
                                "Nome da Equipe": nome_equipe,
                                "Treinador": treinador,
                                "Treinador Wins": treinador_wins,
                                "Treinador Runs": treinador_runs,
                                "Treinador Placed": treinador_placed,
                                "Jockey": jockey,
                                "Jockey Wins": jockey_wins,
                                "Jockey Rides": jockey_rides,
                                "Jockey 2nds": jockey_seconds,
                                "Jockey 3rds": jockey_thirds,
                            })
                            st.success(f"Alterações na equipe '{nome_equipe}' salvas com sucesso!")
# 🔹 Configuração do GitHub
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")  # Pegando o token do ambiente
REPO_OWNER = "vbautistacode"
REPO_NAME = "app"
BRANCH = "main"
FILE_PATH = "dados_equipe.csv"
GITHUB_API_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{FILE_PATH}"

# ✅ Função para salvar CSV no GitHub
def salvar_csv_no_github(dataframe):
    try:
        if dataframe.empty:
            st.warning("⚠️ O arquivo CSV está vazio! Não será salvo.")
            return

        csv_content = dataframe.to_csv(index=False, encoding="utf-8")
        encoded_content = base64.b64encode(csv_content.encode()).decode()
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}

        response = requests.get(GITHUB_API_URL, headers=headers)
        sha = response.json().get("sha", None)

        payload = {
            "message": "Atualizando dados_equipe.csv via API",
            "content": encoded_content,
            "branch": BRANCH
        }
        if sha:
            payload["sha"] = sha

        response = requests.put(GITHUB_API_URL, json=payload, headers=headers)
        if response.status_code in [200, 201]:
            st.success("✅ CSV de Equipes salvo no GitHub com sucesso!")
        else:
            st.error(f"❌ Erro ao salvar no GitHub: {response.json()}")

    except Exception as e:
        st.error(f"❌ Erro inesperado: {e}")

with tab3:
# 🔹 Exibir equipes já cadastradas
    if "team_data" not in st.session_state:
        st.session_state["team_data"] = []
    
    if st.session_state["team_data"]:
        st.write("### Equipes Cadastradas")
        df_teams = pd.DataFrame(st.session_state["team_data"])
        st.dataframe(df_teams)
    
        # ✅ Botão para salvar no GitHub
        if st.button("Salvar em CSV", key="unique_key_2"):
            salvar_csv_no_github(df_teams)
    else:
        st.warning("Ainda não há equipes cadastradas.")

# --- Aba 4: Resultados ---
with tab4:
#4.0. Dutching e Kelly
    if st.session_state["horse_data"]:
    df_cavalos = pd.DataFrame(st.session_state["horse_data"])
    bankroll = st.number_input("Digite o valor do Bankroll", min_value=1.00, step=1.0)

    if "Odds" in df_cavalos.columns and not df_cavalos["Odds"].isnull().all():
        df_cavalos["Probability"] = (1 / df_cavalos["Odds"]).round(2)
        df_cavalos["Dutching Bet"] = calculate_dutching(df_cavalos["Odds"], bankroll)
        df_cavalos["Dutching Bet"] = df_cavalos["Dutching Bet"].round(2)

        if bankroll > 0:
            df_cavalos["Kelly Bet"] = df_cavalos.apply(
                lambda row: kelly_criterion(row["Odds"], row["Probability"], bankroll), axis=1
            )
            df_cavalos["Lucro KB"] = round(df_cavalos["Odds"] * df_cavalos["Kelly Bet"], 2)
            df_cavalos["Lucro DB"] = round(df_cavalos["Odds"] * df_cavalos["Dutching Bet"], 2)
            df_cavalos["ROI-kb($)"] = round((df_cavalos["Lucro KB"] - df_cavalos["Kelly Bet"]), 2)
            df_cavalos["ROI-db($)"] = round((df_cavalos["Lucro DB"] - df_cavalos["Dutching Bet"]), 2)
            df_cavalos["ROI (%)"] = round((df_cavalos["Lucro DB"] / df_cavalos["Dutching Bet"]) * 100, 2)

        # Exibir tabela formatada no Streamlit
        st.dataframe(df_cavalos[["Nome", "Odds", "Probability", "Kelly Bet", "Dutching Bet", "Lucro KB", "Lucro DB", "ROI (%)"]])

        # Cálculo do somatório da coluna "Dutching Bet"
        total_dutching = round(df_cavalos["Dutching Bet"].sum(), 2)

# --- Ajuste das apostas baseado na performance das equipes ---
st.write("### Análise de Performance por Equipe")

if "team_data" in st.session_state and st.session_state["team_data"]:
    df_desempenho = []
    for team in st.session_state["team_data"]:
        # Calcular desempenho do cavalo
        podiums_horse = team.get("Wins", 0) + team.get("2nds", 0) + team.get("3rds", 0)
        runs_horse = team.get("Runs", 1)
        desempenho_horse = podiums_horse / max(runs_horse, 1)
        st.session_state["desempenho_horse"] = desempenho_horse

        # Calcular desempenho do jóquei
        podiums_jockey = team.get("Jockey Wins", 0) + team.get("Jockey 2nds", 0) + team.get("Jockey 3rds", 0)
        rides_jockey = team.get("Jockey Rides", 1)
        desempenho_jockey = podiums_jockey / max(rides_jockey, 1)
        st.session_state["desempenho_jockey"] = desempenho_jockey

        # Calcular desempenho do treinador
        podiums_trainer = team.get("Treinador Placed", 0) + team.get("Treinador Wins", 0)
        runs_trainer = team.get("Treinador Runs", 1)
        desempenho_trainer = podiums_trainer / max(runs_trainer, 1)
        st.session_state["desempenho_trainer"] = desempenho_trainer

        # Ajuste baseado na performance média
        media_desempenho = (desempenho_jockey + desempenho_trainer + desempenho_horse) / 3
        df_desempenho.append({
            "Nome da Equipe": team["Nome da Equipe"],
            "Desempenho Médio Ajustado": round(media_desempenho, 2)
        })

    # Converter para DataFrame e ordenar por desempenho
    df_desempenho = pd.DataFrame(df_desempenho).sort_values(by="Desempenho Médio Ajustado", ascending=False)

    # Ajustar valores de aposta com base no desempenho médio
    melhor_equipe = df_desempenho.iloc[0]
    ajuste_percentual = melhor_equipe["Desempenho Médio Ajustado"] / 100
    df_cavalos["Adjusted Bet"] = df_cavalos["Dutching Bet"] * (1 + ajuste_percentual)

    # Exibir tabela final ajustada
    st.write(f"🏆 **Melhor Equipe:** {melhor_equipe['Nome da Equipe']} com Desempenho Médio de {melhor_equipe['Desempenho Médio Ajustado']:.2f}")
    st.dataframe(df_desempenho)

    # Exibir apostas ajustadas
    st.write("### Apostas Ajustadas")
    st.dataframe(df_cavalos[["Nome", "Adjusted Bet"]])
