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
st.caption("Versão 17.0 • Correção de Nomes e Parser Dinâmico")

# =========================
# CONFIG
# =========================
PLANILHA_URL = "https://docs.google.com/spreadsheets/d/1er5DKT8jNm4qLTgQzdT2eQL8BrxxDlceUfkASYKYEZ8/edit"
ENV_KEY_JSON = "GCP_SERVICE_ACCOUNT_JSON"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

MESES_PT = {
    1: "JANEIRO", 2: "FEVEREIRO", 3: "MARCO", 4: "ABRIL",
    5: "MAIO", 6: "JUNHO", 7: "JULHO", 8: "AGOSTO",
    9: "SETEMBRO", 10: "OUTUBRO", 11: "NOVEMBRO", 12: "DEZEMBRO"
}

LOJAS = {"JPBB": ["JPBB"], "TPBR": ["TPBR"]}

MAPA_LINHAS_JPBB = {
    "ADRIAN LOPES LIMA": 2, "CAIANE DE LIMA MEIRELES DA SILVA": 3, "DRIELLE DE JESUS CERQUEIRA": 4,
    "ERICK CERQUEIRA FERREIRA": 5, "PABLO HENRIQUE MACEDO NASCIMENTO": 6, "VICTOR EDUARDO MACEDO NASCIMENTO": 7,
    "YURI CRUZ DA SILVA": 8, "CAIO DE JESUS DA SILVA": 11, "MARCOS CRISPIM DOS SANTOS OLIVEIRA": 12,
    "UBIRATAN SANTOS DE JESUS": 13,
}

MAPA_LINHAS_TPBR = {
    "ANDREIA GOMES DOS SANTOS": 2, "DILSON ALVES VASCONCELLOS": 3, "ELEN SILVA DE JESUS": 4,
    "KAUAN VITOR DA ROCHA SANTOS": 5, "MARCOS ANTONIO DOS SANTOS DIAS": 6, "RAIAN DE JESUS GONCALVES": 7,
    "RODRIGO DE SOUZA PAIVA": 8, "SAMARA FARIAS DOS SANTOS": 9, "SAULO TADEU FARIAS DOS SANTOS": 10,
    "VITORIA LUIZA HUGHES DE FREITAS": 11, "ADRIANO ARAUJO TEIXEIRA": 14, "MARCIO OLIVEIRA MUNIZ": 15,
    "WILLIAM DOS SANTOS SILVA": 16,
}

# =========================
# FUNÇÕES AUXILIARES
# =========================
def hhmm_to_min(s):
    if not s or ":" not in str(s): return 0
    s = str(s).strip().lstrip("-")
    try:
        h, m = s.split(":")
        return int(h) * 60 + int(m)
    except: return 0

def min_to_hhmm(minutes):
    sign = "-" if minutes < 0 else ""
    minutes = abs(minutes)
    return f"{sign}{minutes // 60:02d}:{minutes % 60:02d}"

def normalize_name(s):
    if not s: return ""
    s = s.strip().upper()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^A-Z0-9\s]", "", s)
    return re.sub(r"\s+", " ", s).strip()

# =========================
# PARSER DINÂMICO
# =========================
def parse_page_v17(page):
    words = page.extract_words()
    text_full = page.extract_text()
    if not words or not text_full: return None

    # 1. Captura de Nome e Cargo (Melhorada)
    nome = "DESCONHECIDO"
    nome_match = re.search(r"NOME DO FUNCION[AÁ]RIO:\s*(.+?)(?:\s+PIS|\s+MATR|\n|$)", text_full, re.IGNORECASE)
    if nome_match:
        nome = nome_match.group(1).strip()

    cargo = ""
    cargo_match = re.search(r"NOME DO CARGO:\s*(.+?)(?:\s+SEG|\s+TER|\s+QUA|\s+QUI|\s+SEX|\s+SAB|\s+DOM|\s+CNPJ|\s+DATA|\n|$)", text_full, re.IGNORECASE)
    if cargo_match:
        cargo = cargo_match.group(1).strip()

    # 2. Mapear Âncoras de Cabeçalho
    anchors = {"TOTAL NORMAIS": None, "TOTAL NOTURNO": None, "FALTA E ATRASO": None, "EXTRA 70%": None}
    for i in range(len(words)):
        txt = words[i]['text'].upper()
        if txt == "TOTAL" and i+1 < len(words) and words[i+1]['text'].upper() == "NORMAIS":
            anchors["TOTAL NORMAIS"] = words[i]['x0']
        if txt == "TOTAL" and i+1 < len(words) and words[i+1]['text'].upper() == "NOTURNO":
            anchors["TOTAL NOTURNO"] = words[i]['x0']
        if txt == "FALTA" and i+2 < len(words) and words[i+2]['text'].upper() == "ATRASO":
            anchors["FALTA E ATRASO"] = words[i]['x0']
        if txt == "EXTRA" and i+1 < len(words) and "70" in words[i+1]['text']:
            anchors["EXTRA 70%"] = words[i]['x0']

    # 3. Extrair Totais
    result = {
        "NOME": nome, "CARGO": cargo,
        "TOTAL NORMAIS": "", "TOTAL NOTURNO": "",
        "FALTA E ATRASO": "", "EXTRA 70%": "",
        "EXTRA OU FALTA": ""
    }

    totais_y = None
    for word in words:
        if word['text'].upper() == "TOTAIS":
            totais_y = word['top']
            break
    
    if totais_y:
        totais_words = [w for w in words if abs(w['top'] - totais_y) < 10]
        for w in totais_words:
            txt = w['text']
            x = w['x0']
            if ":" in txt:
                best_col = None
                min_dist = 60
                for col, anchor_x in anchors.items():
                    if anchor_x is not None:
                        dist = abs(x - anchor_x)
                        if dist < min_dist:
                            min_dist = dist
                            best_col = col
                if best_col:
                    result[best_col] = txt

    # 4. Cálculo de Saldo
    f_min = hhmm_to_min(result["FALTA E ATRASO"])
    e_min = hhmm_to_min(result["EXTRA 70%"])
    if f_min or e_min:
        result["EXTRA OU FALTA"] = min_to_hhmm(e_min - f_min)
    
    return result

