# Sample pages

Test documents for trying a PPD on a real printer. The `.ps` files are the
sources; rebuild a PDF with
`gs -q -dSAFER -dBATCH -dNOPAUSE -sDEVICE=pdfwrite -sOutputFile=x.pdf x.ps`.

| File | Size | For |
|---|---|---|
| `label-3x2in.pdf` | 3 x 2 in | TSPL label printers (e.g. Munbyn RW403B-N) |
| `receipt-80mm-200mm.pdf` | 72 x 200 mm (80 mm roll) | ESC/POS receipt printers (e.g. Rongta RP850P) |
| `label-3x2in-3pages.pdf` | 3 x 2 in, 3 pages | multi-page test: expect 3 labels |
| `receipt-80mm-200mm-3pages.pdf` | 72 x 200 mm, 3 pages | multi-page test: expect one long receipt, one cut at the end |
