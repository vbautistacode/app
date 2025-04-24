import streamlit as st
import numpy as np
import requests
import json
import joblib
import os
import plotly.express as px
import plotly.graph_objects as go
import matplotlib.pyplot as plt
import logging
from datetime import datetime, timedelta
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder, StandardScaler, OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, precision_score, recall_score, f1_score
import pandas as pd
# Configurar Pandas para aceitar futuras mudanças no tratamento de objetos
pd.set_option('future.no_silent_downcasting', True)
# --- Funções para persistência ---
diretorio_base = r"https://raw.github.com/vbautistacode/app/main/"
def load_data():
    arquivos = ["horse_data.json", "team_data.json", "bet_data.json"]
    for arquivo in arquivos:
        url_arquivo = diretorio_base + arquivo
        try:
            response = requests.get(url_arquivo)
            response.raise_for_status()  # Verifica erros na requisição
# Carregar JSON corretamente
            st.session_state[arquivo.replace(".json", "")] = response.json()
        except requests.exceptions.RequestException:
            st.session_state[arquivo.replace(".json", "")] = []  # Retorna lista vazia se houver erro
# Inicializa os dados no session_state
if "horse_data" not in st.session_state:
    st.session_state["horse_data"] = []
if "team_data" not in st.session_state:
    st.session_state["team_data"] = []
if not st.session_state.get("initialized", False):
    load_data()
    st.session_state["initialized"] = True
if 'Nome ' not in st.session_state:
    st.session_state['Nom'] = "Cavalo_Default"  # Nome padrão ou escolha inicial
# --- Funções de cálculo ---
def kelly_criterion(b, implied_probability):
    kelly_fraction = (b * implied_probability - ((1 - implied_probability)) / b)
    return max(0, kelly_fraction)
    b = odds - 1
def calculate_dutching(odds, bankroll):
# Calcula as probabilidades implícitas com base nas odds fornecidas
    implied_probabilities = [1 / odd for odd in odds]
    total_probability = sum(implied_probabilities)
# Normaliza as probabilidades se a soma delas exceder 1
    if total_probability > 1:
        implied_probabilities = [p / total_probability for p in implied_probabilities]
# Usa o valor do bankroll como o total a ser investido
    return [bankroll * p for p in implied_probabilities]
# --- Interface Streamlit ---
st.title("Apostas | Dados & Estratégias")
# Abas para organização
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(["Locais", "Dados dos Cavalos", "Dados das Equipes", "Análises","Predições","Controle de Apostas", "Machine Learning"])

# --- Aba 1: Escolha ou Registro do Local de Prova ---
with tab1:
    st.subheader("Escolha ou Registre o Local de Prova")
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
# Salvar o local selecionado no `session_state`
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
    going_conditions = [
        "Firm", "Good to Firm", "Good", "Good to Soft", "Soft", "Heavy", 
        "Yielding", "Standard", "Slow", "All-Weather"
    ] 
# Dropdown para selecionar um tipo de pista
    tipo_pista = st.selectbox("Escolha o tipo de pista (Going):", going_conditions, key="select_going_1")
# Salvar o tipo de pista selecionado no `session_state`
    st.session_state["tipo_pista_atual"] = tipo_pista
    st.session_state["going_conditions"] = going_conditions
# Inserir a distância e salvar
    distance = st.number_input("Distância da Pista", min_value=0.00, step=0.01)
    st.session_state["distance"] = distance

# --- Aba 2: Dados dos Cavalos ---
with tab2:
    st.subheader("Informações Técnicas de Cavalos")
# Check if a location was selected in the previous tab
    if "local_atual" in st.session_state and st.session_state["local_atual"]:
        st.write(f"Registrando para o local: **{st.session_state['local_atual']}**")
    if "horse_data" not in st.session_state:
        st.session_state["horse_data"] = []
# Button to start horse registration
    if st.button("Cadastro de Dados dos Cavalos"):
        st.session_state["horse_data_started"] = True
    if st.session_state.get("horse_data_started", False):
# Dropdown to select or add a new horse
        if st.session_state["horse_data"]:
            cavalo_selecionado = st.selectbox(
            "Selecione o Cavalo para Editar ou Adicionar Novo",
            ["Adicionar Novo"] + [horse["Nome"] for horse in st.session_state["horse_data"]],
            key="select_horse_edit"
        )
        if cavalo_selecionado == "Adicionar Novo":
            cavalo_dados = None
        else:
            cavalo_dados = next(
                (horse for horse in st.session_state["horse_data"] if horse["Nome"] == cavalo_selecionado),
                None
            )
    else:
# st.warning("Ainda não há cavalos registrados. Preencha os dados para adicionar um novo cavalo.")
        cavalo_selecionado = "Adicionar Novo"
        cavalo_dados = None
# Divisão em duas colunas
        col1, col2 = st.columns(2)
# Campos na primeira coluna
        with col1:
# Form for horse details
            if "local_atual" in st.session_state:
                local_atual = st.session_state["local_atual"]
                Nome  = st.text_input("Nome do Cavalo", cavalo_dados["Nome"] if cavalo_dados else "")
                idade = st.number_input("Idade", min_value=0, max_value=30, step=1, value=cavalo_dados["Idade"] if cavalo_dados else 0)
                runs = st.number_input("Runs (Corridas)", min_value=0, step=1, value=cavalo_dados["Runs"] if cavalo_dados else 0)
                wins = st.number_input("Wins (Vitórias)", min_value=0, step=1, value=cavalo_dados["Wins"] if cavalo_dados else 0)
                seconds = st.number_input("2nds (Segundos Lugares)", min_value=0, step=1, value=cavalo_dados["2nds"] if cavalo_dados else 0)
                thirds = st.number_input("3rds (Terceiros Lugares)", min_value=0, step=1, value=cavalo_dados["3rds"] if cavalo_dados else 0)
        with col2:
                odds = st.number_input("Odds (Probabilidades)", min_value=0.01, step=0.01, value=cavalo_dados["Odds"] if cavalo_dados else 0.01)
# Processar: Calcular diferença em dias
# Entrada: data anterior
                data_anterior = st.date_input("Data Ultima Corrida", value=datetime.today().date())
# Processar: Converter 'data_anterior' para o mesmo tipo de 'data_atual'
                data_anterior = datetime.combine(data_anterior, datetime.min.time())  # Converte para datetime
                data_atual = datetime.now()  # Apenas data
# Calcular a diferença em dias (com precisão decimal)
                diferenca_dias = (data_atual - data_anterior).days
                if 'diferenca_dias' not in st.session_state:
                    st.session_state['diferenca_dias'] = diferenca_dias
                else:
                    st.session_state['diferenca_dias'] = diferenca_dias  # Atualiza o valor armazenado
                intervalo_corridas = st.number_input("Intervalo", min_value=0, step=1, value=diferenca_dias)
                Ranking = st.number_input("Ranking (Colocação)", min_value=0, step=0, value=cavalo_dados["Ranking"] if cavalo_dados else 0)
# Verificar se o tipo de pista foi armazenado no session_state
                if "going_conditions" in st.session_state:
# Usar o valor armazenado no session_state
                    going = st.selectbox("Going", st.session_state["going_conditions"], key="select_going_2")
                else:
                    going = st.selectbox("Going", ["Firm", "Good to Firm", "Good", "Good to Soft", "Soft", "Heavy", "Yielding", "Standard", "Slow", "All-Weather"])
                distancia = st.number_input("Distancia", min_value=0.00, step=0.00, value=cavalo_dados["Distancia"] if cavalo_dados else 0.00) 
