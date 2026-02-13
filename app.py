import streamlit as st
import pdfplumber
import re
import pandas as pd
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

st.set_page_config(page_title="Leitor Cartão de Ponto", layout="centered")
st.title("📄 Leitor Inteligente - Cartão de Ponto")
st.write("Envie o PDF (TPBR ou JPBB). O app separa Motoboys e gera Excel no seu modelo.")

uploaded_file = st.file_uploader("Enviar PDF", type=["pdf"])


# ==========================
# Funções auxiliares
# ==========================
def hhmm_to_minutes(hhmm: str) -> int:
    if not hhmm or ":" not in hhmm:
        return 0
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def minutes_to_hhmm(minutes: int) -> str:
    sign = "-" if minutes < 0 else ""
    minutes = abs(minutes)
    return f"{sign}{minutes // 60:02d}:{minutes % 60:02d}"


# ==========================
# Leitura do PDF
# ==========================
def extract_full_text(pdf_file) -> str:
    with pdfplumber.open(pdf_file) as pdf:
        parts = []
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                parts.append(t)
    return "\n".join(parts)


# ==========================
# Parser
# ==========================
def parse_employee_blocks(texto: str) -> list[dict]:
    blocos = re.split(r"\bCartão\s+de\s+Ponto\b", texto)
    out = []

    for bloco in blocos:
        if "NOME DO FUNCIONÁRIO:" not in bloco or "TOTAIS" not in bloco:
            continue

        nome_match = re.search(r"NOME DO FUNCIONÁRIO:\s*(.+?)\s+PIS", bloco)
        if not nome_match:
            continue
        nome = nome_match.group(1).strip()

        # Captura cargo corretamente
        cargo_match = re.search(r"NOME DO CARGO:\s*(.+)", bloco)
        cargo = cargo_match.group(1).split("\n")[0].strip().upper() if cargo_match else ""

        totais_match = re.search(r"TOTAIS\s+([0-9:\s]+)", bloco)
        if not totais_match:
            continue

        horarios = re.findall(r"\d{1,3}:\d{2}", totais_match.group(1))

        noturnas_normais = "00:00"
        total_normais = "00:00"
        total_noturno = "00:00"
        falta_e_atraso = "00:00"
        extra70 = "00:00"

        if len(horarios) == 5:
            noturnas_normais, total_normais, total_noturno, falta_e_atraso, extra70 = horarios
        elif len(horarios) == 4:
            total_normais, total_noturno, falta_e_atraso, extra70 = horarios
        elif len(horarios) >= 6:
            base = horarios[:5]
            noturnas_normais, total_normais, total_noturno, falta_e_atraso, extra70 = base
        elif len(horarios) == 3:
            total_normais, total_noturno, extra70 = horarios
        elif len(horarios) == 2:
            total_normais, extra70 = horarios
        elif len(horarios) == 1:
            total_normais = horarios[0]

        falta = falta_e_atraso
        atraso = "00:00"

        out.append({
            "NOME": nome,
            "CARGO": cargo,
            "NOTURNAS NORMAIS": noturnas_normais,
            "TOTAL NORMAIS": total_normais,
            "TOTAL NOTURNO": total_noturno,
            "FALTA": falta,
            "ATRASO": atraso,
            "EXTRA 70%": extra70,
        })

    return out


# ==========================
# Excel Formatado
# ==========================
def build_excel(df_func: pd.DataFrame, df_moto: pd.DataFrame) -> BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = "RELATORIO"

    thin = Side(style="thin", color="000000")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    header_gray = PatternFill(start_color="BFBFBF", fill_type="solid")
    title_yellow = PatternFill(start_color="FFFF00", fill_type="solid")

    def style_cell(cell, bold=False, fill=None):
        cell.font = Font(bold=bold)
        cell.alignment = Alignment(horizontal="center", vertical="center")
        if fill:
            cell.fill = fill
        cell.border = border

    # BLOCO FUNCIONÁRIOS
    start_row = 2

    for col, name in enumerate(df_func.columns, start=1):
        c = ws.cell(row=start_row, column=col, value=name)
        style_cell(c, bold=True, fill=header_gray)

    for r_idx, row in enumerate(df_func.itertuples(index=False), start=start_row + 1):
        for col_idx, value in enumerate(row, start=1):
            c = ws.cell(row=r_idx, column=col_idx, value=value)
            style_cell(c)

    # Título Motoboys
    row_title = start_row + len(df_func) + 3
    ws.merge_cells(start_row=row_title, start_column=1, end_row=row_title, end_column=4)
    t = ws.cell(row=row_title, column=1, value="MOTOBOYS HORISTAS")
    style_cell(t, bold=True, fill=title_yellow)
    ws.row_dimensions[row_title].height = 20

    # BLOCO MOTOBOYS
    header_row2 = row_title + 1

    for col, name in enumerate(df_moto.columns, start=1):
        c = ws.cell(row=header_row2, column=col, value=name)
        style_cell(c, bold=True, fill=header_gray)

    for r_idx, row in enumerate(df_moto.itertuples(index=False), start=header_row2 + 1):
        for col_idx, value in enumerate(row, start=1):
            c = ws.cell(row=r_idx, column=col_idx, value=value)
            style_cell(c)

    ws.column_dimensions["A"].width = 35
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 14
    ws.column_dimensions["D"].width = 18
    ws.column_dimensions["E"].width = 14

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


# ==========================
# EXECUÇÃO
# ==========================
if uploaded_file:
    texto = extract_full_text(uploaded_file)
    dados = parse_employee_blocks(texto)

    if not dados:
        st.error("Não encontrei funcionários no PDF.")
        st.stop()

    df = pd.DataFrame(dados)

    df["EXTRA OU FALTA"] = (
        df["EXTRA 70%"].apply(hhmm_to_minutes)
        - df["FALTA"].apply(hhmm_to_minutes)
    ).apply(minutes_to_hhmm)

    # Separar motoboys corretamente
    is_motoboy = df["CARGO"].astype(str).str.contains(r"\bMOTOBOY\b", regex=True, na=False)

    df_func = df[~is_motoboy][["NOME", "FALTA", "EXTRA 70%", "EXTRA OU FALTA", "TOTAL NOTURNO"]].copy()
    df_func.columns = ["NOME", "FALTA", "EXTRA", "EXTRA OU FALTA", "NOTURNO"]

    df_moto_raw = df[is_motoboy].copy()
    df_moto = df_moto_raw[["NOME", "TOTAL NOTURNO", "TOTAL NORMAIS", "EXTRA 70%"]].copy()
    df_moto.columns = ["NOME", "NOTURNO", "HORAS", "EXTRA"]

    st.success("✅ Relatório gerado com sucesso!")
    st.subheader("FUNCIONÁRIOS")
    st.dataframe(df_func, use_container_width=True)

    st.subheader("MOTOBOYS HORISTAS")
    st.dataframe(df_moto, use_container_width=True)

    excel_buffer = build_excel(df_func, df_moto)
    st.download_button(
        "⬇️ Baixar Excel no modelo",
        data=excel_buffer,
        file_name="Relatorio_Modelo.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
