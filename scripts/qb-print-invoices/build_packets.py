r"""
Builds one collection packet per location folder, plus one summary for all of them.

  <root>\<location>\*.pdf   invoices printed from QuickBooks (any number of PDFs per folder)
  balances.csv              Folder,Account,Balance - what QuickBooks says each location owes

Everything else (invoice numbers, dates, amounts, Bill To, logo) is read from the invoice PDFs.

Output in <root>\_COMBINED\ :
  <location> - Packet.pdf       cover page (Bill To, number of invoices, amount owed, invoice list) + the invoices
  ALL LOCATIONS - Summary.pdf   what every location owes, with the grand total

Usage: python build_packets.py "<root folder>" "<balances.csv>"
"""
import csv
import io
import re
import sys
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUT_DIR = '_COMBINED'
SELLER = ['BEST WHOLESALE FISH & SEA FOOD', '15151 Wyoming St, Detroit, MI 48238',
          'Office (313) 722-7750  |  Cell (313) 685-6689', 'Bestwholealefish@gmail.com']
NAVY, RED, GREY, STRIPE = colors.HexColor('#1f3a5f'), colors.HexColor('#b00020'), colors.HexColor('#555555'), colors.HexColor('#f2f4f7')

HDR = re.compile(r'Date\s*\n\s*(\d{1,2}/\d{1,2}/\d{4})\s*\n\s*Invoice #\s*\n\s*(\d+)')
BILL = re.compile(r'Bill To :\s*\n(.*?)Office:', re.S)
TOTAL = re.compile(r'^\s*(-?\$-?[\d,]+\.\d\d)\s*$', re.M)


def money(d):
    return f'-${-d:,.2f}' if d < 0 else f'${d:,.2f}'


def style(size, bold=False, color=colors.black, align=0):
    return ParagraphStyle('s', fontName='Helvetica-Bold' if bold else 'Helvetica', fontSize=size,
                          leading=size * 1.25, textColor=color, alignment=align)


def read_folder(folder):
    """-> (readers, invoices, problems, logo_bytes). An invoice spanning pages is counted once."""
    readers, invs, problems, logo = [], {}, [], None
    for pdf in sorted(folder.glob('*.pdf'), key=lambda p: [int(t) if t.isdigit() else t for t in re.split(r'(\d+)', p.name)]):
        rd = PdfReader(str(pdf))
        readers.append(rd)
        for i, page in enumerate(rd.pages, 1):
            text = page.extract_text() or ''
            h = HDR.search(text)
            if not h:
                problems.append(f'{pdf.name} page {i}: no invoice number found')
                continue
            num = h.group(2)
            inv = invs.setdefault(num, {'num': num, 'date': datetime.strptime(h.group(1), '%m/%d/%Y'),
                                        'amount': None, 'billto': None})
            totals = TOTAL.findall(text)
            if totals:   # last page of the invoice carries the total
                inv['amount'] = Decimal(totals[-1].replace('$', '').replace(',', ''))
            b = BILL.search(text)
            if b and not inv['billto']:
                inv['billto'] = tuple(l.strip() for l in b.group(1).strip().splitlines() if l.strip())
            if logo is None and page.images:
                buf = io.BytesIO()
                page.images[0].image.convert('RGB').resize((400, 400)).save(buf, format='JPEG', quality=85)
                logo = buf.getvalue()
    for inv in invs.values():
        if inv['amount'] is None:
            problems.append(f'invoice {inv["num"]}: total not found')
            inv['amount'] = Decimal(0)
    return readers, sorted(invs.values(), key=lambda v: (v['date'], int(v['num']))), problems, logo


def header(logo, title):
    left = [Paragraph(SELLER[0], style(14, True, NAVY))] + [Paragraph(s, style(9)) for s in SELLER[1:]]
    img = Image(io.BytesIO(logo), 0.95 * inch, 0.95 * inch) if logo else ''
    t = Table([[img, left, Paragraph(title, style(16, True, NAVY, 2))]], colWidths=[1.1 * inch, 3.3 * inch, 2.9 * inch])
    t.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LEFTPADDING', (0, 0), (-1, -1), 0)]))
    return [t, Spacer(1, 0.08 * inch),
            Table([['']], colWidths=[7.3 * inch], style=[('LINEABOVE', (0, 0), (-1, -1), 1.5, NAVY)]),
            Spacer(1, 0.12 * inch)]


