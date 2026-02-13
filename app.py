import streamlit as st
import os
import json
import re
import pdfplumber
import gspread
from google.oauth2.service_account import Credentials

# ========================================
# CONFIGURAÇÃO GOOGLE SHEETS
# ========================================

PLANILHA_URL = "https://docs.google.com/spreadsheets/d/1er5DKT8jNm4qLTgQzdT2eQL8BrxxDlceUfkASYKYEZ8"

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

# ========================================
# INTERFACE
# ========================================

st.title("🚀 Sistema Calculadora de Horas")
st.subheader("📤 Enviar PDF de Espelho de Ponto")

pdf_file = st.file_uploader(
    "Selecione o PDF da loja (JPBB ou TPBR)",
    type="pdf"
)

# ========================================
# IDENTIFICAR LOJA
# ========================================

def identificar_loja(texto):
    texto = texto.upper()
    if "TPBR" in texto:
        return "TPBR"
    elif "JPBB" in texto:
        return "JPBB"
    return None

# ========================================
# EXTRAIR DADOS DO PDF
# ========================================

def extrair_dados(texto):
    funcionarios = {}

    linhas = texto.split("\n")

    for linha in linhas:
        linha = linha.strip()

        # Exemplo de padrão simples (ajustaremos conforme seu PDF)
        match = re.search(r"([A-Z\s]+)\s+(\d+:\d+)\s+(\d+:\d+)\s+(-?\d+:\d+)", linha)

        if match:
            nome = match.group(1).strip()
            extra = match.group(2)
            noturno = match.group(3)
            falta = match.group(4)

            funcionarios[nome] = {
                "extra": extra,
                "noturno": noturno,
                "falta": falta
            }

    return funcionarios

# ========================================
# PROCESSAR PDF
# ========================================

if pdf_file is not None:

    with st.spinner("⏳ Processando PDF..."):
        with pdfplumber.open(pdf_file) as pdf:
            texto_completo = ""
            for pagina in pdf.pages:
                texto_completo += pagina.extract_text() + "\n"

    st.success("✅ PDF lido com sucesso!")

    # DEBUG (mostrar texto)
    st.write("📄 Texto extraído:")
    st.text(texto_completo[:2000])

    loja = identificar_loja(texto_completo)

    if not loja:
        st.error("❌ Não foi possível identificar a loja no PDF.")
        st.stop()

    st.write(f"🏬 Loja identificada: {loja}")

    mes = "FEVEREIRO"  # depois podemos automatizar
    nome_aba = f"{mes}_{loja}"

    try:
        planilha = client.open_by_url(PLANILHA_URL)
        aba = planilha.worksheet(nome_aba)
    except:
        st.error(f"❌ Aba {nome_aba} não encontrada.")
        st.stop()

    dados = extrair_dados(texto_completo)

    if not dados:
        st.warning("⚠ Nenhum funcionário identificado no PDF.")
    else:
        st.write("📊 Funcionários encontrados:")
        st.write(dados)

        # Buscar nomes na planilha
        nomes_planilha = aba.col_values(1)

        for nome_pdf, info in dados.items():
            for i, nome_planilha in enumerate(nomes_planilha):
                if nome_pdf.upper() in nome_planilha.upper():

                    linha = i + 1

                    aba.update(f"B{linha}", info["falta"])
                    aba.update(f"C{linha}", info["extra"])
                    aba.update(f"E{linha}", info["noturno"])

        st.success("🎉 Dados enviados para o Google Sheets com sucesso!")
