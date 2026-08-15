import os
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

pdf_path = "Kazumi_Official_Economy_Audit_Report.pdf"

doc = SimpleDocTemplate(
    pdf_path,
    pagesize=letter,
    rightMargin=36,
    leftMargin=36,
    topMargin=36,
    bottomMargin=36
)

styles = getSampleStyleSheet()

# Custom styles
title_style = ParagraphStyle(
    "TitleStyle",
    parent=styles["Heading1"],
    fontName="Helvetica-Bold",
    fontSize=22,
    leading=26,
    textColor=colors.HexColor("#6366f1"),
    alignment=1, # Center
)

subtitle_style = ParagraphStyle(
    "SubTitleStyle",
    parent=styles["Normal"],
    fontName="Helvetica-Oblique",
    fontSize=11,
    leading=14,
    textColor=colors.HexColor("#64748b"),
    alignment=1, # Center
)

section_heading = ParagraphStyle(
    "SectionHeading",
    parent=styles["Heading2"],
    fontName="Helvetica-Bold",
    fontSize=13,
    leading=17,
    textColor=colors.HexColor("#0f172a"),
    spaceBefore=12,
    spaceAfter=6
)

body_style = ParagraphStyle(
    "BodyStyle",
    parent=styles["Normal"],
    fontName="Helvetica",
    fontSize=9,
    leading=13,
    textColor=colors.HexColor("#334155")
)

table_header_style = ParagraphStyle(
    "TableHeader",
    parent=styles["Normal"],
    fontName="Helvetica-Bold",
    fontSize=9,
    leading=11,
    textColor=colors.white,
    alignment=1
)

table_cell_style = ParagraphStyle(
    "TableCell",
    parent=styles["Normal"],
    fontName="Helvetica",
    fontSize=8,
    leading=10,
    textColor=colors.HexColor("#1e293b"),
    alignment=0
)

table_cell_bold = ParagraphStyle(
    "TableCellBold",
    parent=styles["Normal"],
    fontName="Helvetica-Bold",
    fontSize=8,
    leading=10,
    textColor=colors.HexColor("#0f172a"),
    alignment=0
)

status_capped = ParagraphStyle(
    "StatusCapped",
    parent=styles["Normal"],
    fontName="Helvetica-Bold",
    fontSize=8,
    leading=10,
    textColor=colors.HexColor("#dc2626"), # Red
    alignment=1
)

status_clean = ParagraphStyle(
    "StatusClean",
    parent=styles["Normal"],
    fontName="Helvetica-Bold",
    fontSize=8,
    leading=10,
    textColor=colors.HexColor("#16a34a"), # Green
    alignment=1
)

elements = []

# Title & Subtitle
elements.append(Paragraph("🌸 KAZUMI RPG BOT — OFFICIAL ECONOMY AUDIT REPORT", title_style))
elements.append(Spacer(1, 4))
elements.append(Paragraph("Transparency Statement & Game Economy Rebalance Audit | Date: July 24, 2026", subtitle_style))
elements.append(Spacer(1, 10))
elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#6366f1"), spaceAfter=12))

# Executive Summary
summary_text = (
    "<b>EXECUTIVE SUMMARY & PRIVACY NOTICE:</b><br/>"
    "This official report details the comprehensive game economy rebalance performed on Kazumi RPG Bot servers. "
    "To protect user privacy and security, all User IDs and handles in this public report have been partially masked (blurred).<br/><br/>"
    "<b>Key Actions Enforced:</b><br/>"
    "• <b>Aviator Glitch Neutralization:</b> Uncapped bet compounding in Web Aviator was patched with a strict <b>$10,000,000</b> max wager limit.<br/>"
    "• <b>Glitch Winnings Rebalance:</b> Accounts that accumulated extreme glitched balances (Quintillions/Trillions) were capped at a safe baseline of <b>$50,000,000</b>.<br/>"
    "• <b>Gift Supply Chain Audit:</b> Glitch currency transferred or gifted to secondary accounts was fully deducted and notified via DM.<br/>"
    "• <b>Legitimate Balances Preserved:</b> All non-aviator, fair player accounts remain <b>100% intact & verified</b>."
)
elements.append(Paragraph(summary_text, body_style))
elements.append(Spacer(1, 12))

