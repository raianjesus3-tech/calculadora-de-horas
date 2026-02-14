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
    hhmm = str(hhmm).strip()
    sign = -1 if hhmm.startswith("-") else 1
    if sign == -1:
        hhmm = hhmm[1:]
    parts = hhmm.split(":")
    try:
        if len(parts) >= 2:
            h = int(parts[0])
            m = int(parts[1])
            return sign * (h * 60 + m)
    except Exception:
        return 0
    return 0


def minutes_to_hhmm(minutes: int) -> str:
    sign = "-" if minutes < 0 else ""
    minutes = abs(int(minutes))
    return f"{sign}{minutes // 60:02d}:{minutes % 60:02d}"


# =========================
# Helpers (texto / nome)
# =========================
def normalize_name(s: str) -> str:
    """Remove acentos/pontuação, normaliza espaços e deixa em MAIÚSCULO."""
    if not s:
        return ""
    s = str(s).strip().upper()
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
    """
    Procura trecho tipo: 'DE 01/01/2026 ATÉ 31/01/2026'
    Retorna ("JANEIRO", 2026).
    """
    m = re.search(
        r"DE\s+(\d{2})/(\d{2})/(\d{4})\s+AT[ÉE]\s+(\d{2})/(\d{2})/(\d{4})",
        texto or "",
        flags=re.IGNORECASE,
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
def extract_full_text(pdf_file) -> str:
    with pdfplumber.open(pdf_file) as pdf:
        parts = []
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                parts.append(t)
    return "\n".join(parts)


# =========================
# Parser (TOTAIS)
# =========================
def interpret_totais_times(times: list[str]) -> dict:
    """
    Tenta padronizar os valores:
      - TOTAL NORMAIS
      - TOTAL NOTURNO
      - FALTA (pode somar atraso quando existir)
      - EXTRA 70%

    Observado nos seus PDFs:
      len=6 -> [NOTURNAS_NORMAIS, TOTAL_NORMAIS, TOTAL_NOTURNO, FALTA, ATRASO, EXTRA]
      len=5 -> [NOTURNAS_NORMAIS, TOTAL_NORMAIS, TOTAL_NOTURNO, FALTA(ou FALTA+ATRASO), EXTRA]
      len=4 -> [TOTAL_NORMAIS, TOTAL_NOTURNO, FALTA(ou FALTA+ATRASO), EXTRA]
      len=2 -> [TOTAL_NORMAIS, TOTAL_NOTURNO]
    """
    # defaults
    total_normais = "00:00"
    total_noturno = "00:00"
    falta = "00:00"
    atraso = "00:00"
    extra70 = "00:00"

    if len(times) >= 6:
        # nn = times[0] (ignora)
        total_normais = times[1]
        total_noturno = times[2]
        falta = times[3]
        atraso = times[4]
        extra70 = times[5]
    elif len(times) == 5:
        # nn = times[0] (ignora)
        total_normais = times[1]
        total_noturno = times[2]
        falta = times[3]
        extra70 = times[4]
    elif len(times) == 4:
        total_normais = times[0]
        total_noturno = times[1]
        falta = times[2]
        extra70 = times[3]
    elif len(times) == 3:
        total_normais = times[0]
        total_noturno = times[1]
        extra70 = times[2]
    elif len(times) == 2:
        total_normais = times[0]
        total_noturno = times[1]
    elif len(times) == 1:
        total_normais = times[0]

    # soma FALTA + ATRASO quando existir
    falta_total = minutes_to_hhmm(hhmm_to_minutes(falta) + hhmm_to_minutes(atraso))

    return {
        "TOTAL NORMAIS": total_normais,
        "TOTAL NOTURNO": total_noturno,
        "FALTA": falta_total,
        "EXTRA 70%": extra70,
    }


def parse_employee_blocks(texto: str) -> list[dict]:
    """
    Retorna lista de dicts por funcionário.
    """
    t = texto or ""
    # encontra cada ocorrência do NOME DO FUNCIONÁRIO:
    starts = [m.start() for m in re.finditer(r"NOME DO FUNCION[AÁ]RIO:", t, flags=re.IGNORECASE)]
    if not starts:
        return []

    # fatia blocos entre um funcionário e outro
    blocks = []
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else len(t)
        blocks.append(t[s:e])

    out = []
    for bloco in blocks:
        # nome: pega entre "NOME DO FUNCIONÁRIO:" e "PIS"
        nome_match = re.search(
            r"NOME DO FUNCION[AÁ]RIO:\s*(.+?)\s+PIS",
            bloco,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not nome_match:
            continue
        nome = nome_match.group(1).replace("\n", " ").strip()

        # cargo (se existir)
        cargo_match = re.search(r"NOME DO CARGO:\s*(.+)", bloco, flags=re.IGNORECASE)
        cargo = cargo_match.group(1).split("\n")[0].strip().upper() if cargo_match else ""

        # pega a linha/trecho do TOTAIS
        totais_match = re.search(r"TOTAIS\s+([0-9:\s]+)", bloco, flags=re.IGNORECASE)
        if not totais_match:
            continue

        times = re.findall(r"\d{1,3}:\d{2}(?::\d{2})?", totais_match.group(1))
        vals = interpret_totais_times(times)

        out.append(
            {
                "NOME": nome,
                "CARGO": cargo,
                "TOTAL NORMAIS": vals["TOTAL NORMAIS"],
                "TOTAL NOTURNO": vals["TOTAL NOTURNO"],
                "FALTA": vals["FALTA"],
                "EXTRA 70%": vals["EXTRA 70%"],
            }
        )

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
        ws = sh.add_worksheet(title=tab_name, rows=250, cols=30)
    return sh, ws


def col_to_letter(n: int) -> str:
    # 1 -> A, 2 -> B ...
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def find_row_in_colA_containing(ws, needle_norm: str) -> int | None:
    colA = ws.col_values(1)
    for idx, val in enumerate(colA, start=1):
        if needle_norm in normalize_name(val):
            return idx
    return None


def map_name_to_rows(ws) -> dict:
    colA = ws.col_values(1)
    mapping = {}
    for idx, val in enumerate(colA, start=1):
        n = normalize_name(val)
        if n and n not in mapping:
            mapping[n] = idx
    return mapping


def read_row_values(ws, row: int, start_col: int, end_col: int) -> list[str]:
    rng = f"{col_to_letter(start_col)}{row}:{col_to_letter(end_col)}{row}"
    vals = ws.get(rng)
    if not vals:
        return []
    return [str(x) if x is not None else "" for x in vals[0]]


def header_map_from_row(values: list[str], start_col: int) -> dict:
    """
    values = ["NOME","FALTA","EXTRA",...]
    retorna {"FALTA":"B", "EXTRA":"C"...} baseado no índice.
    """
    mp = {}
    for i, v in enumerate(values):
        key = normalize_name(v)
        if not key:
            continue
        col_letter = col_to_letter(start_col + i)
        mp[key] = col_letter
    return mp


def get_layout_maps(ws):
    """
    Descobre:
      - linha do título "MOTOBOYS HORISTAS"
      - mapa de colunas do cabeçalho principal (linha 1)
      - mapa de colunas do cabeçalho motoboy (linha após o título)
    """
    # cabeçalho principal normalmente na linha 1 (A1:E1)
    main_vals = read_row_values(ws, row=1, start_col=1, end_col=10)
    main_map = header_map_from_row(main_vals, start_col=1)

    # acha a linha do título MOTOBOYS
    mot_title_row = find_row_in_colA_containing(ws, "MOTOBOYS HORISTAS")
    mot_header_map = {}
    mot_header_row = None

    if mot_title_row:
        mot_header_row = mot_title_row + 1
        mot_vals = read_row_values(ws, row=mot_header_row, start_col=1, end_col=10)
        mot_header_map = header_map_from_row(mot_vals, start_col=1)

    return main_map, mot_title_row, mot_header_row, mot_header_map


def update_rows(ws, df: pd.DataFrame):
    """
    Atualiza a aba:
      - Parte de cima: FALTA / EXTRA / EXTRA OU FALTA / NOTURNO
      - Motoboys: escreve conforme o cabeçalho (HORAS / NOTURNO / EXTRA)
    """
    name_map = map_name_to_rows(ws)
    main_map, mot_title_row, mot_header_row, mot_map = get_layout_maps(ws)

    # normaliza alias para NOTURNO (tem gente que escreve NOTUNO)
    def get_main_col(label_norm: str, fallback: str | None = None):
        if label_norm in main_map:
            return main_map[label_norm]
        if fallback and fallback in main_map:
            return main_map[fallback]
        return None

    col_falta = get_main_col("FALTA")
    col_extra = get_main_col("EXTRA")
    col_extra_ou_falta = get_main_col("EXTRA OU FALTA")
    col_noturno = get_main_col("NOTURNO", fallback="NOTUNO")  # aceita NOTUNO

    not_found = []

    for _, r in df.iterrows():
        nome_original = str(r.get("NOME", "")).strip()
        nome_norm = normalize_name(nome_original)
        if not nome_norm:
            continue

        sheet_row = name_map.get(nome_norm)
        if not sheet_row:
            not_found.append(nome_original)
            continue

        # determina se é motoboy pela POSIÇÃO (abaixo do título MOTOBOYS)
        is_motoboy = bool(mot_title_row and sheet_row > mot_title_row)

        falta = str(r.get("FALTA", "00:00"))
        extra = str(r.get("EXTRA 70%", "00:00"))
        noturno = str(r.get("TOTAL NOTURNO", "00:00"))
        horas = str(r.get("TOTAL NORMAIS", "00:00"))

        extra_ou_falta = minutes_to_hhmm(hhmm_to_minutes(extra) - hhmm_to_minutes(falta))

        updates = []

        if is_motoboy:
            # lê as colunas pelo cabeçalho real do bloco motoboy
            # (pode ser NOME | HORAS | NOTURNO | EXTRA  OU NOME | NOTURNO | HORAS | EXTRA)
            col_horas = mot_map.get("HORAS")
            col_not = mot_map.get("NOTURNO", mot_map.get("NOTUNO"))
            col_ext = mot_map.get("EXTRA")

            # se por algum motivo não achou o cabeçalho, usa fallback B/C/D
            if not col_horas:
                col_horas = "B"
            if not col_not:
                col_not = "C"
            if not col_ext:
                col_ext = "D"

            updates.extend(
                [
                    {"range": f"{col_horas}{sheet_row}", "values": [[horas]]},
                    {"range": f"{col_not}{sheet_row}", "values": [[noturno]]},
                    {"range": f"{col_ext}{sheet_row}", "values": [[extra]]},
                ]
            )
        else:
            # fallback se não achou colunas no cabeçalho
            c_falta = col_falta or "B"
            c_extra = col_extra or "C"
            c_eof = col_extra_ou_falta or "D"
            c_not = col_noturno or "E"

            updates.extend(
                [
                    {"range": f"{c_falta}{sheet_row}", "values": [[falta]]},
                    {"range": f"{c_extra}{sheet_row}", "values": [[extra]]},
                    {"range": f"{c_eof}{sheet_row}", "values": [[extra_ou_falta]]},
                    {"range": f"{c_not}{sheet_row}", "values": [[noturno]]},
                ]
            )

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
            tab_name = f"SEM_MES_{loja}"
            st.warning("Não consegui detectar o mês/ano automaticamente. Vou enviar para uma aba padrão.")
        else:
            tab_name = f"{mes}_{loja}"

        st.write(f"🏪 **Loja identificada:** {loja}")
        st.write(f"🗂️ **Dados irão para a aba:** {tab_name}")

        with st.spinner("🧩 Lendo funcionários e totais..."):
            dados = parse_employee_blocks(texto)

        if not dados:
            st.warning("Nenhum funcionário foi encontrado no PDF (ou o texto do PDF está vindo incompleto).")
            st.stop()

        df = pd.DataFrame(dados)

        with st.expander("👀 Ver prévia do que foi extraído"):
            st.dataframe(df, use_container_width=True)

        with st.spinner("🔐 Conectando no Google Sheets..."):
            client = get_gspread_client()
            _, ws = get_sheet_and_tab(client, PLANILHA_URL, tab_name)

        with st.spinner("📤 Enviando dados para a planilha..."):
            not_found = update_rows(ws, df)

        st.success("🎉 Dados enviados com sucesso!")

        if not_found:
            st.warning("⚠️ Alguns nomes do PDF não foram encontrados na coluna A da aba (confira se estão iguais):")
            st.write(not_found)
            st.info("Dica: o sistema já normaliza acentos/espaços. Se não achar, o nome está diferente na planilha.")

    except Exception as e:
        st.error("❌ Deu erro ao processar/enviar.")
        st.code(str(e))
