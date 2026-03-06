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
st.set_page_config(page_title="Calculadora de Horas", layout="wide")

PLANILHA_URL = "https://docs.google.com/spreadsheets/d/1er5DKT8jNm4qLTgQzdT2eQL8BrxxDlceUfkASYKYEZ8/edit"
ENV_KEY_JSON = "GCP_SERVICE_ACCOUNT_JSON"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# =========================
# TEMPO
# =========================
def hhmm_to_minutes(hhmm):

    if not hhmm or ":" not in str(hhmm):
        return 0

    sign = -1 if str(hhmm).startswith("-") else 1
    hhmm = str(hhmm).replace("-", "")

    h, m = hhmm.split(":")[:2]

    return sign * (int(h) * 60 + int(m))


def minutes_to_hhmm(minutes):

    sign = "-" if minutes < 0 else ""

    minutes = abs(minutes)

    return f"{sign}{minutes // 60:02d}:{minutes % 60:02d}"

# =========================
# TEXTO
# =========================
def normalize_name(s):

    if not s:
        return ""

    s = s.strip().upper()

    s = unicodedata.normalize("NFKD", s)

    s = "".join([c for c in s if not unicodedata.combining(c)])

    s = re.sub(r"[^A-Z0-9\s]", " ", s)

    s = re.sub(r"\s+", " ", s).strip()

    return s

# =========================
# LOJA
# =========================
def identificar_loja(texto):

    t = texto.upper()

    if "TPBR" in t:
        return "TPBR"

    if "JPBB" in t or "JPB" in t:
        return "JPBB"

    return None

# =========================
# MÊS
# =========================
def detectar_mes_ano(texto):

    m = re.search(
        r"DE\s+(\d{2})/(\d{2})/(\d{4})\s+AT",
        texto,
        flags=re.IGNORECASE
    )

    if not m:
        return None, None

    mes_num = int(m.group(2))
    ano = int(m.group(3))

    meses = {
        1: "JANEIRO",
        2: "FEVEREIRO",
        3: "MARCO",
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

    return meses.get(mes_num), ano

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
def get_gspread_client():

    creds_raw = os.environ.get(ENV_KEY_JSON)

    if not creds_raw:
        st.error("Credenciais Google não encontradas.")
        st.stop()

    creds_dict = json.loads(creds_raw)

    creds = Credentials.from_service_account_info(
        creds_dict,
        scopes=SCOPES
    )

    return gspread.authorize(creds)

def extract_sheet_id(url):

    m = re.search(r"/d/([a-zA-Z0-9-_]+)", url)

    return m.group(1)

def map_name_to_rows(ws):

    colA = ws.col_values(1)

    mapping = {}

    for i, name in enumerate(colA, start=1):

        n = normalize_name(name)

        if n:
            mapping[n] = i

    return mapping

# =========================
# ENVIO
# =========================
def update_rows(ws, df):

    name_map = map_name_to_rows(ws)

    colA = ws.col_values(1)

    motoboy_row = None

    for i, v in enumerate(colA, start=1):

        if "MOTOBOYS HORISTAS" in v.upper():
            motoboy_row = i

    for _, row in df.iterrows():

        nome = normalize_name(row["NOME"])

        sheet_row = name_map.get(nome)

        if not sheet_row:
            continue

        cargo = row["CARGO"].upper()

        is_motoboy = "MOTOBOY" in cargo or sheet_row > motoboy_row

        falta = row["FALTA"]
        extra = row["EXTRA 70%"]
        noturno = row["TOTAL NOTURNO"]
        horas = row["TOTAL NORMAIS"]

        extra_ou_falta = minutes_to_hhmm(
            hhmm_to_minutes(extra) - hhmm_to_minutes(falta)
        )

        if is_motoboy:

            ws.update(f"B{sheet_row}", [[horas]])
            ws.update(f"C{sheet_row}", [[noturno]])
            ws.update(f"D{sheet_row}", [[extra]])

        else:

            ws.update(f"B{sheet_row}", [[falta]])
            ws.update(f"C{sheet_row}", [[extra]])
            ws.update(f"D{sheet_row}", [[extra_ou_falta]])
            ws.update(f"E{sheet_row}", [[noturno]])

# =========================
# UI
# =========================
st.title("🚀 Sistema Calculadora de Horas")

uploaded_file = st.file_uploader("Enviar PDF", type=["pdf"])

if uploaded_file:

    texto = extract_full_text(uploaded_file)

    loja = identificar_loja(texto)

    mes, ano = detectar_mes_ano(texto)

    tab_name = f"{mes}_{loja}"

    dados = parse_employee_blocks(texto)

    df = pd.DataFrame(dados)

    st.dataframe(df)

    client = get_gspread_client()

    sheet_id = extract_sheet_id(PLANILHA_URL)

    sh = client.open_by_key(sheet_id)

    try:
        ws = sh.worksheet(tab_name)
    except:
        ws = sh.add_worksheet(title=tab_name, rows="100", cols="20")

    if st.button("Enviar para planilha"):

        update_rows(ws, df)

        st.success("Dados enviados para Google Sheets!")