# Table Header
elements.append(Paragraph("📊 Official Top 20 Economy Leaderboard (Masked Public Copy)", section_heading))

table_data = [
    [
        Paragraph("Rank", table_header_style),
        Paragraph("Masked User ID", table_header_style),
        Paragraph("Masked Handle", table_header_style),
        Paragraph("Wallet Balance", table_header_style),
        Paragraph("Bank Balance", table_header_style),
        Paragraph("Audit Status", table_header_style),
    ]
]

# Rows Data (Masked for Privacy)
rows = [
    ("#1", "7642******", "@ogab****", "$912,004,803", "$13,756,594", "Clean / Verified", True),
    ("#2", "7130******", "@hsjs****", "$525,000,000", "$0", "Rebalanced & Capped", False),
    ("#3", "7005******", "@rajs****", "$127,080,144", "$0", "Rebalanced & Capped", False),
    ("#4", "8860******", "Evo (Protected)", "$99,985,169", "$0", "Rebalanced & Capped", False),
    ("#5", "8661******", "@rage****", "$63,430,000", "$0", "Rebalanced & Capped", False),
    ("#6", "6477******", "@sidh****", "$51,000,708", "$0", "Rebalanced & Capped", False),
    ("#7", "8159******", "@jagg****", "$50,000,000", "$0", "Rebalanced & Capped", False),
    ("#8", "8201******", "@shin****", "$50,000,000", "$50,000,000", "Rebalanced & Capped", False),
    ("#9", "8335******", "@dest****", "$50,000,000", "$0", "Rebalanced & Capped", False),
    ("#10", "8419******", "ALPHA (Protected)", "$50,000,000", "$50,000,000", "Rebalanced & Capped", False),
    ("#11", "8541******", "@kazu****", "$20,592,377", "$0", "Clean / Verified", True),
    ("#12", "7678******", "RAVAN (Protected)", "$1,197,067", "$45,356,989", "Clean / Verified", True),
    ("#13", "8267******", "@apif****", "$419,988", "$0", "Rebalanced & Capped", False),
    ("#14", "8666******", "Ashutosh (Prot.)", "$184,200", "$0", "Clean / Verified", True),
    ("#15", "6973******", "@shre****", "$183,109", "$2", "Clean / Verified", True),
    ("#16", "8452******", "@easy****", "$139,398", "$100", "Clean / Verified", True),
    ("#17", "8374******", "@prat****", "$39,347", "$0", "Clean / Verified", True),
    ("#18", "6799******", "@nish****", "$33,850", "$0", "Clean / Verified", True),
    ("#19", "8225******", "Anusha (Prot.)", "$26,453", "$1,025,301", "Clean / Verified", True),
    ("#20", "2012******", "@naru****", "$25,000", "$0", "Clean / Verified", True),
]

for rank, uid, handle, wallet, bank, status_str, is_clean in rows:
    st_style = status_clean if is_clean else status_capped
    r_style = table_cell_bold if is_clean else table_cell_style
    table_data.append([
        Paragraph(rank, r_style),
        Paragraph(uid, table_cell_style),
        Paragraph(handle, table_cell_style),
        Paragraph(wallet, r_style),
        Paragraph(bank, table_cell_style),
        Paragraph(status_str, st_style),
    ])

t = Table(table_data, colWidths=[35, 75, 105, 95, 80, 110])
t.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4f46e5")),
    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ("TOPPADDING", (0, 0), (-1, -1), 4),
    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
]))

elements.append(t)
elements.append(Spacer(1, 14))

# Official Footer
footer_text = (
    "<b>Official Kazumi Core Team Certification:</b><br/>"
    "This document certifies that all Kazumi RPG Bot game databases have been stabilized. "
    "Wager safety algorithms, session recovery workers, and anti-inflation limits are active.<br/>"
    "<i>Issued by: Kazumi Administration & Security Operations | @KazumiRpgBot</i>"
)
elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cbd5e1"), spaceAfter=8))
elements.append(Paragraph(footer_text, subtitle_style))

doc.build(elements)
print("PDF Generated Successfully at:", pdf_path)
