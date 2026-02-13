import streamlit as st
import os
import json
import re
import unicodedata
import gspread
from google.oauth2.service_account import Credentials
import pdfplumber

# ==============================
# CONFIG GOOGLE SHEETS
# ==============================

PLANILHA_URL = "https://docs.google.com/spreadsheets/d/1er5DKT8jNm4qLTgQzdT2eQL8BrxxDlceUfkASYKYEZ8/edit"

scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds_dict = json.loads(os.environ["GCP_SERVICE_ACCOUNT_JSON"])
creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
client = gspread.authorize(creds)
planilha = client.open_by_url(PLANILHA_URL)

# ==============================
# FUNÇÕES AUXILIARES
# ==============================

def normalizar(texto):
    texto = texto.upper().strip()
    texto = unicodedata.normalize("NFD", texto)
    texto = texto.encode("ascii", "ignore").decode("utf-8")
    texto = re.sub(r"\s+", " ", texto)
    return texto

def identificar_loja(texto):
    texto = texto.upper()
    if "TPBR" in texto:
        return "TPBR"
    if "JPBB" in texto:
        return "JPBB"
    return None

def extrair_nome(texto):
    match = re.search(r"NOME DA EMPRESA.*?\n(.*?)PIS DO FUNCIONÁRIO", texto, re.DOTALL)
    if match:
        nome = match.group(1).strip()
        nome = re.sub(r"\s+", " ", nome)
        return nome
    return None

# ==============================
# INTERFACE
# ==============================

st.title("🚀 Sistema Calculadora de Horas")
st.subheader("📤 Enviar PDF de Espelho de Ponto")

arquivo = st.file_uploader("Selecione o PDF da loja (JPBB ou TPBR)", type=["pdf"])

if arquivo:

    with pdfplumber.open(arquivo) as pdf:
        texto = ""
        for pagina in pdf.pages:
            texto += pagina.extract_text() + "\n"

    st.success("PDF lido com sucesso!")

    loja = identificar_loja(texto)
    if not loja:
        st.error("Loja não identificada.")
        st.stop()

    st.info(f"🏬 Loja identificada: {loja}")

    # Identifica mês automaticamente pelo PDF
    if "01/2026" in texto:
        mes = "JANEIRO"
    elif "02/2026" in texto:
        mes = "FEVEREIRO"
    else:
        mes = "JANEIRO"

    nome_aba = f"{mes}_{loja}"
    st.info(f"📄 Dados irão para aba: {nome_aba}")

    aba = planilha.worksheet(nome_aba)

    nome_pdf = extrair_nome(texto)

    if not nome_pdf:
        st.error("Nome do funcionário não encontrado no PDF.")
        st.stop()

    nome_pdf_norm = normalizar(nome_pdf)

    st.write(f"👤 Funcionário identificado: {nome_pdf}")

    nomes_planilha = aba.col_values(1)

    encontrado = False

    for i, nome_plan in enumerate(nomes_planilha):
        if normalizar(nome_plan) == nome_pdf_norm:

            # EXTRAÇÃO SIMPLES DAS HORAS (você pode melhorar depois)
            extra = re.search(r"EXTRA\s+(\d+:\d+)", texto)
            noturno = re.search(r"NOTURNO\s+(\d+:\d+)", texto)
            falta = re.search(r"FALTA\s+(\d+:\d+)", texto)

            extra = extra.group(1) if extra else "00:00"
            noturno = noturno.group(1) if noturno else "00:00"
            falta = falta.group(1) if falta else "00:00"

            linha = i + 1

            # ==============================
            # BLOCO MOTOBOYS (abaixo da linha 11)
            # ==============================

            if linha >= 12:
                aba.update(f"B{linha}", noturno)
                aba.update(f"C{linha}", extra)
                aba.update(f"D{linha}", "00:00")
            else:
                aba.update(f"B{linha}", falta)
                aba.update(f"C{linha}", extra)
                aba.update(f"E{linha}", noturno)

            encontrado = True
            break

    if encontrado:
        st.success("🎉 Dados enviados para o Google Sheets com sucesso!")
    else:
        st.error("Funcionário não encontrado na planilha.")
