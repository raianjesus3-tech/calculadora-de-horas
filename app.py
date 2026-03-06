def parse_employee_blocks(texto: str):
    blocos = re.split(r"Cart[aã]o\s+de\s+Ponto", texto, flags=re.IGNORECASE)

    out = []

    for bloco in blocos:
        bloco_up = bloco.upper()

        if ("NOME DO FUNCION" not in bloco_up) or ("TOTAIS" not in bloco_up):
            continue

        nome_match = re.search(
            r"NOME DO FUNCION[AÁ]RIO:\s*(.+?)\s+PIS",
            bloco,
            flags=re.IGNORECASE | re.DOTALL
        )

        if not nome_match:
            continue

        nome = nome_match.group(1).replace("\n", " ").strip()
        nome = re.sub(r"\s+", " ", nome)

        cargo_match = re.search(
            r"NOME DO CARGO:\s*(.+)",
            bloco,
            flags=re.IGNORECASE
        )

        cargo = cargo_match.group(1).split("\n")[0].strip() if cargo_match else ""

        # pega somente a LINHA do TOTAIS
        totais_line_match = re.search(
            r"^TOTAIS\s*(.*)$",
            bloco,
            flags=re.IGNORECASE | re.MULTILINE
        )

        totais_line = totais_line_match.group(1).strip() if totais_line_match else ""

        # extrai apenas horários hh:mm
        horarios = re.findall(r"\d{1,3}:\d{2}", totais_line)

        total_normais = "00:00"
        total_noturno = "00:00"
        falta = "00:00"
        extra = "00:00"

        if len(horarios) == 2:
            # Ex.: KAUAN -> TOTAIS 168:40 34:50
            total_normais = horarios[0]
            extra = horarios[1]

        elif len(horarios) == 3:
            # Ex.: ANDREIA -> TOTAIS 158:45 00:16 02:41
            total_normais = horarios[0]
            falta = horarios[1]
            extra = horarios[2]

        elif len(horarios) == 4:
            # Ex.: ADRIANO -> TOTAIS 41:05 124:05 42:54 01:42
            # 1 = NOTURNAS NORMAIS (ignora)
            total_normais = horarios[1]
            total_noturno = horarios[2]
            extra = horarios[3]

        elif len(horarios) >= 5:
            # Ex.: MARCIO / RODRIGO / ELEN
            # 1 = NOTURNAS NORMAIS (ignora)
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
