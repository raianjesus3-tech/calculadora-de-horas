import streamlit as st
import os
import json
import re
import unicodedata
import gspread
from google.oauth2.service_account import Credentials
import pdfplumber

st.set_page_config(page_title="Sistema Calculadora de Horas", layout="wide")

st.title("🚀 Sistema Calculadora de Horas")

# =============================
# CONEXÃO GOOGLE SHEETS
# =============================

try:
    creds_dict = json.loads(os.environ["GCP_SERVICE_ACCOUNT_JSON"])

    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)

    PLANILHA_URL = "https://docs.google.com/spreadsheets/d/1er5DKT8jNm4qLTgQzdT2eQL8BrxxDlceUfkASYKYEZ8"

    planilha = client.open_by_url(PLANILHA_URL)

except Exception as e:
    st.error("Erro ao conectar no Google Sheets")
    st.code(str(e))
    st.stop()

# =============================
# FUNÇÕES AUXILIARES
# =============================

def normalizar(texto):
    texto = texto.upper().strip()
    texto = unicodedata.normalize("NFD", texto)
    texto = texto.encode("ascii", "ignore").decode("utf-8")
    return texto

def identificar_loja(texto):
    texto = texto.upper()
    if "TPBR" in texto:
        return "TPBR"
    if "JPBB" in texto:
        return "JPBB"
    return None

def identificar_mes(texto):
    meses = {
        "01": "JANEIRO",
        "02": "FEVEREIRO",
        "03": "MARCO",
        "04": "ABRIL",
        "05": "MAIO",
        "06": "JUNHO",
        "07": "JULHO",
        "08": "AGOSTO",
        "09": "SETEMBRO",
        "10": "OUTUBRO",
        "11": "NOVEMBRO",
        "12": "DEZEMBRO"
    }

    match = re.search(r"DE \d{2}/(\d{2})/\d{4}", texto)
    if match:
        numero_mes = match.group(1)
        return meses.get(numero_mes)
    return None

def extrair_nome(texto):
    match = re.search(r"NOME DO FUNCIONÁRIO:\s*(.+)", texto)
    if not match:
        return None

    nome = match.group(1)

    nome = nome.split("PIS")[0]
    nome = nome.split("ENT")[0]

    nome = nome.strip()

    return nome

# =============================
# UPLOAD PDF
# =============================

st.subheader("📤 Enviar PDF de Espelho de Ponto")

arquivo = st.file_uploader("Selecione o PDF da loja (JPBB ou TPBR)", type="pdf")

if arquivo:

    with pdfplumber.open(arquivo) as pdf:
        texto_pdf = ""
        for pagina in pdf.pages:
            texto_pdf += pagina.extract_text() + "\n"

    st.success("PDF lido com sucesso!")

    loja = identificar_loja(texto_pdf)
    mes = identificar_mes(texto_pdf)

    if not loja or not mes:
        st.error("Não foi possível identificar loja ou mês.")
        st.stop()

    nome_aba = f"{mes}_{loja}"

    st.info(f"🏢 Loja identificada: {loja}")
    st.info(f"📄 Dados irão para aba: {nome_aba}")

    try:
        aba = planilha.worksheet(nome_aba)
    except:
        st.error("Aba não encontrada na planilha.")
        st.stop()

    nome_funcionario = extrair_nome(texto_pdf)

    if not nome_funcionario:
        st.error("Nome do funcionário não encontrado no PDF.")
        st.stop()

    st.write(f"👤 Funcionário identificado: {nome_funcionario}")

    # =============================
    # PROCURAR NA PLANILHA
    # =============================

    nomes_planilha = aba.col_values(1)

    nome_pdf_normalizado = normalizar(nome_funcionario)

    linha_encontrada = None

    for i, nome_planilha in enumerate(nomes_planilha):
        if normalizar(nome_planilha) == nome_pdf_normalizado:
            linha_encontrada = i + 1
            break

    if not linha_encontrada:
        st.error("Funcionário não encontrado na planilha.")
        st.stop()

    st.success(f"Funcionário localizado na linha {linha_encontrada}")

    # =============================
    # AQUI VOCÊ COLOCA A LÓGICA DE HORAS
    # =============================
    # Por enquanto exemplo fixo:
    falta = "00:00"
    extra = "00:00"
    noturno = "00:00"

    aba.update(f"B{linha_encontrada}", falta)
    aba.update(f"C{linha_encontrada}", extra)
    aba.update(f"E{linha_encontrada}", noturno)

    st.success("🎉 Dados enviados para o Google Sheets com sucesso!")
