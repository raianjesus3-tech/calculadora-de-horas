import streamlit as st
import pdfplumber
import re
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="Leitor de Cartão de Ponto", layout="centered")

st.title("📄 Leitor Inteligente - Cartão de Ponto")
st.write("Envie o PDF do cartão de ponto para gerar o relatório automático.")

uploaded_file = st.file_uploader("Enviar PDF", type=["pdf"])


# ==========================
# Funções auxiliares
# ==========================

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


# ==========================
# Processamento
# ==========================

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

        # Captura Nome
        if "Nome:" in linha:
            nome_atual = linha.split("Nome:")[1].strip()

        # Captura Totais
        if "TOTAIS" in linha and nome_atual:

            # Captura todos os horários da linha
            horarios = re.findall(r"\d{1,3}:\d{2}", linha)

            if len(horarios) >= 6:
                noturnas_normais = horarios[0]
                total_noturno = horarios[1]
                falta = horarios[2]
                atraso = horarios[3]
                extra70 = horarios[4]

                # Regra de cálculo (ajuste se quiser)
                saldo_minutos = (
                    hhmm_to_minutes(extra70)
                    - hhmm_to_minutes(falta)
                    - hhmm_to_minutes(atraso)
                )

                dados.append({
                    "NOME": nome_atual,
                    "NOTURNAS NORMAIS": noturnas_normais,
                    "TOTAL NOTURNO": total_noturno,
                    "FALTA": falta,
                    "ATRASO": atraso,
                    "EXTRA 70%": extra70,
                    "SALDO FINAL": minutes_to_hhmm(saldo_minutos)
                })

    if dados:
        df = pd.DataFrame(dados)

        st.success("Relatório gerado com sucesso!")
        st.subheader("📊 Resultado Processado")
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
        st.error("Nenhum funcionário encontrado ou padrão diferente no PDF.")
