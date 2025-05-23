# --- Importações ---
from datetime import datetime, timedelta, time
import plotly.graph_objects as go
import matplotlib.pyplot as plt
import plotly.express as px
import streamlit as st
from fpdf import FPDF
import pandas as pd
import numpy as np
import requests
import logging
import joblib
import pdfkit
import base64
import json
import os

# Configurar Pandas para aceitar futuras mudanças no tratamento de objetos
pd.set_option('future.no_silent_downcasting', True)

# ✅ Ajustar tamanho dos campos de entrada usando CSS
st.markdown("""
    <style>
        div[data-baseweb="input"] {
            width: 222px !important;
        }
        div[data-baseweb="select"] {
            width: 222px !important;
        }
    </style>
""", unsafe_allow_html=True)

# --- Configuração do GitHub ---
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_OWNER = "vbautistacode"
REPO_NAME = "app"
BRANCH = "main"

# Diretório do repositório no GitHub
diretorio_base = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/{BRANCH}/"

# --- Funções de carregamento e salvamento ---
def load_data():
#Carrega os dados do GitHub para o session_state
    arquivos = ["horse_data.json", "team_data.json", "bet_data.json"]
    for arquivo in arquivos:
        url_arquivo = diretorio_base + arquivo
        try:
            response = requests.get(url_arquivo)
            response.raise_for_status()
            st.session_state[arquivo.replace(".json", "")] = response.json()
        except requests.exceptions.RequestException:
            st.session_state[arquivo.replace(".json", "")] = []

def salvar_csv_no_github(dataframe, nome_arquivo):
#Salva o dataframe como CSV no GitHub via API
    if dataframe.empty:
        st.warning(f"⚠️ O arquivo '{nome_arquivo}' está vazio! Não será salvo.")
        return

    try:
        csv_content = dataframe.to_csv(index=False, encoding="utf-8")
        encoded_content = base64.b64encode(csv_content.encode()).decode()
        github_api_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{nome_arquivo}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        response = requests.get(github_api_url, headers=headers)
        sha = response.json().get("sha", None)

        payload = {"message": f"Atualizando {nome_arquivo} via API", "content": encoded_content, "branch": BRANCH}
        if sha:
            payload["sha"] = sha  # Atualiza arquivo existente
        response = requests.put(github_api_url, json=payload, headers=headers)

        if response.status_code in [200, 201]:
            st.success(f"✅ {nome_arquivo} salvo no GitHub com sucesso!")
        else:
            st.error(f"❌ Erro ao salvar {nome_arquivo}: {response.json()}")

    except Exception as e:
        st.error(f"❌ Erro inesperado: {e}")

# --- Inicialização de dados ---
if "initialized" not in st.session_state:
    load_data()
    st.session_state["initialized"] = True

# 🔹 Bloco para armazenar variáveis persistentes
st.session_state.setdefault("horse_data", [])
st.session_state.setdefault("team_data", [])
st.session_state.setdefault("Nome", "Cavalo_Default")
st.session_state.setdefault("df_cavalos", pd.DataFrame(columns=["Nome", "Odds", "Dutching Bet", "Lucro Dutch"]))
st.session_state.setdefault("df_desempenho", pd.DataFrame(columns=["Nome da Equipe", "Desempenho Médio Ajustado"]))
st.session_state.setdefault("bankroll", 1000.0)  # Valor padrão do Bankroll
st.session_state.setdefault("ajuste_percentual", 1.0)
st.session_state.setdefault("fator_exclusao", 0.0)
st.session_state.setdefault("horse_data", [])
st.session_state.setdefault("team_data", [])
st.session_state.setdefault("Nome", "Cavalo_Default")

# --- Funções de cálculo ---

# Ajuste de odds removendo overround
def ajustar_odds(odds, overround_pct):
    return [odd / (1 + overround_pct) for odd in odds]

# Cálculo da distribuição de apostas ajustadas considerando probabilidade real do favorito
def distribuir_apostas(df, total_aposta, incluir_desempenho):
    if incluir_desempenho:
        fator_ajuste = df["historico_vitoria"] / 100
    else:
        fator_ajuste = 1  # Sem ajuste se a análise de desempenho estiver desativada

    df["valor_apostado"] = np.round(total_aposta * (fator_ajuste / fator_ajuste.sum()), 2)
    return df

#Calcula a distribuição de apostas usando Dutching
def calculate_dutching(odds, bankroll, historical_factor):
    probabilities = np.array([1 / odd for odd in odds])
    adjusted_probabilities = probabilities * historical_factor
    total_probability = adjusted_probabilities.sum()
    adjusted_probabilities /= total_probability if total_probability > 1 else 1
    return np.round(bankroll * adjusted_probabilities, 2)

