# QuickBooks Unpaid Invoice Packets

Tools for collecting on a customer's unpaid invoices in **QuickBooks Desktop**.
Built for Best Wholesale Fish & Sea Food (Yum Yoshis + BBQ Central locations).

There are two parts:

1. **Print the invoices.** `RUN-ME.bat` puts one location's unpaid invoices in
   QuickBooks' print queue, so you can print them all at once.
2. **Build the packets.** `BUILD-PACKETS.bat` turns the printed PDFs into one
   packet per location, plus a summary of all locations.

## Files

| File | What it does | Runs on |
|---|---|---|
| `RUN-ME.bat` | Starts the print-queue script. Double-click it. | QuickBooks PC |
| `Mark-YoshisInvoicesToPrint.ps1` | The print-queue script | QuickBooks PC |
| `DIAGNOSE.bat` / `Diagnose-QB.ps1` | Checks the QuickBooks connection if the script can't connect. Changes nothing. | QuickBooks PC |
| `BUILD-PACKETS.bat` | Starts the packet builder. Drag the invoices folder onto it. | Any PC with Python |
| `build_packets.py` | The packet builder | Any PC with Python |
| `balances.csv` | What each location owes, from QuickBooks | – |

---

## Part 1: Print each location's unpaid invoices

### First time only

1. Open QuickBooks, log in as **Admin**, and open the company file.
2. Make sure **Edit → Preferences → Integrated Applications → Company Preferences →
   "Don't allow any applications to access this company file"** is **unchecked**.
3. Copy `RUN-ME.bat` and `Mark-YoshisInvoicesToPrint.ps1` into the same folder on the
   QuickBooks PC.
4. Double-click `RUN-ME.bat`. QuickBooks asks whether to let "Yoshis Invoice Printer" access
   the file. Choose **"Yes, whenever this QuickBooks company file is open"**, then
   **Continue → Done**.

### Each time

1. Open QuickBooks with the company file, then double-click `RUN-ME.bat`.
2. The script lists every location with how many invoices are unpaid and the total:

   ```
     #  Location                            Unpaid   Unpaid total     QB balance   Marked
     1  BBQ CENTRAL 2                           25       7,682.91       7,682.91        0
     ...
   ```

   A **yellow** row means the unpaid invoices don't add up to the QuickBooks balance,
   for example because of journal entries or unapplied payments.

3. Type a choice:

   | Type | What happens |
   |---|---|
   | `5` | Only location 5's unpaid invoices go in the print queue. Every other invoice is un-marked. |
   | `5/50` | The same, but in parts of 50 invoices. It asks which part. Use this for big locations. |
   | `C` | Clears the whole print queue. |
   | `Q` | Quit |

4. In QuickBooks, go to **File → Print Forms → Invoices**.
   - **Check that the count at the top matches** what the script said.
   - **Select All → OK**, then set **Number of copies = 1**.
   - Choose **Microsoft Print to PDF** and save the file into that location's folder.
5. **Wait until the PDF file has a size** (not 0 KB). Then click **OK** when QuickBooks asks
   "Did form(s) print OK?". That clears the marks.
6. Type the next location number and repeat.

**Tips**

- Microsoft Print to PDF can fail on very large jobs and leave a **0 KB** file. Use parts,
  for example `3/50`. If 50 is still too many, use `3/25`.
- The first run scans every invoice in the company file (about 50,000), which takes a few
  minutes. After that, each round only checks invoices changed since the last one, which
  takes seconds.
- Each run saves `open_invoices_<date>.csv`, a list of all unpaid invoices for these
  locations.
- `removed_print_marks.txt` keeps a record of every invoice the script un-marked.
- Which customers are listed is set at the top of the script: `$Match = @('Yoshi', 'BBQ')`.
  Add a word to include more customers. The script lists every customer whose name
  contains one of these words.

### If it says "Could not start QuickBooks"

The script window and QuickBooks must run at the **same level**: both normal, or both
"Run as administrator". The script tries to fix this itself by reopening as a normal
window. If that doesn't work:

- Close QuickBooks, right-click its icon, choose **Run as administrator**, and open the
  company file. Then run `RUN-ME.bat` again.
- Close any pop-up windows inside QuickBooks.
- Still stuck? Double-click `DIAGNOSE.bat` and look at what it reports. It shows whether
  each program runs as administrator and whether the connection works.

---

## Part 2: Build the packets

### Setup (once)

Install Python 3 from python.org, then run:

```bash
pip install pypdf reportlab
```

### Folder layout

One folder per location, with that location's printed invoice PDF(s) inside. A location
can have several PDFs (for example part 1, part 2, ...):

```
YOSHI INVOICES\
  Yum Yoshis LLC 1F\      1.pdf  2.pdf  3.pdf  4.pdf
  Yum Yoshis LLC 2 KL\    1.pdf
  BBQ CENTRAL 2\          1.pdf
  ...
```

### Update `balances.csv`

This file says what each location owes. The **Folder** column must match the folder name
exactly. Copy the balances from the QuickBooks **Customer Center** on the day you build
the packets:

```csv
Folder,Account,Balance
Yum Yoshis LLC 1F,Yum Yoshis LLC 1F,159561.73
Yum Yoshus 5 LV,Yum Yoshis LLC 5 LV,10581.88
```

The current file has the balances as of **10/03/2026**. Update it if payments have come in
since then.

### Run it

Drag the `YOSHI INVOICES` folder onto `BUILD-PACKETS.bat`. Or run:

```bash
python build_packets.py "C:\path\to\YOSHI INVOICES" balances.csv
```

### What you get

The files are saved in `YOSHI INVOICES\_COMBINED\`:

- **`<location> - Packet.pdf`**:
  - **Cover page:** your logo and company details, the **Bill To** address, the
    **number of invoices**, and the **total amount owed**.
  - A list of every invoice (number, date, amount), with the total of the invoices,
    minus payments and credits received, and the **balance owed**.
  - All of that location's invoices behind it, oldest first.
- **`ALL LOCATIONS - Summary.pdf`**: one page with every location, its address, number of
  invoices, amount invoiced, payments, amount owed, and the **grand total**.

Invoice numbers, dates, amounts, Bill To addresses and the logo are all read from the
invoice PDFs. The amount owed comes from `balances.csv`, because printed invoices show
the **original** amount and don't include partial payments. If a page can't be read, or a
folder has no balance in `balances.csv`, a red note appears on that cover page and in
the window.
