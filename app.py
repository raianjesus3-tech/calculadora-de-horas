import streamlit as st
import os
import json
import re
import unicodedata
import pdfplumber
import gspread
from google.oauth2.service_account import Credentials

# ==========================================================
# CONFIGURAÇÃO GOOGLE SHEETS
# ==========================================================

st.set_page_config(page_title="Sistema Calculadora de Horas")

# 🔑 Conexão segura com variável de ambiente
if "GCP_SERVICE_ACCOUNT_JSON" not in os.environ:
    st.error("Variável GCP_SERVICE_ACCOUNT_JSON não encontrada.")
    st.stop()

creds_dict = json.loads(os.environ["GCP_SERVICE_ACCOUNT_JSON"])

scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
client = gspread.authorize(creds)

# 🔐 USANDO OPEN_BY_KEY (NUNCA MAIS DÁ ERRO)
planilha = client.open_by_key("1er5DKT8jNm4qLTgQzdT2eQL8BrxxDlceUfkASYKYEZ8")

# ==========================================================
# FUNÇÕES AUXILIARES
# ==========================================================

def normalizar_nome(nome):
    nome = unicodedata.normalize("NFKD", nome)
    nome = nome.encode("ASCII", "ignore").decode("utf-8")
    nome = nome.upper().strip()
    return nome


def identificar_loja(texto):
    texto = texto.upper()
    if "TPBR" in texto:
        return "TPBR"
    elif "JPBB" in texto:
        return "JPBB"
    return None


# ==========================================================
# INTERFACE
# ==========================================================

st.title("🚀 Sistema Calculadora de Horas")
st.subheader("📤 Enviar PDF de Espelho de Ponto")

pdf = st.file_uploader("Selecione o PDF da loja (JPBB ou TPBR)", type=["pdf"])

if pdf:

    with pdfplumber.open(pdf) as arquivo:
        texto = ""
        for pagina in arquivo.pages:
            texto += pagina.extract_text() + "\n"

    st.success("PDF lido com sucesso!")

    loja = identificar_loja(texto)

    if not loja:
        st.error("Não foi possível identificar a loja no PDF.")
        st.stop()

    st.info(f"🏬 Loja identificada: {loja}")

    # ===============================
    # IDENTIFICAR MÊS
    # ===============================

    mes = None

    if "01/2026" in texto:
        mes = "JANEIRO"
    elif "02/2026" in texto:
        mes = "FEVEREIRO"
    elif "03/2026" in texto:
        mes = "MARÇO"

    if not mes:
        st.error("Não foi possível identificar o mês.")
        st.stop()

    aba_nome = f"{mes}_{loja}"

    st.info(f"📄 Dados irão para aba: {aba_nome}")

    aba = planilha.worksheet(aba_nome)

    # ===============================
    # IDENTIFICAR FUNCIONÁRIO
    # ===============================

    nomes_pdf = re.findall(r"NOME DO FUNCIONÁRIO:\s*(.+)", texto)

    if not nomes_pdf:
        st.error("Funcionário não encontrado no PDF.")
        st.stop()

    nome_funcionario = normalizar_nome(nomes_pdf[0])

    st.write(f"👤 Funcionário identificado: {nome_funcionario}")

    # ===============================
    # BUSCAR NA PLANILHA
    # ===============================

    coluna_a = aba.col_values(1)

    linha_funcionario = None

    for i, nome in enumerate(coluna_a):
        if normalizar_nome(nome) == nome_funcionario:
            linha_funcionario = i + 1
            break

    if not linha_funcionario:
        st.error("Funcionário não encontrado na planilha.")
        st.stop()

    # ===============================
    # EXTRAIR HORAS (RESUMO FINAL)
    # ===============================

    extra = re.findall(r"EXTRAS\s+(\d+:\d+)", texto)
    falta = re.findall(r"FALTAS\s+(\d+:\d+)", texto)
    noturno = re.findall(r"ADICIONAL NOTURNO\s+(\d+:\d+)", texto)

    extra = extra[0] if extra else "00:00"
    falta = falta[0] if falta else "00:00"
    noturno = noturno[0] if noturno else "00:00"

    # ===============================
    # VERIFICAR SE É MOTOBOY
    # ===============================

    coluna_a_upper = [normalizar_nome(n) for n in coluna_a]

    try:
        indice_bloco = coluna_a_upper.index("MOTOBOYS HORISTAS")
    except:
        indice_bloco = None

    if indice_bloco and linha_funcionario > indice_bloco + 1:
        # BLOCO MOTOBOY
        aba.update_cell(linha_funcionario, 2, noturno)
        aba.update_cell(linha_funcionario, 3, extra)
        aba.update_cell(linha_funcionario, 4, "00:00")
    else:
        # BLOCO NORMAL
        aba.update_cell(linha_funcionario, 2, falta)
        aba.update_cell(linha_funcionario, 3, extra)
        aba.update_cell(linha_funcionario, 5, noturno)

    st.success("🎉 Dados enviados para o Google Sheets com sucesso!")