#Calcula o desempenho das equipes com ajuste de variância
def calcular_desempenho_equipes(team_data):
    if not team_data:
        st.warning("⚠️ Nenhum dado de equipe disponível.")
        return pd.DataFrame(columns=["Nome da Equipe", "Desempenho Médio Ajustado", "Desvio Padrão"])
    
    df_desempenho_lista = []
    
    for team in team_data:
        # 🔹 Cálculo dos desempenhos individuais
        podiums_horse = team.get("Wins", 0) + team.get("2nds", 0) + team.get("3rds", 0)
        runs_horse = max(team.get("Runs", 1), 1)
        desempenho_horse = podiums_horse / runs_horse

        podiums_jockey = team.get("Jockey Wins", 0) + team.get("Jockey 2nds", 0) + team.get("Jockey 3rds", 0)
        rides_jockey = max(team.get("Jockey Rides", 1), 1)
        desempenho_jockey = podiums_jockey / rides_jockey

        podiums_trainer = team.get("Treinador Placed", 0) + team.get("Treinador Wins", 0)
        runs_trainer = max(team.get("Treinador Runs", 1), 1)
        desempenho_trainer = podiums_trainer / runs_trainer

        desempenhos = np.array([desempenho_horse, desempenho_jockey, desempenho_trainer])

        # 🔹 Normalização dos desempenhos
        desempenhos_norm = desempenhos / np.max(desempenhos) if np.max(desempenhos) > 0 else desempenhos

        # 🔹 Ponderação dos fatores
        peso_horse = 0.5
        peso_jockey = 0.3
        peso_trainer = 0.2
        media_desempenho = (desempenhos_norm[0] * peso_horse) + (desempenhos_norm[1] * peso_jockey) + (desempenhos_norm[2] * peso_trainer)

        # 🔹 Melhorando o ajuste com desvio padrão adaptativo
        desvio_padrao = np.std(desempenhos_norm)
        peso_ajuste = desvio_padrao / (media_desempenho + 1)  # Ajuste dinâmico para variação
        resultado_ajustado = media_desempenho - (peso_ajuste * desvio_padrao)

        df_desempenho_lista.append({
            "Nome da Equipe": team["Nome da Equipe"],
            "Desempenho Médio Ajustado": round(resultado_ajustado, 2),
            "Desvio Padrão": round(desvio_padrao, 2)
        })

    return pd.DataFrame(df_desempenho_lista).sort_values(by="Desempenho Médio Ajustado", ascending=False)

# Função para calcular aposta ajustada com base nas odds e desempenho
def calcular_aposta_ajustada(df, bankroll_favoritos, prob_vitoria_favorito):
    if not df.empty and "Desempenho Médio Ajustado" in df.columns:
        # ✅ Criar fator ajustado incluindo probabilidade histórica de vitória
        df["Fator Ajustado"] = (df["Desempenho Médio Ajustado"] / df["Desempenho Médio Ajustado"].max()) * (1 + prob_vitoria_favorito)

        # ✅ Ajustar as odds com base no fator ajustado
        df["Odds Ajustadas"] = df["Odds"] * df["Fator Ajustado"]

        # ✅ Redistribuir apostas proporcionalmente considerando Odds Ajustadas
        df["Valor Apostado Ajustado"] = round(
            (bankroll_favoritos / df["Odds Ajustadas"].sum()) * df["Odds Ajustadas"], 2
        )
    else:
        st.warning("⚠️ Dados insuficientes para calcular aposta ajustada.")

    return df

# ✅ Função para calcular probabilidade implícita das odds
def calcular_probabilidade_implicita(odds):
    return (1 / odds) * 100

# ✅ Função para calcular odds ajustadas removendo a margem das casas de apostas
def remover_margem_casas(df):
    soma_probabilidades = df["Probabilidade Implícita"].sum()
    df["Probabilidade Ajustada"] = (df["Probabilidade Implícita"] / soma_probabilidades) * 100
    return df
    
# ✅ Função para calcular o Valor Esperado (EV)
def calcular_valor_esperado(probabilidade_real, odds, valor_apostado):
    retorno_potencial = odds * valor_apostado
    ev = (probabilidade_real * retorno_potencial) - valor_apostado
    return round(ev, 2)

# --- Interface Streamlit ---
st.title("Apostas | Estratégias Dutching")

# Abas para organização
tab1, tab2, tab3, tab4, tab5 = st.tabs(["Locais", "Dados dos Cavalos", "Dados das Equipes", "Análises", "Apostas"])

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

# ✅ Campo para inserção da hora abaixo do botão
    hora_prova = st.time_input("⏰ Insira o horário da prova:", value=time(12,0))

# ✅ Salvar local e hora na `session_state`
if hora_prova:
    st.session_state["hora_prova"] = hora_prova.strftime("%H:%M")
if novo_local:
    st.session_state["local_atual"] = novo_local
            
# --- Aba 2: Dados dos Cavalos ---
with tab2:
    st.subheader("Dados Históricos | Cavalos")
    
