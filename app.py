import streamlit as st
import os
import json
import re
import gspread
import pdfplumber
from google.oauth2.service_account import Credentials

# ===============================
# CONFIGURAÇÃO INICIAL
# ===============================

st.set_page_config(page_title="Sistema Calculadora de Horas", layout="wide")

st.title("🚀 Sistema Calculadora de Horas")

# ===============================
# CONECTAR GOOGLE SHEETS
# ===============================

try:
    if "GCP_SERVICE_ACCOUNT_JSON" not in os.environ:
        st.error("❌ Variável GCP_SERVICE_ACCOUNT_JSON não encontrada.")
        st.stop()

    creds_dict = json.loads(os.environ["GCP_SERVICE_ACCOUNT_JSON"])

    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)

except Exception as e:
    st.error("❌ Erro na conexão com Google Sheets")
    st.code(str(e))
    st.stop()

# ===============================
# URL DA PLANILHA (COLOQUE ENTRE ASPAS!)
# ===============================

PLANILHA_URL = "https://docs.google.com/spreadsheets/d/1er5DKT8jNm4qLTgQzdT2eQL8BrxxDlceUfkASYKYEZ8"

planilha = client.open_by_url(PLANILHA_URL)

# ===============================
# IDENTIFICAR LOJA
# ===============================

def identificar_loja(texto):
    texto = texto.upper()
    if "TPBR" in texto:
        return "TPBR"
    elif "JPBB" in texto:
        return "JPBB"
    return None

# ===============================
# UPLOAD PDF
# ===============================

st.header("📤 Enviar PDF de Espelho de Ponto")

pdf_file = st.file_uploader("Selecione o PDF da loja (JPBB ou TPBR)", type=["pdf"])

if pdf_file:

    texto_extraido = ""

    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            texto_extraido += page.extract_text() + "\n"

    st.success("✅ PDF lido com sucesso!")

    # ===============================
    # IDENTIFICAR LOJA
    # ===============================

    loja = identificar_loja(texto_extraido)

    if not loja:
        st.error("❌ Loja não identificada no PDF.")
        st.stop()

    st.write("🏬 Loja identificada:", loja)

    # ===============================
    # IDENTIFICAR MÊS
    # ===============================

    match_mes = re.search(r"DE\s+(\d{2})/(\d{2})/(\d{4})", texto_extraido)

    if match_mes:
        mes_num = match_mes.group(2)
        ano = match_mes.group(3)
    else:
        st.error("❌ Não foi possível identificar o mês no PDF.")
        st.stop()

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
        "12": "DEZEMBRO",
    }

    nome_aba = f"{meses[mes_num]}_{loja}"

    try:
        aba = planilha.worksheet(nome_aba)
    except:
        st.error(f"❌ Aba {nome_aba} não encontrada na planilha.")
        st.stop()

    st.write("📄 Dados irão para aba:", nome_aba)

    # ===============================
    # IDENTIFICAR NOME FUNCIONÁRIO
    # ===============================

    match_nome = re.search(r"NOME DO FUNCIONÁRIO:\s*(.+)", texto_extraido)

    if match_nome:
        nome_funcionario = match_nome.group(1).strip().upper()
    else:
        st.error("❌ Não foi possível identificar o nome do funcionário.")
        st.stop()

    st.write("👤 Funcionário identificado:", nome_funcionario)

    # ===============================
    # EXTRAIR HORAS (AJUSTE SE NECESSÁRIO)
    # ===============================

    # Aqui você pode melhorar depois
    total_extra = "00:00"
    total_noturno = "00:00"
    total_falta = "00:00"

    # ===============================
    # ENVIAR PARA PLANILHA
    # ===============================

    dados = aba.get_all_values()

    linha_funcionario = None

    for i, linha in enumerate(dados):
        if linha and linha[0].strip().upper() == nome_funcionario:
            linha_funcionario = i + 1
            break

    if not linha_funcionario:
        st.error("❌ Funcionário não encontrado na planilha.")
        st.stop()

    # Atualizar colunas
    aba.update(f"B{linha_funcionario}", total_falta)
    aba.update(f"C{linha_funcionario}", total_extra)
    aba.update(f"E{linha_funcionario}", total_noturno)

    st.success("🎉 Dados enviados para o Google Sheets com sucesso!")