# Button to save or add a new horse
                if st.button("Salvar Dados do Cavalo"):
                    if cavalo_selecionado == "Adicionar Novo":
                        novo_cavalo = {
                            "Local": local_atual,
                            "Nome": Nome ,
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
                        st.session_state["horse_data"].append(novo_cavalo)
                        st.success(f"Novo cavalo '{Nome}' adicionado com sucesso no local '{st.session_state['local_atual']}'!")
                    else:
                        for horse in st.session_state["horse_data"]:
                            if horse["Nome"] == cavalo_selecionado:
                                horse.update({
                                    "Local": local_atual,
                                    "Nome": Nome ,
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
                                })
                                st.success(f"Alterações no cavalo '{Nome }' salvas com sucesso!")
# Display registered horses
    if st.session_state["horse_data"]:
            st.write("### Cavalos Registrados")
            df_horses = pd.DataFrame(st.session_state["horse_data"])
            st.dataframe(df_horses)
# Função para salvar os dados em um arquivo .csv
    def salvar_csv(dataframe, nome_arquivo):
            try:
                dataframe.to_csv(nome_arquivo, index=False, encoding='utf-8')
                st.success(f"Arquivo '{nome_arquivo}' salvo com sucesso!")
            except Exception as e:
                st.error(f"Erro ao salvar o arquivo: {e}")
# Botão para salvar em CSV
    if st.button("Salvar em CSV", key="unique_key_1"):
                salvar_csv(df_horses, 'https://raw.githubusercontent.com/vbautistacode/app/main/dados_corridas.csv')
    else:
        st.warning("Ainda não há cavalos registrados.")

# --- Aba 3: Dados das Equipes ---
with tab3:
    st.subheader("Informações Técnicas de Equipes")
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
# Exibir equipes já cadastradas
    if st.session_state["team_data"]:
        st.write("### Equipes Cadastradas")
        df_teams = pd.DataFrame(st.session_state["team_data"])
        st.dataframe(df_teams)
# Função para salvar os dados em um arquivo .csv
        def salvar_csv(dataframe, nome_arquivo):
            try:
                dataframe.to_csv(nome_arquivo, index=False, encoding='utf-8')
                st.success(f"Arquivo '{nome_arquivo}' salvo com sucesso!")
            except Exception as e:
                st.error(f"Erro ao salvar o arquivo: {e}")
# Botão para salvar em CSV
    if st.button("Salvar em CSV", key="unique_key_2"):
            salvar_csv(df_teams, 'https://raw.githubusercontent.com/vbautistacode/app/main/dados_equipe.csv')
    else:
        st.warning("Ainda não há equipes cadastradas.")

# --- Aba 4: Resultados ---
with tab4:
#4.0. Dutching e Kelly
    st.write("### Dutching e Kelly Criterion")
    if st.session_state["horse_data"]:
        df_cavalos = pd.DataFrame(st.session_state["horse_data"])
        bankroll = st.number_input("Digite o valor do Bankroll", min_value=1.00, step=1.0)
        if "Odds" in df_cavalos.columns and not df_cavalos["Odds"].isnull().all():
            df_cavalos["Probability"] = (1 / df_cavalos["Odds"]).round(2)
            df_cavalos["Dutching Bet"] = calculate_dutching(df_cavalos["Odds"], bankroll)
            df_cavalos["Dutching Bet"] = df_cavalos["Dutching Bet"].round(2)
            if bankroll > 0:
                df_cavalos["Kelly Bet"] = df_cavalos.apply(
                    lambda row: round(kelly_criterion(bankroll, row["Probability"]), 2), axis=1
                )
                df_cavalos["Lucro KB"] = round(df_cavalos["Odds"] * df_cavalos["Kelly Bet"], 2)
                df_cavalos["Lucro DB"] = round(df_cavalos["Odds"] * df_cavalos["Dutching Bet"], 2)
                df_cavalos["ROI (%)"] = round((df_cavalos["Lucro DB"] / df_cavalos["Dutching Bet"]) * 100, 2)
# Exibir a tabela no Streamlit com os dados formatados
                st.dataframe(df_cavalos[["Nome", "Odds", "Probability", "Kelly Bet", "Dutching Bet", "Lucro KB", "Lucro DB", "ROI (%)"]])
# Cálculo do somatório da coluna "Dutching Bet"
                total_dutching = round(df_cavalos["Dutching Bet"].sum(), 2)
#4.1.Análise de Performance (Pódio H,J&T) - Garantir controle único
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
# 4.1.1. Melhor Equipe com Base na Performance
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
# Encontrar a melhor equipe (primeira linha após a ordenação)
            melhor_equipe = df_desempenho.iloc[0]
# Exibir resultados
            st.write(f"🏆 **Melhor Equipe:** {melhor_equipe['Nome da Equipe']} com Desempenho Médio de {melhor_equipe['Desempenho Médio Ajustado']:.2f}")
            st.write("### Ranking de Equipes por Performance")
            st.dataframe(df_desempenho)
        else:
            st.warning("Dados de equipe indisponíveis para análise.")
#4.2 Métricas Financeiras
with tab4:
    st.write("### Métricas Financeiras")
# Garantir que o estado de 'bet_data' e 'metrics' esteja inicializado
    if "bet_data" not in st.session_state:
        st.session_state["bet_data"] = []
    if "metrics" not in st.session_state:
        st.session_state["metrics"] = {
            "total_apostas": 0,
            "taxa_sucesso": 0,
            "odds_media": 0,
            "lucro_medio": 0,
            "lucro_total": 0,
        }
# Atualizar os dados ao adicionar uma nova aposta
    if len(st.session_state["bet_data"]) > 0:
# Criar DataFrame
        df_apostas = pd.DataFrame(st.session_state["bet_data"])
# Recalcular métricas
        total_apostas = len(df_apostas)
        apostas_vencedoras = len(df_apostas[df_apostas["Resultado"] == "Vitória"])
        taxa_sucesso = (apostas_vencedoras / total_apostas) * 100 if total_apostas > 0 else 0
        odds_media = df_apostas["Odds"].mean()
# Cálculo do lucro total
        lucro_total = (
            df_apostas.loc[df_apostas["Resultado"] == "Vitória", "Lucro"].sum()
            - df_apostas.loc[df_apostas["Resultado"] == "Derrota", "Valor Apostado"].sum()
        )
# Cálculo do lucro médio
        lucro_medio = lucro_total / total_apostas if total_apostas > 0 else 0
# Atualizar métricas em session_state
        st.session_state["metrics"] = {
            "total_apostas": total_apostas,
            "taxa_sucesso": taxa_sucesso,
            "odds_media": odds_media,
            "lucro_medio": lucro_medio,
            "lucro_total": lucro_total,
        }
# Exibir métricas
        st.write(f"🔢 **Total de Apostas:** {total_apostas}")
        st.write(f"✅ **Taxa de Sucesso:** {taxa_sucesso:.2f}%")
        st.write(f"📊 **Odds Média:** {odds_media:.2f}")
        st.write(f"💰 **Lucro Médio por Aposta:** R$ {lucro_medio:.2f}")
        st.write(f"💸 **Lucro Total:** R$ {lucro_total:.2f}")
    else:
        st.warning("Nenhuma aposta registrada para calcular as métricas.")
# Inicializar 'bankroll_data' caso não exista
    if "bankroll_data" not in st.session_state:
        st.markdown("💰 **Bankroll Inicial**: Insira o valor que será utilizado no controle das apostas.")
        bankroll_inicial = st.number_input("Valor do Bankroll", min_value=1.00, step=1.0, key="bankroll_input")
        st.session_state["bankroll_data"] = [{"Data": pd.Timestamp.now(), "Bankroll": bankroll_inicial}]
# Atualizar o bankroll com base nas apostas
    if len(st.session_state["bet_data"]) > 0:
        # Criar DataFrame de Apostas
        df_apostas = pd.DataFrame(st.session_state["bet_data"])
# Cálculo do Bankroll ajustado com base nas apostas
        bankroll_atual = st.session_state["bankroll_data"][-1]["Bankroll"]  # Último valor registrado no bankroll
        for _, aposta in df_apostas.iterrows():
            if aposta["Resultado"] == "Vitória":
# Adicionar lucro em caso de vitória
                bankroll_atual += aposta["Lucro"]
            elif aposta["Resultado"] == "Derrota":
# Subtrair valor apostado em caso de derrota
                bankroll_atual -= aposta["Valor Apostado"]
# Adicionar novo valor atualizado ao bankroll_data
        st.session_state["bankroll_data"].append({"Data": pd.Timestamp.now(), "Bankroll": bankroll_atual})
# 4.3 Métricas de Apostas
with tab4:
    st.subheader("Métrica de Apostas")
# Caminho do arquivo
    nome_arquivo = "https://raw.githubusercontent.com/vbautistacode/app/main/apostas_registradas.csv"
    try:
# Carregar os dados automaticamente da planilha
        df_cavalos = pd.read_csv(nome_arquivo)
# 4.3.1 Histórico de Performance Pessoal
        if {"Nome", "Lucro", "Valor Apostado", "Odds"}.issubset(df_cavalos.columns):
# Criar a coluna "Lucro Total" com a subtração de "Lucro" e "Valor Apostado"
            df_cavalos["Lucro Total"] = df_cavalos["Lucro"] - df_cavalos["Valor Apostado"]
# Agrupar por "Nome" e calcular os agregados
            performance_pessoal = df_cavalos.groupby("Nome").agg({
                "Lucro": "sum",
                "Valor Apostado": "sum",
                "Lucro Total": "sum",
                "Odds": "mean"
            }).rename(columns={
                "Lucro": "Ganhos",
                "Odds": "Odds Média"
            })
# Exibir a tabela no Streamlit
            st.write("##### Histórico de Performance Pessoal")
            st.dataframe(performance_pessoal)
        else:
            st.warning("As colunas 'Nome', 'Lucro', 'Valor Apostado' e 'Odds' são necessárias para calcular o Histórico de Performance Pessoal.")
#4.3.2 Índice de Recuperação
        if "Data" in df_cavalos.columns:
            df_cavalos["Data"] = pd.to_datetime(df_cavalos["Data"], errors='coerce')  # Garantir formato datetime
            df_cavalos["Intervalo (Dias)"] = df_cavalos["Data"].diff().dt.days
            st.write("##### Índice de Recuperação")
            st.write(f"📅 **Média do Intervalo Entre Corridas:** {df_cavalos['Intervalo (Dias)'].mean():.2f} dias")
        else:
            st.warning("A coluna 'Data' é necessária para calcular o Índice de Recuperação.")
    except FileNotFoundError:
        st.error(f"O arquivo '{nome_arquivo}' não foi encontrado. Certifique-se de que ele está na mesma pasta que o aplicativo.")
    except Exception as e:
        st.error(f"Erro ao carregar o arquivo: {str(e)}")
        
#4.4.Gráficos e Visuais
#4.4.1.Gráfico de barras - Lucro por cavalo
nome_arquivo = "https://raw.githubusercontent.com/vbautistacode/app/main/apostas_registradas.csv"
try:
    with tab4:
# Carregar os dados do arquivo
        df_cavalos = pd.read_csv(nome_arquivo)
# Verificar se as colunas necessárias estão disponíveis
        if {"Nome", "Lucro", "Valor Apostado"}.issubset(df_cavalos.columns):
# Calcular "Lucro Total"
            df_cavalos["Lucro Total"] = df_cavalos["Lucro"] - df_cavalos["Valor Apostado"]
# Agrupar por "Nome" e calcular os valores de "Lucro Total"
            lucro_por_cavalo = df_cavalos.groupby("Nome")["Lucro Total"].sum().reset_index()
# Gerar o gráfico de barras
            st.write("##### Gráficos")
            fig_bar = px.bar(
                lucro_por_cavalo,
                x="Nome",
                y="Lucro Total",
                title="Lucro Total por Cavalo",
                color="Lucro Total",
                text="Lucro Total",
                labels={"Nome": "Cavalo", "Lucro Total": "Lucro Total (R$)"}
            )
# Ajustar layout do gráfico
            fig_bar.update_traces(texttemplate='%{text:.2f}', textposition='outside')
            fig_bar.update_layout(
                uniformtext_minsize=8,
                uniformtext_mode='hide',
                xaxis_title="Cavalo",
                yaxis_title="Lucro Total (R$)",
                title_x=0.5  # Centralizar título
            )
# Exibir o gráfico
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.warning("As colunas 'Nome', 'Lucro' e 'Valor Apostado' são necessárias para gerar o gráfico.")
except FileNotFoundError:
    st.error(f"O arquivo '{nome_arquivo}' não foi encontrado. Certifique-se de que ele está na mesma pasta do aplicativo.")
except Exception as e:
    st.error(f"Erro ao carregar ou processar os dados: {str(e)}")
        
#4.4.2.Gráficos de Evolução do Bankroll: Monitorar o crescimento ou retração ao longo do tempo.
with tab4:    
    if st.session_state["bankroll_data"]:
        df_bankroll = pd.DataFrame(st.session_state["bankroll_data"])
        df_bankroll["Data"] = pd.to_datetime(df_bankroll["Data"])  # Garantir formato datetime
        st.write("#### Evolução do Bankroll")
        fig_line = px.line(
            df_bankroll,
            x="Data",
            y="Bankroll",
            title="Evolução do Bankroll ao Longo do Tempo",
            markers=True
        )
        st.plotly_chart(fig_line, use_container_width=True)
    else:
        st.warning("Dados insuficientes para gerar o gráfico de evolução do bankroll.")

# --- Aba 5: Análise de Probabilidades ---
with tab5:
# Configuração de logging
    logging.basicConfig(level=logging.INFO)
    caminho_corridas = "https://raw.githubusercontent.com/vbautistacode/app/main/dados_corridas.csv"
    df = pd.read_csv(caminho_corridas)
    print((df.head))
    try:
# Carregar os dados de corridas
        if not os.path.exists(caminho_corridas):
            st.error(f"O arquivo '{caminho_corridas}' não foi encontrado.")
        dados_corridas = pd.read_csv(caminho_corridas)
        if dados_corridas.empty:
            st.warning("O arquivo de corridas está vazio. Por favor, adicione os dados necessários.")
    except Exception as e:
        st.error(f"Erro ao carregar o arquivo: {e}")
# Funções utilitárias
def validar_caminho_arquivo(caminho_arquivo):
    try:
        diretorio = os.path.dirname(caminho_arquivo)
        if not os.path.exists(diretorio):
            os.makedirs(diretorio)
            logging.info(f"Diretório criado: {diretorio}")
        if not os.path.isfile(caminho_arquivo):
            logging.warning(f"Arquivo não encontrado: {caminho_arquivo}")
            return False
        return True
    except Exception as e:
        logging.error(f"Erro ao validar o caminho do arquivo: {e}")
        return False
def carregar_dados_csv(caminho_arquivo_1, caminho_arquivo_2):
    try:
        if not validar_caminho_arquivo(caminho_arquivo_1):
            st.error(f"Arquivo não encontrado ou inacessível: {caminho_arquivo_1}")
            return None, None
        if not validar_caminho_arquivo(caminho_arquivo_2):
            st.error(f"Arquivo não encontrado ou inacessível: {caminho_arquivo_2}")
            return None, None
        dados_1 = pd.read_csv(caminho_arquivo_1)
        dados_2 = pd.read_csv(caminho_arquivo_2)
        return dados_1, dados_2
    except Exception as e:
        st.error(f"Erro inesperado ao carregar os arquivos: {e}")
        logging.error(f"Erro ao carregar arquivos: {e}")
        return None, None
# Adicionar categorização do intervalo de descanso
    if 'Intervalo' in dados_corridas.columns:
        dados_corridas['Intervalo_Categoria'], dados_corridas['Intervalo_Peso'] = zip(*dados_corridas['Intervalo'].apply(categorizar_intervalo))
        logging.info("Categorização de intervalo aplicada com sucesso.")
    else:
        st.warning("A coluna 'Intervalo' está ausente em 'dados_corridas'. Não foi possível categorizar períodos de descanso.")
def categorizar_intervalo(intervalo):
#Função para categorizar o intervalo de descanso entre corridas
    if intervalo <= 7:
        return "Muito Curto", 9
    elif intervalo <= 14:
        return "Curto", 7
    elif intervalo <= 30:
        return "Médio", 5
    elif intervalo <= 60:
        return "Longo", 3
    else:
        return "Muito Longo", 1
def preprocessar_dados(dados_1, dados_2):
    try:
# Verificar se os dados estão carregados
        if dados_1.empty or dados_2.empty:
            st.error("Os arquivos `dados_1` ou `dados_2` estão vazios.")
            return None, None
# Codificação de colunas categóricas
        label_encoder = LabelEncoder()
        if 'Nome' in dados_1.columns:
            dados_1['Nome_encoded'] = label_encoder.fit_transform(dados_1['Nome'])
        if 'Going' in dados_1.columns:
# Atribuir pesos a 'Going'
            pesos_going = {
                "Firm": 3,
                "Good to Firm": 2,
                "Good": 1,
                "Good to Soft": 4,
                "Soft": 6,
                "Heavy": 9,
                "Yielding": 5,
                "Standard": 1,
                "Slow": 9,
                "All-Wether": 2,
            }
            dados_1['Going_encoded'] = dados_1['Going'].map(pesos_going).fillna(0)
        if 'Local' in dados_1.columns:
            dados_1['Local_encoded'] = label_encoder.fit_transform(dados_1['Local'])
        if 'Intervalo' in dados_1.columns:
            dados_1['Intervalo_Categoria'], dados_1['Intervalo_Peso'] = zip(*dados_1['Intervalo'].apply(categorizar_intervalo))
        else:
            st.warning("A coluna 'Intervalo' está ausente em `dados_1`. Não foi possível categorizar períodos de descanso.")
# Verificar colunas obrigatórias em dados_1
        colunas_features_1 = [
            'Local_encoded', 'Nome_encoded', 'Idade', 'Runs', 'Wins', '2nds', '3rds', 'Odds',
            'Intervalo', 'Intervalo_Peso', 'Going_encoded', 'Distancia']
        colunas_faltantes_1 = [col for col in colunas_features_1 if col not in dados_1.columns]
        if colunas_faltantes_1:
            st.error(f"Colunas ausentes no primeiro arquivo: {colunas_faltantes_1}")
            return None, None
# Verificar e adicionar colunas ausentes
        colunas_necessarias = ['Local_encoded', 'experiencia_jet', 'Previsao', 'Resultado_Oficial', 'Acerto']
        for coluna in colunas_necessarias:
            if coluna not in dados_corridas.columns:
                if coluna == 'Local_encoded':
                    dados_corridas[coluna] = 0
                elif coluna == 'experiencia_jet':
                    dados_corridas[coluna] = 0
                elif coluna == 'Previsao':
                    dados_corridas[coluna] = 0
                elif coluna == 'Resultado_Oficial':
                    dados_corridas[coluna] = 0
                elif coluna == 'Acerto':
                    dados_corridas[coluna] = 0
# Salvar em resultados_corridas.csv
        caminho_resultados = "https://raw.githubusercontent.com/vbautistacode/app/main/resultados_corridas.csv"
# if st.button("Salvar Resultados"):
        try:
            dados_corridas.to_csv(caminho_resultados, index=False)
# st.success(f"Arquivo salvo como '{caminho_resultados}' com sucesso!")
        except Exception as e:
            st.error(f"Erro ao salvar 'resultados_corridas': {e}")
# Lógica para calcular acertos
        if 'Previsao' in dados_corridas.columns and 'Resultado_Oficial' in dados_corridas.columns:
            dados_corridas['Acerto'] = (dados_corridas['Previsao'] == dados_corridas['Resultado_Oficial']).astype(int)
# Calcular desempenho do jóquei
        dados_2['desempenho_jockey'] = (
            dados_2['Jockey Wins'] + dados_2['Jockey 2nds'] + dados_2['Jockey 3rds']
        ) / dados_2['Jockey Rides'].replace(0, 1)
# Calcular desempenho do treinador
        dados_2['desempenho_trainer'] = (
            dados_2['Treinador Placed'] + dados_2['Treinador Wins']
        ) / dados_2['Treinador Runs'].replace(0, 1)
# Combinar dados para calcular experiência
        dados_2['experiencia_jet'] = dados_2['desempenho_jockey'] + dados_2['desempenho_trainer']
# Validar colunas para mapeamento
        if 'Nome' in dados_1.columns and 'Nome da Equipe' in dados_2.columns:
            dados_1['experiencia_jet'] = dados_1['Nome'].map(
                dados_2.set_index('Nome da Equipe')['experiencia_jet']
            )
        else:
            st.warning("A coluna 'Nome' em `dados_1` ou 'Nome da Equipe' em `dados_2` está ausente.")
            dados_1['experiencia_jet'] = 0  # Preencher com valor padrão
# Verificar valores mapeados
        dados_1['experiencia_jet'] = dados_1['experiencia_jet'].fillna(0)
# Substituir valores ausentes
        dados_1['experiencia_jet'] = dados_1['experiencia_jet'].fillna(0)
        dados_1['experiencia_jet'] = dados_1['experiencia_jet'].fillna(0)
# Preparar os dados para o modelo
        X = dados_1[colunas_features_1 + ['experiencia_jet']]
        y = dados_1['Wins']
        return X, y
    except Exception as e:
        st.error(f"Erro inesperado no preprocessamento: {e}")
        return None, None
def calcular_probabilidades_vencedor_e_exibir(dados):
    try:
        if dados.empty:
            st.error("O conjunto de dados está vazio. Não é possível calcular probabilidades.")
            st.stop()
        with tab5:
# Cálculos de probabilidade
            dados['desempenho_historico'] = (
                ((dados['Wins'] + dados['2nds'] + dados['3rds']) / (dados['Runs'] + 1e-6))
            )
            dados['probabilidade_vitoria'] = (((1 / dados['desempenho_historico'] + dados['experiencia_jet']) + (1 / dados['Odds']) * 0.15) * ((dados['Intervalo_Peso'] * 0.15) - (dados['Going_encoded'] * 0.15)))
# Normalizar as probabilidades
            prob_min = dados['probabilidade_vitoria'].min()
            prob_max = dados['probabilidade_vitoria'].max()
            if prob_max - prob_min == 0:
                st.error("Erro: As probabilidades calculadas são todas iguais.")
            else:
                num_cavalos = dados['Nome'].nunique()
                dados['probabilidade_vitoria_normalizada'] = (
                    ((dados['probabilidade_vitoria'] - prob_min) / (prob_max - prob_min)) * 100
                ) / num_cavalos
# Cavalo vencedor
            vencedor = dados.loc[dados['probabilidade_vitoria_normalizada'].idxmax(), 'Nome']
            prob_vencedor = dados['probabilidade_vitoria_normalizada'].max()
            st.success(f"O cavalo com maior probabilidade de vencer é *{vencedor}* com *{prob_vencedor:.2f}%* de chance!")
# Exibir gráfico
            st.write("##### Análise de Probabilidade Composta")
            plt.figure(figsize=(8, 6))
            plt.barh(dados['Nome'], dados['probabilidade_vitoria_normalizada'], color='lightgreen')
            plt.xlabel('Probabilidade de Vitória (%)')
            plt.ylabel('Cavalos')
            plt.grid(axis='x', linestyle='--', alpha=0.7)
            st.pyplot(plt)
# Exibir probabilidades em formato de tabela
            st.write("##### Probabilidades de Cada Cavalo")
            tabela_probabilidades = dados[['Nome', 'probabilidade_vitoria_normalizada']].sort_values(by='probabilidade_vitoria_normalizada', ascending=False)
            st.dataframe(tabela_probabilidades)
    except Exception as e:
            st.error(f"Erro ao calcular ou exibir as probabilidades: {e}")
def treinar_e_avaliar_modelo(X, y):
    try:
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
# Configurar pipeline
        preprocessor = ColumnTransformer(
            transformers=[
                ('num', StandardScaler(), ['Intervalo_Peso', 'Idade', 'Runs', 'Wins', '2nds', '3rds', 'Odds', 'Distancia','experiencia_jet']),
                ('cat', OneHotEncoder(handle_unknown='ignore'), ['Going_encoded'])
            ]
        )
        pipeline = Pipeline(steps=[
            ('preprocessor', preprocessor),
            ('modelo', RandomForestClassifier(random_state=42))
        ])
        pipeline.fit(X_train, y_train)
        y_pred = pipeline.predict(X_test)
        precisao = accuracy_score(y_test, y_pred)
        with tab5:
            st.write(f"Precisão do modelo: {precisao:.2f}")
        return pipeline
    except Exception as e:
        st.error(f"Erro ao treinar o modelo: {e}")
        return None
# Calculando o Índice de Valor Real
with tab5:
    try:
        dados = pd.read_csv("https://raw.githubusercontent.com/vbautistacode/app/main/dados_corridas.csv")
        if dados.empty:
            st.error("O arquivo 'dados_corridas.csv' está vazio. Verifique os dados de entrada.")
            st.stop()
    except FileNotFoundError:
        st.error("Arquivo 'dados_corridas.csv' não encontrado. Verifique o caminho do arquivo.")
        st.stop()
    def calcular_valor_real(dados):
        try:
            dados['valor_real'] = dados['Wins'] / (dados['Runs'] + 1e-6)  # Evita divisão por zero
            dados['oportunidade_aposta'] = dados['valor_real'] > (1 / dados['Odds'])
            melhores_oportunidades = dados.loc[dados['oportunidade_aposta'], ['Nome', 'valor_real', 'Odds']]
            melhores_oportunidades.rename(columns={'valor_real': 'Valor Real'}, inplace=True)
            return melhores_oportunidades
        except KeyError as e:
            st.error(f"Coluna ausente: {e}")
            return None
# Certifique-se de que 'dados' está carregado
    melhores_oportunidades = calcular_valor_real(dados)
    st.write("##### Melhores Oportunidades de Aposta")
    st.dataframe(melhores_oportunidades)
# Comparação de condições em mesmas pistas
def comparar_condicoes_corrida(dados_corridas):
    try:
# Recuperar as condições da corrida atual do session_state
        tipo_pista_atual = st.session_state.get("tipo_pista_atual", None)
        distancia_atual = st.session_state.get("distance", None)
        if tipo_pista_atual is None or distancia_atual is None:
            st.error("As condições da corrida atual não foram fornecidas.")
            return None
# Certificar-se de que as colunas necessárias existem antes de filtrar
        if 'Going' not in dados_corridas.columns or 'Distancia' not in dados_corridas.columns or 'Ranking' not in dados_corridas.columns:
            st.error("Colunas esperadas ('Going', 'Distancia', ou 'Ranking') estão ausentes em `dados_corridas`.")
            return None
# Filtrar corridas semelhantes com base no tipo de pista e distância
        corridas_filtradas = dados_corridas[
        (dados_corridas['Going'] == st.session_state.get('tipo_pista_atual', 'Default')) &
        (abs(dados_corridas['Distancia'] - st.session_state.get('distance', 0)) <= 100)
        ]
# Calcular o desempenho dos cavalos nessas condições
        desempenho_cavalo = corridas_filtradas.groupby('Nome')['Ranking'].apply(
            lambda x: (x <= 3).sum() / len(x) if len(x) > 0 else 0  # Taxa de pódio
        ).reset_index()
        desempenho_cavalo.columns = ['Nome', 'Desempenho em Condições Semelhantes']
        return desempenho_cavalo
    except Exception as e:
        st.error(f"Erro ao comparar condições da corrida: {e}")
        return None
def calcular_probabilidade_vitoria(dados, tipo_pista_atual, distancia_atual):
    try:
# Verificar se as colunas necessárias estão presentes
        colunas_necessarias = ['Going', 'Distancia', 'Nome', 'Ranking']
        for coluna in colunas_necessarias:
            if coluna not in dados.columns:
                st.error(f"A coluna '{coluna}' está ausente em `dados`.")
                return None
# Filtrar corridas em condições semelhantes
        corridas_filtradas = dados[
            (dados['Going'] == tipo_pista_atual) &
            (abs(dados['Distancia'] - distancia_atual) <= 100)  # Tolerância de 100m
        ]
# Verificar se houve resultados na filtragem
        if corridas_filtradas.empty:
            st.warning("Nenhuma corrida em condições semelhantes foi encontrada.")
            return None
# Calcular probabilidade com base no ranking (pódio: 1º, 2º ou 3º lugar)
        desempenho_cavalo = corridas_filtradas.groupby('Nome')['Ranking'].apply(
            lambda x: (x <= 3).sum() / len(x) if len(x) > 0 else 0
        ).reset_index()
        desempenho_cavalo.columns = ['Nome', 'Probabilidade de Vitória']
        return desempenho_cavalo
    except Exception as e:
        st.error(f"Erro ao calcular probabilidade de vitória: {e}")
        return None
def calcular_boa_aposta(dados):
    try:
# Verificar se as colunas necessárias estão presentes
        colunas_necessarias = ['Wins', 'Runs', 'Odds', 'Going', 'Distancia', 'Nome']
        for coluna in colunas_necessarias:
            if coluna not in dados.columns:
                st.error(f"A coluna '{coluna}' está ausente em `dados`.")
                return None
# Calcular 'valor_real' baseado na probabilidade de vitória
        dados['valor_real'] = dados['Wins'] / (dados['Runs'].replace(0, 1))  # Evita divisão por zero
# Identificar as melhores oportunidades de aposta
        dados['oportunidade_aposta'] = dados['valor_real'] > (1 / dados['Odds'])
        boas_oportunidades = dados.loc[dados['oportunidade_aposta'], ['Nome', 'valor_real', 'Odds', 'Going', 'Distancia']]
# Exibir mensagem caso nenhuma oportunidade seja encontrada
        if boas_oportunidades.empty:
            st.warning("Nenhuma oportunidade de aposta foi encontrada.")
            return None
        return boas_oportunidades
    except Exception as e:
        st.error(f"Erro ao calcular boas apostas: {e}")
        return None
def main():
# Configuração inicial dos caminhos dos arquivos
    caminho_corridas = "https://raw.githubusercontent.com/vbautistacode/app/main/dados_corridas.csv"
    caminho_equipes = "https://raw.githubusercontent.com/vbautistacode/app/main/dados_equipe.csv"
    caminho_resultados = "https://raw.githubusercontent.com/vbautistacode/app/main/resultados_corridas.csv"
    with tab5:  # Exibe os resultados na aba específica
        try:
# Carregar os dados necessários
            dados_corridas = pd.read_csv(caminho_corridas)
            dados_resultados = pd.read_csv(caminho_resultados)
# Verificar condições de corrida atual no session_state
            tipo_pista_atual = st.session_state.get("tipo_pista_atual", None)
            distancia_atual = st.session_state.get("distance", None)
            if tipo_pista_atual is None or distancia_atual is None:
                st.error("As condições da corrida atual (tipo de pista e distância) não foram definidas. Configure-as na Aba 1.")
                return
# 1. Comparar condições de corrida com histórico de corridas
            desempenho_comparativo = comparar_condicoes_corrida(dados_corridas)
            if desempenho_comparativo is not None:
                st.write("##### Desempenho dos Cavalos em Condições Semelhantes")
                st.dataframe(desempenho_comparativo)
# 2. Carregar dados adicionais e processá-los
            dados_1, dados_2 = carregar_dados_csv(caminho_corridas, caminho_equipes)
            if dados_1 is not None and dados_2 is not None:
# Pré-processar os dados
                X, y = preprocessar_dados(dados_1, dados_2)
                if X is not None and y is not None:
# Treinar e avaliar o modelo
                    modelo = treinar_e_avaliar_modelo(X, y)
                    if modelo:
# Calcular probabilidades de vitória com base no modelo treinado
                        calcular_probabilidades_vencedor_e_exibir(dados_1)
# 3. Gerar insights de valor real e boas oportunidades de aposta
            boas_oportunidades = calcular_boa_aposta(dados_resultados)
            if boas_oportunidades is not None:
                st.write("##### Melhor Escolha")
                st.dataframe(boas_oportunidades)
        except FileNotFoundError as e:
            st.error(f"Erro: Arquivo necessário não encontrado ({e.filename}). Verifique os caminhos dos arquivos.")
        except Exception as e:
            st.error(f"Erro inesperado: {e}")
if __name__ == "__main__":
    main()

# --- Aba 6: Registro de Apostas ---
with tab6:
    st.subheader("Registro de Apostas")
    # Inicializar 'bet_data' e 'metrics' no estado global, se necessário
    if "bet_data" not in st.session_state:
        st.session_state["bet_data"] = []
    if "metrics" not in st.session_state:
        st.session_state["metrics"] = {
            "total_apostas": 0,
            "taxa_sucesso": 0,
            "odds_media": 0,
            "lucro_medio": 0
        }
    if "bankroll_data" not in st.session_state:
        st.session_state["bankroll_data"] = []
# Verificar se há dados de cavalos registrados
    if "horse_data" in st.session_state and st.session_state["horse_data"]:
        df_cavalos = pd.DataFrame(st.session_state["horse_data"])
# Selectbox para selecionar o cavalo
        nome = st.selectbox(
            "Escolha o Cavalo",
            df_cavalos["Nome"]
        )
# Atualizar as odds conforme o cavalo selecionado
        odds_selecionadas = df_cavalos.loc[
            df_cavalos["Nome"] == nome, "Odds"
        ].values[0]
        st.write(f"**Odds do Cavalo Selecionado:** {odds_selecionadas:.2f}")
# Recuperar local ou usar padrão
        local = st.session_state.get("local_atual", "Não definido")
# Formulário para registrar nova aposta
        with st.form("form_aposta"):
            valor_apostado = st.number_input(
                "Valor Apostado", min_value=1.0, step=1.0)
            resultado = st.selectbox("Resultado", ["Vitória", "Derrota"])
            lucro = st.number_input("Lucro", min_value=0.0, step=1.0)
            data = st.date_input("Data da Aposta")
            hora = st.time_input("Hora da Corrida")
# tipo = st.text_input("Tipo de Pista")
            submit_button = st.form_submit_button("Registrar Aposta")
        if submit_button:
# Criar a nova aposta
            nova_aposta = {
                "Local": local,
                "Nome": nome,
                "Odds": odds_selecionadas,
                "Valor Apostado": valor_apostado,
                "Resultado": resultado,
                "Lucro": lucro,
                "Data": data,
                "Hora": hora,
# "Tipo de Pista": tipo,
            }
            st.session_state["bet_data"].append(nova_aposta)
            st.success("Aposta registrada com sucesso!")
# Salvar aposta em um arquivo Excel
            file_path = "https://raw.githubusercontent.com/vbautistacode/app/main/apostas_registradas.csv"
            if os.path.exists(file_path):
# Ler os dados existentes
                df_existente = pd.read_csv(file_path)
                df_nova_aposta = pd.DataFrame([nova_aposta])
                df_final = pd.concat(
                    [df_existente, df_nova_aposta], ignore_index=True
                )
            else:
# Criar novo DataFrame se o arquivo não existir
                df_final = pd.DataFrame([nova_aposta])
# Salvar no arquivo .xlsx
            df_final.to_excel(file_path, index=False)
            st.success(f"As informações foram salvas em '{file_path}'!")
    else:
        st.warning(
            "Nenhum dado de cavalos registrado. Cadastre os cavalos na aba Dados dos Cavalos antes de realizar apostas."
        )
# Garantir que há apostas antes de calcular as métricas
    if st.session_state["bet_data"]:
# Criar DataFrame a partir das apostas registradas
        df_apostas = pd.DataFrame(st.session_state["bet_data"])
# Calcular métricas de apostas
        total_apostas = len(df_apostas)
        apostas_vencedoras = len(
            df_apostas[df_apostas["Resultado"] == "Vitória"])
        taxa_sucesso = (
            (apostas_vencedoras / total_apostas) * 100
            if total_apostas > 0
            else 0
        )
        odds_media = df_apostas["Odds"].mean() if total_apostas > 0 else 0
        lucro_medio = df_apostas["Lucro"].mean() if total_apostas > 0 else 0
# Salvar as métricas calculadas em 'metrics'
        st.session_state["metrics"] = {
            "total_apostas": total_apostas,
            "taxa_sucesso": taxa_sucesso,
            "odds_media": odds_media,
            "lucro_medio": lucro_medio,
        }
# Exibir apostas registradas
        st.write("### Apostas Realizadas")
        st.dataframe(df_apostas)
    else:
        st.info("Nenhuma aposta registrada ainda.")

# #---Aba 7: Machine Learning ---
# Configuração de logging
logging.basicConfig(level=logging.INFO)
# Função para integrar o histórico ao conjunto de dados de corridas
with tab7:
    def integrar_retroalimentacao(dados_corridas, historico):
        try:
    # Carregar resultados_corridas na tab7
            caminho_resultados = "https://raw.githubusercontent.com/vbautistacode/app/main/resultados_corridas.csv"
            dados_resultados = pd.read_csv(caminho_resultados)
            colunas_esperadas = ['Nome', 'Resultado_Oficial']
            colunas_faltantes = [col for col in colunas_esperadas if col not in dados_resultados.columns]
            if colunas_faltantes:
                st.error(f"Colunas faltantes em 'resultados_corridas': {colunas_faltantes}")
            else:
                st.success("Arquivo carregado corretamente com todas as colunas presentes!")
                return dados_corridas
    # Merge do histórico com os dados de corridas
            dados_corridas = pd.merge(
                dados_corridas,
                historico[['Nome', 'Resultado_Oficial']],
                on="Nome",
                how="left"
            )
            if dados_corridas.empty:
                st.error("O conjunto de dados ficou vazio após o merge. Verifique os valores no arquivo histórico.")
                logging.error("Erro: o conjunto de dados ficou vazio após o merge.")
                return dados_corridas
    # Criar coluna `Acerto` para validar previsões
            if 'Previsao' in dados_corridas.columns:
                dados_corridas['Acerto'] = (dados_corridas['Previsao'] == dados_corridas['Resultado_Oficial']).astype(int)
            else:
                st.warning("A coluna 'Previsao' não está presente em `dados_corridas`. Não foi possível calcular acertos.")
                logging.warning("A coluna 'Previsao' está ausente em `dados_corridas`.")
            return dados_corridas
        except Exception as e:
            st.error(f"Erro ao integrar retroalimentação: {e}")
            logging.error(f"Erro ao integrar retroalimentação: {e}")
            return dados_corridas
    # Função para treinar o modelo e calcular métricas
    def treinar_e_calcular_metricas(X, y, tab7):
        try:
    # Validar os dados antes de prosseguir
                if X.isnull().values.any() or y.isnull().values.any():
                    st.error("Os dados contêm valores nulos. Preprocessamento necessário antes do treinamento.")
                    logging.error("Valores nulos detectados em `X` ou `y`.")
                    return None, None
    # Divisão dos dados em treino e teste
                X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
                logging.info("Divisão dos dados concluída.")
    # Configuração do pipeline de pré-processamento e modelo
                preprocessor = ColumnTransformer(
                    transformers=[
                        ('num', StandardScaler(), [
                            'Local_encoded', 'Intervalo', 'Nome', 'Idade', 'Runs', 'Wins', 'Odds', 'Distancia', 'experiencia_jet'
                        ]),
                        ('cat', OneHotEncoder(handle_unknown='ignore'), ['Going_encoded'])
                    ])
                pipeline = Pipeline(steps=[
                    ('preprocessor', preprocessor),
                    ('modelo', RandomForestClassifier(random_state=42))
                ])
                logging.info("Pipeline configurado.")
    # Treinamento do modelo
                pipeline.fit(X_train, y_train)
                logging.info("Modelo treinado com sucesso.")
    # Predição e cálculo de métricas
                y_pred = pipeline.predict(X_test)
                precision = precision_score(y_test, y_pred, average='weighted')
                recall = recall_score(y_test, y_pred, average='weighted')
                precisao = accuracy_score(y_test, y_pred)
                f1 = f1_score(y_test, y_pred, average='weighted')
    # Exibir métricas na aba
                st.write("#### Métricas de Desempenho do Modelo")
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric(label="Acurácia (Accuracy)", value=f"{precisao:.2f}")
                with col2:
                    st.metric(label="Recall", value=f"{recall:.2f}")
                with col3:
                    st.metric(label="Precisão (Precision)", value=f"{precision:.2f}")
                with col4:
                    st.metric(label="F1-Score", value=f"{f1:.2f}")
    # Exibir relatório detalhado
                try:
                    report = classification_report(y_test, y_pred, output_dict=True)
                    report_df = pd.DataFrame(report).transpose()
                    st.write("#### Relatório de Classificação")
                    st.dataframe(report_df)
                except Exception as e:
                    st.error("Erro ao gerar relatório detalhado.")
                    logging.error(f"Erro ao gerar relatório: {e}")
                    report_df = None
                return pipeline, report_df
        except Exception as e:
            st.error(f"Erro ao calcular métricas ou treinar o modelo: {e}")
            logging.error(f"Erro ao calcular métricas ou treinar o modelo: {e}")
            return None, None
    # Função principal para retroalimentação e acompanhamento
    def retroalimentacao_e_historico(X, y, tab7):
            try:
    # Caminhos para os arquivos de dados
                caminho_resultados = "https://raw.githubusercontent.com/vbautistacode/app/main/resultados_corridas.csv"
                caminho_historico = "https://raw.githubusercontent.com/vbautistacode/app/main/historico_modelo.csv"
    # Verificar se o arquivo existe e carregar os dados
                if os.path.exists(caminho_historico):
                    historico_existente = pd.read_csv(caminho_historico)
                else:
                    historico_existente = pd.DataFrame(columns=dados_corridas.columns)  # Criar histórico vazio com as mesmas colunas
    # Carregar os dados de resultados
                dados_corridas = pd.read_csv(caminho_resultados)
    # Verificar se a coluna 'Nome' existe em dados_corridas
                if 'Nome' not in dados_corridas.columns:
                    st.error("A coluna 'Nome' não está presente em 'dados_corridas'. Verifique os dados de entrada.")
                    return
                if dados_corridas.empty:
                    st.error("O arquivo 'dados_corridas' está vazio. Nenhum dado disponível para processar.")
                    return
    # Obter os nomes já cadastrados dos cavalos
                cavalos_cadastrados = dados_corridas['Nome'].unique()
    # Entradas do usuário - selecionar cavalo previsto e vencedor oficial
                previsao = st.selectbox("Escolha o cavalo previsto como vencedor:", cavalos_cadastrados, help="Selecione o cavalo que você acredita ser o vencedor.")
                resultado_oficial = st.selectbox("Escolha o cavalo vencedor oficial:", cavalos_cadastrados, help="Selecione o cavalo que venceu oficialmente a corrida.")
                acerto_manual = st.selectbox("A previsão foi correta?", ["Sim", "Não"], help="Indique se a previsão estava correta com base nos resultados oficiais.")
    # Definir filtro para previsão
                filtro_previsao = dados_corridas['Nome'] == previsao
    # Atualizar os resultados com as seleções do usuário
                if filtro_previsao.any():
                    dados_corridas.loc[filtro_previsao, 'Previsao'] = previsao
                    logging.info(f"Atualização feita: Previsão - {previsao}")
                else:
                    st.warning(f"Nenhum registro encontrado para o cavalo previsto '{previsao}'.")
    # Definir filtro para resultado oficial
                filtro_resultado = dados_corridas['Nome'] == resultado_oficial
    # Atualizar os resultados com as seleções do usuário
                if filtro_resultado.any():
                    dados_corridas.loc[filtro_resultado, 'Resultado_Oficial'] = resultado_oficial
                    logging.info(f"Atualização feita: Resultado Oficial - {resultado_oficial}")
                else:
                    st.warning(f"Nenhum registro encontrado para o cavalo vencedor '{resultado_oficial}'.")
                dados_corridas['Acerto'] = 1 if acerto_manual == "Sim" else 0
    # Criar um botão para salvar os resultados
                if st.button("Confirmar Atualização do Histórico"):
                    try:
    # Validar antes de salvar
                        if dados_corridas.empty:
                            st.error("O DataFrame está vazio. Não há nada para salvar.")
                            return
                        dados_corridas.to_csv(caminho_resultados, index=False)
                        st.success("Resultados atualizados com sucesso!")
                        logging.info(f"Resultados salvos no arquivo: {caminho_resultados}")
                    except Exception as e:
                        st.error(f"Erro ao salvar os resultados: {e}")
                        logging.error(f"Erro ao salvar os resultados: {e}")
    # Criar o histórico com todas as colunas de resultados_corridas
                colunas_necessarias = dados_corridas.columns  # Pega todas as colunas existentes
                historico = pd.DataFrame(columns=colunas_necessarias)
    # Adicionar os valores do usuário
                historico.loc[0] = dados_corridas.iloc[0]  # Adiciona uma linha baseada no DataFrame original
                historico.at[0, 'Nome'] = st.session_state.get('Nome')
                historico.at[0, 'Previsao'] = previsao
                historico.at[0, 'Resultado Oficial'] = resultado_oficial
                historico.at[0, 'Acerto'] = 1 if acerto_manual == "Sim" else 0
    # Preencher valores ausentes para evitar colunas em branco
                historico.fillna("None", inplace=True)
    # Garantir que todas as colunas estão presentes no histórico
                colunas_faltantes = [col for col in colunas_necessarias if col not in historico_existente.columns]
                for coluna in colunas_faltantes:
                    historico_existente[coluna] = "None"
    # Concatenar o novo histórico com o existente
                historico_atualizado = pd.concat([historico_existente, historico], ignore_index=True)
    # Remover duplicatas para evitar repetições e salvar no arquivo
                historico_atualizado.drop_duplicates(subset=['Nome', 'Previsao'], keep='last', inplace=True)
                historico_atualizado.to_csv(caminho_historico, index=False)
                st.success("Histórico atualizado e salvo com sucesso!")
    # Integrar histórico aos dados de corridas
                dados_corridas = integrar_retroalimentacao(dados_corridas, historico)
            except Exception as e:
                st.error(f"Erro ao carregar ou atualizar resultados: {e}")
    # Função para preprocessamento
    def preprocessar_dados(dados_1, dados_2):
        try:
    # Validar arquivos vazios
            if dados_1.empty:
                st.error("O arquivo de corridas está vazio. Adicione dados antes de prosseguir.")
                logging.error("O arquivo 'dados_corridas.csv' está vazio.")
                return None, None
            if dados_2.empty:
                st.error("O arquivo de equipes está vazio. Adicione dados antes de prosseguir.")
                logging.error("O arquivo 'dados_equipe.csv' está vazio.")
                return None, None
    # Codificação da coluna 'Nome'
            label_encoder = LabelEncoder()
            if 'Nome' in dados_1.columns:
                dados_1['Nome_encoded'] = label_encoder.fit_transform(dados_1['Nome'])
                logging.info("Codificação da coluna 'Nome' concluída.")
            else:
                st.error("A coluna 'Nome' está ausente no arquivo de corridas.")
                logging.error("A coluna 'Nome' está ausente no arquivo de corridas.")
                return None, None
    # Codificação da coluna 'Going'
            if 'Going' in dados_1.columns:
                pesos_going = {
                    "Firm": 3, "Good to Firm": 2, "Good": 1, "Good to Soft": 4,
                    "Soft": 6, "Heavy": 9, "Yielding": 5, "Standard": 1, "Slow": 9,
                    "All-Wether": 2
                }
                dados_1['Going_encoded'] = dados_1['Going'].map(pesos_going).fillna(0)
                logging.info("Codificação da coluna 'Going' concluída.")
            else:
                st.error("A coluna 'Going' está ausente no arquivo de corridas.")
                logging.error("A coluna 'Going' está ausente no arquivo de corridas.")
                return None, None
    # Validar colunas esperadas
            colunas_features = ['Local', 'Nome_encoded', 'Idade', 'Runs', 'Wins', '2nds', '3rds', 'Odds',
                                'Intervalo', 'Ranking', 'Going_encoded', 'Distancia', 'experiencia_jet',
                                'Previsao', 'Resultado_Oficial', 'Acerto']
            colunas_faltantes = [col for col in colunas_features if col not in dados_1.columns]
            if colunas_faltantes:
                st.error(f"Colunas ausentes no arquivo de corridas: {colunas_faltantes}")
                logging.error(f"Colunas ausentes: {colunas_faltantes}")
                return None, None
    # Criar conjuntos X e y
            X = dados_1[colunas_features]
            y = dados_1['Ranking']
            logging.info("Preprocessamento concluído com sucesso.")
            return X, y
        except Exception as e:
            st.error(f"Erro no preprocessamento: {e}")
            logging.error(f"Erro no preprocessamento: {e}")
            return None, None
    # Função principal para execução do fluxo
    def main():
    # Caminhos para os arquivos de entrada
            caminho_corridas = "https://raw.githubusercontent.com/vbautistacode/app/main/resultados_corridas.csv"
            caminho_equipes = "https://raw.githubusercontent.com/vbautistacode/app/main/dados_equipe.csv"
            try:
    # Verificar se os arquivos existem
                if not os.path.exists(caminho_corridas):
                    st.error(f"O arquivo '{caminho_corridas}' não foi encontrado.")
                    logging.error(f"Arquivo não encontrado: {caminho_corridas}")
                    return
                if not os.path.exists(caminho_equipes):
                    st.error(f"O arquivo '{caminho_equipes}' não foi encontrado.")
                    logging.error(f"Arquivo não encontrado: {caminho_equipes}")
                    return
    # Carregar e preprocessar os dados
                dados_1 = pd.read_csv(caminho_corridas)
                dados_2 = pd.read_csv(caminho_equipes)
                X, y = preprocessar_dados(dados_1, dados_2)
                if X is None or y is None:
                    st.error("Erro no preprocessamento. Certifique-se de que os arquivos de dados estão corretos.")
                    logging.error("Erro no preprocessamento dos dados.")
                    return
                st.success("Preprocessamento concluído com sucesso!")
            except Exception as e:
                st.error(f"Erro ao carregar os arquivos: {e}")
                logging.error(f"Erro ao carregar os arquivos: {e}")
                return
    # Retroalimentação e métricas
            try:
                retroalimentacao_e_historico(X, y, tab7)
            except Exception as e:
                st.error(f"Erro na retroalimentação ou métricas: {e}")
                logging.error(f"Erro na retroalimentação ou métricas: {e}")
    if __name__ == "__main__":
        main()
