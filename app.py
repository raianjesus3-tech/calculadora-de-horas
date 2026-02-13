import streamlit as st
import pdfplumber
import re
import pandas as pd
import os
import json
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# ==============================
# CONFIG STREAMLIT
# ==============================
st.set_page_config(page_title="Leitor Cartão de Ponto", layout="centered")
st.title("📄 Leitor Inteligente - Cartão de Ponto")
st.write("Envie o PDF. O sistema separa Motoboys e integra automaticamente com Google Sheets.")

uploaded_file = st.file_uploader("Enviar PDF", type=["pdf"])

# ==============================
# FUNÇÕES DE TEMPO
# ==============================

def hhmm_to_minutes(hhmm: str) -> int:
    if not hhmm or ":" not in hhmm:
        return 0
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)

def minutes_to_hhmm(minutes: int) -> str:
    sign = "-" if minutes < 0 else ""
    minutes = abs(minutes)
    return f"{sign}{minutes // 60:02d}:{minutes % 60:02d}"

# ==============================
# LEITURA PDF
# ==============================

def extract_full_text(pdf_file):
    with pdfplumber.open(pdf_file) as pdf:
        text = ""
        for page in pdf.pages:
            content = page.extract_text()
            if content:
                text += content + "\n"
        return text

# ==============================
# PARSER
# ==============================

def parse_employee_blocks(text):
    blocks = re.split(r"\bCartão\s+de\s+Ponto\b", text)
    data = []

    for block in blocks:
        if "NOME DO FUNCIONÁRIO:" not in block or "TOTAIS" not in block:
            continue

        nome_match = re.search(r"NOME DO FUNCIONÁRIO:\s*(.+?)\s+PIS", block)
        if not nome_match:
            continue

        nome = nome_match.group(1).strip()

        cargo_match = re.search(r"NOME DO CARGO:\s*(.+)", block)
        cargo = cargo_match.group(1).split("\n")[0].strip().upper() if cargo_match else ""

        totais_match = re.search(r"TOTAIS\s+([0-9:\s]+)", block)
        if not totais_match:
            continue

        horarios = re.findall(r"\d{1,3}:\d{2}", totais_match.group(1))

        noturnas_normais = "00:00"
        total_normais = "00:00"
        total_noturno = "00:00"
        falta_e_atraso = "00:00"
        extra70 = "00:00"

        if len(horarios) >= 5:
            noturnas_normais, total_normais, total_noturno, falta_e_atraso, extra70 = horarios[:5]
        elif len(horarios) == 4:
            total_normais, total_noturno, falta_e_atraso, extra70 = horarios
        elif len(horarios) == 3:
            total_normais, total_noturno, extra70 = horarios

        data.append({
            "nome": nome,
            "cargo": cargo,
            "falta": falta_e_atraso,
            "extra": extra70,
            "noturno": total_noturno,
            "horas": total_normais
        })

    return data

# ==============================
# GOOGLE SHEETS
# ==============================

def conectar_google_sheets():
    creds_dict = json.loads(os.environ["GCP_SERVICE_ACCOUNT_JSON"])

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(credentials)

    return client

def obter_nome_mes():
    meses = {
        1: "JANEIRO",
        2: "FEVEREIRO",
        3: "MARÇO",
        4: "ABRIL",
        5: "MAIO",
        6: "JUNHO",
        7: "JULHO",
        8: "AGOSTO",
        9: "SETEMBRO",
        10: "OUTUBRO",
        11: "NOVEMBRO",
        12: "DEZEMBRO",
    }

    return meses[datetime.now().month]

def atualizar_planilha(dados_funcionarios, dados_motoboys):

    client = conectar_google_sheets()

    PLANILHA_ID = "1er5DKT8jNm4qLTgQzdT2eQL8BrxxDlceUfkASYKYEZ8"
    planilha = client.open_by_key(PLANILHA_ID)

    aba = planilha.worksheet(obter_nome_mes())

    # FUNCIONÁRIOS
    for i, func in enumerate(dados_funcionarios):
        linha = 2 + i

        extra_ou_falta = minutes_to_hhmm(
            hhmm_to_minutes(func["extra"]) - hhmm_to_minutes(func["falta"])
        )

        aba.update(f"A{linha}:E{linha}", [[
            func["nome"],
            func["falta"],
            func["extra"],
            extra_ou_falta,
            func["noturno"]
        ]])

    # MOTOBOYS
    for i, moto in enumerate(dados_motoboys):
        linha = 11 + i

        aba.update(f"A{linha}:D{linha}", [[
            moto["nome"],
            moto["noturno"],
            moto["horas"],
            moto["extra"]
        ]])

# ==============================
# EXECUÇÃO
# ==============================

if uploaded_file:

    with st.spinner("🔄 Processando PDF e integrando com planilha..."):
        
        text = extract_full_text(uploaded_file)
        data = parse_employee_blocks(text)

        if not data:
            st.error("Nenhum funcionário encontrado no PDF.")
            st.stop()

        # Separar Motoboys
        funcionarios = [d for d in data if "MOTOBOY" not in d["cargo"]]
        motoboys = [d for d in data if "MOTOBOY" in d["cargo"]]

        atualizar_planilha(funcionarios, motoboys)

    st.success("✅ Planilha atualizada com sucesso!")

    st.subheader("Funcionários")
    st.dataframe(pd.DataFrame(funcionarios))

    st.subheader("Motoboys")
    st.dataframe(pd.DataFrame(motoboys))
