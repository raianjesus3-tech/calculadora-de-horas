import streamlit as st
import pdfplumber
import re
import pandas as pd
import os
import json
import unicodedata
import gspread
from google.oauth2.service_account import Credentials

# Configuração da página
st.set_page_config(
    page_title="Sistema Calculadora de Horas",
    page_icon="⏱",
    layout="wide"
)

st.markdown("""
<style>
.big-title { font-size:32px; font-weight:bold; }
</style>
""", unsafe_allow_html=True)

st.markdown('<p class="big-title">⏱ Sistema Calculadora de Horas</p>', unsafe_allow_html=True)
st.caption("Versão 13.1 • Sistema Profissional Finalizado")

# =========================
# CONFIG
# =========================
PLANILHA_URL = "https://docs.google.com/spreadsheets/d/1er5DKT8jNm4qLTgQzdT2eQL8BrxxDlceUfkASYKYEZ8/edit"
ENV_KEY_JSON = "GCP_SERVICE_ACCOUNT_JSON"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

MESES_PT = {
    1: "JANEIRO", 2: "FEVEREIRO", 3: "MARCO", 4: "ABRIL",
    5: "MAIO", 6: "JUNHO", 7: "JULHO", 8: "AGOSTO",
    9: "SETEMBRO", 10: "OUTUBRO", 11: "NOVEMBRO", 12: "DEZEMBRO"
}

LOJAS = {
    "JPBB": ["JPBB"],
    "TPBR": ["TPBR"],
}

# -------------------------------------------------------
# MAPEAMENTO JPBB: nome normalizado -> linha na planilha
# -------------------------------------------------------
MAPA_LINHAS_JPBB = {
    "ADRIAN LOPES LIMA": 2,
    "CAIANE DE LIMA MEIRELES DA SILVA": 3,
    "DRIELLE DE JESUS CERQUEIRA": 4,
    "ERICK CERQUEIRA FERREIRA": 5,
    "PABLO HENRIQUE MACEDO NASCIMENTO": 6,
    "VICTOR EDUARDO MACEDO NASCIMENTO": 7,
    "YURI CRUZ DA SILVA": 8,
    "CAIO DE JESUS DA SILVA": 11,
    "MARCOS CRISPIM DOS SANTOS OLIVEIRA": 12,
    "UBIRATAN SANTOS DE JESUS": 13,
}

# -------------------------------------------------------
# MAPEAMENTO TPBR: nome normalizado -> linha na planilha
# -------------------------------------------------------
MAPA_LINHAS_TPBR = {
    "ANDREIA GOMES DOS SANTOS": 2,
    "DILSON ALVES VASCONCELLOS": 3,
    "ELEN SILVA DE JESUS": 4,
    "KAUAN VITOR DA ROCHA SANTOS": 5,
    "MARCOS ANTONIO DOS SANTOS DIAS": 6,
    "RAIAN DE JESUS GONCALVES": 7,
    "RODRIGO DE SOUZA PAIVA": 8,
    "SAMARA FARIAS DOS SANTOS": 9,
    "SAULO TADEU FARIAS DOS SANTOS": 10,
    "VITORIA LUIZA HUGHES DE FREITAS": 11,
    "ADRIANO ARAUJO TEIXEIRA": 14,
    "MARCIO OLIVEIRA MUNIZ": 15,
    "WILLIAM DOS SANTOS SILVA": 16,
}

# -------------------------------------------------------
# TEMPLATES para criação automática de aba nova
# -------------------------------------------------------
TEMPLATE_JPBB = [
    ["NOME", "FALTA", "EXTRA", "EXTRA OU FALTA", "NOTURNO"],
    ["ADRIAN LOPES LIMA", "", "", "", ""],
    ["CAIANE DE LIMA MEIRELES DA SILVA", "", "", "", ""],
    ["DRIELLE DE JESUS CERQUEIRA", "", "", "", ""],
    ["ERICK CERQUEIRA FERREIRA", "", "", "", ""],
    ["PABLO HENRIQUE MACEDO NASCIMENTO", "", "", "", ""],
    ["VICTOR EDUARDO MACEDO NASCIMENTO", "", "", "", ""],
    ["YURI CRUZ DA SILVA", "", "", "", ""],
    ["", "", "", "", ""],
    ["MOTOBOYS HORISTAS", "", "", "", ""],
    ["NOME", "NOTURNO", "HORAS", "EXTRA", ""],
    ["CAIO DE JESUS DA SILVA", "", "", "", ""],
    ["MARCOS CRISPIM DOS SANTOS OLIVEIRA", "", "", "", ""],
    ["UBIRATAN SANTOS DE JESUS", "", "", "", ""],
]

