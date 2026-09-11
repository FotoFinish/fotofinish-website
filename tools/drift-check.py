#!/usr/bin/env python3
"""
drift-check — report structural variance in the site's shared chrome.

The site has no templating: the <nav> and <footer> are copy-pasted into every
page and hand-maintained. Adding /es took that from 15 hand-maintained
marketing files to 30, so a change made in one place and forgotten in another
is now twice as easy and twice as invisible.

This tool makes that drift DETECTABLE instead of discovered by a customer.
It reports; it never edits. Whitespace is normalised for comparison so
reindentation is not mistaken for a change — the markup itself is not.

The language switcher lives inside <nav> and its href is per-page BY DESIGN
(/es/pricing from /pricing, and so on), so with it included every page's nav
hashes uniquely and the rest of the nav becomes uncomparable. --mask-switcher
blanks just that element so the surrounding chrome can still be compared.
It is off by default: the default run is whitespace-normalisation only.

Usage:
    python3 tools/drift-check.py                   # whitespace-normalised only
    python3 tools/drift-check.py --mask-switcher   # also ignore the per-page switcher
    python3 tools/drift-check.py --all             # include blog/ build output
    python3 tools/drift-check.py --strict          # exit 1 if es has more variants than en

Run from the repository root.
"""
import hashlib
import re
import subprocess
import sys

BLOCKS = {
    "main nav":    (r'<nav class="nav" id="mainNav"', '</nav>'),
    "mobile nav":  (r'<div class="mobile-nav-overlay"', '<div class="mobile-nav-footer">'),
    "footer":      (r'<footer class="footer"', '</footer>'),
    "footer hook": (r'<div class="footer-top-hook">', '</div>\n</div>'),
}


def tracked_html(include_blog):
    out = subprocess.check_output(["git", "ls-files", "*.html"]).decode().split("\n")
    files = [f for f in out if f.strip()]
    if not include_blog:
        files = [f for f in files if not f.startswith("blog/")]
    return files


def extract(html, start_pat, end_lit):
    m = re.search(start_pat, html)
    if not m:
        return None
    i = html.find(end_lit, m.end())
    if i == -1:
        return None
    return html[m.start():i + len(end_lit)]


SWITCHER = re.compile(
    r'<div class="lang-switch".*?</div>|<div class="mobile-lang">.*?</div>', re.S)


def norm(s, mask_switcher=False):
    """Whitespace only, unless --mask-switcher is given."""
    if mask_switcher:
        s = SWITCHER.sub("<!--lang-switch-->", s)
    return re.sub(r"\s+", " ", s).strip()


def digest(s, mask_switcher=False):
    return hashlib.sha256(norm(s, mask_switcher).encode("utf-8")).hexdigest()[:8]


def group(files, start_pat, end_lit, mask_switcher=False):
    groups = {}
    for f in files:
        try:
            html = open(f, encoding="utf-8").read()
        except OSError:
            continue
        blk = extract(html, start_pat, end_lit)
        key = digest(blk, mask_switcher) if blk else "ABSENT"
        groups.setdefault(key, []).append(f)
    return groups


def report(label, groups, lang):
    real = {k: v for k, v in groups.items() if k != "ABSENT"}
    absent = groups.get("ABSENT", [])
    print(f"\n  {lang}: {len(real)} variant(s) of the {label} "
          f"across {sum(len(v) for v in real.values())} file(s)")
    for k, v in sorted(real.items(), key=lambda x: (-len(x[1]), x[0])):
        print(f"    [{k}] {len(v):3d}  {', '.join(v)}")
    if absent:
        print(f"    [no {label}] {len(absent):3d}  {', '.join(absent)}")
    return len(real)


def main():
    include_blog = "--all" in sys.argv
    strict = "--strict" in sys.argv
    mask = "--mask-switcher" in sys.argv
    files = tracked_html(include_blog)
    en = [f for f in files if not f.startswith("es/")]
    es = [f for f in files if f.startswith("es/")]

    print("=" * 74)
    print("DRIFT CHECK — shared chrome across hand-maintained pages")
    print("=" * 74)
    print(f"English pages: {len(en)}    Spanish pages: {len(es)}"
          f"{'    (blog build output included)' if include_blog else ''}")
    print("comparison: whitespace-normalised"
          + ("; per-page language switcher masked" if mask else ""))
    print("\nVariants are counted WITHIN each language. English and Spanish blocks")
    print("necessarily differ from each other — that is translation, not drift.")
    print("Drift is: more variants in one language than the other, or a variant")
    print("that covers an odd subset of pages.")

    worse = []
    for label, (start, end) in BLOCKS.items():
        print(f"\n{'-' * 74}\n{label.upper()}")
        n_en = report(label, group(en, start, end, mask), "en")
        n_es = report(label, group(es, start, end, mask), "es")
        flag = "  <-- es has MORE variants than en" if n_es > n_en else ""
        print(f"\n  => en={n_en}  es={n_es}{flag}")
        if n_es > n_en:
            worse.append((label, n_en, n_es))

    print("\n" + "=" * 74)
    if worse:
        print("VERDICT: Spanish has more variants than English in:")
        for label, a, b in worse:
            print(f"  - {label}: en={a} es={b}")
        print("That is drift introduced on the Spanish side. Investigate.")
    else:
        print("VERDICT: Spanish introduces no variants beyond the English ones.")
    print("\nNOTE: the English variant counts are a PRE-EXISTING condition of this")
    print("repo, not something the /es work created. They are reported, not fixed —")
    print("normalising them is an English-site change that should land once, on the")
    print("English side, and propagate to both mirrors.")
    print("=" * 74)

    if strict and worse:
        sys.exit(1)


if __name__ == "__main__":
    main()
