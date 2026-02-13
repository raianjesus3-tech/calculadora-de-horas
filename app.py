import streamlit as st
import os
import json
import re
import unicodedata
import gspread
from google.oauth2.service_account import Credentials
from pdfminer.high_level import extract_text

# =============================
# CONFIG GOOGLE
# =============================

PLANILHA_KEY = "1er5DKT8jNm4qLTgQzdT2eQL8BrxxDlceUfkASYKYEZ8"

scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds_dict = json.loads(os.environ["GCP_SERVICE_ACCOUNT_JSON"])
creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
client = gspread.authorize(creds)

planilha = client.open_by_key(PLANILHA_KEY)

# =============================
# FUNÇÕES
# =============================

def normalizar(texto):
    texto = texto.upper().strip()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto

def identificar_loja(texto):
    texto = texto.upper()
    if "JPBB" in texto:
        return "JPBB"
    elif "TPBR" in texto:
        return "TPBR"
    return None

def extrair_nome(texto):
    match = re.search(r"NOME DO FUNCIONÁRIO:\s*(.+)", texto)
    if match:
        nome = match.group(1)
        nome = nome.split("PIS")[0]
        nome = nome.strip()
        return normalizar(nome)
    return None

def extrair_totais(texto):
    match = re.search(r"TOTAIS\s+([\d:]+)\s+([\d:]+)\s+([\d:]+)\s+([\d:]+)", texto)
    if match:
        return {
            "normais": match.group(1),
            "noturno": match.group(2),
            "falta": match.group(3),
            "extra": match.group(4)
        }
    return None

# =============================
# INTERFACE
# =============================

st.title("🚀 Sistema Calculadora de Horas")
st.subheader("📤 Enviar PDF de Espelho de Ponto")

arquivo = st.file_uploader("Selecione o PDF da loja (JPBB ou TPBR)", type="pdf")

if arquivo:

    texto = extract_text(arquivo)
    st.success("PDF lido com sucesso!")

    loja = identificar_loja(texto)
    st.info(f"🏢 Loja identificada: {loja}")

    nome_funcionario = extrair_nome(texto)
    totais = extrair_totais(texto)

    if not loja:
        st.error("Loja não identificada.")
        st.stop()

    if not nome_funcionario:
        st.error("Funcionário não identificado no PDF.")
        st.stop()

    st.write("👤 Funcionário identificado:", nome_funcionario)

    aba_nome = f"JANEIRO_{loja}"
    st.write("📄 Dados irão para aba:", aba_nome)

    aba = planilha.worksheet(aba_nome)
    dados = aba.get_all_values()

    nome_normalizado = normalizar(nome_funcionario)

    linha_encontrada = None

    for i, linha in enumerate(dados):
        if normalizar(linha[0]) == nome_normalizado:
            linha_encontrada = i + 1
            break

    if not linha_encontrada:
        st.error("Funcionário não encontrado na planilha.")
        st.stop()

    st.success("Funcionário encontrado na linha " + str(linha_encontrada))

    # =============================
    # BLOCO NORMAL
    # =============================
    if linha_encontrada < 10:
        aba.update(f"B{linha_encontrada}", totais["falta"])
        aba.update(f"C{linha_encontrada}", totais["extra"])
        aba.update(f"E{linha_encontrada}", totais["noturno"])

    # =============================
    # BLOCO MOTOBOY
    # =============================
    else:
        aba.update(f"C{linha_encontrada}", totais["normais"])
        aba.update(f"B{linha_encontrada}", totais["noturno"])
        aba.update(f"D{linha_encontrada}", totais["extra"])

    st.success("🎉 Dados enviados para o Google Sheets com sucesso!")
