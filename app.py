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

PLANILHA_URL = "https://docs.google.com/spreadsheets/d/1er5DKT8jNm4qLTgQzdT2eQL8BrxxDlceUfkASYKYEZ8/edit?gid=0#gid=0"
ENV_KEY_JSON = "GCP_SERVICE_ACCOUNT_JSON"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# =========================
# Helpers tempo
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
# Helpers nome
# =========================
def normalize_name(s: str) -> str:
    if not s:
        return ""
    s = s.strip().upper()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^A-Z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def identificar_loja(texto: str):
    t = texto.upper()
    if "TPBR" in t:
        return "TPBR"
    if "JPBB" in t or "JPB" in t:
        return "JPBB"
    return None


def detectar_mes_ano(texto: str):
    m = re.search(
        r"DE\s+(\d{2})/(\d{2})/(\d{4})\s+AT[ÉE]\s+(\d{2})/(\d{2})/(\d{4})",
        texto,
        flags=re.IGNORECASE,
    )
    if not m:
        return None

    mes_num = int(m.group(2))
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
    return meses.get(mes_num)


# =========================
# PDF
# =========================
def extract_full_text(pdf_file) -> str:
    with pdfplumber.open(pdf_file) as pdf:
        text = []
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text.append(t)
    return "\n".join(text)


def parse_employee_blocks(texto: str) -> list[dict]:
    blocos = re.split(r"\bCart[aã]o\s+de\s+Ponto\b", texto, flags=re.IGNORECASE)
    out = []

    for bloco in blocos:
        if "NOME DO FUNCION" not in bloco.upper():
            continue

        nome_match = re.search(
            r"NOME DO FUNCION[AÁ]RIO:\s*(.+?)\s+PIS",
            bloco,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not nome_match:
            continue

        nome = nome_match.group(1).replace("\n", " ").strip()

        cargo_match = re.search(r"NOME DO CARGO:\s*(.+)", bloco, flags=re.IGNORECASE)
        cargo = cargo_match.group(1).split("\n")[0].strip().upper() if cargo_match else ""

        totais_match = re.search(r"TOTAIS\s+([0-9:\s]+)", bloco, flags=re.IGNORECASE)
        if not totais_match:
            continue

        horarios = re.findall(r"\d{1,3}:\d{2}", totais_match.group(1))

        falta = horarios[2] if len(horarios) >= 3 else "00:00"
        noturno = horarios[1] if len(horarios) >= 2 else "00:00"
        horas = horarios[0] if len(horarios) >= 1 else "00:00"
        extra = horarios[-1] if len(horarios) >= 4 else "00:00"

        out.append(
            {
                "NOME": nome,
                "CARGO": cargo,
                "TOTAL NORMAIS": horas,
                "TOTAL NOTURNO": noturno,
                "FALTA": falta,
                "EXTRA 70%": extra,
            }
        )

    return out


# =========================
# Google Sheets
# =========================
@st.cache_resource
def get_gspread_client():
    creds_dict = json.loads(os.environ[ENV_KEY_JSON])
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)


def map_name_to_rows(ws):
    colA = ws.col_values(1)
    mapping = {}
    for idx, val in enumerate(colA, start=1):
        n = normalize_name(val)
        if n:
            mapping[n] = idx
    return mapping


def update_rows(ws, df: pd.DataFrame):
    name_map = map_name_to_rows(ws)
    not_found = []

    for _, row in df.iterrows():
        nome_pdf_original = str(row["NOME"])
        nome_pdf = normalize_name(nome_pdf_original)

        sheet_row = None

        # 🔥 Busca inteligente
        for nome_planilha, linha in name_map.items():
            if nome_pdf in nome_planilha or nome_planilha in nome_pdf:
                sheet_row = linha
                break

        if not sheet_row:
            not_found.append(nome_pdf_original)
            continue

        is_motoboy = "MOTOBOY" in row.get("CARGO", "").upper()

        falta = row["FALTA"]
        extra = row["EXTRA 70%"]
        noturno = row["TOTAL NOTURNO"]
        horas = row["TOTAL NORMAIS"]

        extra_ou_falta = minutes_to_hhmm(
            hhmm_to_minutes(extra) - hhmm_to_minutes(falta)
        )

        if is_motoboy:
            updates = [
                {"range": f"B{sheet_row}", "values": [[horas]]},
                {"range": f"C{sheet_row}", "values": [[noturno]]},
                {"range": f"D{sheet_row}", "values": [[extra]]},
            ]
        else:
            updates = [
                {"range": f"B{sheet_row}", "values": [[falta]]},
                {"range": f"C{sheet_row}", "values": [[extra]]},
                {"range": f"D{sheet_row}", "values": [[extra_ou_falta]]},
                {"range": f"E{sheet_row}", "values": [[noturno]]},
            ]

        ws.batch_update(updates)

    return not_found


# =========================
# UI
# =========================
st.title("🚀 Sistema Calculadora de Horas")
st.subheader("📤 Enviar PDF de Espelho de Ponto")

uploaded_file = st.file_uploader("Enviar PDF", type=["pdf"])

if uploaded_file:
    try:
        texto = extract_full_text(uploaded_file)
        st.success("PDF lido com sucesso!")

        loja = identificar_loja(texto)
        mes = detectar_mes_ano(texto)

        tab_name = f"{mes}_{loja}"

        st.write("Loja:", loja)
        st.write("Aba:", tab_name)

        dados = parse_employee_blocks(texto)
        df = pd.DataFrame(dados)

        client = get_gspread_client()
        sh = client.open_by_url(PLANILHA_URL)
        ws = sh.worksheet(tab_name)

        not_found = update_rows(ws, df)

        st.success("Dados enviados com sucesso!")

        if not_found:
            st.warning("Nomes não encontrados:")
            st.write(not_found)

    except Exception as e:
        st.error("Erro:")
        st.code(str(e))
