def parse_employee_blocks(texto: str):

    # divide por funcionário
    blocos = re.split(r"NOME DO FUNCION", texto, flags=re.IGNORECASE)

    out = []

    for bloco in blocos:

        bloco = "NOME DO FUNCION" + bloco

        if "PIS" not in bloco:
            continue

        # -------------------------
        # NOME
        # -------------------------
        nome_match = re.search(
            r"NOME DO FUNCION[ÁA]RIO:\s*(.+?)\s+PIS",
            bloco,
            flags=re.IGNORECASE | re.DOTALL
        )

        if not nome_match:
            continue

        nome = nome_match.group(1).replace("\n", " ").strip()
        nome = re.sub(r"\s+", " ", nome)

        # -------------------------
        # CARGO
        # -------------------------
        cargo_match = re.search(
            r"NOME DO CARGO:\s*(.+)",
            bloco,
            flags=re.IGNORECASE
        )

        cargo = cargo_match.group(1).split("\n")[0].strip() if cargo_match else ""

        # -------------------------
        # TOTAIS
        # -------------------------
        totais_match = re.search(
            r"TOTAIS\s*(.*)",
            bloco,
            flags=re.IGNORECASE
        )

        totais_line = totais_match.group(1) if totais_match else ""

        # pega todos horários da linha
        horarios = re.findall(r"\d{1,3}:\d{2}", totais_line)

        total_normais = "00:00"
        total_noturno = "00:00"
        falta = "00:00"
        extra = "00:00"

        # -------------------------
        # INTERPRETAÇÃO
        # -------------------------

        if len(horarios) == 2:

            total_normais = horarios[0]
            extra = horarios[1]

        elif len(horarios) == 3:

            total_normais = horarios[0]
            falta = horarios[1]
            extra = horarios[2]

        elif len(horarios) == 4:

            total_normais = horarios[1]
            total_noturno = horarios[2]
            extra = horarios[3]

        elif len(horarios) >= 5:

            total_normais = horarios[1]
            total_noturno = horarios[2]
            falta = horarios[3]
            extra = horarios[4]

        out.append({

            "NOME": nome,
            "CARGO": cargo,
            "TOTAL NORMAIS": total_normais,
            "TOTAL NOTURNO": total_noturno,
            "FALTA": falta,
            "EXTRA 70%": extra

        })

    return out