# ✅ Verifica se 'horse_data' já foi inicializado
    if "horse_data" not in st.session_state:
        st.session_state["horse_data"] = []
    if "local_atual" not in st.session_state: 
        st.session_state["local_atual"] = None
        
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
            odds = st.number_input("Odds (Probabilidades)", min_value=0.01, step=0.01, value=cavalo_dados["Odds"] if cavalo_dados else 0.01)
            runs = st.number_input("Runs (Corridas)", min_value=0, step=1, value=cavalo_dados["Runs"] if cavalo_dados else 0)
        with col2:
            wins = st.number_input("Wins (Vitórias)", min_value=0, step=1, value=cavalo_dados["Wins"] if cavalo_dados else 0)
            seconds = st.number_input("2nds (Segundos Lugares)", min_value=0, step=1, value=cavalo_dados["2nds"] if cavalo_dados else 0)
            thirds = st.number_input("3rds (Terceiros Lugares)", min_value=0, step=1, value=cavalo_dados["3rds"] if cavalo_dados else 0)
            
# ✅ Botão para salvar dados do cavalo
            if st.button("Salvar Dados do Cavalo"):
                novo_cavalo = {
                    "Local": local_atual,
                    "Nome": Nome,
                    "Runs": runs,
                    "Wins": wins,
                    "2nds": seconds,
                    "3rds": thirds,
                    "Odds": odds,
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
#with tab2:
    
# ✅ Botão para salvar no GitHub
#    if st.button("Salvar em CSV", key="unique_key_1"):
#        salvar_csv_no_github(df_horses)
#    else:
#        st.warning("Ainda não há cavalos registrados.")
        
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
        #if st.button("Salvar em CSV", key="unique_key_2"):
        #    salvar_csv_no_github(df_teams)
    else:
        st.warning("Ainda não há equipes cadastradas.")
        
# --- Aba 4: Resultados ---
with tab4:
    st.write("#### 🏇 | Dutching e Performance de Equipes |")
# ✅ Exibir local e horário no cabeçalho da Aba 4
# Divisão em duas colunas
    col1, col2 = st.columns(2)
    with col1:
        st.write(f"📍 **Local da Prova:** {st.session_state.get('local_atual', 'Não definido')}")
    with col2:
        st.write(f"⏰ **Horário da Prova:** {st.session_state.get('hora_prova', 'Não definido')}")

    # Verificação de dados de equipes e criação do DataFrame
    df_desempenho = pd.DataFrame(columns=["Nome da Equipe", "Desempenho Médio Ajustado"])
    if st.session_state.get("team_data"):
        df_desempenho = calcular_desempenho_equipes(st.session_state["team_data"])
    else:
        st.warning("⚠️ Nenhuma equipe cadastrada!")

    # Verificação de dados de cavalos e criação do DataFrame
    df_cavalos = pd.DataFrame(columns=["Nome", "Odds", "Dutching Bet", "Gain Dutch"])
    if st.session_state.get("horse_data"):
        df_cavalos = pd.DataFrame(st.session_state["horse_data"])
        bankroll = st.number_input("Digite o valor do Bankroll:", min_value=100.0, max_value=100000.0, step=10.0, value=1000.0, key="bankroll_input")
    else:
        st.warning("⚠️ Nenhum dado de cavalos disponível.")

    # Definição do bankroll, evitando verificações repetidas
    bankroll = st.session_state.get("bankroll_input", 1000.0)

    # Filtragem de cavalos
    nomes_selecionados = st.multiselect("Selecione os cavalos:", df_cavalos["Nome"].unique()) if not df_cavalos.empty else []
    df_cavalos_filtrado = df_cavalos[df_cavalos["Nome"].isin(nomes_selecionados)] if nomes_selecionados else df_cavalos

    if df_cavalos_filtrado.empty:
        st.warning("⚠️ Nenhum cavalo foi selecionado ou carregado.")
    else:
        incluir_desempenho = st.checkbox("Incluir análise de desempenho?", value=False, key="incluir_desempenho_aba4")
    
        # Merge de desempenho apenas se necessário
        if incluir_desempenho and not df_desempenho.empty:
            df_cavalos_filtrado = df_cavalos_filtrado.merge(df_desempenho, left_on="Nome", right_on="Nome da Equipe", how="left")
            df_cavalos_filtrado["Desempenho Médio Ajustado"].fillna(1, inplace=True)
        else:
            df_cavalos_filtrado["Desempenho Médio Ajustado"] = 1
    
        # Calcular apostas Dutching e probabilidades
        df_cavalos_filtrado["Probabilidade"] = (1 / df_cavalos_filtrado["Odds"]).round(2)
        df_cavalos_filtrado["Dutching Bet"] = calculate_dutching(df_cavalos_filtrado["Odds"], bankroll, np.ones(len(df_cavalos_filtrado)))
        df_cavalos_filtrado["Gain Dutch"] = round(df_cavalos_filtrado["Odds"] * df_cavalos_filtrado["Dutching Bet"], 2)
        df_cavalos_filtrado["ROI (%)"] = round((df_cavalos_filtrado["Gain Dutch"] / df_cavalos_filtrado["Dutching Bet"]) * 100, 2)

        st.dataframe(df_cavalos_filtrado[["Nome", "Odds", "Probabilidade", "Dutching Bet", "Gain Dutch", "ROI (%)"]])

        st.write(f"💰 **Total de Aposta:** R$ {df_cavalos_filtrado['Dutching Bet'].sum():.2f}")
        st.write(f"💸 **Gain Esperado:** R$ {df_cavalos_filtrado['Gain Dutch'].iloc[0]:.2f}")
        lucro_aposta = df_cavalos_filtrado["Gain Dutch"].iloc[0] - df_cavalos_filtrado["Dutching Bet"].sum()
        st.write(f"✅ **Lucro:** R$ {lucro_aposta:.2f}")
        
        st.divider()
        
    # ✅ Exibir análise de desempenho de equipes
    st.write("#### 📊 | Análise de Desempenho |")
    
    # ✅ Garantir que há dados antes de exibir os desempenhos individuais
    if not df_desempenho.empty and "Desempenho Médio Ajustado" in df_desempenho.columns:
        
        # ✅ Ordenar do melhor para o pior e selecionar os 3 primeiros
        top_desempenho = df_desempenho.nlargest(3, "Desempenho Médio Ajustado")
    
        # ✅ Exibir o Top 3 lado a lado
        if len(top_desempenho) >= 3:
            st.markdown("<h2 style='text-align: left; font-size: 18px;'>🏆 Top 3 Melhores Desempenhos 🏆</h2>", unsafe_allow_html=True)
            col1, col2, col3 = st.columns(3)  # Criando três colunas para exibir os melhores
            with col1:
                st.write(f"🥇 **{top_desempenho.iloc[0]['Nome da Equipe']}** → {top_desempenho.iloc[0]['Desempenho Médio Ajustado']:.2f}")
            with col2:
                st.write(f"🥈 **{top_desempenho.iloc[1]['Nome da Equipe']}** → {top_desempenho.iloc[1]['Desempenho Médio Ajustado']:.2f}")
            with col3:
                st.write(f"🥉 **{top_desempenho.iloc[2]['Nome da Equipe']}** → {top_desempenho.iloc[2]['Desempenho Médio Ajustado']:.2f}")
                st.text("")
        else:
            st.warning("⚠️ Dados insuficientes para exibir o Top 3. Insira mais informações.")

        # ✅ Filtrar as equipes restantes
        equipes_restantes = df_desempenho[~df_desempenho["Nome da Equipe"].isin(top_desempenho["Nome da Equipe"])]
    
        # ✅ Exibir o restante das equipes em duas colunas
        st.markdown("<h3 style='text-align: left; font-size: 18px;'>🏇 Desempenho das Outras Equipes</h3>", unsafe_allow_html=True)
        col_a, col_b = st.columns(2)
        for index, row in equipes_restantes.iterrows():
            if index % 2 == 0:  # Alterna entre as colunas
                with col_a:
                    st.write(f"🔹 **{row['Nome da Equipe']}** → Desempenho: {row['Desempenho Médio Ajustado']:.2f}")
            else:
                with col_b:
                    st.write(f"🔹 **{row['Nome da Equipe']}** → Desempenho: {row['Desempenho Médio Ajustado']:.2f}")
    
    else:
        st.warning("⚠️ Dados insuficientes para calcular o desempenho das equipes.")
        
    st.divider()
            
# --- Aposta Top 3 ---
    st.write("#### 🏆 | Aposta Top 3 |")
    
    # ✅ Criar duas colunas para exibir os inputs lado a lado
    col1, col2 = st.columns(2)
    
    # ✅ Entrada para definir probabilidade histórica de vitória
    with col1:
        prob_vitoria_favorito = st.number_input(
            "📊 Probabilidade Histórica de Vitória (%)",
            min_value=0.0, max_value=100.0, step=0.1, value=39.68
        ) / 100
    
    # ✅ Entrada para definir percentual do bankroll nos favoritos
    with col2:
        percentual_bankroll_favoritos = st.number_input(
            "💰 Percentual do Bankroll para Favoritos (%)",
            min_value=0.0, max_value=100.0, step=1.0, value=50.0
        ) / 100
    
    # ✅ Entrada manual para seleção dos favoritos, ordenando por desempenho se ativado
    incluir_desempenho = st.checkbox("Incluir análise de desempenho?", value=True, key="incluir_desempenho_top3")
    if incluir_desempenho and not df_cavalos_filtrado.empty and "Desempenho Médio Ajustado" in df_cavalos_filtrado.columns:
        df_cavalos_filtrado = df_cavalos_filtrado.sort_values("Desempenho Médio Ajustado", ascending=False)
    else:
        st.text("")

    nomes_favoritos = st.multiselect(
        "Selecione os cavalos para apostar:",
        df_cavalos_filtrado["Nome"].unique(),
        default=df_cavalos_filtrado["Nome"].unique()[:3]  # Prioriza os 3 melhores desempenhos por padrão
    )
    
    # ✅ Filtrar os favoritos com base na seleção manual
    df_favoritos = df_cavalos_filtrado[df_cavalos_filtrado["Nome"].isin(nomes_favoritos)] if nomes_favoritos else pd.DataFrame()
    
    # ✅ Verificação de existência de dados antes de prosseguir com cálculos
    if not df_favoritos.empty:
        # ✅ Ajuste correto do bankroll, distribuindo proporcionalmente
        bankroll_favoritos = bankroll * percentual_bankroll_favoritos
        df_favoritos["Valor Apostado"] = round((bankroll_favoritos / df_favoritos["Odds"].sum()) * df_favoritos["Odds"], 2)

        # ✅ Cálculo da probabilidade implícita das odds
        df_favoritos["Probabilidade Implícita"] = df_favoritos["Odds"].apply(lambda odds: (1 / odds) * 100)
    
        # ✅ Ajustar odds removendo a margem das casas de apostas
        soma_probabilidades = df_favoritos["Probabilidade Implícita"].sum()
        df_favoritos["Probabilidade Ajustada"] = (df_favoritos["Probabilidade Implícita"] / soma_probabilidades) * 100

        # ✅ Calcular o EV de cada aposta
        df_favoritos["Valor Esperado (EV)"] = df_favoritos.apply(
            lambda row: calcular_valor_esperado(row["Probabilidade Ajustada"] / 100, row["Odds"], row["Valor Apostado"]), axis=1
        )
                
        # ✅ Botão para inverter lógica de distribuição das apostas
        inverter_logica = st.button("Inverter lógica de aposta")

    # ✅ Aplicar lógica de distribuição de apostas
    if not df_favoritos.empty and "Odds" in df_favoritos.columns:
        max_odds = df_favoritos["Odds"].max()  # Obtém o maior valor de odds
    
        if inverter_logica:
            # Normalizar a inversão para manter a soma igual
            odds_invertidas = max_odds - df_favoritos["Odds"]
            fator_ajuste = bankroll_favoritos / odds_invertidas.sum()
            df_favoritos["Valor Apostado"] = round(odds_invertidas * fator_ajuste, 2)
            logica_aplicada = "🔄 **Modo invertido:** Maior valor apostado nas menores odds."
        else:
            # Modo padrão: maior valor apostado nas maiores odds
            fator_ajuste = bankroll_favoritos / df_favoritos["Odds"].sum()
            df_favoritos["Valor Apostado"] = round(df_favoritos["Odds"] * fator_ajuste, 2)
            logica_aplicada = "✅ **Modo padrão:** Maior valor apostado nas maiores odds."

        # ✅ Criar coluna "Ganhos" apenas se as colunas necessárias existirem
        if "Odds" in df_favoritos.columns and "Valor Apostado" in df_favoritos.columns:
            df_favoritos["Ganhos"] = round(df_favoritos["Odds"] * df_favoritos["Valor Apostado"], 2)
        
        # ✅ Exibir mensagem sobre qual lógica está sendo aplicada
        st.write(logica_aplicada)
    
        # ✅ Exibir DataFrame atualizado
        st.dataframe(df_favoritos[["Nome", "Odds", "Valor Apostado", "Ganhos", "Probabilidade Ajustada", "Valor Esperado (EV)"]])
    
        # ✅ Cálculo do valor total apostado e do lucro esperado
        total_apostado = df_favoritos["Valor Apostado"].sum()
        retorno_aposta = (df_favoritos["Valor Apostado"] * df_favoritos["Odds"]).sum()
        lucro_aposta = retorno_aposta - total_apostado
       
        # ✅ Conversão de odds e limpeza de dados
        if not df_favoritos.empty:
            df_favoritos["Odds"] = pd.to_numeric(df_favoritos["Odds"], errors="coerce")
            df_favoritos.dropna(subset=["Odds"], inplace=True)
    
        # ✅ Calcular retorno máximo e mínimo corretamente
        if not df_favoritos.empty and "Valor Apostado" in df_favoritos.columns:
            df_favoritos["Gain Adjusted"] = df_favoritos["Valor Apostado"] * df_favoritos["Odds"]
        
            retorno_maximo = df_favoritos.nlargest(3, "Odds")["Gain Adjusted"].sum()
            retorno_minimo = df_favoritos.nsmallest(3, "Odds")["Gain Adjusted"].sum()
    
            # ✅ Criar duas colunas para organizar os blocos
            col1, col2 = st.columns(2)
            
            # ✅ Bloco 1 - Exibir informações gerais de aposta
            with col1:
                st.write("📊 **Informações da Aposta:**")
                st.write(f"💰 **Total de Aposta:** R$ {total_apostado:.2f}")
                st.write(f"💸 **Gain Esperado:** R$ {retorno_aposta:.2f}")
                st.write(f"✅ **Lucro Esperado:** R$ {lucro_aposta:.2f}")
            
            # ✅ Bloco 2 - Exibir cálculos de retorno máximo e mínimo
            with col2:
                st.write("🔝 **Cálculo de Retorno:**")
                st.write(f"📈 **Retorno Máximo (+odds):** R$ {retorno_maximo:.2f}")
                st.write(f"📉 **Retorno Mínimo (-odds):** R$ {retorno_minimo:.2f}")
        else:
            st.warning("⚠️ Não há dados suficientes para calcular retorno máximo e mínimo.")
        
        st.divider()
        
        # ✅ Verificar se existem dados de cavalos antes de prosseguir
        if not df_cavalos_filtrado.empty:
    
            st.write("#### 📊| Apostas Balanceadas (Desempenho) |")
            
            # ✅ Incluir análise de desempenho antes de prosseguir com cálculos
            incluir_desempenho = st.checkbox("Incluir análise de desempenho?", value=False, key="incluir_desempenho_check")
        
            # ✅ Garantir que df_desempenho possui os dados necessários antes da aplicação
            if incluir_desempenho and not df_desempenho.empty:
                if "Nome da Equipe" in df_desempenho.columns and "Desempenho Médio Ajustado" in df_desempenho.columns:
                    
                    # ✅ Padronizar nomes para evitar erro de correspondência
                    df_cavalos_filtrado["Nome"] = df_cavalos_filtrado["Nome"].str.strip().str.lower()
                    df_desempenho["Nome da Equipe"] = df_desempenho["Nome da Equipe"].str.strip().str.lower()
        
                    # ✅ Criar dicionário de mapeamento
                    desempenho_dict = df_desempenho.set_index("Nome da Equipe")["Desempenho Médio Ajustado"].to_dict()
        
                    # ✅ Aplicar valores de desempenho diretamente via map()
                    df_cavalos_filtrado["Desempenho Médio Ajustado"] = df_cavalos_filtrado["Nome"].map(desempenho_dict).fillna(1)
        
                else:
                    st.warning("⚠️ O DataFrame de desempenho não tem as colunas esperadas. Verifique os dados antes da aplicação.")
        
            else:
                df_cavalos_filtrado["Desempenho Médio Ajustado"] = 1  # Define valor padrão se não houver análise
        
            # ✅ Garantir que "Valor Apostado" seja criado corretamente antes de usar desempenho
            bankroll_favoritos = bankroll * percentual_bankroll_favoritos
        
            if df_cavalos_filtrado["Odds"].sum() > 0:
                df_cavalos_filtrado["Valor Apostado"] = round(
                    (bankroll_favoritos / df_cavalos_filtrado["Odds"].sum()) * df_cavalos_filtrado["Odds"], 2
                )
            else:
                st.warning("⚠️ Erro: Soma das Odds é zero. Verifique os dados antes de calcular apostas.")
        
            # ✅ Aplicando ajuste antes da exibição dos dados
            df_cavalos_filtrado = calcular_aposta_ajustada(df_cavalos_filtrado, bankroll_favoritos, prob_vitoria_favorito)
            
            # ✅ Exibir DataFrame atualizado
            st.dataframe(df_cavalos_filtrado[["Nome", "Odds", "Valor Apostado Ajustado"]])
            
            # ✅ Dividir apostas ajustadas entre os 50% primeiros e os 50% restantes
            df_cavalos_filtrado = df_cavalos_filtrado.sort_values("Odds", ascending=True)
            metade_index = len(df_cavalos_filtrado) // 2  # Define ponto de separação
            
            # ✅ Selecionar os 50% primeiros e 50% restantes
            df_top50 = df_cavalos_filtrado.iloc[:metade_index]
            df_bottom50 = df_cavalos_filtrado.iloc[metade_index:]
            
            # ✅ Calcular soma das apostas ajustadas para cada grupo
            soma_top50 = df_top50["Valor Apostado Ajustado"].sum()
            soma_bottom50 = df_bottom50["Valor Apostado Ajustado"].sum()
            
            # ✅ Calcular retorno máximo e mínimo para cada grupo
            retorno_maximo_top50 = (df_top50["Valor Apostado Ajustado"] * df_top50["Odds"]).sum()
            retorno_minimo_top50 = df_top50["Valor Apostado Ajustado"].sum()
            
            retorno_maximo_bottom50 = (df_bottom50["Valor Apostado Ajustado"] * df_bottom50["Odds"]).sum()
            retorno_minimo_bottom50 = df_bottom50["Valor Apostado Ajustado"].sum()
            
            # ✅ Exibir resultados organizados
            st.write("##### | Resumo das Apostas por Odds |")
            st.text("")
            col1, col2 = st.columns(2)
            
            # ✅ Bloco 1 - Apostas nos 50% primeiros valores de odds
            with col1:
                st.write("🔝 **Apostas nos 50% Menores Odds**")
                st.write(f"💰 **Total de Aposta:** R$ {soma_top50:.2f}")
                st.write(f"📈 **Retorno Máximo (+odds):** R$ {retorno_maximo_top50:.2f}")
                st.write(f"📉 **Retorno Mínimo (-odds):** R$ {retorno_minimo_top50:.2f}")
            
            # ✅ Bloco 2 - Apostas nos 50% restantes valores de odds
            with col2:
                st.write("🔻 **Apostas nos 50% Maiores Odds**")
                st.write(f"💰 **Total de Aposta:** R$ {soma_bottom50:.2f}")
                st.write(f"📈 **Retorno Máximo (+odds):** R$ {retorno_maximo_bottom50:.2f}")
                st.write(f"📉 **Retorno Mínimo (-odds):** R$ {retorno_minimo_bottom50:.2f}")
    
            st.divider()

# --- Aba 5: Apostas ---

with tab5:
# ✅ Nome do arquivo da planilha
    nome_arquivo = "apostas_registradas.xlsx"
    
    # ✅ Função para salvar apostas no Excel
    def salvar_aposta(local, nome, hora, odds, valor_apostado, lucro, resultado):
        try:
            # 🔹 Verificar se o arquivo já existe
            try:
                df_apostas = pd.read_excel(nome_arquivo)
            except FileNotFoundError:
                df_apostas = pd.DataFrame(columns=["Local", "Nome", "Hora", "Odds", "Valor Apostado", "Lucro", "Resultado", "Data"])
    
            # 🔹 Adicionar Data automaticamente
            data_atual = datetime.now().strftime("%Y-%m-%d")
    
            # 🔹 Criar nova linha com todos os campos necessários
            nova_aposta = pd.DataFrame([[local, nome, hora.strftime("%H:%M"), odds, valor_apostado, lucro, resultado, data_atual]], columns=df_apostas.columns)
    
            # 🔹 Concatenar ao DataFrame e salvar no Excel
            df_apostas = pd.concat([df_apostas, nova_aposta], ignore_index=True)
            df_apostas.to_excel(nome_arquivo, index=False)
    
            st.success(f"✅ Aposta salva com sucesso! 🏇 {nome} - Local: {local} - Hora: {hora.strftime('%H:%M')} - Valor: {valor_apostado:.2f} - Lucro: {lucro:.2f}")

        except Exception as e:
            st.error(f"⚠️ Erro ao salvar aposta: {str(e)}")

# ✅ Definição da função para salvar arquivo no GitHub
    def salvar_xlsx_no_github(nome_arquivo_local, nome_arquivo_remoto):
        GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
        REPO_OWNER = "vbautistacode"
        REPO_NAME = "app"
        BRANCH = "main"
        GITHUB_API_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{nome_arquivo_remoto}"
    
        try:
            with open(nome_arquivo_local, "rb") as f:
                file_content = base64.b64encode(f.read()).decode("utf-8")
            
            headers = {"Authorization": f"token {GITHUB_TOKEN}"}
            response = requests.get(GITHUB_API_URL, headers=headers)
    
            sha = response.json().get("sha") if response.status_code == 200 else None
    
            payload = {
                "message": "Atualizando arquivo apostas_registradas.xlsx",
                "content": file_content,
                "branch": BRANCH,
            }
            if sha:
                payload["sha"] = sha
    
            response = requests.put(GITHUB_API_URL, headers=headers, json=payload)
    
            if response.status_code in [200, 201]:
                st.success("✅ Arquivo salvo no GitHub com sucesso!")
            else:
                st.error(f"⚠️ Erro ao salvar o arquivo: {response.json()}")
    
        except FileNotFoundError:
            st.error(f"❌ Arquivo '{nome_arquivo_local}' não encontrado!")
    
    try:
        df_cavalos = pd.read_excel(nome_arquivo)
    
        # ✅ Aba de Apostas
        with st.container():
            st.write("#### 🏆 Histórico de Performance")
    
            if {"Nome", "Lucro", "Valor Apostado", "Odds"}.issubset(df_cavalos.columns):
                df_cavalos["Lucro Total"] = df_cavalos["Lucro"] - df_cavalos["Valor Apostado"]
                
                # ✅ Corrigir agregação sem duplicação
                performance_pessoal = df_cavalos.groupby("Nome").agg({
                    "Lucro Total": "sum",
                    "Valor Apostado": "sum",
                    "Odds": "mean"
                }).rename(columns={"Odds": "Odds Média"})
    
                #st.dataframe(performance_pessoal)
                st.write(f"💰 **Lucro Total:** R$ {performance_pessoal['Lucro Total'].sum():,.2f}")
    
            else:
                st.warning("⚠️ As colunas necessárias estão ausentes no arquivo!")
                
            st.divider()
                        
            # ✅ Gráfico de Lucro por Cavalo
            st.write("#### 📊 Gráficos")
    
            if {"Nome", "Lucro", "Valor Apostado", "Local"}.issubset(df_cavalos.columns):
                df_cavalos["Lucro Total"] = df_cavalos["Lucro"] - df_cavalos["Valor Apostado"]
    
                lucro_por_cavalo = df_cavalos.groupby("Nome")["Lucro Total"].sum().reset_index()
                fig_bar_cavalo = px.bar(
                    lucro_por_cavalo, x="Nome", y="Lucro Total", title="Lucro por Cavalo",
                    color="Lucro Total", text="Lucro Total",
                    labels={"Nome": "Cavalo", "Lucro Total": "Lucro Total (R$)"}
                )
                fig_bar_cavalo.update_traces(texttemplate='%{text:.2f}', textposition='outside')
                fig_bar_cavalo.update_layout(title_x=0.5, xaxis_title="Cavalo", yaxis_title="Lucro Total (R$)")
                st.plotly_chart(fig_bar_cavalo, use_container_width=True)
                
                st.divider()
                
                # ✅ Gráfico de Lucro por Local
                lucro_por_local = df_cavalos.groupby("Local")["Lucro Total"].sum().reset_index()
                fig_bar_local = px.bar(
                    lucro_por_local, x="Local", y="Lucro Total", title="Lucro por Pista",
                    color="Lucro Total", text="Lucro Total",
                    labels={"Local": "Local", "Lucro Total": "Lucro Total (R$)"}
                )
                fig_bar_local.update_traces(texttemplate='%{text:.2f}', textposition='outside')
                fig_bar_local.update_layout(title_x=0.5, xaxis_title="Local", yaxis_title="Lucro Total (R$)")
                st.plotly_chart(fig_bar_local, use_container_width=True)
    
            else:
                st.warning("⚠️ As colunas necessárias estão ausentes no arquivo!")

                # ✅ Índice de Recuperação
            st.write("#### 🔄 Índice de Recuperação")
    
            if "Data" in df_cavalos.columns:
                df_cavalos["Data"] = pd.to_datetime(df_cavalos["Data"], errors='coerce')
                df_cavalos["Intervalo (Dias)"] = df_cavalos["Data"].diff().dt.days
                st.write(f"📅 **Média do Intervalo Entre Corridas:** {df_cavalos['Intervalo (Dias)'].mean():.2f} dias")
            else:
                st.warning("⚠️ A coluna 'Data' é necessária para calcular o Índice de Recuperação.")
                
            st.divider()
            
            # ✅ Criar campos de entrada
            st.write("#### 🏇 Registrar Nova Aposta")
            col1, col2 = st.columns(2)
            
            with col1:
                local = st.text_input("📍 Local da Corrida", value=st.session_state.get("local_atual",""))
                hora = st.time_input("⏰ Insira o horário da prova:", value=st.session_state.get("hora_prova", time(12, 0)))
                nome_cavalo = st.text_input("🐴 Nome do Cavalo")
            
            with col2:
                odds = st.number_input("📊 Odds", min_value=1.0, step=0.01, value=2.0)
                valor_apostado = st.number_input("💰 Valor Apostado", min_value=1.0, step=0.1, value=10.0)
                lucro = st.number_input("💰 Lucro", min_value=-10000.0, step=0.1, value=0.0)  # Usuário insere manualmente
                resultado = st.selectbox("🏆 Resultado", ["Vitória", "Derrota", "Pendente"])  # Usuário pode definir resultado
            
            if st.button("📌 Salvar Aposta"):
                if local and nome_cavalo and hora and odds and valor_apostado:
                    salvar_aposta(local, nome_cavalo, hora, odds, valor_apostado, lucro, resultado)
                else:
                    st.warning("⚠️ Preencha todos os campos antes de salvar!")
            
            st.divider()
            
            # ✅ Exibir tabela com apostas já registradas
            try:
                df_exibir = pd.read_excel(nome_arquivo)
                st.write("📊 **Apostas Registradas:**")
                st.dataframe(df_exibir)

                # ✅ Criar botão de download do arquivo
                with open(nome_arquivo, "rb") as f:
                    st.download_button(
                        label="⬇️ Baixar Apostas Registradas",
                        data=f,
                        file_name="apostas_registradas.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    
            except FileNotFoundError:
                st.info("ℹ️ Nenhuma aposta registrada ainda.")
                    
    except FileNotFoundError:
        st.error(f"❌ O arquivo '{nome_arquivo}' não foi encontrado.")

    except Exception as e:
        st.error(f"⚠️ Erro ao carregar ou processar os dados: {str(e)}")
