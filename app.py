import streamlit as st
import pdfplumber
import re
import pandas as pd
import os
import json
import unicodedata
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(
    page_title="Sistema Calculadora de Horas",
    page_icon="⏱",
    layout="wide"
)

# =========================
# VISUAL
# =========================

st.markdown("""
<style>
.big-title {
    font-size:32px;
    font-weight:bold;
}
.card {
    background-color:#1e1e1e;
    padding:20px;
    border-radius:10px;
}
</style>
""", unsafe_allow_html=True)

st.markdown('<p class="big-title">⏱ Sistema Calculadora de Horas</p>', unsafe_allow_html=True)

st.caption("Versão 4 • Sistema Profissional")

# =========================
# CONFIG
# =========================

PLANILHA_URL = "https://docs.google.com/spreadsheets/d/1er5DKT8jNm4qLTgQzdT2eQL8BrxxDlceUfkASYKYEZ8/edit"
ENV_KEY_JSON = "GCP_SERVICE_ACCOUNT_JSON"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# =========================
# FUNÇÕES DE TEMPO
# =========================

def hhmm_to_minutes(hhmm):

    if not hhmm or ":" not in str(hhmm):
        return 0

    sign = -1 if str(hhmm).startswith("-") else 1

    hhmm = str(hhmm).replace("-", "")

    h, m = hhmm.split(":")

    return sign * (int(h) * 60 + int(m))


def minutes_to_hhmm(minutes):

    sign = "-" if minutes < 0 else ""

    minutes = abs(minutes)

    return f"{sign}{minutes//60:02d}:{minutes%60:02d}"

# =========================
# NORMALIZAÇÃO
# =========================

def normalize_name(s):

    if not s:
        return ""

    s = s.strip().upper()

    s = unicodedata.normalize("NFKD", s)

    s = "".join(c for c in s if not unicodedata.combining(c))

    s = re.sub(r"[^A-Z0-9\s]", "", s)

    s = re.sub(r"\s+", " ", s)

    return s.strip()

# =========================
# PDF
# =========================

def extract_full_text(pdf_file):

    with pdfplumber.open(pdf_file) as pdf:

        text = []

        for page in pdf.pages:

            t = page.extract_text()

            if t:
                text.append(t)

        return "\n".join(text)

# =========================
# PARSER
# =========================

def parse_employee_blocks(texto):

    blocos = re.split(r"NOME DO FUNCION", texto, flags=re.IGNORECASE)

    out = []

    for bloco in blocos:

        bloco = "NOME DO FUNCION" + bloco

        if "PIS" not in bloco:
            continue

        nome_match = re.search(
            r"NOME DO FUNCION[ÁA]RIO:\s*(.+?)\s+PIS",
            bloco,
            flags=re.IGNORECASE | re.DOTALL
        )

        if not nome_match:
            continue

        nome = nome_match.group(1).replace("\n", " ").strip()

        cargo_match = re.search(
            r"NOME DO CARGO:\s*(.+)",
            bloco,
            flags=re.IGNORECASE
        )

        cargo = cargo_match.group(1).split("\n")[0].strip() if cargo_match else ""

        totais_match = re.search(
            r"TOTAIS\s*(.*)",
            bloco,
            flags=re.IGNORECASE
        )

        totais_line = totais_match.group(1) if totais_match else ""

        horarios = re.findall(r"\d{1,3}:\d{2}", totais_line)

        total_normais = "00:00"
        total_noturno = "00:00"
        falta = "00:00"
        extra = "00:00"

        if len(horarios) == 2:

            total_normais = horarios[0]
            extra = horarios[1]

        elif len(horarios) == 3:

            total_normais = horarios[0]
            falta = horarios[1]
            extra = horarios[2]

        elif len(horarios) == 4:

            total_normais = horarios[1]
            total_noturno = horarios[2]
            extra = horarios[3]

        elif len(horarios) >= 5:

            total_normais = horarios[1]
            total_noturno = horarios[2]
            falta = horarios[3]
            extra = horarios[4]

        out.append({
            "NOME": nome,
            "CARGO": cargo,
            "TOTAL NORMAIS": total_normais,
            "TOTAL NOTURNO": total_noturno,
            "FALTA": falta,
            "EXTRA 70%": extra
        })

    return out

# =========================
# GOOGLE SHEETS
# =========================

@st.cache_resource
def get_client():

    creds_raw = os.environ.get(ENV_KEY_JSON)

    creds_dict = json.loads(creds_raw)

    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)

    return gspread.authorize(creds)

def extract_sheet_id(url):

    m = re.search(r"/d/([a-zA-Z0-9-_]+)", url)

    return m.group(1)

# =========================
# UI
# =========================

uploaded_file = st.file_uploader("Enviar espelho de ponto", type=["pdf"])

if uploaded_file:

    with st.spinner("⏳ Lendo PDF..."):

        texto = extract_full_text(uploaded_file)

    with st.spinner("⏳ Extraindo funcionários..."):

        dados = parse_employee_blocks(texto)

    df = pd.DataFrame(dados)

    st.success("Funcionários extraídos com sucesso")

    col1, col2, col3 = st.columns(3)

    col1.metric("Funcionários", len(df))
    col2.metric("Motoboys", len(df[df["CARGO"].str.contains("MOTOBOY", case=False, na=False)]))
    col3.metric("Total registros", len(df))

    st.subheader("Conferência")

    st.dataframe(df, use_container_width=True)

    if st.button("Enviar para planilha"):

        with st.spinner("⏳ Enviando para Google Sheets..."):

            client = get_client()

            sheet_id = extract_sheet_id(PLANILHA_URL)

            sh = client.open_by_key(sheet_id)

            st.success("Dados enviados com sucesso!")
