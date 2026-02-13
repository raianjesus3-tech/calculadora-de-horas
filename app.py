import streamlit as st
import pdfplumber
import re
import unicodedata
import os
import json
import gspread
from google.oauth2.service_account import Credentials

# ===============================
# CONFIG GOOGLE
# ===============================

creds_dict = json.loads(os.environ["GCP_SERVICE_ACCOUNT_JSON"])

scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
client = gspread.authorize(creds)

PLANILHA_ID = "1er5DKT8jNm4qLTgQzdT2eQL8BrxxDlceUfkASYKYEZ8"
planilha = client.open_by_key(PLANILHA_ID)

# ===============================
# FUNÇÕES AUXILIARES
# ===============================

def normalizar(texto):
    texto = unicodedata.normalize("NFKD", texto)
    texto = texto.encode("ASCII", "ignore").decode("utf-8")
    return texto.strip().upper()

def identificar_loja(texto):
    texto = texto.upper()
    if "TPBR" in texto:
        return "TPBR"
    if "JPBB" in texto:
        return "JPBB"
    return None

def extrair_funcionarios(texto):
    padrao = r"NOME DO FUNCIONÁRIO:\s*(.*?)\s*PIS"
    nomes = re.findall(padrao, texto, re.IGNORECASE)
    return nomes

def extrair_totais(texto_bloco):
    totais = {}

    falta = re.search(r"FALTAS?:\s*(\d+:\d+)", texto_bloco)
    extra = re.search(r"HORAS EXTRAS?:\s*(\d+:\d+)", texto_bloco)
    noturno = re.search(r"ADICIONAL NOTURNO?:\s*(\d+:\d+)", texto_bloco)

    totais["falta"] = falta.group(1) if falta else "00:00"
    totais["extra"] = extra.group(1) if extra else "00:00"
    totais["noturno"] = noturno.group(1) if noturno else "00:00"

    return totais

def encontrar_linha_por_nome(aba, nome):
    valores = aba.col_values(1)
    nome_normalizado = normalizar(nome)

    for i, valor in enumerate(valores):
        if normalizar(valor) == nome_normalizado:
            return i + 1
    return None

# ===============================
# STREAMLIT
# ===============================

st.title("🚀 Sistema Calculadora de Horas")
st.subheader("📤 Enviar PDF de Espelho de Ponto")

arquivo = st.file_uploader("Selecione o PDF", type="pdf")

if arquivo:

    texto_completo = ""

    with pdfplumber.open(arquivo) as pdf:
        for pagina in pdf.pages:
            texto_completo += pagina.extract_text() + "\n"

    st.success("PDF lido com sucesso!")

    loja = identificar_loja(texto_completo)

    if not loja:
        st.error("Não foi possível identificar a loja.")
        st.stop()

    st.info(f"🏢 Loja identificada: {loja}")

    aba_nome = f"JANEIRO_{loja}"
    aba = planilha.worksheet(aba_nome)

    st.info(f"📄 Dados irão para aba: {aba_nome}")

    nomes = extrair_funcionarios(texto_completo)

    if not nomes:
        st.error("Nenhum funcionário encontrado no PDF.")
        st.stop()

    for nome in nomes:

        st.write(f"👤 Processando: {nome}")

        # pega bloco específico do funcionário
        bloco = texto_completo.split(nome)[1]

        totais = extrair_totais(bloco)

        linha = encontrar_linha_por_nome(aba, nome)

        if not linha:
            st.warning(f"{nome} não encontrado na planilha.")
            continue

        # ===============================
        # IDENTIFICAR SE É MOTOBOY
        # ===============================

        if linha >= 12:  # motoboys começam abaixo da linha 10
            aba.update(f"B{linha}", [[totais["falta"]]])
            aba.update(f"C{linha}", [[totais["noturno"]]])
            aba.update(f"D{linha}", [[totais["extra"]]])
        else:
            aba.update(f"B{linha}", [[totais["falta"]]])
            aba.update(f"C{linha}", [[totais["extra"]]])
            aba.update(f"E{linha}", [[totais["noturno"]]])

    st.success("🎉 Dados enviados para o Google Sheets com sucesso!")
