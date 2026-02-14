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

PLANILHA_URL = "https://docs.google.com/spreadsheets/d/1er5DKT8jNm4qLTgQzdT2eQL8BrxxDlceUfkASYKYEZ8/edit#gid=1614614460"
ENV_KEY_JSON = "GCP_SERVICE_ACCOUNT_JSON"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# =========================
# FUNÇÕES DE TEMPO
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

# =========================
# NORMALIZAÇÃO DE NOME
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
# IDENTIFICAÇÃO
# =========================
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
        return None
    mes_num = int(m.group(2))
    meses = {
        1:"JANEIRO",2:"FEVEREIRO",3:"MARCO",4:"ABRIL",
        5:"MAIO",6:"JUNHO",7:"JULHO",8:"AGOSTO",
        9:"SETEMBRO",10:"OUTUBRO",11:"NOVEMBRO",12:"DEZEMBRO"
    }
    return meses.get(mes_num)

# =========================
# EXTRAÇÃO DO PDF
# =========================
def extract_full_text(pdf_file):
    with pdfplumber.open(pdf_file) as pdf:
        return "\n".join([p.extract_text() or "" for p in pdf.pages])

def parse_employee_blocks(texto):
    blocos = re.split(r"\bCart[aã]o\s+de\s+Ponto\b", texto, flags=re.IGNORECASE)
    dados = []

    for bloco in blocos:
        if "NOME DO FUNCION" not in bloco.upper():
            continue

        nome_match = re.search(r"NOME DO FUNCION[AÁ]RIO:\s*(.+?)\s+PIS", bloco, re.DOTALL)
        if not nome_match:
            continue
        nome = nome_match.group(1).replace("\n", " ").strip()

        cargo_match = re.search(r"NOME DO CARGO:\s*(.+)", bloco)
        cargo = cargo_match.group(1).split("\n")[0].strip().upper() if cargo_match else ""

        totais_match = re.search(r"TOTAIS\s+([0-9:\s]+)", bloco)
        horarios = re.findall(r"\d{1,3}:\d{2}", totais_match.group(1)) if totais_match else []

        falta = "00:00"
        extra = "00:00"
        noturno = "00:00"
        horas = "00:00"

        if len(horarios) >= 4:
            horas = horarios[0]
            noturno = horarios[1]
            falta = horarios[2]
            extra = horarios[3]

        dados.append({
            "NOME": nome,
            "CARGO": cargo,
            "FALTA": falta,
            "EXTRA 70%": extra,
            "TOTAL NOTURNO": noturno,
            "TOTAL NORMAIS": horas,
        })

    return dados

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
    not_found = []

    motoboy_row = None
    for i, val in enumerate(colA, start=1):
        if "MOTOBOYS HORISTAS" in str(val).upper():
            motoboy_row = i
            break

    for _, r in df.iterrows():

        nome_pdf = normalize_name(r["NOME"])
        linha = None

        for i, nome_planilha in enumerate(colA, start=1):
            if normalize_name(nome_planilha) == nome_pdf:
                linha = i
                break

        if not linha:
            not_found.append(r["NOME"])
            continue

        falta = r["FALTA"]
        extra = r["EXTRA 70%"]
        noturno = r["TOTAL NOTURNO"]
        horas = r["TOTAL NORMAIS"]

        extra_ou_falta = minutes_to_hhmm(
            hhmm_to_minutes(extra) - hhmm_to_minutes(falta)
        )

        if motoboy_row and linha > motoboy_row:
            ws.update(f"B{linha}", [[horas]])
            ws.update(f"C{linha}", [[noturno]])
            ws.update(f"D{linha}", [[extra]])
        else:
            ws.update(f"B{linha}", [[falta]])
            ws.update(f"C{linha}", [[extra]])
            ws.update(f"D{linha}", [[extra_ou_falta]])
            ws.update(f"E{linha}", [[noturno]])

    return not_found

# =========================
# INTERFACE
# =========================
st.title("🚀 Sistema Calculadora de Horas")

uploaded_file = st.file_uploader("Selecione o PDF", type=["pdf"])

if uploaded_file:
    texto = extract_full_text(uploaded_file)
    st.success("PDF lido com sucesso!")

    loja = identificar_loja(texto)
    mes = detectar_mes_ano(texto)

    if not loja:
        st.error("Loja não identificada.")
        st.stop()

    aba_nome = f"{mes}_{loja}" if mes else f"SEM_MES_{loja}"

    st.write("Loja:", loja)
    st.write("Aba:", aba_nome)

    dados = parse_employee_blocks(texto)
    df = pd.DataFrame(dados)

    with st.expander("Ver prévia"):
        st.dataframe(df)

    client = get_client()
    planilha = client.open_by_url(PLANILHA_URL)
    ws = planilha.worksheet(aba_nome)

    not_found = update_rows(ws, df)

    st.success("Dados enviados com sucesso!")

    if not_found:
        st.warning("Nomes não encontrados:")
        st.write(not_found)
