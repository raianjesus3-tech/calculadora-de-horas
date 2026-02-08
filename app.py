import streamlit as st
import pdfplumber
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="Calculadora de Horas", layout="centered")

st.title("🧮 Calculadora de Horas")
st.write("Envie o PDF 'Extrato por Período' para gerar o relatório automático.")

uploaded_file = st.file_uploader("Enviar PDF", type=["pdf"])

def hhmm_to_minutes(hhmm):
    if not hhmm or ":" not in hhmm:
        return 0
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)

def minutes_to_hhmm(minutes):
    h = abs(minutes) // 60
    m = abs(minutes) % 60
    return f"{h:02d}:{m:02d}"

def calcular_saldo(extra70, extra100, falta):
    total_extra = hhmm_to_minutes(extra70) + hhmm_to_minutes(extra100)
    total_falta = hhmm_to_minutes(falta)
    saldo = total_extra - total_falta

    if saldo > 0:
        return minutes_to_hhmm(saldo) + " EXTRA"
    elif saldo < 0:
        return minutes_to_hhmm(saldo) + " FALTA"
    else:
        return "00:00"

if uploaded_file:

    dados = []

    with pdfplumber.open(uploaded_file) as pdf:
        texto = ""
        for page in pdf.pages:
            texto += page.extract_text() + "\n"

    linhas = texto.split("\n")

    for linha in linhas:
        if "TPBR SERVICOS" in linha and "TOTAL:" not in linha:

            partes = linha.split()
            nome = " ".join(partes[3:-8])

            valores = re.findall(r"\d{1,3}:\d{2}", linha)

            noturno = valores[1] if len(valores) > 1 else "00:00"
            falta = valores[2] if len(valores) > 2 else "00:00"
            extra70 = valores[3] if len(valores) > 3 else "00:00"
            extra100 = valores[4] if len(valores) > 4 else "00:00"

            saldo = calcular_saldo(extra70, extra100, falta)

            dados.append({
                "NOME": nome,
                "FALTA": falta,
                "EXTRA": minutes_to_hhmm(hhmm_to_minutes(extra70) + hhmm_to_minutes(extra100)),
                "EXTRA OU FALTA": saldo,
                "NOTURNO": noturno
            })

    if dados:
        df = pd.DataFrame(dados)

        st.success("Relatório gerado com sucesso!")
        st.dataframe(df)

        buffer = BytesIO()
        df.to_excel(buffer, index=False)
        buffer.seek(0)

        st.download_button(
            label="⬇️ Baixar Excel",
            data=buffer,
            file_name="Relatorio_Calculadora_de_Horas.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.error("Nenhum dado encontrado no PDF.")
