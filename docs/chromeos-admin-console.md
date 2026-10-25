# Deploying with the Google Admin console

For managed ChromeOS devices, including managed guest sessions and kiosks,
the printer can be pushed from the Admin console so nobody has to set it up
on the device.

## 1. Host the PPD

Put the PPD on any HTTPS server the devices can reach without logging in,
for example the server that hosts your kiosk page:
`https://example.com/printers/munbyn-rw403b-n.ppd`

(A "raw" file link from a public GitHub repository also works.)

## 2. Add the printer

Admin console → **Devices → Chrome → Printers** → choose the org unit →
**Add printer**:

| Field | USB printer | Network printer (e.g. Rongta RP850P on Ethernet) |
|---|---|---|
| Connection method | USB | Network address |
| Address | Vendor ID + Product ID (4 hex digits each, from the profile or `probe.py --list`) | `socket://<printer IP>:9100` |
| Setup method | Custom PPD file → the URL from step 1 | Custom PPD file → the URL from step 1 |
| Availability | Allow for managed guest sessions / users / devices as needed | same |

Example: Munbyn RW403B-N = vendor `0D28`, product `CCDD`.

Note from Google's documentation: ChromeOS can't tell apart several USB
printers of the same model on one device.

## 3. Defaults (recommended)

In the user/managed guest session settings (Printing section) set the
**default printer** so the label printer is pre-selected. If your devices print
only to this printer, also set the **default paper size** to the size your
labels or receipts use, so nobody has to pick it each time.

## 4. Kiosk web pages

Give the page the exact paper size so Chrome lays it out 1:1:

```css
@page { size: 3in 2in; margin: 0; }      /* label */
@page { size: 72mm 200mm; margin: 0; }   /* 80 mm receipt, 72 mm printable */
html, body { margin: 0; }
```

Then `window.print()`.
