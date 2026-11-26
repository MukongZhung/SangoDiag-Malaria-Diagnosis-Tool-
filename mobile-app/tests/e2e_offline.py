"""End-to-end test of the field app, fully offline, in a phone-sized Chrome.

    pip install playwright && python -m playwright install chromium
    python3 mobile-app/tests/e2e_offline.py mobile-app /tmp/sangodiag-shots

Set CHROME=/path/to/chrome to use an installed Chrome instead of Playwright's.
"""
import sys, threading, http.server, functools, os, json
from playwright.sync_api import sync_playwright
root, out = sys.argv[1], sys.argv[2]; os.makedirs(out, exist_ok=True)
http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8767), functools.partial(http.server.SimpleHTTPRequestHandler, directory=root))
threading.Thread(target=srv.serve_forever, daemon=True).start()
errors = []
def shot(pg, name, full=True): pg.wait_for_timeout(450); pg.screenshot(path=f"{out}/{name}.png", full_page=full)
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=os.environ.get("CHROME") or None)
    ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True, locale="fr-FR", accept_downloads=True)
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: errors.append(str(e))); pg.on("console", lambda m: m.type == "error" and errors.append(m.text))
    pg.on("dialog", lambda d: d.accept())
    pg.goto("http://127.0.0.1:8767/"); pg.wait_for_function("navigator.serviceWorker.controller !== null", timeout=15000)
    # --- go fully offline from here
    srv.shutdown(); ctx.set_offline(True); pg.reload(); pg.wait_for_selector("form.setup")
    print("1 setup screen offline, lang:", pg.get_attribute("html", "lang"))
    shot(pg, "01-setup-fr", False)
    pins = pg.locator("form.setup input.pin"); pins.nth(0).fill("2580"); pins.nth(1).fill("2580")
    ins = pg.locator("form.setup label.field input")
    pg.locator("form.setup label.field", has_text="Nom du centre").locator("input").fill("CSI de Nkolbisson")
    pg.locator("form.setup label.field", has_text="District").locator("input").fill("Cité Verte")
    vr = pg.locator(".village-row").first
    vr.locator("input").first.fill("Nkolbisson"); vr.locator("select").select_option("high"); vr.locator("input[type=number]").fill("42")
    pg.click("form.setup .dock button"); pg.wait_for_selector(".plist")
    print("2 home:", pg.inner_text(".post"))
    # register a patient
    pg.click("text=Enregistrer un nouveau patient")
    pg.locator("label.field", has_text="Nom complet").locator("input").fill("Ngono Marie")
    pg.click(".seg button:has-text('Féminin')")
    pg.locator("label.field", has_text="Âge").locator("input").fill("24")
    pg.locator("label.field", has_text="Village").locator("select").select_option(label="Nkolbisson")
    pg.click("text=Paludisme récent dans la famille")
    pg.click(".dock button[type=submit]"); pg.wait_for_selector(".phead")
    pid = pg.inner_text(".phead .hint").split(",")[0]
    print("3 patient page:", pg.inner_text(".phead h1"), pid)
    # visit 1: RDT positive
    pg.click("text=Nouvelle visite"); pg.wait_for_selector(".who-line")
    pg.locator("label.field", has_text="Température").locator("input").fill("39,2")
    for c in ["Fièvre (signalée)", "Frissons", "Maux de tête"]: pg.click(f"button.chip:has-text('{c}')")
    pg.click(".tests button:has-text('TDR positif')"); shot(pg, "02-visit-fr")
    pg.click(".dock button[type=submit]"); pg.wait_for_selector(".slab")
    print("4 visit 1:", pg.get_attribute(".slab", "data-action"), pg.inner_text(".score-num")); shot(pg, "03-result-treat-fr")
    pg.click("#result .dock button"); pg.wait_for_selector(".vlist")
    # visit 2: fever back -> memory
    pg.click("text=Nouvelle visite"); pg.locator("label.field", has_text="Température").locator("input").fill("38.6")
    pg.click("button.chip:has-text('Fièvre (signalée)')"); pg.click(".dock button[type=submit]"); pg.wait_for_selector(".slab")
    print("5 visit 2 (H-MEM):", pg.get_attribute(".slab", "data-action"), "|", pg.inner_text(".memory p").splitlines()[0])
    shot(pg, "04-result-followup-fr")
    pg.click("#result .dock button"); pg.wait_for_selector(".vlist")
    pg.click(".vlist li:nth-child(2) .feedback .yes"); pg.wait_for_selector(".vlist")
    pg.wait_for_timeout(300); print("6 visits on patient page:", pg.locator(".vlist li").count(), "| li1:", pg.inner_text(".vlist li:nth-child(1)").replace("\n"," / "), "| li2:", pg.inner_text(".vlist li:nth-child(2)").replace("\n"," / "))
    shot(pg, "05-patient-page-fr")
    # reload offline -> lock, wrong PIN, right PIN
    pg.reload(); pg.wait_for_selector("form.lock")
    pg.fill("input.pin", "1111"); pg.click("form.lock button[type=submit]"); pg.wait_for_selector("text=Code incorrect")
    pg.fill("input.pin", "2580"); pg.click("form.lock button[type=submit]"); pg.wait_for_selector(".plist")
    print("7 unlocked after reload, patients:", pg.locator(".plist li").count(), "|", pg.inner_text(".stats"))
    shot(pg, "06-home-fr", False)
    # data on disk is encrypted
    raw = pg.evaluate("""() => new Promise(r => { const q = indexedDB.open('sangodiag-v2'); q.onsuccess = () => {
        const t = q.result.transaction('records'); const g = t.objectStore('records').getAll(); g.onsuccess = () => r(JSON.stringify(g.result)); }; })""")
    print("8 name in raw storage?", "Ngono" in raw, "| records:", raw.count('"kind"'))
    # search
    pg.fill(".searchbox input", "ngono"); print("9 search hits:", pg.locator(".plist li").count())
    # settings: export CSV + backup
    pg.click("#open-settings"); pg.wait_for_selector(".settings")
    with pg.expect_download() as d: pg.click("text=Exporter les visites du mois (CSV)")
    csv = open(d.value.path(), encoding="utf-8-sig").read(); print("10 CSV:", csv.splitlines()[0][:80], "| rows:", len(csv.splitlines()) - 1, "| name in CSV?", "Ngono" in csv)
    with pg.expect_download() as d: pg.click("text=Enregistrer une sauvegarde")
    bpath = f"{out}/backup.json"; d.value.save_as(bpath); bk = json.load(open(bpath)); print("11 backup:", bk["format"], len(bk["records"]), "records | name readable?", "Ngono" in open(bpath).read())
    shot(pg, "07-settings-fr")
    # demo data + demo case
    pg.click("text=Ajouter des patients et villages de démonstration"); pg.wait_for_selector("text=Retirer les patients")
    pg.select_option(".settings select >> nth=-1", "danger_signs"); pg.wait_for_selector(".who-line"); pg.click(".dock button[type=submit]"); pg.wait_for_selector(".slab")
    print("12 demo case 4:", pg.get_attribute(".slab", "data-action"))
    pg.click("#result .dock button"); pg.wait_for_selector(".phead")
    # erase -> restore backup with PIN
    pg.click("#open-settings"); pg.wait_for_selector(".settings"); pg.click("text=Effacer toutes les données de ce téléphone"); pg.wait_for_selector("form.setup")
    print("13 erased, setup shown")
    pg.click("form.setup summary"); pg.set_input_files("form.setup input[type=file]", bpath)
    pg.fill("form.setup .restore input.pin", "0000"); pg.click("form.setup .restore button"); pg.wait_for_selector("text=ne s'ouvre pas")
    pg.fill("form.setup .restore input.pin", "2580"); pg.click("form.setup .restore button"); pg.wait_for_selector(".plist")
    print("14 restored:", pg.locator(".plist li").count(), "patient(s):", pg.inner_text(".plist li").splitlines()[0], "| demo present?", pg.locator(".tag").count())
    # English
    pg.click("#open-settings"); pg.click(".seg button:has-text('English')"); pg.click(".back"); pg.wait_for_selector(".plist"); shot(pg, "08-home-en", False)
    print("errors:", errors); b.close()
