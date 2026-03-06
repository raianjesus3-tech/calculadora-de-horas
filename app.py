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

    hhmm = str(hhmm).strip()

    sign = -1 if hhmm.startswith("-") else 1
    if sign == -1:
        hhmm = hhmm[1:]

    try:
        h, m = hhmm.split(":")[:2]
        return sign * (int(h) * 60 + int(m))
    except:
        return 0


def minutes_to_hhmm(minutes: int) -> str:
    sign = "-" if minutes < 0 else ""
    minutes = abs(int(minutes))
    return f"{sign}{minutes // 60:02d}:{minutes % 60:02d}"


def limpar_hora(valor: str) -> str:
    if not valor:
        return "00:00"

    valor = str(valor).strip()
    m = re.search(r"-?\d{1,3}:\d{2}", valor)

    if not m:
        return "00:00"

    return m.group(0)

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


def normalize_text(s: str) -> str:
    if not s:
        return ""

    s = unicodedata.normalize("NFKD", s)
    s = "".join([c for c in s if not unicodedata.combining(c)])
    return s.upper()

# =========================
# LOJA
# =========================
def identificar_loja(texto: str):
    t = normalize_text(texto)

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
# PARSER
# =========================
def extrair_valor_por_rotulo(totais: str, padrao_rotulo: str) -> str:
    """
    Procura um rótulo e pega a hora mais próxima dele.
    Ex.: TOTAL NORMAIS 124:00
    """
    if not totais:
        return "00:00"

    # tenta achar na mesma linha
    m = re.search(
        rf"(?:{padrao_rotulo})[^\d\-]{{0,20}}(-?\d{{1,3}}:\d{{2}})",
        totais,
        flags=re.IGNORECASE
    )
    if m:
        return limpar_hora(m.group(1))

    # tenta achar com quebra de linha ou texto no meio
    m = re.search(
        rf"(?:{padrao_rotulo})[\s\S]{{0,60}}?(-?\d{{1,3}}:\d{{2}})",
        totais,
        flags=re.IGNORECASE
    )
    if m:
        return limpar_hora(m.group(1))

    return "00:00"


def extrair_secao_totais(bloco: str) -> str:
    """
    Extrai somente a área após TOTAIS, evitando pegar horários soltos do resto do bloco.
    """
    bloco_norm = normalize_text(bloco)

    pos = bloco_norm.find("TOTAIS")
    if pos == -1:
        return ""

    secao = bloco[pos:]

    # corta em possíveis marcadores seguintes, se existirem
    marcadores_fim = [
        "OCORRENCIAS",
        "OBSERVACOES",
        "ASSINATURA",
        "CONFERIDO",
        "RESUMO",
        "BATIDAS",
        "HORARIO",
    ]

    menor_corte = len(secao)

    secao_norm = normalize_text(secao)
    for marcador in marcadores_fim:
        idx = secao_norm.find(marcador, 10)
        if idx != -1 and idx < menor_corte:
            menor_corte = idx

    secao = secao[:menor_corte]

    # limite de segurança
    return secao[:600]


def parse_employee_blocks(texto: str):
    blocos = re.split(r"Cart[aã]o\s+de\s+Ponto", texto, flags=re.IGNORECASE)

    out = []

    for bloco in blocos:
        bloco_norm = normalize_text(bloco)

        if "NOME DO FUNCION" not in bloco_norm or "TOTAIS" not in bloco_norm:
            continue

        nome_match = re.search(
            r"NOME DO FUNCION[AÁ]RIO:\s*(.+?)\s+PIS",
            bloco,
            flags=re.IGNORECASE | re.DOTALL
        )

        if not nome_match:
            continue

        nome = nome_match.group(1).replace("\n", " ").strip()
        nome = re.sub(r"\s+", " ", nome)

        cargo_match = re.search(
            r"NOME DO CARGO:\s*(.+)",
            bloco,
            flags=re.IGNORECASE
        )
        cargo = cargo_match.group(1).split("\n")[0].strip() if cargo_match else ""

        totais = extrair_secao_totais(bloco)

        total_normais = extrair_valor_por_rotulo(
            totais,
            r"TOTAL\s*NORMAIS|HORAS\s*NORMAIS|NORMAIS"
        )

        total_noturno = extrair_valor_por_rotulo(
            totais,
            r"TOTAL\s*NOTURNO|ADICIONAL\s*NOTURNO|NOTURNO"
        )

        falta = extrair_valor_por_rotulo(
            totais,
            r"FALTA\s*E\s*ATRASO|FALTAS?\s*E\s*ATRASOS?|FALTA/ATRASO|FALTA|ATRASO"
        )

        extra = extrair_valor_por_rotulo(
            totais,
            r"EXTRA\s*70%|HORAS?\s*EXTRAS?\s*70%|EXTRA\s*70"
        )

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
        raise ValueError(f"Variável de ambiente '{ENV_KEY_JSON}' não encontrada.")

    creds_dict = json.loads(creds_raw)

    creds = Credentials.from_service_account_info(
        creds_dict,
        scopes=SCOPES
    )

    return gspread.authorize(creds)


