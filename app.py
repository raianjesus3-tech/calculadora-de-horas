import streamlit as st
import os
import json
import re
import unicodedata
import gspread
import pdfplumber
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Sistema Calculadora de Horas", layout="wide")

st.title("🚀 Sistema Calculadora de Horas")
st.subheader("📤 Enviar PDF de Espelho de Ponto")

# =========================
# CONEXÃO GOOGLE SHEETS
# =========================

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

PLANILHA_URL = "https://docs.google.com/spreadsheets/d/1er5DKT8jNm4qLTgQzdT2eQL8BrxxDlceUfkASYKYEZ8"

planilha = client.open_by_url(PLANILHA_URL)

# =========================
# FUNÇÕES AUXILIARES
# =========================

def normalizar_nome(nome):
    nome = nome.upper().strip()
    nome = unicodedata.normalize("NFKD", nome)
    nome = "".join(c for c in nome if not unicodedata.combining(c))
    nome = re.sub(r"\s+", " ", nome)
    return nome

def identificar_loja(texto):
    texto = texto.upper()
    if "TPBR" in texto:
        return "TPBR"
    if "JPBB" in texto:
        return "JPBB"
    return None

def extrair_nome(texto):
    match = re.search(r"NOME DO FUNCIONÁRIO:\s*(.+)", texto, re.IGNORECASE)
    if match:
        nome = match.group(1)
        nome = nome.split("PIS")[0]
        return normalizar_nome(nome)
    return None

def extrair_totais(texto):
    match = re.search(
        r"TOTAIS.*?(\d+:\d+)\s+(\d+:\d+)\s+(\d+:\d+)\s+(\d+:\d+)",
        texto,
        re.DOTALL
    )
    if match:
        return {
            "normais": match.group(1),
            "noturno": match.group(2),
            "falta": match.group(3),
            "extra": match.group(4),
        }
    return None

# =========================
# UPLOAD PDF
# =========================

pdf_file = st.file_uploader("Selecione o PDF da loja (JPBB ou TPBR)", type=["pdf"])

if pdf_file:

    with pdfplumber.open(pdf_file) as pdf:
        texto = ""
        for page in pdf.pages:
            texto += page.extract_text() + "\n"

    st.success("✅ PDF lido com sucesso!")

    loja = identificar_loja(texto)

    if not loja:
        st.error("❌ Loja não identificada.")
        st.stop()

    st.info(f"🏢 Loja identificada: {loja}")

    nome_funcionario = extrair_nome(texto)

    if not nome_funcionario:
        st.error("❌ Nome do funcionário não encontrado.")
        st.stop()

    st.info(f"👤 Funcionário identificado: {nome_funcionario}")

    totais = extrair_totais(texto)

    if not totais:
        st.error("❌ Linha TOTAIS não encontrada no PDF.")
        st.stop()

    # =========================
    # DEFINIR ABA
    # =========================

    mes = "JANEIRO"  # você pode automatizar depois
    nome_aba = f"{mes}_{loja}"

    try:
        aba = planilha.worksheet(nome_aba)
    except:
        st.error(f"❌ Aba {nome_aba} não encontrada na planilha.")
        st.stop()

    st.info(f"📄 Dados irão para aba: {nome_aba}")

    # =========================
    # PROCURAR FUNCIONÁRIO
    # =========================

    nomes_planilha = aba.col_values(1)
    linha_encontrada = None

    for i, nome in enumerate(nomes_planilha):
        if normalizar_nome(nome) == nome_funcionario:
            linha_encontrada = i + 1
            break

    if not linha_encontrada:
        st.error("❌ Funcionário não encontrado na planilha.")
        st.stop()

    # =========================
    # BLOCO NORMAL
    # =========================

    if linha_encontrada < 10:

        aba.update(f"B{linha_encontrada}", totais["falta"])
        aba.update(f"C{linha_encontrada}", totais["extra"])
        aba.update(f"E{linha_encontrada}", totais["noturno"])

    # =========================
    # BLOCO MOTOBOY
    # =========================

    else:

        aba.update(f"C{linha_encontrada}", totais["normais"])
        aba.update(f"D{linha_encontrada}", totais["noturno"])
        aba.update(f"E{linha_encontrada}", totais["extra"])

    st.success("🎉 Dados enviados para o Google Sheets com sucesso!")
