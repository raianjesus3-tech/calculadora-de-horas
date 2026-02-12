import streamlit as st
import pdfplumber
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="Calculadora de Horas", layout="centered")

st.title("🧮 Calculadora de Horas")
st.write("Envie o PDF 'Extrato por Período' para gerar o relatório automático.")

uploaded_file = st.file_uploader("Enviar PDF", type=["pdf"])

# ---------------- FUNÇÕES ---------------- #

def hhmm_to_minutes(hhmm):
    if not hhmm or ":" not in hhmm:
        return 0
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)

def minutes_to_hhmm(minutes):
    h = abs(minutes) // 60
    m = abs(minutes) % 60
    return f"{h:02d}:{m:02d}"

def calcular_saldo(total_extra, falta):
    saldo = total_extra - falta
    return minutes_to_hhmm(saldo)

# ---------------- PROCESSAMENTO ---------------- #

if uploaded_file:

    dados_normais = []
    dados_motoboys = []

    with pdfplumber.open(uploaded_file) as pdf:
        texto = ""
        for page in pdf.pages:
            texto += page.extract_text() + "\n"

    linhas = texto.split("\n")

    for linha in linhas:

        if ("TPBR" in linha or "JPBB" in linha) and "TOTAL:" not in linha:

            partes = linha.split()
            nome = partes[3]

            valores = re.findall(r"\d{1,3}:\d{2}", linha)

            if len(valores) < 3:
                continue

            noturno = valores[0]
            falta = valores[1]
            extra70 = valores[2]
            extra100 = valores[3] if len(valores) > 3 else "00:00"

            total_extra_min = hhmm_to_minutes(extra70) + hhmm_to_minutes(extra100)
            total_falta_min = hhmm_to_minutes(falta)

            saldo = calcular_saldo(total_extra_min, total_falta_min)

            # Detectar motoboy
            if "MOTOBOY" in linha.upper():

                dados_motoboys.append({
                    "NOME": nome,
                    "NOTURNO": noturno,
                    "HORAS": minutes_to_hhmm(total_extra_min + total_falta_min),
                    "EXTRA": saldo
                })

            else:

                dados_normais.append({
                    "NOME": nome,
                    "FALTA": falta,
                    "EXTRA": minutes_to_hhmm(total_extra_min),
                    "EXTRA OU FALTA": saldo,
                    "NOTURNO": noturno
                })

    # ---------------- EXIBIÇÃO ---------------- #

    if dados_normais:

        st.subheader("Funcionários")

        df_normais = pd.DataFrame(dados_normais)
        st.dataframe(df_normais)

        buffer = BytesIO()
        df_normais.to_excel(buffer, index=False)
        buffer.seek(0)

        st.download_button(
            label="⬇️ Baixar Excel",
            data=buffer,
            file_name="Relatorio_Calculadora_de_Horas.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    if dados_motoboys:

        st.subheader("Motoboys Horistas")

        df_motoboys = pd.DataFrame(dados_motoboys)
        st.dataframe(df_motoboys)

    if not dados_normais and not dados_motoboys:
        st.error("Nenhum dado encontrado no PDF.")
