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


def _cut_seconds(h: str) -> str:
    """Corta segundos se vier HH:MM:SS -> HH:MM"""
    if not h:
        return "00:00"
    h = h.strip()
    m = re.match(r"^-?\d{1,3}:\d{2}(:\d{2})?$", h)
    if not m:
        return "00:00"
    # Se tiver segundos, corta
    if len(h.split(":")) == 3:
        return ":".join(h.split(":")[:2])
    return h


# =========================
# Helpers (texto / nome)
# =========================
def normalize_name(s: str) -> str:
    """Remove acentos, pontuação, múltiplos espaços e deixa MAIÚSCULO."""
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
    """
    Ex: 'DE 01/01/2026 ATÉ 31/01/2026' -> ("JANEIRO", 2026)
    """
    m = re.search(
        r"DE\s+(\d{2})/(\d{2})/(\d{4})\s+AT[ÉE]\s+(\d{2})/(\d{2})/(\d{4})",
        texto,
        flags=re.IGNORECASE,
    )
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
    """
    Evita erro NoValidUrlKeyFound. Pega o ID da planilha do link.
    """
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", url)
    if not m:
        raise RuntimeError("Não consegui extrair o ID da planilha do link.")
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
# Parser por funcionário (ROBUSTO POR ROTULO)
# =========================
def _get_totais_section(bloco: str) -> str:
    """
    Pega um trecho "grande o suficiente" após a palavra TOTAIS
    para achar os rótulos e seus horários, sem depender de posição.
    """
    up = bloco.upper()
    idx = up.find("TOTAIS")
    if idx == -1:
        return ""
    # pega um pedaço após "TOTAIS" (normalmente cabe a tabela inteira)
    tail = bloco[idx: idx + 1200]
    return tail


def _find_time_for_label(section: str, label: str) -> str:
    """
    Encontra o primeiro horário que aparece logo após um rótulo.
    Funciona mesmo se o horário estiver na linha de baixo.
    """
    # tenta "LABEL  12:34" ou "LABEL: 12:34" ou "LABEL\n12:34"
    pattern = (
        rf"{re.escape(label)}"
        rf"(?:\s*[:\-]?\s*)"
        rf"(?:\n\s*)?"
        rf"(-?\d{{1,3}}:\d{{2}}(?::\d{{2}})?)"
    )
    m = re.search(pattern, section, flags=re.IGNORECASE)
    if not m:
        return "00:00"
    return _cut_seconds(m.group(1))


