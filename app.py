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
    if len(parts) == 2:
        h, m = parts
        return sign * (int(h) * 60 + int(m))
    if len(parts) == 3:
        h, m, s = parts
        # ignora segundos para padronizar
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
    """Remove acentos, pontuação, múltiplos espaços e deixa em MAIÚSCULO.
    Ajuda MUITO a bater nome do PDF x nome da planilha."""
    if not s:
        return ""
    s = s.strip().upper()
    s = unicodedata.normalize("NFKD", s)
    s = "".join([c for c in s if not unicodedata.combining(c)])
    s = re.sub(r"[^A-Z0-9\s]", " ", s)  # remove pontuação
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
    """
    Procura trecho tipo:
    'DE 01/01/2026 ATÉ 31/01/2026'
    Retorna ("JANEIRO", 2026) se achar.
    """
    m = re.search(r"DE\s+(\d{2})/(\d{2})/(\d{4})\s+AT[ÉE]\s+(\d{2})/(\d{2})/(\d{4})", texto, flags=re.IGNORECASE)
    if not m:
        return None, None
    # usa o mês do "DE"
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
def extract_full_text(pdf_file) -> str:
    with pdfplumber.open(pdf_file) as pdf:
        parts = []
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                parts.append(t)
    return "\n".join(parts)


# =========================
# Parser por funcionário
# =========================
def parse_employee_blocks(texto: str) -> list[dict]:
    """
    Retorna lista de dicts:
      NOME, CARGO, NOTURNAS NORMAIS, TOTAL NORMAIS, TOTAL NOTURNO, FALTA, ATRASO, EXTRA 70%
    """
    blocos = re.split(r"\bCart[aã]o\s+de\s+Ponto\b", texto, flags=re.IGNORECASE)
    out = []

    for bloco in blocos:
        if ("NOME DO FUNCION" not in bloco.upper()) or ("TOTAIS" not in bloco.upper()):
            continue

        # NOME do funcionário: pega entre "NOME DO FUNCIONÁRIO:" e "PIS"
        nome_match = re.search(r"NOME DO FUNCION[AÁ]RIO:\s*(.+?)\s+PIS", bloco, flags=re.IGNORECASE | re.DOTALL)
        if not nome_match:
            continue
        nome = nome_match.group(1).replace("\n", " ").strip()

        # Cargo (pode quebrar linha)
        cargo_match = re.search(r"NOME DO CARGO:\s*(.+)", bloco, flags=re.IGNORECASE)
        cargo = cargo_match.group(1).split("\n")[0].strip().upper() if cargo_match else ""

        # TOTAIS
        totais_match = re.search(r"TOTAIS\s+([0-9:\s]+)", bloco, flags=re.IGNORECASE)
        if not totais_match:
            continue

        horarios = re.findall(r"\d{1,3}:\d{2}(?::\d{2})?", totais_match.group(1))

        # Defaults
        noturnas_normais = "00:00"
        total_normais = "00:00"
        total_noturno = "00:00"
        falta_e_atraso = "00:00"
        extra70 = "00:00"

        # Heurísticas comuns (TPBR/JPBB)
        if len(horarios) == 5:
            noturnas_normais, total_normais, total_noturno, falta_e_atraso, extra70 = horarios
        elif len(horarios) == 4:
            total_normais, total_noturno, falta_e_atraso, extra70 = horarios
        elif len(horarios) >= 6:
            base = horarios[:5]
            noturnas_normais, total_normais, total_noturno, falta_e_atraso, extra70 = base
        elif len(horarios) == 3:
            total_normais, total_noturno, extra70 = horarios
        elif len(horarios) == 2:
            total_normais, extra70 = horarios
        elif len(horarios) == 1:
            total_normais = horarios[0]

        # No PDF pode vir "FALTA E ATRASO" junto -> joga tudo em FALTA
        falta = falta_e_atraso
        atraso = "00:00"

        out.append({
            "NOME": nome,
            "CARGO": cargo,
            "NOTURNAS NORMAIS": noturnas_normais,
            "TOTAL NORMAIS": total_normais,
            "TOTAL NOTURNO": total_noturno,
            "FALTA": falta,
            "ATRASO": atraso,
            "EXTRA 70%": extra70,
        })

    return out


# =========================
# Google Sheets
# =========================
@st.cache_resource
def get_gspread_client():
    if ENV_KEY_JSON not in os.environ:
        raise RuntimeError(f"Variável {ENV_KEY_JSON} não encontrada no ambiente (Render).")
    creds_dict = json.loads(os.environ[ENV_KEY_JSON])
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)


def get_sheet_and_tab(client, planilha_url: str, tab_name: str):
    sh = client.open_by_url(planilha_url)
    try:
        ws = sh.worksheet(tab_name)
    except Exception:
        # se não existir, cria
        ws = sh.add_worksheet(title=tab_name, rows=200, cols=20)
    return sh, ws


