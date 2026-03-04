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
def hhmm_to_minutes(hhmm: str) -> int:

    if not hhmm or ":" not in hhmm:
        return 0

    sign = -1 if hhmm.startswith("-") else 1

    if sign == -1:
        hhmm = hhmm[1:]

    h, m = hhmm.split(":")[:2]

    return sign * (int(h) * 60 + int(m))


def minutes_to_hhmm(minutes: int) -> str:

    sign = "-" if minutes < 0 else ""

    minutes = abs(minutes)

    return f"{sign}{minutes // 60:02d}:{minutes % 60:02d}"


# =========================
# TEXTO
# =========================
def normalize_name(s: str) -> str:

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
def identificar_loja(texto: str):

    t = texto.upper()

    if "TPBR" in t:
        return "TPBR"

    if "JPBB" in t or "JPB" in t:
        return "JPBB"

    return None


# =========================
# MÊS
# =========================
def detectar_mes_ano(texto: str):

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
# FUNÇÃO PRINCIPAL DE LEITURA
# =========================
def find_time_for_label(section: str, label: str):

    lines = section.split("\n")

    for i, line in enumerate(lines):

        if label in line.upper():

            # tenta mesma linha
            m = re.search(r"-?\d{1,3}:\d{2}", line)
            if m:
                return m.group()

            # tenta linha abaixo
            if i + 1 < len(lines):

                m = re.search(r"-?\d{1,3}:\d{2}", lines[i + 1])

                if m:
                    return m.group()

    return "00:00"


# =========================
# PARSER
# =========================
def parse_employee_blocks(texto: str):

    blocos = re.split(r"Cart[aã]o\s+de\s+Ponto", texto, flags=re.IGNORECASE)

    out = []

    for bloco in blocos:

        if "NOME DO FUNCION" not in bloco.upper():
            continue

        nome_match = re.search(
            r"NOME DO FUNCION[AÁ]RIO:\s*(.+?)\s+PIS",
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

        section = bloco.upper()

        total_normais = find_time_for_label(section, "TOTAL NORMAIS")

        total_noturno = find_time_for_label(section, "TOTAL NOTURNO")

        falta = find_time_for_label(section, "FALTA E ATRASO")

        extra = find_time_for_label(section, "EXTRA 70%")

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

    creds_dict = json.loads(os.environ[ENV_KEY_JSON])

    creds = Credentials.from_service_account_info(
        creds_dict,
        scopes=SCOPES
    )

    return gspread.authorize(creds)


def extract_sheet_id(url):

    m = re.search(r"/d/([a-zA-Z0-9-_]+)", url)

    return m.group(1)


def get_sheet_and_tab(client, url, tab):

    sheet_id = extract_sheet_id(url)

    sh = client.open_by_key(sheet_id)

    ws = sh.worksheet(tab)

    return ws


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

st.subheader("📤 Enviar PDF de Espelho de Ponto")

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

    ws = get_sheet_and_tab(client, PLANILHA_URL, tab_name)

    if st.button("Enviar para planilha"):

        update_rows(ws, df)

        st.success("Dados enviados para Google Sheets!")
