# --- Importações ---
from datetime import datetime, timedelta
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

# 🔹 Ajuste de odds removendo overround
def ajustar_odds(odds, overround_pct):
    return [odd / (1 + overround_pct) for odd in odds]

# 🔹 Cálculo da distribuição de apostas ajustadas considerando probabilidade real do favorito
def distribuir_apostas(df, total_aposta, incluir_desempenho):
    if incluir_desempenho:
        fator_ajuste = df["historico_vitoria"] / 100
    else:
        fator_ajuste = 1  # Sem ajuste se a análise de desempenho estiver desativada

    df["valor_apostado"] = np.round(total_aposta * (fator_ajuste / fator_ajuste.sum()), 2)
    return df

def calculate_dutching(odds, bankroll, historical_factor):
#Calcula a distribuição de apostas usando Dutching
    probabilities = np.array([1 / odd for odd in odds])
    adjusted_probabilities = probabilities * historical_factor
    total_probability = adjusted_probabilities.sum()
    adjusted_probabilities /= total_probability if total_probability > 1 else 1
    return np.round(bankroll * adjusted_probabilities, 2)

#Calcula o desempenho das equipes com ajuste de variância
def calcular_desempenho_equipes(team_data):
    if not team_data:
        st.warning("⚠️ Nenhum dado de equipe disponível.")
        return pd.DataFrame(columns=["Nome da Equipe", "Desempenho Médio Ajustado"])

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

        desempenhos = [desempenho_horse, desempenho_jockey, desempenho_trainer]
        
        # 🔹 Melhorando o cálculo com desvio padrão
        media_desempenho = np.mean(desempenhos)
        variancia_desempenho = np.var(desempenhos)
        desvio_padrao = np.std(desempenhos)

        # 🔹 Ajuste com ponderação do desvio padrão
        resultado_ajustado = media_desempenho - (0.5 * desvio_padrao)  # O peso 0.5 pode ser ajustado

        df_desempenho_lista.append({
            "Nome da Equipe": team["Nome da Equipe"],
            "Desempenho Médio Ajustado": round(resultado_ajustado, 2),
            "Desvio Padrão": round(desvio_padrao, 2)
        })

    return pd.DataFrame(df_desempenho_lista).sort_values(by="Desempenho Médio Ajustado", ascending=False)

def distribuir_apostas(df, total_aposta, incluir_desempenho):
    # Garantir que fator_ajuste seja uma série válida
    if incluir_desempenho:
        fator_ajuste = df["Desempenho Médio Ajustado"] / 100
    else:
        fator_ajuste = np.ones(len(df))  # Caso a análise esteja desativada, usa 1 para todos

    # Verificar se fator_ajuste é uma série válida antes da operação
    if isinstance(fator_ajuste, pd.Series):
        df["valor_apostado"] = np.round(total_aposta * (fator_ajuste / fator_ajuste.sum()), 2)
    else:
        st.error("Erro ao calcular fator de ajuste: a variável não é uma série válida.")

    return df

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
    st.write("##### | Dutching e Performance de Equipes")

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
        incluir_desempenho = st.checkbox("Incluir análise de desempenho?", value=True)
        
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
        st.write(f"💸 **Gain Esperado:** R$ {df_cavalos_filtrado['Gain Dutch'].sum():.2f}")
        st.write(f"✅ **Lucro:** R$ {(df_cavalos_filtrado['Gain Dutch'] - df_cavalos_filtrado['Dutching Bet']).sum():.2f}")

    st.divider()
        
    # Exibir dados de desempenho de equipes
    st.write("##### | Analise de Desempenho")
    st.dataframe(df_desempenho)

    st.divider()
    
