import streamlit as st
import pdfplumber
import re
import pandas as pd
import os
import json
import unicodedata
from datetime import datetime

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
# ESTILO (SaaS premium)
# =========================
st.markdown(
    """
<style>
/* largura melhor no wide */
.block-container { padding-top: 1.4rem; padding-bottom: 2.5rem; max-width: 1300px; }

/* header premium */
.premium-header{
  border-radius: 16px;
  padding: 18px 20px;
  background: linear-gradient(90deg, rgba(124,58,237,0.18), rgba(16,185,129,0.10));
  border: 1px solid rgba(255,255,255,0.10);
  margin-bottom: 16px;
}
.premium-title{ font-size: 34px; font-weight: 800; margin: 0; line-height: 1.1; }
.premium-sub{ margin: 6px 0 0 0; opacity: .8; }

/* cards */
.card{
  border-radius: 16px;
  padding: 16px 16px;
  border: 1px solid rgba(255,255,255,0.10);
  background: rgba(255,255,255,0.04);
}

/* upload */
div[data-testid="stFileUploader"]{
  border-radius: 16px;
  border: 1px dashed rgba(255,255,255,0.18);
  padding: 10px 14px;
  background: rgba(255,255,255,0.03);
}

/* metric alinhado */
[data-testid="stMetric"]{
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.10);
  padding: 14px;
  border-radius: 16px;
}

/* expander */
.streamlit-expanderHeader{
  border-radius: 12px !important;
}

/* buttons */
.stButton > button{
  border-radius: 12px;
  padding: 10px 14px;
}
</style>
""",
    unsafe_allow_html=True,
)

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


def extract_sheet_id(url: str) -> str:
    """Evita erro NoValidUrlKeyFound. Pega o ID da planilha do link."""
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
# Parser por funcionário (mantido)
# =========================
def parse_employee_blocks(texto: str) -> list[dict]:
    """
    Retorna lista com:
      NOME, CARGO,
      TOTAL NORMAIS,
      TOTAL NOTURNO,
      FALTA,
      EXTRA 70%
    """
    blocos = re.split(r"\bCart[aã]o\s+de\s+Ponto\b", texto, flags=re.IGNORECASE)
    out = []

    for bloco in blocos:
        if ("NOME DO FUNCION" not in bloco.upper()) or ("TOTAIS" not in bloco.upper()):
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

        totais_match = re.search(r"TOTAIS\s+([0-9:\s-]+)", bloco, flags=re.IGNORECASE)
        if not totais_match:
            continue

        horarios = re.findall(r"-?\d{1,3}:\d{2}(?::\d{2})?", totais_match.group(1))
        horarios = [h[:5] if len(h) >= 5 else h for h in horarios]  # corta segundos se vier

        noturnas_normais = "00:00"
        total_normais = "00:00"
        total_noturno = "00:00"
        falta_e_atraso = "00:00"
        extra70 = "00:00"

        if len(horarios) == 5:
            noturnas_normais, total_normais, total_noturno, falta_e_atraso, extra70 = horarios
        elif len(horarios) == 4:
            total_normais, total_noturno, falta_e_atraso, extra70 = horarios
        elif len(horarios) >= 6:
            noturnas_normais, total_normais, total_noturno, falta_e_atraso, extra70 = horarios[:5]
        elif len(horarios) == 3:
            total_normais, total_noturno, extra70 = horarios
        elif len(horarios) == 2:
            total_normais, extra70 = horarios
        elif len(horarios) == 1:
            total_normais = horarios[0]

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
    ws = sh.worksheet(tab_name)  # você já tem aba criada no modelo
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
    Funcionários (parte de cima):
      B=FALTA, C=EXTRA, D=EXTRA OU FALTA (EXTRA - FALTA), E=NOTURNO
    Motoboys (abaixo do título "MOTOBOYS HORISTAS"):
      B=HORAS, C=NOTURNO, D=EXTRA
    """
    name_map = map_name_to_rows(ws)

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

    return not_found


# =========================
# SESSION STATE
# =========================
if "df" not in st.session_state:
    st.session_state.df = None
if "loja" not in st.session_state:
    st.session_state.loja = None
if "tab_name" not in st.session_state:
    st.session_state.tab_name = None
if "processed_at" not in st.session_state:
    st.session_state.processed_at = None


# =========================
# HEADER
# =========================
st.markdown(
    """
