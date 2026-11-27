# SangoDiag field app

**One Screen, One Next Step.** The SangoDiag nurse screen as an installable, offline-first app for Android phones.

**Open it: https://mukongzhung.github.io/SangoDiag/**

A nurse opens it in Chrome once, taps *Install*, and from then on it opens from the home screen and works with no network at all. She enters temperature, symptoms, danger signs and the test result, and gets one next step with its reasons. The phone remembers each visit, so when a treated patient comes back with fever, it changes the advice to "Send for microscopy / clinician review".

It supports the nurse's decision. It does not replace a test or a doctor, and it never gives a drug dose.

## Why a PWA first, not a Play Store app

| | PWA (this folder) | Play Store app |
|---|---|---|
| Time to the first nurse | Today: send a link | 14-day closed test with 20 testers for a new developer account, then review |
| Works offline | Yes (service worker + on-device rules + IndexedDB) | Yes, if built for it |
| Updates | Next time the phone is online | New build and review each time |
| Cost | Free (GitHub Pages) | $25 developer account |
| Phones | Any Android with Chrome, also iPhone | Android only |

The pilot starts with the PWA. The same app can later be wrapped as a Play Store app (see *Android APK* below) without rewriting anything.

The Kotlin prototype in `app/` stays in the repository as the hackathon field demo. It mixes nurse screens with showcase screens (Zetaris, code viewer), so this app is the one to put in nurses' hands.

## What the nurse does

