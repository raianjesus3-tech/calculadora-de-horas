import streamlit as st
import pdfplumber
import re
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="Leitor Cartão de Ponto", layout="centered")

st.title("📄 Leitor Inteligente - Cartão de Ponto")

uploaded_file = st.file_uploader("Enviar PDF", type=["pdf"])


def hhmm_to_minutes(hhmm):
    if ":" not in hhmm:
        return 0
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def minutes_to_hhmm(minutes):
    sinal = "-" if minutes < 0 else ""
    minutes = abs(minutes)
    return f"{sinal}{minutes//60:02d}:{minutes%60:02d}"


if uploaded_file:

    with pdfplumber.open(uploaded_file) as pdf:
        texto = ""
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                texto += page_text + "\n"

    dados = []

    blocos = texto.split("Cartão")

    for bloco in blocos:

        if "NOME DO FUNCIONÁRIO:" in bloco and "TOTAIS" in bloco:

            nome_match = re.search(r"NOME DO FUNCIONÁRIO:\s*(.+?)\s+PIS", bloco)
            totais_match = re.search(r"TOTAIS\s+([0-9:\s]+)", bloco)

            if nome_match and totais_match:

                nome = nome_match.group(1).strip()

                horarios = re.findall(r"\d{1,3}:\d{2}", totais_match.group(1))

                # Inicializa tudo zerado
                noturnas = "00:00"
                total_noturno = "00:00"
                falta = "00:00"
                atraso = "00:00"
                extra70 = "00:00"

                if len(horarios) == 5:
                    noturnas, total_noturno, falta, atraso, extra70 = horarios

                elif len(horarios) == 4:
                    total_noturno, falta, atraso, extra70 = horarios

                elif len(horarios) == 6:
                    noturnas, total_noturno, falta, atraso, extra70, _ = horarios

                saldo = (
                    hhmm_to_minutes(extra70)
                    - hhmm_to_minutes(falta)
                    - hhmm_to_minutes(atraso)
                )

                dados.append({
                    "NOME": nome,
                    "NOTURNAS NORMAIS": noturnas,
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
            "⬇️ Baixar Excel",
            data=buffer,
            file_name="Relatorio_Cartao_de_Ponto.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.error("Não foi possível identificar dados no PDF.")
