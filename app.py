import streamlit as st
import os
import json
import re
import unicodedata
import gspread
from google.oauth2.service_account import Credentials
import pdfplumber

# =============================
# CONFIG GOOGLE SHEETS
# =============================

PLANILHA_URL = "https://docs.google.com/spreadsheets/d/1er5DKT8jNm4qLTgQzdT2eQL8BrxxDlceUfkASYKYEZ8/edit"

scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds_dict = json.loads(os.environ["GCP_SERVICE_ACCOUNT_JSON"])
creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
client = gspread.authorize(creds)

planilha = client.open_by_url(PLANILHA_URL)

# =============================
# FUNÇÕES AUXILIARES
# =============================

def normalizar(texto):
    texto = unicodedata.normalize("NFKD", texto)
    texto = texto.encode("ASCII", "ignore").decode("ASCII")
    return texto.upper().strip()

def identificar_loja(texto):
    texto = texto.upper()
    if "TPBR" in texto:
        return "TPBR"
    if "JPBB" in texto:
        return "JPBB"
    return None

def extrair_nome(texto):
    match = re.search(r"NOME DO FUNCIONÁRIO:\s*(.+)", texto)
    if match:
        nome = match.group(1).split("PIS")[0]
        return nome.strip()
    return None

def extrair_totais(texto):
    totais = {
        "falta": "00:00",
        "extra": "00:00",
        "noturno": "00:00",
        "normais": "00:00"
    }

    faltas = re.findall(r"FALTAS\s+(\d+:\d+)", texto)
    extras = re.findall(r"HORAS EXTRAS\s+(\d+:\d+)", texto)
    noturno = re.findall(r"ADICIONAL NOTURNO\s+(\d+:\d+)", texto)
    normais = re.findall(r"HORAS NORMAIS\s+(\d+:\d+)", texto)

    if faltas:
        totais["falta"] = faltas[-1]
    if extras:
        totais["extra"] = extras[-1]
    if noturno:
        totais["noturno"] = noturno[-1]
    if normais:
        totais["normais"] = normais[-1]

    return totais

# =============================
# INTERFACE
# =============================

st.title("🚀 Sistema Calculadora de Horas")

uploaded_file = st.file_uploader("Selecione o PDF", type="pdf")

if uploaded_file:

    with pdfplumber.open(uploaded_file) as pdf:
        texto = ""
        for page in pdf.pages:
            texto += page.extract_text()

    st.success("PDF lido com sucesso!")

    loja = identificar_loja(texto)

    if not loja:
        st.error("Loja não identificada.")
        st.stop()

    st.info(f"Loja identificada: {loja}")

    aba_nome = f"JANEIRO_{loja}"
    aba = planilha.worksheet(aba_nome)

    st.info(f"Dados irão para aba: {aba_nome}")

    nome_funcionario = extrair_nome(texto)

    if not nome_funcionario:
        st.error("Nome do funcionário não encontrado no PDF.")
        st.stop()

    st.write(f"Funcionário identificado: {nome_funcionario}")

    totais = extrair_totais(texto)

    # =============================
    # PROCURAR FUNCIONÁRIO NA COLUNA A
    # =============================

    nomes_planilha = aba.col_values(1)

    linha_encontrada = None

    for i, nome in enumerate(nomes_planilha):
        if normalizar(nome) == normalizar(nome_funcionario):
            linha_encontrada = i + 1
            break

    if not linha_encontrada:
        st.error("Funcionário não encontrado na planilha.")
        st.stop()

    # =============================
    # IDENTIFICAR SE É MOTOBOY
    # =============================

    motoboy_inicio = None
    for i, valor in enumerate(nomes_planilha):
        if "MOTOBOYS HORISTAS" in valor:
            motoboy_inicio = i + 1
            break

    if motoboy_inicio and linha_encontrada > motoboy_inicio:

        # BLOCO MOTOBOY
        aba.update_acell(f"C{linha_encontrada}", totais["normais"])
        aba.update_acell(f"D{linha_encontrada}", totais["noturno"])
        aba.update_acell(f"E{linha_encontrada}", totais["extra"])

    else:

        # BLOCO NORMAL
        aba.update_acell(f"B{linha_encontrada}", totais["falta"])
        aba.update_acell(f"C{linha_encontrada}", totais["extra"])
        aba.update_acell(f"E{linha_encontrada}", totais["noturno"])

    st.success("Dados enviados para o Google Sheets com sucesso!")
