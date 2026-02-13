import streamlit as st
import os
import json
import re
import unicodedata
import pdfplumber
import gspread
from google.oauth2.service_account import Credentials

# ==========================================
# CONFIGURAÇÃO GOOGLE
# ==========================================

scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

if "GCP_SERVICE_ACCOUNT_JSON" not in os.environ:
    st.error("❌ Variável GCP_SERVICE_ACCOUNT_JSON não encontrada.")
    st.stop()

creds_dict = json.loads(os.environ["GCP_SERVICE_ACCOUNT_JSON"])
creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
client = gspread.authorize(creds)

PLANILHA_URL = "https://docs.google.com/spreadsheets/d/1er5DKT8jNm4qLTgQzdT2eQL8BrxxDlceUfkASYKYEZ8"
spreadsheet = client.open_by_url(PLANILHA_URL)

# ==========================================
# FUNÇÕES AUXILIARES
# ==========================================

def normalizar_nome(nome):
    nome = nome.upper()
    nome = unicodedata.normalize("NFKD", nome)
    nome = "".join([c for c in nome if not unicodedata.combining(c)])
    nome = re.sub(r"\s+", " ", nome).strip()
    return nome

def identificar_loja(texto):
    texto = texto.upper()
    if "TPBR" in texto:
        return "TPBR"
    if "JPBB" in texto:
        return "JPBB"
    return None

def extrair_dados_pdf(texto):
    funcionarios = {}

    blocos = texto.split("NOME DO FUNCIONÁRIO:")

    for bloco in blocos[1:]:
        linhas = bloco.strip().split("\n")
        nome = linhas[0].strip()

        falta = re.search(r"FALTAS.*?(\d+:\d+)", bloco)
        extra = re.search(r"HORAS EXTRAS.*?(\d+:\d+)", bloco)
        noturno = re.search(r"HORAS NOTURNAS.*?(\d+:\d+)", bloco)
        horas = re.search(r"HORAS TRABALHADAS.*?(\d+:\d+)", bloco)

        funcionarios[nome] = {
            "falta": falta.group(1) if falta else "00:00",
            "extra": extra.group(1) if extra else "00:00",
            "noturno": noturno.group(1) if noturno else "00:00",
            "horas": horas.group(1) if horas else "00:00"
        }

    return funcionarios

# ==========================================
# INTERFACE
# ==========================================

st.title("🚀 Sistema Calculadora de Horas")
st.header("📤 Enviar PDF de Espelho de Ponto")

uploaded_file = st.file_uploader(
    "Selecione o PDF da loja (JPBB ou TPBR)",
    type="pdf"
)

if uploaded_file:

    texto_completo = ""

    with pdfplumber.open(uploaded_file) as pdf:
        for pagina in pdf.pages:
            texto_completo += pagina.extract_text() + "\n"

    st.success("✅ PDF lido com sucesso!")

    loja = identificar_loja(texto_completo)

    if not loja:
        st.error("❌ Não foi possível identificar a loja.")
        st.stop()

    st.info(f"🏬 Loja identificada: {loja}")

    mes = "JANEIRO"  # você pode depois automatizar isso
    aba_nome = f"{mes}_{loja}"

    worksheet = spreadsheet.worksheet(aba_nome)

    st.info(f"📄 Dados irão para aba: {aba_nome}")

    funcionarios = extrair_dados_pdf(texto_completo)

    nao_encontrados = []

    for nome_funcionario, dados in funcionarios.items():

        nome_normalizado_pdf = normalizar_nome(nome_funcionario)

        col_a = worksheet.col_values(1)

        encontrado = False

        for i, nome_planilha in enumerate(col_a):
            nome_normalizado_planilha = normalizar_nome(nome_planilha)

            if nome_normalizado_planilha == nome_normalizado_pdf:

                linha_real = i + 1

                # ==========================
                # FUNCIONÁRIO NORMAL
                # ==========================
                if linha_real < 10:

                    worksheet.update(f"B{linha_real}", dados["falta"])
                    worksheet.update(f"C{linha_real}", dados["extra"])
                    worksheet.update(f"E{linha_real}", dados["noturno"])

                # ==========================
                # BLOCO MOTOBOY
                # ==========================
                else:

                    worksheet.update(f"B{linha_real}", dados["noturno"])
                    worksheet.update(f"C{linha_real}", dados["horas"])
                    worksheet.update(f"D{linha_real}", dados["extra"])

                encontrado = True
                break

        if not encontrado:
            nao_encontrados.append(nome_funcionario)

    st.success("🎉 Dados enviados para o Google Sheets com sucesso!")

    if nao_encontrados:
        st.warning("⚠ Alguns nomes não foram encontrados na planilha:")
        st.write(nao_encontrados)
