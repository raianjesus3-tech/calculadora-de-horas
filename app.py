import streamlit as st
import pdfplumber

st.set_page_config(page_title="Teste PDF", layout="centered")

st.title("🔎 Teste de Leitura do PDF")
st.write("Envie o PDF para verificarmos como o sistema está lendo o conteúdo.")

uploaded_file = st.file_uploader("Enviar PDF", type=["pdf"])

if uploaded_file:

    try:
        with pdfplumber.open(uploaded_file) as pdf:
            for i, page in enumerate(pdf.pages):
                texto = page.extract_text()

                st.subheader(f"Página {i + 1}")

                if texto:
                    st.text(texto)
                else:
                    st.error("⚠️ Nenhum texto encontrado nesta página.")

    except Exception as e:
        st.error(f"Erro ao ler o PDF: {e}")
