if dados:

    df = pd.DataFrame(dados)

    # ===============================
    # BLOCO 1 - FUNCIONÁRIOS NORMAIS
    # ===============================

    df["EXTRA OU FALTA"] = (
        df["EXTRA 70%"].apply(hhmm_to_minutes)
        - df["FALTA"].apply(hhmm_to_minutes)
    ).apply(minutes_to_hhmm)

    df1 = df[[
        "NOME",
        "FALTA",
        "EXTRA 70%",
        "EXTRA OU FALTA",
        "TOTAL NOTURNO"
    ]].copy()

    df1.columns = [
        "NOME",
        "FALTA",
        "EXTRA",
        "EXTRA OU FALTA",
        "NOTURNO"
    ]

    # ===============================
    # BLOCO 2 - MOTOBOYS HORISTAS
    # (exemplo: quem tiver HORAS > 0 e EXTRA 0)
    # ===============================

    df2 = df[[
        "NOME",
        "TOTAL NOTURNO",
        "TOTAL NORMAIS",
        "EXTRA 70%"
    ]].copy()

    df2.columns = [
        "NOME",
        "NOTURNO",
        "HORAS",
        "EXTRA"
    ]

    # ===============================
    # MOSTRAR NA TELA
    # ===============================

    st.success("Relatório gerado com sucesso!")

    st.subheader("FUNCIONÁRIOS")
    st.dataframe(df1)

    st.subheader("MOTOBOYS HORISTAS")
    st.dataframe(df2)

    # ===============================
    # EXPORTAÇÃO FORMATADA
    # ===============================

    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill
    from openpyxl.utils.dataframe import dataframe_to_rows

    wb = Workbook()
    ws = wb.active
    ws.title = "RELATORIO"

    row_num = 1

    # ----- BLOCO 1 -----
    for r in dataframe_to_rows(df1, index=False, header=True):
        ws.append(r)

    # Estilizar cabeçalho
    for col in range(1, 6):
        ws.cell(row=1, column=col).font = Font(bold=True)
        ws.cell(row=1, column=col).alignment = Alignment(horizontal="center")
        ws.cell(row=1, column=col).fill = PatternFill(start_color="CCCCCC", fill_type="solid")

    row_num = ws.max_row + 2

    # ----- TÍTULO MOTOBOYS -----
    ws.merge_cells(start_row=row_num, start_column=1, end_row=row_num, end_column=4)
    ws.cell(row=row_num, column=1).value = "MOTOBOYS HORISTAS"
    ws.cell(row=row_num, column=1).font = Font(bold=True)
    ws.cell(row=row_num, column=1).alignment = Alignment(horizontal="center")
    ws.cell(row=row_num, column=1).fill = PatternFill(start_color="FFFF00", fill_type="solid")

    row_num += 1

    # ----- BLOCO 2 -----
    for r in dataframe_to_rows(df2, index=False, header=True):
        ws.append(r)

    for col in range(1, 5):
        ws.cell(row=row_num, column=col).font = Font(bold=True)
        ws.cell(row=row_num, column=col).alignment = Alignment(horizontal="center")
        ws.cell(row=row_num, column=col).fill = PatternFill(start_color="CCCCCC", fill_type="solid")

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    st.download_button(
        "⬇️ Baixar Modelo Formatado",
        data=buffer,
        file_name="Relatorio_Modelo_Formatado.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