TEMPLATE_TPBR = [
    ["NOME", "FALTA", "EXTRA", "EXTRA OU FALTA", "NOTURNO"],
    ["ANDREIA GOMES DOS SANTOS", "", "", "", ""],
    ["DILSON ALVES VASCONCELLOS", "", "", "", ""],
    ["ELEN SILVA DE JESUS", "", "", "", ""],
    ["KAUAN VITOR DA ROCHA SANTOS", "", "", "", ""],
    ["MARCOS ANTONIO DOS SANTOS DIAS", "", "", "", ""],
    ["RAIAN DE JESUS GONCALVES", "", "", "", ""],
    ["RODRIGO DE SOUZA PAIVA", "", "", "", ""],
    ["SAMARA FARIAS DOS SANTOS", "", "", "", ""],
    ["SAULO TADEU FARIAS DOS SANTOS", "", "", "", ""],
    ["VITORIA LUIZA HUGHES DE FREITAS", "", "", "", ""],
    ["", "", "", "", ""],
    ["MOTOBOYS HORISTAS", "", "", "", ""],
    ["NOME", "HORAS", "NOTURNO", "EXTRA", ""],
    ["ADRIANO ARAUJO TEIXEIRA", "", "", "", ""],
    ["MARCIO OLIVEIRA MUNIZ", "", "", "", ""],
    ["WILLIAM DOS SANTOS SILVA", "", "", "", ""],
]

# =========================
# FUNÇÕES DE TEMPO
# =========================
def hhmm_to_min(s):
    if not s or ":" not in str(s):
        return 0
    s = str(s).strip()
    sign = -1 if s.startswith("-") else 1
    s = s.lstrip("-")
    try:
        parts = s.split(":")
        h = int(parts[0])
        m = int(parts[1])
        return sign * (h * 60 + m)
    except:
        return 0

def min_to_hhmm(minutes):
    sign = "-" if minutes < 0 else ""
    minutes = abs(minutes)
    return f"{sign}{minutes // 60:02d}:{minutes % 60:02d}"

# =========================
# NORMALIZAÇÃO
# =========================
def normalize_name(s):
    if not s:
        return ""
    s = s.strip().upper()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^A-Z0-9\s]", "", s)
    return re.sub(r"\s+", " ", s).strip()

# =========================
# DETECTAR LOJA E MÊS
# =========================
def detect_loja_mes(text):
    loja = "DESCONHECIDA"
    for sigla, keywords in LOJAS.items():
        for kw in keywords:
            if kw in text.upper():
                loja = sigla
                break
    mes_num, ano = None, None
    m = re.search(r"DE \d{2}/(\d{2})/(\d{4})", text)
    if m:
        mes_num = int(m.group(1))
        ano = int(m.group(2))
    return loja, mes_num, ano

def gerar_nome_aba(loja, mes_num, ano):
    if not mes_num:
        return None
    mes_nome = MESES_PT.get(mes_num, f"MES{mes_num}")
    return f"{mes_nome}_{loja}"

# =========================
# PARSER
# =========================
def parse_totais(tokens):
    result = {
        "TOTAL NORMAIS": "", "TOTAL NOTURNO": "",
        "FALTA (dias)": "0", "FALTA E ATRASO": "", "EXTRA 70%": "",
    }
    horas = [t[1] for t in tokens if t[0] == "h"]
    inteiros = [t[1] for t in tokens if t[0] == "i"]

    if inteiros:
        result["FALTA (dias)"] = str(inteiros[0])

    if len(horas) >= 2:
        if hhmm_to_min(horas[0]) < hhmm_to_min(horas[1]):
            horas = horas[1:]

    if not horas:
        return result

    result["TOTAL NORMAIS"] = horas[0]

    for h in horas[1:]:
        v = hhmm_to_min(h)
        if v >= 19 * 60 and not result["TOTAL NOTURNO"]:
            result["TOTAL NOTURNO"] = h
        elif not result["FALTA E ATRASO"]:
            result["FALTA E ATRASO"] = h
        else:
            result["EXTRA 70%"] = h

    return result

