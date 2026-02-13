import streamlit as st
import pdfplumber
import re
import os
import json
import unicodedata
import gspread
from google.oauth2.service_account import Credentials

# ==========================================
# CONFIG GOOGLE
# ==========================================

PLANILHA_URL = "https://docs.google.com/spreadsheets/d/1er5DKT8jNm4qLTgQzdT2eQL8BrxxDlceUfkASYKYEZ8/edit"

scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds_dict = json.loads(os.environ["GCP_SERVICE_ACCOUNT_JSON"])
creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
client = gspread.authorize(creds)

planilha = client.open_by_url(PLANILHA_URL)

# ==========================================
# FUNÇÕES AUXILIARES
# ==========================================

def normalizar_nome(nome):
    nome = nome.upper().strip()
    nome = unicodedata.normalize('NFKD', nome)
    nome = "".join(c for c in nome if not unicodedata.combining(c))
    nome = re.sub(r"\s+", " ", nome)
    return nome

def identificar_loja(texto):
    texto = texto.upper()
    if "TPBR" in texto:
        return "TPBR"
    elif "JPBB" in texto:
        return "JPBB"
    return None

def extrair_totais(bloco):
    horarios = re.findall(r"\d{1,3}:\d{2}", bloco)

    if len(horarios) >= 3:
        return {
            "falta": horarios[-3],
            "extra": horarios[-2],
            "noturno": horarios[-1]
        }

    return {
        "falta": "00:00",
        "extra": "00:00",
        "noturno": "00:00"
    }

# ==========================================
# INTERFACE
# ==========================================

st.title("🚀 Sistema Calculadora de Horas")

pdf_file = st.file_uploader("Selecione o PDF da loja (JPBB ou TPBR)", type="pdf")

if pdf_file:

    texto_completo = ""

    with pdfplumber.open(pdf_file) as pdf:
        for pagina in pdf.pages:
            texto_completo += pagina.extract_text() + "\n"

    st.success("PDF lido com sucesso!")

    loja = identificar_loja(texto_completo)

    if not loja:
        st.error("Loja não identificada no PDF.")
        st.stop()

    st.info(f"🏢 Loja identificada: {loja}")

    mes = "JANEIRO"  # pode automatizar depois
    nome_aba = f"{mes}_{loja}"

    st.info(f"📄 Dados irão para aba: {nome_aba}")

    try:
        aba = planilha.worksheet(nome_aba)
    except:
        st.error(f"Aba {nome_aba} não encontrada na planilha.")
        st.stop()

    linhas = aba.get_all_values()

    # pegar nomes da coluna A
    nomes_planilha = {}
    for i, linha in enumerate(linhas):
        if linha and linha[0]:
            nomes_planilha[normalizar_nome(linha[0])] = i + 1

    # dividir por funcionário
    funcionarios_pdf = re.split(r"NOME DO FUNCIONARIO:", texto_completo)

    atualizados = 0

    for bloco in funcionarios_pdf:

        match_nome = re.search(r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ ]+)", bloco)

        if not match_nome:
            continue

        nome_pdf = normalizar_nome(match_nome.group(1))

        if nome_pdf in nomes_planilha:

            linha_encontrada = nomes_planilha[nome_pdf]
            totais = extrair_totais(bloco)

            try:
                aba.update(f"B{linha_encontrada}:E{linha_encontrada}", [[
                    totais["falta"],
                    totais["extra"],
                    totais["extra"],  # coluna D
                    totais["noturno"]
                ]])
                atualizados += 1

            except Exception as e:
                st.error(f"Erro ao atualizar {nome_pdf}: {e}")

    if atualizados > 0:
        st.success(f"Dados enviados para Google Sheets com sucesso! ({atualizados} funcionários atualizados)")
    else:
        st.warning("Nenhum funcionário foi encontrado na planilha.")
