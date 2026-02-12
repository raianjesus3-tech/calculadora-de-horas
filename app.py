import streamlit as st
import pdfplumber
import re
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="Calculadora de Horas", layout="centered")

st.title("🧮 Calculadora - Folha de Ponto")
st.write("Envie a Folha de Ponto (PDF com todos os funcionários).")

uploaded_file = st.file_uploader("Enviar PDF", type=["pdf"])


def hhmm_to_minutes(hhmm):
    if not hhmm or ":" not in hhmm:
        return 0
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def minutes_to_hhmm(minutes):
    sinal = "-" if minutes < 0 else ""
    minutes = abs(minutes)
    h = minutes // 60
    m = minutes % 60
    return f"{sinal}{h:02d}:{m:02d}"


if uploaded_file:

    dados = []

    with pdfplumber.open(uploaded_file) as pdf:
        texto = ""
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                texto += page_text + "\n"

    linhas = texto.split("\n")

    nome_atual = None

    for linha in linhas:

        # Captura nome
        if linha.strip().startswith("Nome:"):
            nome_atual = linha.replace("Nome:", "").strip()

        # Quando encontra TOTAIS
        if linha.strip().startswith("TOTAIS") and nome_atual:

            horarios = re.findall(r"\d{1,3}:\d{2}", linha)

            if len(horarios) >= 4:

                total_normais = horarios[0]
                total_noturno = horarios[1]
                falta = horarios[2]
                extra70 = horarios[3]

                saldo = hhmm_to_minutes(extra70) - hhmm_to_minutes(falta)

                dados.append({
                    "NOME": nome_atual,
                    "TOTAL NORMAIS": total_normais,
                    "TOTAL NOTURNO": total_noturno,
                    "FALTA": falta,
                    "EXTRA 70%": extra70,
                    "EXTRA OU FALTA": minutes_to_hhmm(saldo)
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
            file_name="Relatorio_Folha_de_Ponto.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    else:
        st.error("Nenhum funcionário encontrado no PDF.")