<div class="premium-header">
  <div class="premium-title">⏱️ Calculadora de Horas</div>
  <div class="premium-sub">Painel executivo • Leitura de PDF • Integração automática com Google Sheets</div>
</div>
""",
    unsafe_allow_html=True,
)

# =========================
# SIDEBAR (filtros / info)
# =========================
with st.sidebar:
    st.markdown("### ⚙️ Controles")
    st.caption("Sem alterar sua lógica — só visual e navegação.")
    st.toggle("Mostrar prévia detalhada", value=True, key="show_preview")
    st.toggle("Mostrar tabelas no Dashboard", value=True, key="show_tables")

    st.markdown("---")
    st.markdown("### 📌 Status")
    if st.session_state.processed_at:
        st.success("Último processamento")
        st.write(st.session_state.processed_at)
        if st.session_state.loja:
            st.write(f"Loja: **{st.session_state.loja}**")
        if st.session_state.tab_name:
            st.write(f"Aba: **{st.session_state.tab_name}**")
    else:
        st.info("Envie um PDF para começar.")


# =========================
# ABAS
# =========================
aba1, aba2 = st.tabs(["📄 Processar PDF", "📊 Dashboard Executivo"])


# =========================
# ABA 1 - PROCESSAR
# =========================
with aba1:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("📤 Envio do PDF")
    st.caption("Selecione o PDF da loja (JPBB ou TPBR). O sistema identifica loja/mês e envia para a aba correta.")
    uploaded_file = st.file_uploader("Enviar PDF", type=["pdf"])
    st.markdown("</div>", unsafe_allow_html=True)

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

            # parse
            with st.spinner("🧩 Separando funcionários e totais..."):
                dados = parse_employee_blocks(texto)

            if not dados:
                st.error("Não encontrei funcionários no PDF. (Se o PDF for imagem, precisa OCR.)")
                st.stop()

            df = pd.DataFrame(dados)

            # guarda no state para o dashboard
            st.session_state.df = df
            st.session_state.loja = loja
            st.session_state.tab_name = tab_name
            st.session_state.processed_at = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

            # KPIs rápidos do processamento
            total_pessoas = len(df)
            total_motoboys = df["CARGO"].astype(str).str.contains(r"\bMOTOBOY\b", regex=True, na=False).sum()

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("👥 Pessoas", f"{total_pessoas}")
            c2.metric("🛵 Motoboys", f"{total_motoboys}")
            c3.metric("🏪 Loja", loja)
            c4.metric("🗂️ Aba", tab_name)

            if st.session_state.show_preview:
                with st.expander("👀 Prévia do que foi extraído (do PDF)"):
                    st.dataframe(df, use_container_width=True)

            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.subheader("📤 Enviar para o Google Sheets")
            st.caption("Clique no botão abaixo para gravar os dados na planilha (layout do seu modelo).")

            if st.button("✅ Enviar para a Planilha", type="primary", use_container_width=True):
                with st.spinner("🔐 Conectando no Google Sheets..."):
                    client = get_gspread_client()
                    _, ws = get_sheet_and_tab(client, PLANILHA_URL, tab_name)

                with st.spinner("🚀 Gravando dados na planilha..."):
                    not_found = update_rows(ws, df)

                st.success("🎉 Dados enviados para o Google Sheets com sucesso!")

                if not_found:
                    st.warning("⚠️ Alguns nomes não foram encontrados na coluna A (confira se estão iguais):")
                    st.write(not_found)
                    st.info("Dica: o sistema normaliza acentos/espaços. Se não achou, o nome está diferente na planilha.")

            st.markdown("</div>", unsafe_allow_html=True)

        except Exception as e:
            st.error("❌ Deu erro ao processar/enviar.")
            st.code(str(e))


# =========================
# ABA 2 - DASHBOARD
# =========================
with aba2:
    df = st.session_state.df

    if df is None or df.empty:
        st.info("Envie um PDF na aba **Processar PDF** para liberar o Dashboard.")
        st.stop()

    # separações
    is_motoboy = df["CARGO"].astype(str).str.contains(r"\bMOTOBOY\b", regex=True, na=False)
    df_func = df[~is_motoboy].copy()
    df_moto = df[is_motoboy].copy()

    # cálculos
    total_horas = df["TOTAL NORMAIS"].apply(hhmm_to_minutes).sum()
    total_noturno = df["TOTAL NOTURNO"].apply(hhmm_to_minutes).sum()
    total_falta = df["FALTA"].apply(hhmm_to_minutes).sum()
    total_extra = df["EXTRA 70%"].apply(hhmm_to_minutes).sum()

    # KPIs (executivo)
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("⏱️ Horas (Normais)", minutes_to_hhmm(total_horas))
    k2.metric("🌙 Total Noturno", minutes_to_hhmm(total_noturno))
    k3.metric("⚠️ Total Faltas", minutes_to_hhmm(total_falta))
    k4.metric("🚀 Total Extras", minutes_to_hhmm(total_extra))

    st.markdown("")

    left, right = st.columns([1.2, 1.0], gap="large")

    with left:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("📈 Visão Geral (categorias)")
        chart_df = pd.DataFrame(
            {
                "Categoria": ["Normais", "Noturno", "Faltas", "Extras"],
                "Minutos": [total_horas, total_noturno, total_falta, total_extra],
            }
        ).set_index("Categoria")
        # Streamlit bar_chart usa tema automático (fica premium com seu tema)
        st.bar_chart(chart_df)
        st.caption("Gráfico em minutos (padrão interno).")
        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("🏪 Contexto")
        st.write(f"**Loja:** {st.session_state.loja}")
        st.write(f"**Aba:** {st.session_state.tab_name}")
        st.write(f"**Processado em:** {st.session_state.processed_at}")

        st.markdown("---")
        st.subheader("🧭 Ações rápidas")
        st.caption("Se quiser reprocessar, volte na aba **Processar PDF** e envie outro arquivo.")
        st.markdown("</div>", unsafe_allow_html=True)

    if st.session_state.show_tables:
        st.markdown("### 📋 Tabelas")

        t1, t2 = st.tabs(["👥 Funcionários", "🛵 Motoboys"])

        with t1:
            df_view = df_func[["NOME", "FALTA", "EXTRA 70%", "TOTAL NOTURNO"]].copy()
            df_view["EXTRA OU FALTA"] = (
                df_view["EXTRA 70%"].apply(hhmm_to_minutes) - df_view["FALTA"].apply(hhmm_to_minutes)
            ).apply(minutes_to_hhmm)
            df_view = df_view[["NOME", "FALTA", "EXTRA 70%", "EXTRA OU FALTA", "TOTAL NOTURNO"]]
            df_view.columns = ["NOME", "FALTA", "EXTRA", "EXTRA OU FALTA", "NOTURNO"]

            st.dataframe(df_view, use_container_width=True)

            # Top 10 extras
            tmp = df_func.copy()
            tmp["EXTRA_MIN"] = tmp["EXTRA 70%"].apply(hhmm_to_minutes)
            top_extra = tmp.sort_values("EXTRA_MIN", ascending=False).head(10)[["NOME", "EXTRA 70%"]]
            st.markdown("#### 🔝 Top 10 (mais EXTRA)")
            st.dataframe(top_extra, use_container_width=True)

        with t2:
            df_m = df_moto[["NOME", "TOTAL NORMAIS", "TOTAL NOTURNO", "EXTRA 70%"]].copy()
            df_m.columns = ["NOME", "HORAS", "NOTURNO", "EXTRA"]
            st.dataframe(df_m, use_container_width=True)

            tmpm = df_moto.copy()
            tmpm["HORAS_MIN"] = tmpm["TOTAL NORMAIS"].apply(hhmm_to_minutes)
            top_h = tmpm.sort_values("HORAS_MIN", ascending=False).head(10)[["NOME", "TOTAL NORMAIS"]]
            top_h.columns = ["NOME", "HORAS"]
            st.markdown("#### 🔝 Top 10 (mais HORAS)")
            st.dataframe(top_h, use_container_width=True)
