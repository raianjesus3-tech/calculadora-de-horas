import streamlit as st
import pdfplumber
import re
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="Leitor de Cartão de Ponto", layout="centered")

st.title("📄 Leitor Inteligente - Cartão de Ponto")

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

    with pdfplumber.open(uploaded_file) as pdf:
        texto = ""
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                texto += page_text + "\n"

    # Debug opcional
    # st.text(texto)

    # Pega todos os nomes
    nomes = re.findall(r"Nome\s*:\s*(.+)", texto)

    # Pega todos os blocos que vêm depois de TOTAIS
    blocos_totais = re.findall(r"TOTAIS.*?(\d{1,3}:\d{2}.*)", texto)

    dados = []

    for i in range(min(len(nomes), len(blocos_totais))):

        nome = nomes[i]

        horarios = re.findall(r"\d{1,3}:\d{2}", blocos_totais[i])

        if len(horarios) >= 5:
            noturnas_normais = horarios[0]
            total_noturno = horarios[1]
            falta = horarios[2]
            atraso = horarios[3]
            extra70 = horarios[4]

            saldo = (
                hhmm_to_minutes(extra70)
                - hhmm_to_minutes(falta)
                - hhmm_to_minutes(atraso)
            )

            dados.append({
                "NOME": nome,
                "NOTURNAS NORMAIS": noturnas_normais,
                "TOTAL NOTURNO": total_noturno,
                "FALTA": falta,
                "ATRASO": atraso,
                "EXTRA 70%": extra70,
                "SALDO FINAL": minutes_to_hhmm(saldo)
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
            file_name="Relatorio_Cartao_de_Ponto.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    else:
        st.error("Não foi possível identificar o padrão no PDF.")
