from datetime import datetime, timedelta
import streamlit as st
from fpdf import FPDF
import pandas as pd
import numpy as np
import requests
import logging
import joblib
import base64
import json
import os
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
if not st.session_state.get("initialized", False):
    load_data()
    st.session_state["initialized"] = True
if "Nome" not in st.session_state:
    st.session_state["Nome"] = "Cavalo_Default"  # Nome padrão ou escolha inicial
# --- Funções de cálculo ---
def calculate_dutching(odds, bankroll, historical_factor):
#Distribui aposta usando Dutching com ponderação das odds e ajuste histórico.
    probabilities = np.array([1 / odd for odd in odds])
    adjusted_probabilities = probabilities * historical_factor  # Ajusta conforme histórico dos cavalos
    total_probability = adjusted_probabilities.sum()
    if total_probability > 1:
        adjusted_probabilities /= total_probability  # Normaliza
    apostas = np.round(bankroll * adjusted_probabilities, 2)
    return apostas
def assess_risk(odds, performance_score):
#Ajusta aposta com base no risco: odds muito altas com baixo desempenho reduzem a alocação.
    risk_factor = np.where((odds > 5) & (performance_score < 0.2), 0.5, 1)  # Redução de 50% para alto risco
    return risk_factor
def rebalance_bets(df_cavalos, bankroll):
#Remove cavalos de baixo desempenho e distribui apostas com Dutching otimizado.
    df_cavalos["Probability"] = 1 / df_cavalos["Odds"]
    df_cavalos["Performance Score"] = (df_cavalos["Wins"] + df_cavalos["2nds"] + df_cavalos["3rds"]) / df_cavalos["Runs"]
    df_cavalos["Risk Factor"] = assess_risk(df_cavalos["Odds"], df_cavalos["Performance Score"])
    df_filtrado = df_cavalos[df_cavalos["Performance Score"] >= 0.15]  # Filtra cavalos fracos
    if df_filtrado.empty:
        st.warning("⚠️ Nenhum cavalo atende aos critérios de desempenho. Ajuste os parâmetros.")
        return df_cavalos
    df_filtrado["Dutching Bet"] = calculate_dutching(df_filtrado["Odds"], bankroll, df_filtrado["Risk Factor"])
    return df_filtrado
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
            odds = st.number_input("Odds (Probabilidades)", min_value=0.01, step=0.01, value=cavalo_dados["Odds"] if cavalo_dados else 0.01)
        with col2:
            # idade = st.number_input("Idade", min_value=0, max_value=30, step=1, value=cavalo_dados["Idade"] if cavalo_dados else 0)
            runs = st.number_input("Runs (Corridas)", min_value=0, step=1, value=cavalo_dados["Runs"] if cavalo_dados else 0)
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
#4.0. Dutching
    if "horse_data" in st.session_state and st.session_state["horse_data"]:
        df_cavalos = pd.DataFrame(st.session_state["horse_data"])
        bankroll = st.slider("Ajuste o valor do Bankroll", min_value=10.0, max_value=5000.0, step=10.0, value=100.0, key="bankroll_slider")
    else:
        st.warning("⚠️ Nenhum dado de cavalos disponível. Verifique as entradas e tente novamente.")
        df_cavalos = pd.DataFrame(columns=["Nome", "Odds", "Wins", "2nds", "3rds", "Runs"])
        df_cavalos["Odds"] = pd.to_numeric(df_cavalos["Odds"], errors="coerce")
        df_cavalos = df_cavalos.dropna(subset=["Odds"])
    if "Odds" in df_cavalos.columns and not df_cavalos["Odds"].isnull().all():
        df_cavalos["Probability"] = (1 / df_cavalos["Odds"]).round(2)
        df_cavalos["Dutching Bet"] = calculate_dutching(df_cavalos["Odds"].tolist(), bankroll)
        df_cavalos["Dutching Bet"] = df_cavalos["Dutching Bet"].round(2)
        df_cavalos["Lucro Dutch"] = round(df_cavalos["Odds"] * df_cavalos["Dutching Bet"], 2)
        df_cavalos["ROI-Dutch($)"] = round((df_cavalos["Lucro Dutch"] - df_cavalos["Dutching Bet"]), 2)
        df_cavalos["ROI (%)"] = round((df_cavalos["Lucro Dutch"] / df_cavalos["Dutching Bet"]) * 100, 2)
# Aplicar rebalanceamento das apostas
        df_cavalos_filtrado = rebalance_bets(df_cavalos, bankroll)
# Exibir tabela formatada no Streamlit
        st.dataframe(df_cavalos_filtrado[["Nome", "Odds", "Probability", "Dutching Bet", "Lucro Dutch", "ROI-Dutch($)", "ROI (%)"]])
# Cálculo do somatório da coluna "Dutching Bet"
        total_dutching = round(df_cavalos["Dutching Bet"].sum(), 2)
# --- Ajuste das apostas baseado na performance das equipes ---
        st.write("### Análise de Performance por Equipe")
    if "team_data" in st.session_state and st.session_state["team_data"]:
        equipe_selecionada = st.selectbox(
            "Selecione uma Equipe",
            [team["Nome da Equipe"] for team in st.session_state["team_data"]],
            key="selectbox_equipes"
        )
