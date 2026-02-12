import streamlit as st
import pdfplumber
import re
import pandas as pd
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils.dataframe import dataframe_to_rows


st.set_page_config(page_title="Leitor Cartão de Ponto", layout="centered")
st.title("📄 Leitor Inteligente - Cartão de Ponto")

uploaded_file = st.file_uploader("Enviar PDF", type=["pdf"])


def hhmm_to_minutes(hhmm: str) -> int:
    if not hhmm or ":" not in hhmm:
        return 0
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def minutes_to_hhmm(minutes: int) -> str:
    sinal = "-" if minutes < 0 else ""
    minutes = abs(minutes)
    h = minutes // 60
    m = minutes % 60
    return f"{sinal}{h:02d}:{m:02d}"


def extract_full_text(pdf_file) -> str:
    with pdfplumber.open(pdf_file) as pdf:
        texto = []
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                texto.append(t)
    return "\n".join(texto)


def parse_employee_blocks(texto: str) -> list[dict]:
    """
    Extrai por funcionário:
      - cargo
      - totais (lista de hh:mm)
    Observação: o número de colunas nos TOTAIS varia por funcionário.
    """
    # Cada página começa com "Cartão de Ponto", então split ajuda a isolar blocos.
    blocos = re.split(r"\bCartão\s+de\s+Ponto\b", texto)

    dados = []

    for bloco in blocos:
        if "NOME DO FUNCIONÁRIO:" not in bloco or "TOTAIS" not in bloco:
            continue

        nome_match = re.search(r"NOME DO FUNCIONÁRIO:\s*(.+?)\s+PIS", bloco)
        cargo_match = re.search(r"NOME DO CARGO:\s*(.+?)\s+CNPJ", bloco)
        totais_match = re.search(r"TOTAIS\s+([0-9:\s]+)", bloco)

        if not (nome_match and totais_match):
            continue

        nome = nome_match.group(1).strip()
        cargo = cargo_match.group(1).strip() if cargo_match else ""

        horarios = re.findall(r"\d{1,3}:\d{2}", totais_match.group(1))

        # Inicializa
        total_normais = "00:00"
        total_noturno = "00:00"
        falta_e_atraso = "00:00"
        extra70 = "00:00"
        noturnas_normais = "00:00"
        falta = "00:00"
        atraso = "00:00"

        # Heurística baseada no que vimos nos seus PDFs:
        # TPBR exemplo: "TOTAIS 45:36 130:46 48:13 00:20 05:55"
        #   -> NOTURNAS NORMAIS, TOTAL NORMAIS, TOTAL NOTURNO, FALTA E ATRASO, EXTRA 70%
        # JPBB exemplo: "TOTAIS 151:42 57:45 00:32 22:20"
        #   -> TOTAL NORMAIS, TOTAL NOTURNO, FALTA E ATRASO, EXTRA 70%
        #
        # Alguns ainda têm EXTRA 100% (6 valores) — a gente ignora o último por enquanto.

        if len(horarios) == 5:
            noturnas_normais, total_normais, total_noturno, falta_e_atraso, extra70 = horarios
        elif len(horarios) == 4:
            total_normais, total_noturno, falta_e_atraso, extra70 = horarios
        elif len(horarios) >= 6:
            # Pega os 5 primeiros e ignora o resto (ex: extra100)
            base = horarios[:5]
            noturnas_normais, total_normais, total_noturno, falta_e_atraso, extra70 = base

        # Como no PDF às vezes vem só "FALTA E ATRASO" (uma coluna),
        # vamos colocar tudo nessa coluna e também separar em "ATRASO" (se quiser no futuro).
        # Por enquanto:
        falta = falta_e_atraso
        atraso = "00:00"

        dados.append({
            "NOME": nome,
            "CARGO": cargo,
            "NOTURNAS NORMAIS": noturnas_normais,
            "TOTAL NORMAIS": total_normais,
            "TOTAL NOTURNO": total_noturno,
            "FALTA": falta,
            "ATRASO": atraso,
            "EXTRA 70%": extra70,
        })

    return dados