def doc(path, title):
    return SimpleDocTemplate(str(path), pagesize=letter, leftMargin=0.6 * inch, rightMargin=0.6 * inch,
                             topMargin=0.5 * inch, bottomMargin=0.6 * inch, title=title)


def cover(path, account, addr, invs, owed, logo, problems):
    invoiced = sum(v['amount'] for v in invs)
    paid = invoiced - owed
    story = header(logo, f'STATEMENT OF<br/>OPEN INVOICES<br/><font size="9" color="#555555">As of {date.today():%B %d, %Y}</font>')

    lab = lambda s: Paragraph(f'<b>{s}</b>', style(8.5, color=GREY))
    box = Table([[lab('BILL TO'), '', lab('NUMBER OF INVOICES')],
                 [Paragraph('<br/>'.join(addr or [account]), style(12)), '', Paragraph(str(len(invs)), style(24, True))],
                 ['', '', lab('TOTAL AMOUNT OWED')],
                 ['', '', Paragraph(money(owed), style(24, True, RED))]],
                colWidths=[3.6 * inch, 0.25 * inch, 3.45 * inch])
    box.setStyle(TableStyle([('SPAN', (0, 1), (0, 3)), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                             ('BOX', (0, 0), (0, 3), 0.75, colors.grey), ('BOX', (2, 0), (2, 3), 0.75, colors.grey),
                             ('LEFTPADDING', (0, 0), (-1, -1), 9), ('TOPPADDING', (0, 0), (-1, -1), 6),
                             ('BOTTOMPADDING', (0, 3), (-1, 3), 9)]))
    story += [box, Spacer(1, 0.08 * inch),
              Paragraph(f'Account: {account} &nbsp;&nbsp;|&nbsp;&nbsp; Balance per QuickBooks as of {date.today():%m/%d/%Y}',
                        style(8.5, color=GREY)), Spacer(1, 0.18 * inch)]

    data = [['#', 'Invoice #', 'Invoice Date', 'Amount']]
    data += [[i, v['num'], f'{v["date"]:%m/%d/%Y}', money(v['amount'])] for i, v in enumerate(invs, 1)]
    n = len(data)
    data += [['', '', 'Total of invoices', money(invoiced)]]
    if paid:
        data += [['', '', 'Less payments & credits received', money(-paid)]]
    data += [['', '', 'BALANCE OWED', money(owed)]]
    t = Table(data, colWidths=[0.6 * inch, 1.6 * inch, 3.0 * inch, 2.1 * inch], repeatRows=1)
    t.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 9), ('FONT', (0, 1), (-1, -1), 'Helvetica', 9),
        ('BACKGROUND', (0, 0), (-1, 0), NAVY), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'), ('ALIGN', (3, 0), (3, -1), 'RIGHT'),
        ('ROWBACKGROUNDS', (0, 1), (-1, n - 1), [colors.white, STRIPE]),
        ('GRID', (0, 0), (-1, n - 1), 0.25, colors.HexColor('#c8ccd2')),
        ('ALIGN', (2, n), (2, -1), 'RIGHT'), ('LINEABOVE', (2, n), (-1, n), 1, colors.black),
        ('FONT', (0, -1), (-1, -1), 'Helvetica-Bold', 11), ('TEXTCOLOR', (3, -1), (3, -1), RED),
        ('LINEABOVE', (2, -1), (-1, -1), 1, colors.black)]))
    story.append(t)
    if problems:
        story += [Spacer(1, 0.15 * inch)] + [Paragraph('Note: ' + p, style(8, color=RED)) for p in problems]
    doc(path, f'{account} - Open Invoices').build(story)
    return invoiced