def parse_page(text):
    nome_match = re.search(r"NOME DO FUNCION[AÁ]RIO:\s*(.+?)\s+PIS", text, re.IGNORECASE)
    if not nome_match:
        return None
    nome = nome_match.group(1).replace("\n", " ").strip()

    cargo_match = re.search(
        r"NOME DO CARGO:\s*([A-Za-záàâãéèêíïóôõöúçñÁÀÂÃÉÈÊÍÏÓÔÕÖÚÇÑ\.\s/]+?)"
        r"(?:\s+(?:SEG|TER|QUA|QUI|SEX|SAB|DOM|CNPJ))",
        text, re.IGNORECASE
    )
    if not cargo_match:
        cargo_match = re.search(r"NOME DO CARGO:\s*(.+)", text, re.IGNORECASE)
    cargo = cargo_match.group(1).strip() if cargo_match else ""

    empresa_match = re.search(r"NOME DA EMPRESA:\s*(.+)", text, re.IGNORECASE)
    empresa = empresa_match.group(1).strip() if empresa_match else ""

    totais_match = re.search(r"^TOTAIS\s+(.*)", text, re.MULTILINE)
    if not totais_match:
        return {
            "NOME": nome, "CARGO": cargo, "EMPRESA": empresa,
            "TOTAL NORMAIS": "", "TOTAL NOTURNO": "",
            "FALTA (dias)": "0", "FALTA E ATRASO": "", "EXTRA 70%": "",
            "EXTRA OU FALTA": "", "OBS": "Sem totais (cargo confiança/férias)"
        }

    totais_line = totais_match.group(1).strip()
    tokens = []
    for t in re.findall(r'\d{1,3}:\d{2}|\b\d{1,2}\b', totais_line):
        tokens.append(("h", t) if ":" in t else ("i", int(t)))

    campos = parse_totais(tokens)

    falt_min = hhmm_to_min(campos["FALTA E ATRASO"])
    extra_min = hhmm_to_min(campos["EXTRA 70%"])
    saldo = extra_min - falt_min
    saldo_str = min_to_hhmm(saldo) if (falt_min or extra_min) else ""

    return {
        "NOME": nome, "CARGO": cargo, "EMPRESA": empresa,
        **campos,
        "EXTRA OU FALTA": saldo_str,
        "OBS": ""
    }

def extract_pdf(pdf_file):
    results = []
    loja, mes_num, ano = "DESCONHECIDA", None, None
    with pdfplumber.open(pdf_file) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue
            if i == 0:
                loja, mes_num, ano = detect_loja_mes(text)
            data = parse_page(text)
            if data:
                data["LOJA"] = loja
                data["MES"] = mes_num
                data["ANO"] = ano
                results.append(data)
    return results, loja, mes_num, ano

# =========================
# GOOGLE SHEETS
# =========================
@st.cache_resource
def get_client():
    creds_raw = os.environ.get(ENV_KEY_JSON)
    if not creds_raw:
        raise ValueError("Credencial GCP_SERVICE_ACCOUNT_JSON não configurada!")
    creds_dict = json.loads(creds_raw)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)

def extract_sheet_id(url):
    m = re.search(r"/d/([a-zA-Z0-9-_]+)", url)
    return m.group(1) if m else None

def garantir_aba(sh, aba_nome, loja):
    try:
        return sh.worksheet(aba_nome), False
    except gspread.WorksheetNotFound:
        pass

    nova_aba = sh.add_worksheet(title=aba_nome, rows=30, cols=10)
    template = TEMPLATE_JPBB if loja == "JPBB" else TEMPLATE_TPBR
    nova_aba.update("A1", template)
    return nova_aba, True

def enviar_para_planilha(df, aba_nome, loja):
    client = get_client()
    sheet_id = extract_sheet_id(PLANILHA_URL)
    sh = client.open_by_key(sheet_id)

    aba, foi_criada = garantir_aba(sh, aba_nome, loja)
    mapa = MAPA_LINHAS_JPBB if loja == "JPBB" else MAPA_LINHAS_TPBR

    erros = []
    enviados = 0

    for _, row in df.iterrows():
        nome_norm = normalize_name(row["NOME"])
        is_moto = "MOTOBOY" in str(row.get("CARGO", "")).upper()
        linha = mapa.get(nome_norm)

        if not linha:
            erros.append(f"⚠️ {row['NOME']} — não encontrado no mapeamento")
            continue

        if is_moto:
            if loja == "JPBB":
                aba.update(f"B{linha}", [[row.get("TOTAL NOTURNO", "")]])
                aba.update(f"C{linha}", [[row.get("TOTAL NORMAIS", "")]])
                aba.update(f"D{linha}", [[row.get("EXTRA 70%", "")]])
            else:
                aba.update(f"B{linha}", [[row.get("TOTAL NORMAIS", "")]])
                aba.update(f"C{linha}", [[row.get("TOTAL NOTURNO", "")]])
                aba.update(f"D{linha}", [[row.get("EXTRA 70%", "")]])
        else:
            aba.update(f"B{linha}", [[row.get("FALTA E ATRASO", "")]])
            aba.update(f"C{linha}", [[row.get("EXTRA 70%", "")]])
            aba.update(f"D{linha}", [[row.get("EXTRA OU FALTA", "")]])
            aba.update(f"E{linha}", [[row.get("TOTAL NOTURNO", "")]])

        enviados += 1

    return enviados, erros, foi_criada