# --- Aposta Top 3 ---
    st.write("##### | Aposta Top 3")
    
    # Definir probabilidade histórica de vitória do favorito
    prob_vitoria_favorito = st.number_input("Defina a probabilidade histórica de vitória do favorito (%)", min_value=0.0, max_value=100.0, step=0.1, value=39.68) / 100
    
    # Entrada manual para definir percentual do bankroll nos favoritos
    percentual_bankroll_favoritos = st.number_input("Defina o percentual do bankroll para favoritos (%)", min_value=0.0, max_value=100.0, step=1.0, value=50.0) / 100
    
    # Entrada manual para seleção dos favoritos
    nomes_favoritos = st.multiselect("Selecione os cavalos para apostar:", df_cavalos_filtrado["Nome"].unique())
    
    # Filtrar os favoritos com base na seleção manual
    df_favoritos = df_cavalos_filtrado[df_cavalos_filtrado["Nome"].isin(nomes_favoritos)] if nomes_favoritos else pd.DataFrame()
    
    # Verificação de existência de dados antes de prosseguir com cálculos
    if not df_favoritos.empty:
        bankroll_favoritos = bankroll * percentual_bankroll_favoritos
        soma_inverso_odds = df_favoritos["Odds"].apply(lambda x: (1 / x) * prob_vitoria_favorito).sum()
    
        # Verificando se soma_inverso_odds não é zero para evitar erro na divisão
        if soma_inverso_odds > 0:
            df_favoritos["Valor Apostado"] = round(bankroll_favoritos * (1 / df_favoritos["Odds"]) / soma_inverso_odds, 2)
    
            # Exibir dataframe atualizado com valores apostados
            st.dataframe(df_favoritos[["Nome", "Odds", "Valor Apostado"]])
    
            # Cálculo do valor total apostado e do lucro esperado
            total_apostado = df_favoritos["Valor Apostado"].sum()
            retorno_aposta = (df_favoritos["Valor Apostado"] * df_favoritos["Odds"]).sum()
            lucro_aposta = retorno_aposta - total_apostado
            
            st.write(f"💰 **Total de Aposta:** R$ {total_apostado:.2f}")
            st.write(f"💸 **Gain Esperado:** R$ {retorno_aposta:.2f}")
            st.write(f"✅ **Lucro Esperado:** R$ {lucro_aposta:.2f}")
        else:
            st.warning("⚠️ Erro: soma das probabilidades inversas é zero, verifique os dados das odds.")
    else:
        st.warning("⚠️ Nenhum favorito foi identificado, verifique os dados disponíveis.")
    
    # Conversão de odds e limpeza de dados
    if not df_favoritos.empty:
        df_favoritos["Odds"] = pd.to_numeric(df_favoritos["Odds"], errors="coerce")
        df_favoritos.dropna(subset=["Odds"], inplace=True)
    
    # Calcular retorno máximo e mínimo
    if not df_favoritos.empty:
        retorno_maximo = df_favoritos["Valor Apostado"].nlargest(3).sum()
        retorno_minimo = df_favoritos["Valor Apostado"].nsmallest(3).sum()
    
        st.write(f"📈 **Retorno Máximo:** R$ {retorno_maximo:.2f}")
        st.write(f"📉 **Retorno Mínimo:** R$ {retorno_minimo:.2f}")
    else:
        st.warning("⚠️ Não há dados suficientes para calcular retorno máximo e mínimo.")
    
        st.divider()

    # ✅ Ajuste de apostas baseado no desempenho histórico
    if not df_cavalos_filtrado.empty and "Desempenho Médio Ajustado" in df_cavalos_filtrado.columns:
        # Normalizar os valores de desempenho para evitar distorções extremas
        df_cavalos_filtrado["Fator Desempenho"] = df_cavalos_filtrado["Desempenho Médio Ajustado"] / df_cavalos_filtrado["Desempenho Médio Ajustado"].max()
        
        # Aplicar ajuste ao valor apostado
        df_cavalos_filtrado["Valor Apostado Ajustado"] = round(df_cavalos_filtrado["Valor Apostado"] * df_cavalos_filtrado["Fator Desempenho"], 2)
    
        # ✅ Exibir tabela com os ajustes aplicados
        st.write("##### | Ajuste de Apostas Baseado no Desempenho Histórico")
        st.dataframe(df_cavalos_filtrado[["Nome", "Odds", "Desempenho Médio Ajustado", "Valor Apostado", "Valor Apostado Ajustado"]])
    
        # ✅ Exibir totais ajustados
        total_aposta_ajustada = df_cavalos_filtrado["Valor Apostado Ajustado"].sum()
        st.write(f"📊 **Total de Aposta Ajustado:** R$ {total_aposta_ajustada:.2f}")
    
    else:
        st.warning("⚠️ Dados insuficientes para aplicar ajuste de apostas baseado no desempenho histórico.")
