import streamlit as st
import pdfplumber
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="Calculadora de Horas", layout="centered")

st.title("🧮 Calculadora de Horas")
st.write("Envie o PDF 'Extrato por Período' para gerar o relatório automático.")

uploaded_file = st.file_uploader("Enviar PDF", type=["pdf"])


# ==============================
# Funções auxiliares
# ==============================

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


# ==============================
# Processamento do PDF
# ==============================

if uploaded_file:

    dados = []

    with pdfplumber.open(uploaded_file) as pdf:
        texto = ""
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                texto += page_text + "\n"

    linhas = texto.split("\n")

    for linha in linhas:

        # Captura todos horários da linha
        valores = re.findall(r"\d{1,3}:\d{2}", linha)

        # Só processa linhas que realmente parecem funcionário
        if len(valores) >= 3:

            try:
                # Nome = tudo antes do primeiro horário
                primeiro_horario = valores[0]
                nome = linha.split(primeiro_horario)[0].strip()

                # Pegando sempre os últimos horários da linha
                noturno = valores[-4] if len(valores) >= 4 else "00:00"
                falta = valores[-3] if len(valores) >= 3 else "00:00"
                extra70 = valores[-2] if len(valores) >= 2 else "00:00"
                extra100 = valores[-1] if len(valores) >= 4 else "00:00"

                total_extra_min = hhmm_to_minutes(extra70) + hhmm_to_minutes(extra100)
                falta_min = hhmm_to_minutes(falta)

                saldo = total_extra_min - falta_min

                dados.append({
                    "NOME": nome,
                    "FALTA": falta,
                    "EXTRA": minutes_to_hhmm(total_extra_min),
                    "EXTRA OU FALTA": minutes_to_hhmm(saldo),
                    "NOTURNO": noturno
                })

            except:
                continue

    # ==============================
    # Exibir resultado
    # ==============================

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