def extract_sheet_id(url):
    m = re.search(r"/d/([a-zA-Z0-9-_]+)", url)
    if not m:
        raise ValueError("Não foi possível identificar o ID da planilha.")
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


def localizar_motoboy_row(ws):
    colA = ws.col_values(1)

    for i, v in enumerate(colA, start=1):
        if "MOTOBOYS HORISTAS" in normalize_text(v):
            return i

    return None

# =========================
# ENVIO
# =========================
def update_rows(ws, df):
    name_map = map_name_to_rows(ws)
    motoboy_row = localizar_motoboy_row(ws)

    atualizacoes = []

    for _, row in df.iterrows():
        nome = normalize_name(row["NOME"])
        sheet_row = name_map.get(nome)

        if not sheet_row:
            continue

        cargo = normalize_text(row["CARGO"])

        is_motoboy_por_cargo = "MOTOBOY" in cargo
        is_motoboy_por_posicao = motoboy_row is not None and sheet_row > motoboy_row
        is_motoboy = is_motoboy_por_cargo or is_motoboy_por_posicao

        falta = limpar_hora(row["FALTA"])
        extra = limpar_hora(row["EXTRA 70%"])
        noturno = limpar_hora(row["TOTAL NOTURNO"])
        horas = limpar_hora(row["TOTAL NORMAIS"])

        extra_ou_falta = minutes_to_hhmm(
            hhmm_to_minutes(extra) - hhmm_to_minutes(falta)
        )

        if is_motoboy:
            atualizacoes.extend([
                {"range": f"B{sheet_row}", "values": [[horas]]},
                {"range": f"C{sheet_row}", "values": [[noturno]]},
                {"range": f"D{sheet_row}", "values": [[extra]]},
            ])
        else:
            atualizacoes.extend([
                {"range": f"B{sheet_row}", "values": [[falta]]},
                {"range": f"C{sheet_row}", "values": [[extra]]},
                {"range": f"D{sheet_row}", "values": [[extra_ou_falta]]},
                {"range": f"E{sheet_row}", "values": [[noturno]]},
            ])

    if atualizacoes:
        ws.batch_update(atualizacoes)

# =========================
# UI
# =========================
st.title("🚀 Sistema Calculadora de Horas")
st.subheader("📤 Enviar PDF de Espelho de Ponto")

uploaded_file = st.file_uploader("Enviar PDF", type=["pdf"])

if uploaded_file:
    try:
        texto = extract_full_text(uploaded_file)

        loja = identificar_loja(texto)
        mes, ano = detectar_mes_ano(texto)

        if not loja:
            st.error("Não foi possível identificar a loja no PDF.")
            st.stop()

        if not mes or not ano:
            st.error("Não foi possível identificar o mês/ano no PDF.")
            st.stop()

        tab_name = f"{mes}_{loja}"

        dados = parse_employee_blocks(texto)

        if not dados:
            st.error("Nenhum funcionário com bloco de TOTAIS foi encontrado no PDF.")
            st.stop()

        df = pd.DataFrame(dados)

        st.success(f"Loja identificada: {loja}")
        st.success(f"Mês identificado: {mes}/{ano}")
        st.write(f"Aba de destino: **{tab_name}**")

        st.dataframe(df, use_container_width=True)

        client = get_gspread_client()
        ws = get_sheet_and_tab(client, PLANILHA_URL, tab_name)

        if st.button("Enviar para planilha"):
            update_rows(ws, df)
            st.success("Dados enviados para Google Sheets!")

    except Exception as e:
        st.error(f"Erro no processamento: {str(e)}")
