"""
report_generator.py
Gera um relatório PDF profissional a partir dos leads coletados, com marca
d'água diagonal personalizada e rodapé com dados de contato em todas as páginas.
"""

from io import BytesIO
from datetime import datetime
import pandas as pd

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, KeepTogether
from reportlab.pdfgen import canvas


def _draw_watermark_and_footer(canvas_obj: canvas.Canvas, doc_obj, company_name, contact_info, watermark_text):
    """
    Função de callback chamada pelo reportlab em CADA página do documento
    (via onFirstPage/onLaterPages). É aqui que desenhamos elementos que
    devem se repetir em todo o relatório: a marca d'água de fundo e o rodapé.
    """
    canvas_obj.saveState()

    # --- Marca d'água: texto grande, rotacionado, quase transparente ---
    canvas_obj.setFont("Helvetica-Bold", 60)
    canvas_obj.setFillColor(colors.HexColor("#1A237E"))
    canvas_obj.setFillAlpha(0.06)  # opacidade baixa para não atrapalhar a leitura
    canvas_obj.translate(A4[0] / 2, A4[1] / 2)
    canvas_obj.rotate(45)
    canvas_obj.drawCentredString(0, 0, watermark_text)
    canvas_obj.restoreState()

    # --- Rodapé: linha decorativa + contato + número de página ---
    canvas_obj.saveState()
    canvas_obj.setStrokeColor(colors.HexColor("#DDDDDD"))
    canvas_obj.line(1.8 * cm, 1.6 * cm, A4[0] - 1.8 * cm, 1.6 * cm)

    canvas_obj.setFont("Helvetica", 8)
    canvas_obj.setFillColor(colors.HexColor("#777777"))
    canvas_obj.drawString(1.8 * cm, 1.3 * cm, f"{company_name} | {contact_info}")
    canvas_obj.drawRightString(A4[0] - 1.8 * cm, 1.3 * cm, f"Página {doc_obj.page}")
    canvas_obj.restoreState()


def generate_pdf_report(
    df: pd.DataFrame,
    niche: str,
    city: str,
    output_path,
    company_name: str = "LeadHunter Pro",
    contact_info: str = "contato@leadhunterpro.com | (62) 9 9999-9999",
    watermark_text: str = "LEADHUNTER PRO",
) -> None:
    """
    Recebe um DataFrame com os leads e escreve o PDF formatado em `output_path`.
    `output_path` pode ser uma string (caminho de arquivo) ou um buffer
    (ex: io.BytesIO), o que é útil para gerar o PDF em memória sem tocar o disco.
    """
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        topMargin=2.5 * cm,
        bottomMargin=2.5 * cm,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleCustom",
        parent=styles["Title"],
        fontSize=28,
        leading=32,
        textColor=colors.HexColor("#0B3D91"),
        spaceAfter=6,
        alignment=TA_CENTER,
    )
    subtitle_style = ParagraphStyle(
        "SubtitleCustom",
        parent=styles["Normal"],
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#475569"),
        spaceAfter=10,
        alignment=TA_CENTER,
    )
    header_style = ParagraphStyle(
        "HeaderCustom",
        parent=styles["Heading2"],
        fontSize=16,
        leading=20,
        textColor=colors.HexColor("#1C3D72"),
        spaceAfter=8,
    )
    normal_style = ParagraphStyle(
        "NormalCustom",
        parent=styles["BodyText"],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#2E3E5C"),
    )
    small_style = ParagraphStyle(
        "SmallCustom",
        parent=styles["BodyText"],
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#555555"),
    )

    summary_table_data = [
        [Paragraph("<b>Empresa</b>", normal_style), Paragraph(f"<b>{company_name}</b>", normal_style)],
        [Paragraph("Nicho", normal_style), Paragraph(niche, normal_style)],
        [Paragraph("Cidade", normal_style), Paragraph(city, normal_style)],
        [Paragraph("Total de leads", normal_style), Paragraph(str(len(df)), normal_style)],
        [Paragraph("Emitido em", normal_style), Paragraph(datetime.now().strftime('%d/%m/%Y %H:%M'), normal_style)],
    ]

    elements = [
        Paragraph("LEADHUNTER PRO", title_style),
        Paragraph("Relatório Executivo de Inteligência de Mercado", subtitle_style),
        Spacer(1, 0.2 * cm),
        Table(summary_table_data, colWidths=[6.5 * cm, 9 * cm], hAlign="LEFT", style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B3D91")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TEXTCOLOR", (0, 1), (-1, -1), colors.HexColor("#2E3E5C")),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#C1C7D3")),
        ])),
        Spacer(1, 0.35 * cm),
        Paragraph("Visão Geral", header_style),
        Paragraph(
            "Relatório de leads extraídos com foco em empresas qualificadas. Inclui contatos, endereços, telefones e canais digitados, prontos para conversão e prospecção.",
            normal_style,
        ),
        Spacer(1, 0.5 * cm),
    ]

    # --- Tabela de dados ---
    table_data = [list(df.columns)] + df.astype(str).values.tolist()
    col_count = len(df.columns)
    available_width = A4[0] - 3.6 * cm
    col_width = max(4.0 * cm, available_width / col_count)
    table = Table(table_data, colWidths=[col_width] * col_count, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B3D91")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F6F7FB")]),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#C1C7D3")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ]
        )
    )
    elements.append(table)
    elements.append(Spacer(1, 0.4 * cm))
    elements.append(Paragraph("Observações", header_style))
    elements.append(Paragraph(
        "Este relatório foi gerado automaticamente a partir de dados extraídos do Google Maps e filtrados por relevância. "
        "Use-o como base para prospecção ativa, acompanhamento de vendas e construção de pitch comercial.",
        normal_style,
    ))

    # doc.build aceita callbacks separados para a primeira página e as
    # páginas seguintes — usamos a mesma função para as duas, mas a API
    # permite, por exemplo, um cabeçalho diferente só na capa.
    doc.build(
        elements,
        onFirstPage=lambda c, d: _draw_watermark_and_footer(c, d, company_name, contact_info, watermark_text),
        onLaterPages=lambda c, d: _draw_watermark_and_footer(c, d, company_name, contact_info, watermark_text),
    )


def generate_pdf_bytes(df: pd.DataFrame, **kwargs) -> bytes:
    """
    Versão que retorna os bytes do PDF em memória, em vez de salvar em disco.
    Ideal para alimentar diretamente o st.download_button do Streamlit.
    """
    buffer = BytesIO()
    generate_pdf_report(df, output_path=buffer, **kwargs)
    buffer.seek(0)
    return buffer.read()