def summary(path, rows, logo):
    total = [sum(r[i] for r in rows) for i in (2, 3, 4)]
    data = [['Location / Account', 'Bill To', 'Invoices', 'Invoiced', 'Payments', 'Amount Owed']]
    for acct, addr, n, invoiced, owed in sorted(rows, key=lambda r: -r[4]):
        data.append([Paragraph(acct, style(8.5, True)), Paragraph('<br/>'.join(addr[1:3] if addr and len(addr) > 1 else addr or []), style(7.5)),
                     n, money(invoiced), money(owed - invoiced), money(owed)])
    data.append(['GRAND TOTAL', '', total[0], money(total[1]), money(total[2] - total[1]), money(total[2])])
    t = Table(data, colWidths=[1.85 * inch, 1.65 * inch, 0.65 * inch, 1.05 * inch, 1.0 * inch, 1.1 * inch], repeatRows=1)
    t.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 8.5), ('FONT', (0, 1), (-1, -1), 'Helvetica', 8.5),
        ('BACKGROUND', (0, 0), (-1, 0), NAVY), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (2, 0), (-1, -1), 'RIGHT'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, STRIPE]),
        ('GRID', (0, 0), (-1, -2), 0.25, colors.HexColor('#c8ccd2')),
        ('FONT', (-1, 1), (-1, -1), 'Helvetica-Bold', 8.5),
        ('LINEABOVE', (0, -1), (-1, -1), 1.2, colors.black), ('FONT', (0, -1), (-1, -1), 'Helvetica-Bold', 10),
        ('TEXTCOLOR', (-1, -1), (-1, -1), RED), ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5)]))
    big = Table([[Paragraph('<b>LOCATIONS</b>', style(8.5, color=GREY)), Paragraph('<b>OPEN INVOICES</b>', style(8.5, color=GREY)),
                  Paragraph('<b>TOTAL AMOUNT OWED</b>', style(8.5, color=GREY))],
                 [Paragraph(str(len(rows)), style(22, True)), Paragraph(str(total[0]), style(22, True)),
                  Paragraph(money(total[2]), style(22, True, RED))]], colWidths=[2.0 * inch, 2.2 * inch, 3.1 * inch])
    big.setStyle(TableStyle([('BOX', (0, 0), (-1, -1), 0.75, colors.grey), ('LEFTPADDING', (0, 0), (-1, -1), 9),
                             ('BOTTOMPADDING', (0, 1), (-1, 1), 9)]))
    story = header(logo, f'OPEN BALANCE<br/>SUMMARY<br/><font size="9" color="#555555">As of {date.today():%B %d, %Y}</font>')
    story += [big, Spacer(1, 0.25 * inch), t, Spacer(1, 0.1 * inch),
              Paragraph(f'Amounts owed are the balances per QuickBooks as of {date.today():%m/%d/%Y}. '
                        '"Invoiced" is the original amount of the open invoices; "Payments" are partial payments and credits already applied.',
                        style(7.5, color=GREY))]
    doc(path, 'Open Balance Summary').build(story)


def main(root, balances_csv):
    root = Path(root)
    with open(balances_csv, newline='', encoding='utf-8-sig') as f:
        bal = {r['Folder'].strip(): (r['Account'].strip(), Decimal(r['Balance'])) for r in csv.DictReader(f)}
    out = root / OUT_DIR
    out.mkdir(exist_ok=True)
    rows, logo_any = [], None
    for folder in sorted(p for p in root.iterdir() if p.is_dir() and p.name != OUT_DIR):
        readers, invs, problems, logo = read_folder(folder)
        logo_any = logo_any or logo
        if not invs:
            print(f'SKIP {folder.name}: no invoices found')
            continue
        account, owed = bal.get(folder.name, (folder.name, None))
        if owed is None:
            problems.append('no QuickBooks balance on file - amount owed shown is the invoice total')
        addr = Counter(v['billto'] for v in invs if v['billto']).most_common(1)
        addr = addr[0][0] if addr else None

        cover_path = out / f'~cover {folder.name}.pdf'
        invoiced = cover(cover_path, account, addr, invs, owed if owed is not None else sum(v['amount'] for v in invs), logo, problems)
        owed = owed if owed is not None else invoiced
        w = PdfWriter()
        w.append(str(cover_path))
        for rd in readers:
            w.append(rd)
        with open(out / f'{account} - Packet.pdf', 'wb') as f:
            w.write(f)
        cover_path.unlink()
        rows.append((account, addr, len(invs), invoiced, owed))
        warn = f'   <-- {"; ".join(problems)}' if problems else ''
        print(f'{account:30} {len(invs):4} invoices  invoiced {money(invoiced):>13}  owed {money(owed):>13}{warn}')

    summary(out / 'ALL LOCATIONS - Summary.pdf', rows, logo_any)
    print(f'\nTOTAL: {len(rows)} locations, {sum(r[2] for r in rows)} invoices, owed {money(sum(r[4] for r in rows))}')
    print(f'Saved in: {out}')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
