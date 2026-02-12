import streamlit as st
import pdfplumber
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="Calculadora de Horas", layout="centered")

st.title("🧮 Calculadora de Horas")
st.write("Envie o PDF 'Extrato por Período'.")

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


def buscar_valor(texto, campo):
    match = re.search(rf"{campo}\s+(\d{{1,3}}:\d{{2}})", texto)
    return match.group(1) if match else "00:00"


if uploaded_file:

    dados = []

    with pdfplumber.open(uploaded_file) as pdf:
        texto = ""
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                texto += page_text + "\n"

    # Separar funcionários por blocos
    blocos = re.split(r"\n(?=\d{6,})", texto)

    for bloco in blocos:

        if "TOTAL NOTURNO" in bloco:

            linhas = bloco.strip().split("\n")
            nome = linhas[0].strip()

            noturno = buscar_valor(bloco, "TOTAL NOTURNO")
            falta = buscar_valor(bloco, "FALTA")
            atraso = buscar_valor(bloco, "ATRASO")
            extra70 = buscar_valor(bloco, "70%")

            total_extra = hhmm_to_minutes(extra70)
            total_falta = hhmm_to_minutes(falta) + hhmm_to_minutes(atraso)

            saldo = total_extra - total_falta

            dados.append({
                "NOME": nome,
                "TOTAL NOTURNO": noturno,
                "FALTA + ATRASO": minutes_to_hhmm(total_falta),
                "EXTRA 70%": minutes_to_hhmm(total_extra),
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
            file_name="Relatorio_Calculadora_de_Horas.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.error("Nenhum dado encontrado no PDF.")
