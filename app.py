import streamlit as st
import pdfplumber
import re
import os
import json
import unicodedata
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Sistema Calculadora de Horas")

st.title("🚀 Sistema Calculadora de Horas")
st.subheader("📤 Enviar PDF de Espelho de Ponto")

# =========================
# GOOGLE AUTH
# =========================

scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds_dict = json.loads(os.environ["GCP_SERVICE_ACCOUNT_JSON"])
creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
client = gspread.authorize(creds)

PLANILHA_URL = "COLE_AQUI_SUA_URL_DA_PLANILHA"
planilha = client.open_by_url(PLANILHA_URL)

# =========================
# FUNÇÕES AUXILIARES
# =========================

def normalizar_nome(nome):
    nome = unicodedata.normalize("NFKD", nome)
    nome = nome.encode("ASCII", "ignore").decode("utf-8")
    return nome.upper().strip()

def identificar_loja(texto):
    texto = texto.upper()
    if "TPBR" in texto:
        return "TPBR"
    if "JPBB" in texto:
        return "JPBB"
    return None

def extrair_texto_pdf(pdf_file):
    texto_completo = ""
    with pdfplumber.open(pdf_file) as pdf:
        for pagina in pdf.pages:
            texto_completo += pagina.extract_text() + "\n"
    return texto_completo

# =========================
# EXTRAIR DADOS
# =========================

def extrair_dados_pdf(texto):
    funcionarios = {}

    blocos = texto.split("NOME DO FUNCIONÁRIO:")

    for bloco in blocos[1:]:

        linhas = bloco.strip().split("\n")
        linha_nome = linhas[0]

        # 🔥 CORREÇÃO PRINCIPAL
        nome = linha_nome.split("PIS DO FUNCIONÁRIO")[0].strip()
        nome = normalizar_nome(nome)

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

# =========================
# ENVIAR PARA SHEETS
# =========================

def enviar_para_planilha(funcionarios, aba_nome):
    aba = planilha.worksheet(aba_nome)

    nomes_planilha = aba.col_values(1)

    for nome_pdf, dados in funcionarios.items():

        nome_pdf_norm = normalizar_nome(nome_pdf)

        for i, nome_sheet in enumerate(nomes_planilha):
            if normalizar_nome(nome_sheet) == nome_pdf_norm:

                linha = i + 1

                # BLOCO NORMAL
                if linha < 10:
                    aba.update(f"B{linha}", dados["falta"])
                    aba.update(f"C{linha}", dados["extra"])
                    aba.update(f"E{linha}", dados["noturno"])

                # BLOCO MOTOBOY
                else:
                    aba.update(f"C{linha}", dados["noturno"])
                    aba.update(f"D{linha}", dados["horas"])
                    aba.update(f"E{linha}", dados["extra"])

                break

# =========================
# UPLOAD PDF
# =========================

pdf_file = st.file_uploader("Selecione o PDF da loja (JPBB ou TPBR)", type=["pdf"])

if pdf_file:

    texto = extrair_texto_pdf(pdf_file)

    loja = identificar_loja(texto)

    if not loja:
        st.error("❌ Loja não identificada no PDF.")
        st.stop()

    st.success(f"📌 Loja identificada: {loja}")

    funcionarios = extrair_dados_pdf(texto)

    mes = st.selectbox("Selecione o mês:", [
        "JANEIRO",
        "FEVEREIRO",
        "MARÇO",
        "ABRIL",
        "MAIO",
        "JUNHO",
        "JULHO",
        "AGOSTO",
        "SETEMBRO",
        "OUTUBRO",
        "NOVEMBRO",
        "DEZEMBRO"
    ])

    aba_nome = f"{mes}_{loja}"

    enviar_para_planilha(funcionarios, aba_nome)

    st.success("🎉 Dados enviados para o Google Sheets com sucesso!")