# =========================
# UI
# =========================
uploaded_files = st.file_uploader(
    "📂 Enviar espelhos de ponto (pode enviar múltiplos PDFs de uma vez)",
    type=["pdf"],
    accept_multiple_files=True
)

if uploaded_files:
    todos_dados = []
    infos_pdfs = []

    for uploaded_file in uploaded_files:
        with st.spinner(f"⏳ Lendo {uploaded_file.name}..."):
            dados, loja, mes_num, ano = extract_pdf(uploaded_file)
            todos_dados.extend(dados)
            aba_auto = gerar_nome_aba(loja, mes_num, ano)
            infos_pdfs.append({
                "arquivo": uploaded_file.name,
                "loja": loja,
                "mes": mes_num,
                "ano": ano,
                "aba_sugerida": aba_auto
            })

    df = pd.DataFrame(todos_dados)

    st.success(f"✅ {len(df)} funcionários extraídos de {len(uploaded_files)} arquivo(s)")

    st.subheader("📌 PDFs detectados")
    for info in infos_pdfs:
        mes_nome = MESES_PT.get(info["mes"], "?") if info["mes"] else "?"
        aba = info["aba_sugerida"] or "não detectada"
        st.info(f"**{info['arquivo']}** → Loja: `{info['loja']}` | Mês: `{mes_nome}/{info['ano']}` | Aba: `{aba}`")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total funcionários", len(df))
    col2.metric("Motoboys", len(df[df["CARGO"].str.contains("MOTOBOY", case=False, na=False)]))
    col3.metric("Com falta", len(df[df["FALTA (dias)"].astype(str) != "0"]))
    col4.metric("Com extra", len(df[df["EXTRA 70%"] != ""]))

    st.subheader("📋 Conferência dos dados")
    colunas_exibir = ["NOME", "CARGO", "EMPRESA", "FALTA (dias)", "EXTRA 70%", "EXTRA OU FALTA", "TOTAL NOTURNO", "TOTAL NORMAIS", "OBS"]
    st.dataframe(df[[c for c in colunas_exibir if c in df.columns]], use_container_width=True)

    with st.expander("ℹ️ Legenda"):
        st.markdown("""
        | Coluna | Descrição |
        |---|---|
        | **FALTA (dias)** | Dias de falta |
        | **EXTRA 70%** | Horas extras (70%) |
        | **EXTRA OU FALTA** | FALTA E ATRASO − EXTRA 70% *(+ deve horas / − banco de horas)* |
        | **TOTAL NOTURNO** | Total de horas noturnas |
        | **TOTAL NORMAIS** | Total de horas trabalhadas (motoboys) |
        """)

    excel_path = "/tmp/resultado_horas.xlsx"
    df.to_excel(excel_path, index=False)
    with open(excel_path, "rb") as f:
        st.download_button(
            "📥 Baixar como Excel",
            data=f,
            file_name="resultado_horas.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    st.divider()
    st.subheader("🚀 Enviar para Google Sheets")

    if not os.environ.get(ENV_KEY_JSON):
        st.error("❌ Credencial GCP_SERVICE_ACCOUNT_JSON não configurada no ambiente!")
    else:
        for info in infos_pdfs:
            aba_sugerida = info["aba_sugerida"] or ""
            col_a, col_b = st.columns([2, 1])
            with col_a:
                aba_input = st.text_input(
                    f"Aba para **{info['arquivo']}**",
                    value=aba_sugerida,
                    key=f"aba_{info['arquivo']}"
                )
            with col_b:
                st.write("")
                st.write("")
                if st.button(f"Enviar {info['loja']}", key=f"btn_{info['arquivo']}"):
                    df_loja = df[df["LOJA"] == info["loja"]]
                    with st.spinner(f"⏳ Enviando para '{aba_input}'..."):
                        try:
                            enviados, erros, foi_criada = enviar_para_planilha(df_loja, aba_input, info["loja"])
                            if foi_criada:
                                st.info(f"📋 Aba **'{aba_input}'** não existia — foi criada automaticamente com o template!")
                            if enviados:
                                st.success(f"✅ {enviados} funcionários enviados para **'{aba_input}'**!")
                            if erros:
                                st.warning("Alguns funcionários não foram mapeados:")
                                for e in erros:
                                    st.write(e)
                        except Exception as ex:
                            st.error(f"❌ Erro: {ex}")