def map_name_to_rows(ws) -> dict:
    """
    Lê a coluna A inteira e cria um mapa:
      NOME_NORMALIZADO -> linha (int)
    Assim funciona para a parte de cima e para motoboys embaixo.
    """
    colA = ws.col_values(1)  # coluna A
    mapping = {}
    for idx, val in enumerate(colA, start=1):
        n = normalize_name(val)
        if n and n not in mapping:
            mapping[n] = idx
    return mapping


def update_rows(ws, df: pd.DataFrame):
    """
    Atualiza a aba respeitando layout do seu modelo:
      - Funcionários (não motoboy):
          B=FALTA, C=EXTRA, D=EXTRA OU FALTA, E=NOTURNO
      - Motoboys:
          B=HORAS, C=NOTURNO, D=EXTRA
    Procura o nome na coluna A (normalizado).
    """
    name_map = map_name_to_rows(ws)

    not_found = []

    for _, row in df.iterrows():
        nome_pdf = normalize_name(str(row["NOME"]))
        if not nome_pdf:
            continue

        sheet_row = name_map.get(nome_pdf)
        if not sheet_row:
            not_found.append(row["NOME"])
            continue

        is_motoboy = "MOTOBOY" in str(row.get("CARGO", "")).upper()

        falta = row.get("FALTA", "00:00")
        extra = row.get("EXTRA 70%", "00:00")
        noturno = row.get("TOTAL NOTURNO", "00:00")
        horas = row.get("TOTAL NORMAIS", "00:00")

        extra_ou_falta = minutes_to_hhmm(hhmm_to_minutes(extra) - hhmm_to_minutes(falta))

        if is_motoboy:
            # Motoboy: B=HORAS, C=NOTURNO, D=EXTRA
            updates = [
                {"range": f"B{sheet_row}", "values": [[horas]]},
                {"range": f"C{sheet_row}", "values": [[noturno]]},
                {"range": f"D{sheet_row}", "values": [[extra]]},
            ]
        else:
            # Funcionário: B=FALTA, C=EXTRA, D=EXTRA OU FALTA, E=NOTURNO
            updates = [
                {"range": f"B{sheet_row}", "values": [[falta]]},
                {"range": f"C{sheet_row}", "values": [[extra]]},
                {"range": f"D{sheet_row}", "values": [[extra_ou_falta]]},
                {"range": f"E{sheet_row}", "values": [[noturno]]},
            ]

        # batch_update (mais rápido/estável)
        ws.batch_update(updates)

    return not_found


# =========================
# UI
# =========================
st.title("🚀 Sistema Calculadora de Horas")
st.subheader("📤 Enviar PDF de Espelho de Ponto")
st.caption("Selecione o PDF da loja (JPBB ou TPBR). O sistema identifica a loja e o mês e envia para a aba correta.")

uploaded_file = st.file_uploader("Enviar PDF", type=["pdf"])

if uploaded_file:
    try:
        with st.spinner("🔎 Lendo PDF e extraindo texto..."):
            texto = extract_full_text(uploaded_file)

        st.success("✅ PDF lido com sucesso!")

        loja = identificar_loja(texto)
        mes, ano = detectar_mes_ano(texto)

        if not loja:
            st.error("Não consegui identificar a loja (TPBR/JPBB) no PDF.")
            st.stop()
        if not mes or not ano:
            st.warning("Não consegui detectar o mês/ano automaticamente. Vou enviar para uma aba padrão.")
            tab_name = f"SEM_MES_{loja}"
        else:
            tab_name = f"{mes}_{loja}"

        st.write(f"🏪 **Loja identificada:** {loja}")
        st.write(f"🗂️ **Dados irão para a aba:** {tab_name}")

        with st.spinner("🧩 Separando funcionários e totais..."):
            dados = parse_employee_blocks(texto)

        if not dados:
            st.error("Não encontrei funcionários no PDF. (Às vezes o PDF vem como imagem; aí precisamos OCR.)")
            st.stop()

        df = pd.DataFrame(dados)

        # Mostra prévia (opcional)
        with st.expander("👀 Ver prévia do que foi extraído"):
            st.dataframe(df, use_container_width=True)

        with st.spinner("🔐 Conectando no Google Sheets..."):
            client = get_gspread_client()
            _, ws = get_sheet_and_tab(client, PLANILHA_URL, tab_name)

        with st.spinner("📤 Enviando dados para a planilha..."):
            not_found = update_rows(ws, df)

        st.success("🎉 Dados enviados para o Google Sheets com sucesso!")

        if not_found:
            st.warning("⚠️ Alguns nomes do PDF não foram encontrados na coluna A da aba (confira se estão iguais):")
            st.write(not_found)
            st.info("Dica: o sistema já normaliza acentos/espacos. Se mesmo assim não achar, é porque o nome está diferente na planilha.")

    except Exception as e:
        st.error("❌ Deu erro ao processar/enviar.")
        st.code(str(e))