def parse_employee_blocks(texto: str) -> list[dict]:
    """
    Retorna lista com:
      NOME, CARGO,
      TOTAL NORMAIS, TOTAL NOTURNO,
      FALTA (vem do FALTA E ATRASO),
      EXTRA 70%,
      NOTURNAS NORMAIS (se existir)
    """
    blocos = re.split(r"\bCart[aã]o\s+de\s+Ponto\b", texto, flags=re.IGNORECASE)
    out = []

    for bloco in blocos:
        up = bloco.upper()
        if ("NOME DO FUNCION" not in up) or ("TOTAIS" not in up):
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

        section = _get_totais_section(bloco)
        if not section:
            continue

        # ✅ Lê por rótulo (não por posição)
        total_normais = _find_time_for_label(section, "TOTAL NORMAIS")
        total_noturno = _find_time_for_label(section, "TOTAL NOTURNO")
        falta_e_atraso = _find_time_for_label(section, "FALTA E ATRASO")
        extra70 = _find_time_for_label(section, "EXTRA 70%")

        # Alguns PDFs têm "NOTURNAS NORMAIS"
        noturnas_normais = _find_time_for_label(section, "NOTURNAS NORMAIS")

        # Fallback: se algum veio zerado e o PDF trouxe só números, tenta heurística antiga
        # (isso evita travar em PDFs “diferentes”)
        if (
            (total_normais == "00:00" and total_noturno == "00:00" and extra70 == "00:00")
            or re.search(r"\d{1,3}:\d{2}", section) is None
        ):
            # tenta pegar os horários e usar posição como último recurso
            candidatos = re.findall(r"-?\d{1,3}:\d{2}(?::\d{2})?", section)
            candidatos = [_cut_seconds(x) for x in candidatos]
            # formato mais comum: 5 valores
            if len(candidatos) >= 5:
                noturnas_normais, total_normais, total_noturno, falta_e_atraso, extra70 = candidatos[:5]
            elif len(candidatos) == 4:
                total_normais, total_noturno, falta_e_atraso, extra70 = candidatos
            elif len(candidatos) == 3:
                total_normais, total_noturno, extra70 = candidatos

        falta = falta_e_atraso

        out.append(
            {
                "NOME": nome,
                "CARGO": cargo,
                "NOTURNAS NORMAIS": noturnas_normais,
                "TOTAL NORMAIS": total_normais,
                "TOTAL NOTURNO": total_noturno,
                "FALTA": falta,
                "EXTRA 70%": extra70,
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
    sheet_id = extract_sheet_id(planilha_url)
    sh = client.open_by_key(sheet_id)
    ws = sh.worksheet(tab_name)  # aba já existe pelo seu modelo
    return sh, ws


def map_name_to_rows(ws) -> dict:
    colA = ws.col_values(1)
    mapping = {}
    for idx, val in enumerate(colA, start=1):
        n = normalize_name(val)
        if n and n not in mapping:
            mapping[n] = idx
    return mapping


def update_rows(ws, df: pd.DataFrame):
    """
    Atualiza conforme seu layout:

    Funcionários (parte de cima):
      B=FALTA, C=EXTRA, D=EXTRA OU FALTA (EXTRA - FALTA), E=NOTURNO

    Motoboys (abaixo do título "MOTOBOYS HORISTAS"):
      B=HORAS, C=NOTURNO, D=EXTRA
    """
    name_map = map_name_to_rows(ws)

    # Descobrir a linha do bloco "MOTOBOYS HORISTAS"
    colA = ws.col_values(1)
    motoboy_title_row = None
    for i, v in enumerate(colA, start=1):
        if "MOTOBOYS HORISTAS" in str(v).upper():
            motoboy_title_row = i
            break

    not_found = []

    for _, row in df.iterrows():
        nome_pdf_norm = normalize_name(str(row["NOME"]))
        if not nome_pdf_norm:
            continue

        sheet_row = name_map.get(nome_pdf_norm)
        if not sheet_row:
            not_found.append(row["NOME"])
            continue

        cargo = str(row.get("CARGO", "")).upper()
        is_motoboy = ("MOTOBOY" in cargo) or (motoboy_title_row is not None and sheet_row > motoboy_title_row)

        falta = str(row.get("FALTA", "00:00"))
        extra = str(row.get("EXTRA 70%", "00:00"))
        noturno = str(row.get("TOTAL NOTURNO", "00:00"))
        horas = str(row.get("TOTAL NORMAIS", "00:00"))

        # EXTRA OU FALTA = EXTRA - FALTA
        extra_ou_falta = minutes_to_hhmm(hhmm_to_minutes(extra) - hhmm_to_minutes(falta))

        if is_motoboy:
            # Motoboy: B=HORAS, C=NOTURNO, D=EXTRA
            ws.update(f"B{sheet_row}", [[horas]])
            ws.update(f"C{sheet_row}", [[noturno]])
            ws.update(f"D{sheet_row}", [[extra]])
        else:
            # Funcionário: B=FALTA, C=EXTRA, D=EXTRA OU FALTA, E=NOTURNO
            ws.update(f"B{sheet_row}", [[falta]])
            ws.update(f"C{sheet_row}", [[extra]])
            ws.update(f"D{sheet_row}", [[extra_ou_falta]])
            ws.update(f"E{sheet_row}", [[noturno]])

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

        tab_name = f"{mes}_{loja}" if (mes and ano) else f"SEM_MES_{loja}"

        st.write(f"🏪 **Loja identificada:** {loja}")
        st.write(f"🗂️ **Dados irão para a aba:** {tab_name}")

        with st.spinner("🧩 Separando funcionários e totais..."):
            dados = parse_employee_blocks(texto)

        if not dados:
            st.error("Não encontrei funcionários no PDF. (Se o PDF for imagem, precisa OCR.)")
            st.stop()

        df = pd.DataFrame(dados)

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
            st.info("Dica: o sistema já normaliza acentos/espaços. Se mesmo assim não achar, o nome está diferente na planilha.")

    except Exception as e:
        st.error("❌ Deu erro ao processar/enviar.")
        st.code(str(e))
