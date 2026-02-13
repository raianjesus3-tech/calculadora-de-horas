import streamlit as st
import os
import json
import re
import pdfplumber
import gspread
from google.oauth2.service_account import Credentials

# ==========================================
# CONFIGURAÇÃO INICIAL
# ==========================================

st.set_page_config(page_title="Sistema Calculadora de Horas", layout="wide")

st.title("🚀 Sistema Calculadora de Horas")

# ==========================================
# CONEXÃO GOOGLE SHEETS
# ==========================================

try:
    if "GCP_SERVICE_ACCOUNT_JSON" not in os.environ:
        st.error("❌ Variável GCP_SERVICE_ACCOUNT_JSON não encontrada.")
        st.stop()

    creds_dict = json.loads(os.environ["GCP_SERVICE_ACCOUNT_JSON"])

    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)

    st.success("✅ Conectado ao Google Sheets")

except Exception as e:
    st.error("❌ Erro na integração Google:")
    st.code(str(e))
    st.stop()

# ==========================================
# IDENTIFICAR LOJA
# ==========================================

def identificar_loja(texto):
    texto = texto.upper()
    if "TPBR" in texto:
        return "TPBR"
    elif "JPBB" in texto:
        return "JPBB"
    return None

# ==========================================
# CONFIG PLANILHA
# ==========================================

PLANILHA_URL = "https://docs.google.com/spreadsheets/d/1er5DKT8jNm4qLTgQzdT2eQL8BrxxDlceUfkASYKYEZ8/edit#gid=0"

planilha = client.open_by_url(PLANILHA_URL)

abas = planilha.worksheets()
nomes_abas = [aba.title for aba in abas]

aba_selecionada = st.selectbox("📄 Escolha a aba", nomes_abas)

worksheet = planilha.worksheet(aba_selecionada)

st.subheader(f"📊 Dados da aba: {aba_selecionada}")

dados = worksheet.get_all_values()

if dados:
    st.dataframe(dados)
else:
    st.warning("Aba vazia.")

# ==========================================
# UPLOAD DO PDF
# ==========================================

st.divider()
st.subheader("📤 Enviar PDF de Espelho de Ponto")

uploaded_file = st.file_uploader(
    "Selecione o PDF da loja (JPBB ou TPBR)",
    type=["pdf"]
)

if uploaded_file is not None:
    st.success("✅ PDF enviado com sucesso!")

    try:
        with pdfplumber.open(uploaded_file) as pdf:
            texto = ""
            for page in pdf.pages:
                conteudo = page.extract_text()
                if conteudo:
                    texto += conteudo + "\n"

        loja_detectada = identificar_loja(texto)

        if loja_detectada:
            st.info(f"🏬 Loja detectada: {loja_detectada}")
        else:
            st.warning("⚠️ Não foi possível identificar a loja no PDF.")

        st.subheader("📄 Prévia do conteúdo do PDF")
        st.code(texto[:1500])

    except Exception as e:
        st.error("❌ Erro ao ler PDF:")
        st.code(str(e))
