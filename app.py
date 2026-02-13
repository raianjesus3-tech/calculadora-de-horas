import streamlit as st
import os
import json
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Calculadora de Horas", layout="wide")

st.title("🚀 Sistema Calculadora de Horas")

# ==================================================
# 🔐 1. VERIFICAR VARIÁVEL DE AMBIENTE
# ==================================================

if "GCP_SERVICE_ACCOUNT_JSON" not in os.environ:
    st.error("❌ Variável GCP_SERVICE_ACCOUNT_JSON NÃO encontrada.")
    st.stop()

# ==================================================
# 📦 2. CARREGAR JSON DA SERVICE ACCOUNT
# ==================================================

try:
    creds_dict = json.loads(os.environ["GCP_SERVICE_ACCOUNT_JSON"])
except Exception as e:
    st.error("❌ Erro ao carregar JSON:")
    st.code(str(e))
    st.stop()

# ==================================================
# 🔗 3. CONECTAR AO GOOGLE SHEETS
# ==================================================

try:
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)

except Exception as e:
    st.error("❌ ERRO NA INTEGRAÇÃO GOOGLE:")
    st.code(str(e))
    st.stop()

# ==================================================
# 📄 4. ABRIR PLANILHA
# ==================================================

try:
    # 🔴 COLE AQUI O LINK COMPLETO DA SUA PLANILHA
    PLANILHA_URL = https://docs.google.com/spreadsheets/d/1er5DKT8jNm4qLTgQzdT2eQL8BrxxDlceUfkASYKYEZ8/edit?gid=0#gid=0

    planilha = client.open_by_url(PLANILHA_URL)

except Exception as e:
    st.error("❌ Erro ao abrir planilha:")
    st.code(str(e))
    st.stop()

# ==================================================
# 🏬 5. ESCOLHER LOJA
# ==================================================

st.sidebar.header("🏬 Selecionar Loja")

loja = st.sidebar.selectbox(
    "Escolha a loja:",
    ["TPBR", "JPBB"]
)

# ==================================================
# 📅 6. ESCOLHER MÊS
# ==================================================

abas_disponiveis = [aba.title for aba in planilha.worksheets()]

abas_filtradas = [aba for aba in abas_disponiveis if loja in aba]

if not abas_filtradas:
    st.warning(f"⚠️ Nenhuma aba encontrada para {loja}")
    st.stop()

aba_selecionada = st.sidebar.selectbox(
    "Escolha o mês:",
    abas_filtradas
)

# ==================================================
# 📊 7. CARREGAR DADOS DA ABA
# ==================================================

try:
    worksheet = planilha.worksheet(aba_selecionada)
    dados = worksheet.get_all_records()
except Exception as e:
    st.error("❌ Erro ao carregar dados da aba:")
    st.code(str(e))
    st.stop()

st.subheader(f"📄 Dados da aba: {aba_selecionada}")

if dados:
    st.dataframe(dados, use_container_width=True)
else:
    st.info("ℹ️ A aba está vazia.")

st.success("✅ Sistema carregado com sucesso")