1. **First start:** chooses a PIN, enters the health post, the district and the villages it serves (endemic zone and active cases this week, from the district's weekly report). Or restores a backup from another phone.
2. **Every day:** unlocks with the PIN, searches the patient by name, ID, phone or village, or registers a new one (name, sex, age, village, phone, malaria in the family). Each patient gets an ID like `SD-QT7HGS`.
3. **Each visit:** temperature, days of fever, symptoms, danger signs, test result. *Check this patient* gives one next step, the reasons and their sources, what to do now, and other causes to keep in mind.
4. **Next visit:** SangoDiag remembers the earlier visits. A fever within 28 days of treatment turns the advice into "Send for microscopy / clinician review". The nurse marks earlier advice right or wrong.
5. **End of month:** Settings > *Export this month's visits (CSV)* for the report, and *Save a backup file*.

## What runs on the phone

| Piece | File | What it does |
|---|---|---|
| Rules | `js/triage.js` | Line-by-line port of `agent/triage.py`: test before treat, danger signs mean referral, fever within 28 days of treatment means microscopy. `tests/parity.test.mjs` checks 405 intakes against the Python rules: same score, same next step, same reasons, word for word |
| Encrypted store | `js/store.js` | Everything is encrypted on the phone with a key made from the PIN (PBKDF2-SHA256, 210,000 rounds, AES-GCM 256). Locks itself after 5 minutes without use. A forgotten PIN cannot be recovered: the data can only be erased, or restored from a backup with that backup's PIN |
| Register | `js/records.js` | The health post's own patients, villages and visits. The rules read them in the same shape as the server's Zetaris queries: `[Q1]` patient register, `[Q2]` village data, `[Q3]` earlier visits, `[MEM]` patient memory, `[NURSE]` what she entered |
| Memory | `js/records.js` | A light H-MEM: observation (0.9) and recommendation (0.6) per visit, right/wrong feedback (+0.05 / −0.20, H-MEM deltas), append-only ledger |
| Reports | `js/records.js` | Monthly CSV for Excel or Google Sheets: one row per visit, patient IDs but no names or phone numbers |
| Backup | `js/store.js` | A JSON file of the encrypted records. Opens only with the PIN in use when it was saved. Use it to move to a new phone or recover a lost one |
| Offline | `sw.js` | Keeps every app file on the phone; serves them first, refreshes them when online |
| Languages | `js/i18n.js` | French and English (follows the phone's language at first start) |
| Demo data | Settings | Synthetic patients and the 5 demo cases can be added for training and removed before the pilot |
| Server link | Settings | Optional: also sends each visit to `POST /diagnose` for the Nemotron explanation. Visits wait in an outbox when there is no connection |

No model runs on the phone. The next step comes from the same transparent rules the server uses.

## Try it on your laptop

```bash
python3 mobile-app/scripts/build_data.py   # bundles the demo register into js/data.js
cd mobile-app
python3 -m http.server 8080
# open http://localhost:8080
```

`js/data.js` and the PNG icons are generated (by that script and by the Pages workflow from `icons/logo.svg` and `icons/maskable.svg`), so they are not committed.

On first start choose *Try with demo data first*. Then Settings (the sliders icon) > *Load a demo case*: run case 1, then case 5, to see the memory change the decision.

To test offline: open the app once, then in Chrome DevTools > Network choose *Offline* and reload. It still opens and decides.

The full offline flow (setup, PIN, register, two visits, memory, wrong PIN, CSV, backup, erase, restore) is automated in `tests/e2e_offline.py`.

## Put it on a phone

**Same Wi-Fi, for a quick look.** Find the laptop's address (`ipconfig` on Windows, `ip addr` on Linux/Mac, e.g. `192.168.1.50`), run `python3 -m http.server 8080 --bind 0.0.0.0` and open `http://192.168.1.50:8080` on the phone. Offline install needs HTTPS, so use this only to look.

**GitHub Pages, for the pilot (recommended).**
1. Merge this branch into `main`.
2. On GitHub: *Settings > Pages > Source: GitHub Actions*.
3. The workflow `.github/workflows/field-app.yml` runs the tests and publishes this folder to `https://mukongzhung.github.io/SangoDiag/`.
4. Send that link to the nurses. In Chrome: open it, wait for the page to load, then menu > *Install app* (or *Add to Home screen*). From then on it works offline. Open it in Chrome itself, not inside WhatsApp or Gmail: in-app browsers cannot install it.

The repository used to be called `SangoDiag-Malaria-Diagnosis-Tool-`. Its old Pages address ended in a dash that messaging apps drop when they make a link, which sent nurses to a 404 page, so it was renamed. Old links to the app no longer work; share the address above.

## If the app keeps loading

Since v0.2.1 the first screen says "Chargement de SangoDiag… / Loading SangoDiag…" and, after 20 seconds, explains what to try. The usual causes:

- **Opened inside WhatsApp, Facebook or Gmail.** Their built-in browsers often block the app's storage. Copy the link and open it in Chrome.
- **Old Chrome.** The app needs Chrome 61 or newer (2017). Update Chrome from the Play Store.
- **Very weak network on the first opening.** The first opening downloads about 80 KB. On 2G/EDGE this takes 10 to 20 seconds. After that the app opens from the phone, with no network.
- **Incognito tab.** Storage is blocked there. Use a normal tab.

## Connect it to the SangoDiag server (optional)

```bash
# on the laptop running Nightshift + Zetaris (or SAMPLE_MODE=true for a rehearsal)
python -m uvicorn agent.api:app --host 0.0.0.0 --port 8000 --ws none
```

In the app: Settings > *SangoDiag server address*, enter the address, *Save*. "Connected to SangoDiag server" confirms it.

A page served over HTTPS (GitHub Pages) can only call an HTTPS server. Put the API behind HTTPS first, for example `ngrok http 8000`, and use the `https://…ngrok…` address. Set `SANGODIAG_CORS_ORIGINS` in `.env` to the app's address before any real patient data is involved.

## Android APK (Play Store path)

The PWA can be wrapped as a Trusted Web Activity, a real Android app that opens this same site full-screen:

1. Deploy to GitHub Pages (above).
2. Go to [pwabuilder.com](https://www.pwabuilder.com), enter the Pages address, choose *Android* > *Generate*. Or with Node: `npx @bubblewrap/cli init --manifest https://mukongzhung.github.io/SangoDiag/manifest.webmanifest` then `npx @bubblewrap/cli build`.
3. Keep the signing key safe and out of git (`*.keystore` and `*.jks` are ignored).
4. Publish the `assetlinks.json` it gives you at `/.well-known/assetlinks.json` on the site so Android hides the browser bar.
5. Upload the `.aab` to Play Console *Internal testing*, then *Closed testing* with 20 testers for 14 days.

The `.apk` from the same step can be shared directly for sideloading during the pilot.

## Tests

```bash
python3 mobile-app/tests/make_fixtures.py   # runs agent/triage.py on 405 intakes
cd mobile-app && npm test                   # phone rules must match exactly
```

After changing `synthetic_data/` or `examples/demo_cases.json`, run `python3 mobile-app/scripts/build_data.py`.

## Honest limits

- **Real patients need approval first.** The app is built to hold real patient data safely (encrypted, PIN, no names in exports), but a pilot with real patients in Cameroon needs ethics approval (CNERSH or a regional ethics committee), the district health service's agreement, and each patient's consent. Start with demo data and training until that is in place.
- **One phone, one register.** Two nurses on two phones have two separate registers. Moving data between phones is by backup file. Shared registers need a server, which is the next step.
- **Demo protocol.** The rules follow WHO test-before-treat and common danger signs but are not clinically validated. Doses are left to the national protocol chart.
- **Data stays on the phone** unless a server address is set. Clearing Chrome's site data, or losing the phone, loses the data: make a backup every week. Installing the app makes Chrome keep the data even when space is low.
- **No smear image on the phone yet.** The image model runs only on the server.