def build_excel(df_func: pd.DataFrame, df_moto: pd.DataFrame) -> BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = "RELATORIO"

    thin = Side(style="thin", color="000000")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    header_gray = PatternFill(start_color="BFBFBF", fill_type="solid")
    title_yellow = PatternFill(start_color="FFFF00", fill_type="solid")

    # ---- Bloco 1
    start_row = 2

    # Cabeçalho
    for col, name in enumerate(df_func.columns, start=1):
        c = ws.cell(row=start_row, column=col, value=name)
        c.font = Font(bold=True)
        c.alignment = Alignment(horizontal="center")
        c.fill = header_gray
        c.border = border

    # Dados
    for r, row in enumerate(df_func.itertuples(index=False), start=start_row + 1):
        for col, value in enumerate(row, start=1):
            c = ws.cell(row=r, column=col, value=value)
            c.alignment = Alignment(horizontal="center")
            c.border = border

    # Espaço e título motoboys
    row_title = start_row + len(df_func) + 3
    ws.merge_cells(start_row=row_title, start_column=1, end_row=row_title, end_column=4)
    t = ws.cell(row=row_title, column=1, value="MOTOBOYS HORISTAS")
    t.font = Font(bold=True)
    t.alignment = Alignment(horizontal="center")
    t.fill = title_yellow
    t.border = border

    # ---- Bloco 2
    header_row2 = row_title + 1
    for col, name in enumerate(df_moto.columns, start=1):
        c = ws.cell(row=header_row2, column=col, value=name)
        c.font = Font(bold=True)
        c.alignment = Alignment(horizontal="center")
        c.fill = header_gray
        c.border = border

    for r, row in enumerate(df_moto.itertuples(index=False), start=header_row2 + 1):
        for col, value in enumerate(row, start=1):
            c = ws.cell(row=r, column=col, value=value)
            c.alignment = Alignment(horizontal="center")
            c.border = border

    # Ajuste de largura
    widths = {1: 26, 2: 14, 3: 14, 4: 16, 5: 14}
    for col, w in widths.items():
        ws.column_dimensions[chr(64 + col)].width = w

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


# =========================
# EXECUÇÃO PRINCIPAL
# =========================
if uploaded_file:
    texto = extract_full_text(uploaded_file)
    dados = parse_employee_blocks(texto)

    if not dados:
        st.error("Não encontrei funcionários no PDF. (Padrão inesperado ou texto vazio)")
        st.stop()

    df = pd.DataFrame(dados)

    # EXTRA OU FALTA = EXTRA - FALTA
    df["EXTRA OU FALTA"] = (
        df["EXTRA 70%"].apply(hhmm_to_minutes)
        - df["FALTA"].apply(hhmm_to_minutes)
    ).apply(minutes_to_hhmm)

    # ----------- BLOCO 1 (funcionários)
    df_func = df[["NOME", "FALTA", "EXTRA 70%", "EXTRA OU FALTA", "TOTAL NOTURNO"]].copy()
    df_func.columns = ["NOME", "FALTA", "EXTRA", "EXTRA OU FALTA", "NOTURNO"]

    # ----------- BLOCO 2 (motoboys horistas) - baseado no CARGO
    is_motoboy = df["CARGO"].str.upper().str.contains("MOTOBOY", na=False)
    df_moto_raw = df[is_motoboy].copy()

    df_moto = df_moto_raw[["NOME", "TOTAL NOTURNO", "TOTAL NORMAIS", "EXTRA 70%"]].copy()
    df_moto.columns = ["NOME", "NOTURNO", "HORAS", "EXTRA"]

    # Mostrar na tela
    st.success("✅ Relatório gerado!")
    st.subheader("FUNCIONÁRIOS")
    st.dataframe(df_func, use_container_width=True)

    st.subheader("MOTOBOYS HORISTAS")
    st.dataframe(df_moto, use_container_width=True)

    # Exportar Excel formatado
    excel_buffer = build_excel(df_func, df_moto)

    st.download_button(
        "⬇️ Baixar Excel no modelo",
        data=excel_buffer,
        file_name="Relatorio_Modelo.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
