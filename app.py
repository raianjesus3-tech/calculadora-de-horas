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

PLANILHA_URL = "https://docs.google.com/spreadsheets/d/1er5DKT8jNm4qLTgQzdT2eQL8BrxxDlceUfkASYKYEZ8/edit?gid=1614614460#gid=1614614460"
ENV_KEY_JSON = "GCP_SERVICE_ACCOUNT_JSON"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# =========================
# Helpers (tempo)
# =========================
def hhmm_to_minutes(hhmm: str) -> int:
    if not hhmm or ":" not in hhmm:
        return 0
    hhmm = hhmm.strip()
    sign = -1 if hhmm.startswith("-") else 1
    if sign == -1:
        hhmm = hhmm[1:]
    parts = hhmm.split(":")
    if len(parts) >= 2:
        h, m = parts[0], parts[1]
        return sign * (int(h) * 60 + int(m))
    return 0

def minutes_to_hhmm(minutes: int) -> str:
    sign = "-" if minutes < 0 else ""
    minutes = abs(minutes)
    return f"{sign}{minutes // 60:02d}:{minutes % 60:02d}"

# =========================
# Helpers (texto / nome)
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

def identificar_loja(texto: str):
    t = (texto or "").upper()
    if "TPBR" in t:
        return "TPBR"
    if "JPBB" in t or "JPB" in t:
        return "JPBB"
    return None

def detectar_mes_ano(texto: str):
    m = re.search(r"DE\s+(\d{2})/(\d{2})/(\d{4})\s+AT[ÉE]\s+(\d{2})/(\d{2})/(\d{4})", texto, flags=re.IGNORECASE)
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
    if not m:
        raise RuntimeError("Não consegui extrair o ID da planilha.")
    return m.group(1)

# =========================
# PDF
# =========================
def extract_full_text(pdf_file) -> str:
    with pdfplumber.open(pdf_file) as pdf:
        parts = []
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                parts.append(t)
    return "\n".join(parts)

# =========================
# Parser
# =========================
def parse_employee_blocks(texto: str):

    blocos = re.split(r"\bCart[aã]o\s+de\s+Ponto\b", texto, flags=re.IGNORECASE)
    out = []

    for bloco in blocos:

        if ("NOME DO FUNCION" not in bloco.upper()) or ("TOTAIS" not in bloco.upper()):
            continue

        nome_match = re.search(r"NOME DO FUNCION[AÁ]RIO:\s*(.+?)\s+PIS", bloco, flags=re.IGNORECASE | re.DOTALL)
        if not nome_match:
            continue

        nome = nome_match.group(1).replace("\n", " ").strip()

        cargo_match = re.search(r"NOME DO CARGO:\s*(.+)", bloco, flags=re.IGNORECASE)
        cargo = cargo_match.group(1).split("\n")[0].strip().upper() if cargo_match else ""

        totais_match = re.search(r"TOTAIS\s+([0-9:\s-]+)", bloco, flags=re.IGNORECASE)
        if not totais_match:
            continue

        horarios = re.findall(r"-?\d{1,3}:\d{2}", totais_match.group(1))

        total_normais = "00:00"
        total_noturno = "00:00"
        falta = "00:00"
        extra70 = "00:00"

        is_motoboy = "MOTOBOY" in cargo.upper()

        if is_motoboy:

            if len(horarios) >= 4:

                total_normais = horarios[1]
                total_noturno = horarios[2]
                extra70 = horarios[3]

        else:

            if len(horarios) == 5:

                total_normais = horarios[1]
                total_noturno = horarios[2]
                falta = horarios[3]
                extra70 = horarios[4]

            elif len(horarios) == 4:

                total_normais = horarios[0]
                total_noturno = horarios[1]
                falta = horarios[2]
                extra70 = horarios[3]

            elif len(horarios) == 3:

                total_normais = horarios[0]
                total_noturno = horarios[1]
                extra70 = horarios[2]

            elif len(horarios) == 2:

                total_normais = horarios[0]
                extra70 = horarios[1]

            elif len(horarios) == 1:

                total_normais = horarios[0]

        out.append({
            "NOME": nome,
            "CARGO": cargo,
            "TOTAL NORMAIS": total_normais,
            "TOTAL NOTURNO": total_noturno,
            "FALTA": falta,
            "EXTRA 70%": extra70,
        })

    return out

# =========================
# Google Sheets
# =========================
@st.cache_resource
def get_gspread_client():

    if ENV_KEY_JSON not in os.environ:
        raise RuntimeError("Credenciais Google não encontradas.")

    creds_dict = json.loads(os.environ[ENV_KEY_JSON])
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)

    return gspread.authorize(creds)

def get_sheet_and_tab(client, planilha_url: str, tab_name: str):

    sheet_id = extract_sheet_id(planilha_url)
    sh = client.open_by_key(sheet_id)
    ws = sh.worksheet(tab_name)

    return sh, ws

def map_name_to_rows(ws):

    colA = ws.col_values(1)
    mapping = {}

    for idx, val in enumerate(colA, start=1):

        n = normalize_name(val)

        if n and n not in mapping:

            mapping[n] = idx

    return mapping

def update_rows(ws, df: pd.DataFrame):

    name_map = map_name_to_rows(ws)

    colA = ws.col_values(1)

    motoboy_title_row = None

    for i, v in enumerate(colA, start=1):

        if "MOTOBOYS HORISTAS" in str(v).upper():
            motoboy_title_row = i
            break

    for _, row in df.iterrows():

        nome_pdf_norm = normalize_name(str(row["NOME"]))
        sheet_row = name_map.get(nome_pdf_norm)

        if not sheet_row:
            continue

        cargo = str(row.get("CARGO", "")).upper()

        is_motoboy = ("MOTOBOY" in cargo) or (motoboy_title_row and sheet_row > motoboy_title_row)

        falta = str(row.get("FALTA", "00:00"))
        extra = str(row.get("EXTRA 70%", "00:00"))
        noturno = str(row.get("TOTAL NOTURNO", "00:00"))
        horas = str(row.get("TOTAL NORMAIS", "00:00"))

        extra_ou_falta = minutes_to_hhmm(hhmm_to_minutes(extra) - hhmm_to_minutes(falta))

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
st.caption("Selecione o PDF da loja (JPBB ou TPBR).")

uploaded_file = st.file_uploader("Enviar PDF", type=["pdf"])

if uploaded_file:

    texto = extract_full_text(uploaded_file)

    st.success("PDF lido com sucesso!")

    loja = identificar_loja(texto)
    mes, ano = detectar_mes_ano(texto)

    tab_name = f"{mes}_{loja}"

    dados = parse_employee_blocks(texto)

    df = pd.DataFrame(dados)

    st.dataframe(df)

    client = get_gspread_client()
    _, ws = get_sheet_and_tab(client, PLANILHA_URL, tab_name)

    if st.button("Enviar para planilha"):

        update_rows(ws, df)

        st.success("Dados enviados com sucesso!")
