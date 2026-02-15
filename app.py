import streamlit as st
import pdfplumber
import re
import pandas as pd
import os
import json
import unicodedata
import gspread
from google.oauth2.service_account import Credentials

# =========================
# CONFIG
# =========================
st.set_page_config(page_title="Sistema Calculadora de Horas", layout="wide")

PLANILHA_URL = "https://docs.google.com/spreadsheets/d/1er5DKT8jNm4qLTgQzdT2eQL8BrxxDlceUfkASYKYEZ8/edit?gid=1614614460#gid=1614614460"
ENV_KEY_JSON = "GCP_SERVICE_ACCOUNT_JSON"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# =========================
# HELPERS
# =========================
def hhmm_to_minutes(hhmm: str) -> int:
    if not hhmm or ":" not in hhmm:
        return 0
    hhmm = hhmm.strip()
    sign = -1 if hhmm.startswith("-") else 1
    if sign == -1:
        hhmm = hhmm[1:]
    h, m = hhmm.split(":")[:2]
    return sign * (int(h) * 60 + int(m))

def minutes_to_hhmm(minutes: int) -> str:
    sign = "-" if minutes < 0 else ""
    minutes = abs(minutes)
    return f"{sign}{minutes // 60:02d}:{minutes % 60:02d}"

def normalize_name(s: str) -> str:
    if not s:
        return ""
    s = s.strip().upper()
    s = unicodedata.normalize("NFKD", s)
    s = "".join([c for c in s if not unicodedata.combining(c)])
    s = re.sub(r"[^A-Z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def identificar_loja(texto: str):
    t = texto.upper()
    if "TPBR" in t:
        return "TPBR"
    if "JPBB" in t:
        return "JPBB"
    return None

def detectar_mes_ano(texto: str):
    m = re.search(r"DE\s+(\d{2})/(\d{2})/(\d{4})", texto)
    if not m:
        return None, None
    mes_num = int(m.group(2))
    ano = int(m.group(3))
    meses = {
        1: "JANEIRO", 2: "FEVEREIRO", 3: "MARCO", 4: "ABRIL",
        5: "MAIO", 6: "JUNHO", 7: "JULHO", 8: "AGOSTO",
        9: "SETEMBRO", 10: "OUTUBRO", 11: "NOVEMBRO", 12: "DEZEMBRO",
    }
    return meses.get(mes_num), ano

def extract_sheet_id(url: str) -> str:
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", url)
    return m.group(1)

def extract_full_text(pdf_file):
    with pdfplumber.open(pdf_file) as pdf:
        return "\n".join([p.extract_text() or "" for p in pdf.pages])

# =========================
# PARSER
# =========================
def parse_employee_blocks(texto):
    blocos = re.split(r"\bCart[aã]o\s+de\s+Ponto\b", texto, flags=re.IGNORECASE)
    out = []

    for bloco in blocos:
        if "NOME DO FUNCION" not in bloco.upper():
            continue

        nome_match = re.search(r"NOME DO FUNCION[AÁ]RIO:\s*(.+?)\s+PIS", bloco, re.DOTALL)
        if not nome_match:
            continue
        nome = nome_match.group(1).replace("\n", " ").strip()

        totais_match = re.search(r"TOTAIS\s+([0-9:\s-]+)", bloco)
        if not totais_match:
            continue

        horarios = re.findall(r"\d{1,3}:\d{2}", totais_match.group(1))

        total_normais = horarios[0] if len(horarios) > 0 else "00:00"
        total_noturno = horarios[1] if len(horarios) > 1 else "00:00"
        falta = horarios[2] if len(horarios) > 2 else "00:00"
        extra70 = horarios[3] if len(horarios) > 3 else "00:00"

        out.append({
            "NOME": nome,
            "TOTAL NORMAIS": total_normais,
            "TOTAL NOTURNO": total_noturno,
            "FALTA": falta,
            "EXTRA 70%": extra70,
        })

    return out

# =========================
# GOOGLE SHEETS
# =========================
@st.cache_resource
def get_client():
    creds_dict = json.loads(os.environ[ENV_KEY_JSON])
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)

def update_rows(ws, df):
    colA = ws.col_values(1)

    for _, r in df.iterrows():
        nome_pdf = normalize_name(r["NOME"])
        linha = None

        for i, nome_planilha in enumerate(colA, start=1):
            if normalize_name(nome_planilha) == nome_pdf:
                linha = i
                break

        if not linha:
            continue

        falta = r["FALTA"]
        extra = r["EXTRA 70%"]
        noturno = r["TOTAL NOTURNO"]
        horas = r["TOTAL NORMAIS"]

        extra_ou_falta = minutes_to_hhmm(
            hhmm_to_minutes(extra) - hhmm_to_minutes(falta)
        )

        ws.update(f"B{linha}", [[falta]])
        ws.update(f"C{linha}", [[extra]])
        ws.update(f"D{linha}", [[extra_ou_falta]])
        ws.update(f"E{linha}", [[noturno]])

# =========================
# INTERFACE COM ABAS
# =========================
st.markdown("# 🚀 Sistema Calculadora de Horas")

aba1, aba2 = st.tabs(["📄 Processar PDF", "📊 Dashboard Executivo"])

with aba1:

    st.subheader("📤 Enviar PDF")
    uploaded_file = st.file_uploader("Selecione o PDF", type=["pdf"])

    if uploaded_file:

        texto = extract_full_text(uploaded_file)
        loja = identificar_loja(texto)
        mes, ano = detectar_mes_ano(texto)

        dados = parse_employee_blocks(texto)
        df = pd.DataFrame(dados)

        st.success("PDF processado com sucesso!")
        st.dataframe(df, use_container_width=True)

        client = get_client()
        planilha = client.open_by_key(extract_sheet_id(PLANILHA_URL))
        ws = planilha.worksheet(f"{mes}_{loja}")

        update_rows(ws, df)

        st.success("Dados enviados para o Google Sheets!")

with aba2:

    st.subheader("📊 Visão Executiva")

    if 'df' in locals() and not df.empty:

        total_extra = df["EXTRA 70%"].apply(hhmm_to_minutes).sum() / 60
        total_falta = df["FALTA"].apply(hhmm_to_minutes).sum() / 60
        total_noturno = df["TOTAL NOTURNO"].apply(hhmm_to_minutes).sum() / 60

        col1, col2, col3 = st.columns(3)

        col1.metric("⏱ Total Horas Extras", f"{round(total_extra,2)}h")
        col2.metric("⚠ Total Horas Falta", f"{round(total_falta,2)}h")
        col3.metric("🌙 Total Horas Noturnas", f"{round(total_noturno,2)}h")

        grafico = pd.DataFrame({
            "Categoria": ["Extra", "Falta", "Noturno"],
            "Horas": [total_extra, total_falta, total_noturno]
        })

        st.bar_chart(grafico.set_index("Categoria"))

    else:
        st.info("Envie um PDF primeiro para visualizar o dashboard.")