# Filtrar desempenho dos jóqueis e treinadores
        if equipe_selecionada:
            df_desempenho = []
            equipe_filtrada = [team for team in st.session_state["team_data"] if team["Nome da Equipe"] == equipe_selecionada]
            for team in equipe_filtrada:
                podiums_jockey = team.get("Jockey Wins", 0) + team.get("Jockey 2nds", 0) + team.get("Jockey 3rds", 0)
                rides_jockey = team.get("Jockey Rides", 1)
                performance_jockey = {
                    "Tipo": "Jóquei",
                    "Nome": team["Jockey"],
                    "Razão Pódios/Corridas":"{:.2f}".format((podiums_jockey / max(rides_jockey, 1)) * 100)
                }
                df_desempenho.append(performance_jockey)
                podiums_trainer = team.get("Treinador Placed", 0) + team.get("Treinador Wins", 1)
                runs_trainer = team.get("Treinador Runs", 1)
                performance_trainer = {
                    "Tipo": "Treinador",
                    "Nome": team["Treinador"],
                    "Razão Pódios/Corridas":"{:.2f}".format((podiums_trainer / max(runs_trainer, 1)) * 100)
                }
                df_desempenho.append(performance_trainer)
                if st.session_state["horse_data"]:
                    cavalos_filtrados = [
                        horse for horse in st.session_state["horse_data"] if horse.get("Nome") == equipe_selecionada
                    ]
                    for horse in cavalos_filtrados:
                        podiums_horse = horse["Wins"] + horse["2nds"] + horse["3rds"]
                        runs_horse = horse["Runs"]
                        performance_horse = {
                            "Tipo": "Cavalo",
                            "Nome": horse["Nome"],
                            "Razão Pódios/Corridas":"{:.2f}".format((podiums_horse / max(runs_horse, 1)) * 100)
                        }
                        df_desempenho.append(performance_horse)
            st.dataframe(pd.DataFrame(df_desempenho))
        else:
            st.warning(f"Nenhum dado encontrado para a equipe '{equipe_selecionada}'.")
# 4.1. Melhor Equipe com Base na Performance
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
# Ajustar o cálculo da média de desempenho para incluir variância
                desempenhos = [desempenho_horse, desempenho_jockey, desempenho_trainer]
                media_desempenho = sum(desempenhos) / len(desempenhos)
                variancia_desempenho = np.var(desempenhos)
                resultado_ajustado = media_desempenho - variancia_desempenho
# Média total de desempenho da equipe
                media_desempenho = (desempenho_jockey + desempenho_trainer + desempenho_horse) / 3
                df_desempenho.append({
                    "Nome da Equipe": team["Nome da Equipe"],
                    "Desempenho Médio Ajustado": round(resultado_ajustado, 2)
                })
# Converter para DataFrame
            df_desempenho = pd.DataFrame(df_desempenho)
# Ordenar DataFrame por Desempenho Médio em ordem decrescente
            df_desempenho = df_desempenho.sort_values(by="Desempenho Médio Ajustado", ascending=False)
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
# --- Simulação de Retornos Esperados ---
    def simulate_returns(df_cavalos, bankroll):
#Simula os possíveis retornos com base nos valores apostados e nas odds.
        resultados = []
        for _, row in df_cavalos.iterrows():
            cavalo = row["Nome"]
            odd = row["Odds"]
            dutching_bet = row["Dutching Bet"]
            lucro_dutching = (odd * dutching_bet) - bankroll
            resultados.append({
                "Cavalo": cavalo,
                "Odd": odd,
                "Dutching Bet": dutching_bet,
                "Lucro Dutching ($)": round(lucro_dutching, 2),
                "ROI Dutching (%)": round((lucro_dutching / bankroll) * 100, 2),
            })
        return pd.DataFrame(resultados)
    st.write("### Simulação de Retornos Esperados")
    if "horse_data" in st.session_state and st.session_state["horse_data"]:
        df_cavalos = pd.DataFrame(st.session_state["horse_data"])    
        bankroll = st.slider("Ajuste o valor do Bankroll", min_value=10.0, max_value=5000.0, step=10.0, value=100.0, key="bankroll_slider_simulacao")
        if "Odds" in df_cavalos.columns and not df_cavalos["Odds"].isnull().all():
            df_cavalos_filtrado = rebalance_bets(df_cavalos, bankroll)
# Executa a simulação
            df_simulacao = simulate_returns(df_cavalos_filtrado, bankroll)    
# Exibir os resultados na interface
            st.dataframe(df_simulacao)
# Função para gerar PDF
    def generate_pdf(locais_prova, df_cavalos, df_simulacao):
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        pdf.set_font("Arial", "B", 16)
        pdf.cell(200, 10, "Relatório de Apostas - Dutching", ln=True, align="C")
        pdf.set_font("Arial", "B", 12)
        pdf.cell(200, 10, f"Local da Prova: {locais_prova}", ln=True)
        pdf.cell(200, 10, "Detalhes das Apostas", ln=True)
        for _, row in df_cavalos.iterrows():
            pdf.set_font("Arial", "", 10)
            pdf.cell(200, 7, f"{row['Nome']} - Odds: {row['Odds']} - Bet: {row['Dutching Bet']}", ln=True)
        pdf.cell(200, 10, "Simulação de Retornos", ln=True)
        for _, row in df_simulacao.iterrows():
            pdf.set_font("Arial", "", 10)
            pdf.cell(200, 7, f"{row['Cavalo']} - ROI: {row['ROI Dutching (%)']}%", ln=True)
        pdf_filename = "relatorio_apostas.pdf"
        pdf.output(pdf_filename)
        return pdf_filename
# Botão para baixar o relatório com local da prova
    if st.button("Baixar Relatório em PDF"):
        pdf_file = generate_pdf(df_cavalos_filtrado, df_simulacao, local_prova)
        with open(pdf_file, "rb") as f:
            st.download_button(label="Clique aqui para baixar o PDF", data=f, file_name=pdf_file, mime="application/pdf")