def extract_pdf_v17(pdf_file):
    results = []
    loja, mes_num, ano = "DESCONHECIDA", None, None
    with pdfplumber.open(pdf_file) as pdf:
        for i, page in enumerate(pdf.pages):
            if i == 0:
                text_first = page.extract_text()
                for sigla, keywords in LOJAS.items():
                    for kw in keywords:
                        if kw in text_first.upper(): loja = sigla; break
                m = re.search(r"DE \d{2}/(\d{2})/(\d{4})", text_first)
                if m: mes_num, ano = int(m.group(1)), int(m.group(2))
            
            data = parse_page_v17(page)
            if data:
                data["LOJA"], data["MES"], data["ANO"] = loja, mes_num, ano
                results.append(data)
    return results, loja, mes_num, ano

# =========================
# GOOGLE SHEETS
# =========================
@st.cache_resource
def get_client():
    creds_raw = os.environ.get(ENV_KEY_JSON)
    if not creds_raw: raise ValueError("Credencial GCP_SERVICE_ACCOUNT_JSON não configurada!")
    return gspread.authorize(Credentials.from_service_account_info(json.loads(creds_raw), scopes=SCOPES))

def enviar_para_planilha(df, aba_nome, loja):
    client = get_client()
    sh = client.open_by_key(re.search(r"/d/([a-zA-Z0-9-_]+)", PLANILHA_URL).group(1))
    try: aba = sh.worksheet(aba_nome)
    except: return 0, ["Aba não encontrada"]

    mapa = MAPA_LINHAS_JPBB if loja == "JPBB" else MAPA_LINHAS_TPBR
    enviados = 0
    for _, row in df.iterrows():
        nome_norm = normalize_name(row["NOME"])
        linha = mapa.get(nome_norm)
        if not linha: continue
        
        is_moto = "MOTOBOY" in str(row["CARGO"]).upper()
        if is_moto:
            if loja == "JPBB":
                aba.update(f"B{linha}:D{linha}", [[row["TOTAL NOTURNO"], row["TOTAL NORMAIS"], row["EXTRA 70%"]]])
            else:
                aba.update(f"B{linha}:D{linha}", [[row["TOTAL NORMAIS"], row["TOTAL NOTURNO"], row["EXTRA 70%"]]])
        else:
            aba.update(f"B{linha}:E{linha}", [[row["FALTA E ATRASO"], row["EXTRA 70%"], row["EXTRA OU FALTA"], row["TOTAL NOTURNO"]]])
        enviados += 1
    return enviados, []

# =========================
# UI
# =========================
uploaded_files = st.file_uploader("📂 Enviar PDFs", type=["pdf"], accept_multiple_files=True)

if uploaded_files:
    todos_dados = []
    infos_pdfs = []
    for f in uploaded_files:
        dados, loja, mes, ano = extract_pdf_v17(f)
        todos_dados.extend(dados)
        infos_pdfs.append({"arquivo": f.name, "loja": loja, "aba": f"{MESES_PT.get(mes, 'MES')}_{loja}"})

    df = pd.DataFrame(todos_dados)
    st.success(f"✅ {len(df)} funcionários extraídos")
    
    # Exibir tabela com nomes visíveis
    st.subheader("📋 Conferência de Dados")
    st.dataframe(df[["NOME", "CARGO", "FALTA E ATRASO", "EXTRA 70%", "EXTRA OU FALTA", "TOTAL NOTURNO", "TOTAL NORMAIS"]], use_container_width=True)

    if os.environ.get(ENV_KEY_JSON):
        st.divider()
        for info in infos_pdfs:
            aba_input = st.text_input(f"Aba para {info['arquivo']}", value=info["aba"], key=f"input_{info['arquivo']}")
            if st.button(f"🚀 Enviar {info['arquivo']} para Planilha", key=f"btn_{info['arquivo']}"):
                df_loja = df[df["LOJA"] == info["loja"]]
                enviados, erros = enviar_para_planilha(df_loja, aba_input, info["loja"])
                if enviados: st.success(f"✅ {enviados} funcionários enviados para '{aba_input}'!")
                if not enviados: st.warning("Nenhum funcionário correspondente encontrado no mapeamento.")
