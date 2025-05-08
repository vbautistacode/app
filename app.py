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

    # ✅ Garantir que há dados antes de calcular o desempenho
    if "team_data" in st.session_state and st.session_state["team_data"]:
        df_desempenho = calcular_desempenho_equipes(st.session_state["team_data"])
    else:
        st.warning("⚠️ Nenhuma equipe cadastrada!")
        df_desempenho = pd.DataFrame(columns=["Nome da Equipe", "Desempenho Médio Ajustado"])

    # ✅ Garantir que há dados antes de calcular apostas
    if "horse_data" in st.session_state and st.session_state["horse_data"]:
        df_cavalos = pd.DataFrame(st.session_state["horse_data"])
        bankroll = st.number_input("Digite o valor do Bankroll:", min_value=100.0, max_value=100000.0, step=10.0, value=1000.0, key="bankroll_input")
    else:
        st.warning("⚠️ Nenhum dado de cavalos disponível.")
        df_cavalos = pd.DataFrame(columns=["Nome", "Odds", "Dutching Bet", "Gain Dutch"])

    # ✅ Aplicação do filtro antes dos cálculos
    nomes_selecionados = st.multiselect("Selecione os cavalos:", df_cavalos["Nome"].unique())
    df_cavalos_filtrado = df_cavalos[df_cavalos["Nome"].isin(nomes_selecionados)] if nomes_selecionados else df_cavalos

    # ✅ Opção de ativar ou desativar a análise de desempenho
    incluir_desempenho = st.checkbox("Incluir análise de desempenho?", value=True)

    # ✅ Verificar se df_desempenho tem dados antes do merge
    if incluir_desempenho and not df_desempenho.empty and "Desempenho Médio Ajustado" in df_desempenho.columns:
        df_cavalos_filtrado = df_cavalos_filtrado.merge(df_desempenho[["Nome da Equipe", "Desempenho Médio Ajustado"]],
                                                         left_on="Nome",
                                                         right_on="Nome da Equipe",
                                                         how="left")
        df_cavalos_filtrado["Desempenho Médio Ajustado"].fillna(1, inplace=True)  # Define 1 como padrão se não houver correspondência
    else:
        df_cavalos_filtrado["Desempenho Médio Ajustado"] = 1  # 🔹 Valor padrão para evitar erro quando ajuste estiver desativado

    # ✅ Cálculo das probabilidades e apostas Dutching
    if not df_cavalos_filtrado.empty and "Odds" in df_cavalos_filtrado.columns:
        df_cavalos_filtrado["Probabilidade"] = (1 / df_cavalos_filtrado["Odds"]).round(2)
        df_cavalos_filtrado["Dutching Bet"] = calculate_dutching(df_cavalos_filtrado["Odds"], bankroll, np.ones(len(df_cavalos_filtrado)))
        df_cavalos_filtrado["Gain Dutch"] = round(df_cavalos_filtrado["Odds"] * df_cavalos_filtrado["Dutching Bet"], 2)
        df_cavalos_filtrado["ROI-Dutch"] = round((df_cavalos_filtrado["Gain Dutch"] - df_cavalos_filtrado["Dutching Bet"]), 2)
        df_cavalos_filtrado["ROI (%)"] = round((df_cavalos_filtrado["Gain Dutch"] / df_cavalos_filtrado["Dutching Bet"]) * 100, 2)

        # ✅ Calcular totais e exibir resultados
        total_dutching = df_cavalos_filtrado["Dutching Bet"].sum()
        lucro_total = df_cavalos_filtrado["Gain Dutch"].sum()

        st.dataframe(df_cavalos_filtrado[["Nome", "Odds", "Probabilidade", "Dutching Bet", "Gain Dutch", "ROI-Dutch", "ROI (%)"]].reset_index(drop=True))

        st.write(f"💰 **Total de Aposta:** R$ {total_dutching:.2f}")
        st.write(f"💸 **Gain Esperado:** R$ {lucro_total:.2f}")
        st.divider()

    # ✅ Exibir seção "Aposta Top 3"
    st.write("##### | Aposta Top 3")

    # ✅ Aplicação da remoção de overround das odds
    if not df_cavalos_filtrado.empty and "Odds" in df_cavalos_filtrado.columns:
        df_cavalos_filtrado["Odd Ajustada"] = df_cavalos_filtrado["Odds"].apply(lambda x: ajustar_odds([x], 0.05)[0])

    # ✅ Entrada manual da probabilidade de vitória do favorito
    prob_vitoria_favorito = st.number_input("Insira a probabilidade histórica de vitória do favorito (%)",
                                            min_value=0.0, max_value=100.0, step=0.1, value=39.68) / 100

    # ✅ Garantir que a coluna existe antes de chamar distribuir_apostas()
    if "Desempenho Médio Ajustado" in df_cavalos_filtrado.columns:
        df_cavalos_filtrado["Valor Apostado"] = distribuir_apostas(df_cavalos_filtrado, bankroll, incluir_desempenho)["valor_apostado"]
    else:
        st.error("Erro: 'Desempenho Médio Ajustado' não foi encontrado no DataFrame de cavalos.")

    # ✅ Seção de ajuste de desempenho
    st.write("##### | Apostas Rebalanceadas com Desempenho")

    # ✅ Ajuste percentual baseado no desempenho
    ajuste_base = st.slider("Defina o ajuste percentual baseado no desempenho (%)", 0.1, 2.0, 0.2, 0.05)
    ajuste_percentual = ajuste_base / max(df_desempenho["Desempenho Médio Ajustado"].mean() - df_desempenho["Desvio Padrão"].mean(), 0.01)

    if "Dutching Bet" in df_cavalos_filtrado.columns:
        df_cavalos_filtrado["Adjusted Bet"] = round(df_cavalos_filtrado["Dutching Bet"] * ajuste_percentual, 2)
        df_cavalos_filtrado["Gain Adjusted"] = round(df_cavalos_filtrado["Adjusted Bet"] * df_cavalos_filtrado["Odds"], 2)

        total_adjusted = df_cavalos_filtrado["Adjusted Bet"].sum()
        lucro_adjusted1 = df_cavalos_filtrado["Gain Adjusted"].sum()

        st.dataframe(df_cavalos_filtrado[["Nome", "Odds", "Dutching Bet", "Adjusted Bet", "Gain Adjusted"]])
        st.write(f"💰 **Total de Aposta Ajustado:** R$ {total_adjusted:.2f}")
        st.write(f"💸 **Gain Esperado:** R$ {lucro_adjusted1:.2f}")
