// Evidence collected inside the page. Pure DOM reads: no clicks, no form submission.
() => {
  const vw = window.innerWidth, vh = window.innerHeight;
  const doc = document.documentElement;
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none";
  };
  const text = (el) => (el.innerText || el.textContent || "").replace(/\s+/g, " ").trim();
  const headings = [...document.querySelectorAll("h1,h2,h3,h4,h5,h6")].filter(visible)
    .map((h) => ({ level: Number(h.tagName[1]), text: text(h).slice(0, 120) }));
  const h1 = document.querySelector("h1");
  let h1Lines = null;
  if (h1 && visible(h1)) {
    const lh = parseFloat(getComputedStyle(h1).lineHeight) || parseFloat(getComputedStyle(h1).fontSize) * 1.2;
    h1Lines = Math.round(h1.getBoundingClientRect().height / lh);
  }
  const imgs = [...document.images];
  const brokenImgs = imgs.filter((i) => i.complete && i.naturalWidth === 0 && (i.currentSrc || i.src))
    .map((i) => (i.currentSrc || i.src).slice(0, 300));
  const missingAlt = imgs.filter((i) => !i.hasAttribute("alt") && visible(i)).length;
  const anchors = [...document.querySelectorAll("a[href]")];
  const sameOrigin = [], external = [];
  for (const a of anchors) {
    try {
      const u = new URL(a.getAttribute("href"), location.href);
      if (!["http:", "https:"].includes(u.protocol)) continue;
      u.hash = "";
      (u.origin === location.origin ? sameOrigin : external).push(u.href);
    } catch (e) {}
  }
  const navLinks = [...document.querySelectorAll("nav a[href], header a[href], [role=navigation] a[href]")].filter(visible);
  const actionWords = /\b(book|call|contact|quote|order|buy|shop|get started|request|schedule|appointment|reserve|enquir|inquir|sign up|subscribe|visit us|whatsapp)\b/i;
  const ctaEls = [...document.querySelectorAll("a[href],button,input[type=submit]")].filter(visible).filter((el) => {
    const href = (el.getAttribute("href") || "").toLowerCase();
    return actionWords.test(text(el) || el.value || "") || href.startsWith("tel:") || href.startsWith("mailto:") || href.includes("wa.me");
  });
  const ctaAboveFold = ctaEls.some((el) => el.getBoundingClientRect().top < vh);
  const contactRoutes = anchors.filter((a) => /^(tel:|mailto:)|wa\.me|\/contact/i.test(a.getAttribute("href") || "")).length;
  let smallText = 0, textNodes = 0;
  for (const el of document.querySelectorAll("p,li,span,a,td")) {
    if (!visible(el) || !text(el)) continue;
    textNodes++;
    if (parseFloat(getComputedStyle(el).fontSize) < 12) smallText++;
  }
  const tapTargets = [...document.querySelectorAll("a[href],button")].filter(visible);
  const smallTaps = tapTargets.filter((el) => { const r = el.getBoundingClientRect(); return r.width < 32 || r.height < 32; }).length;
  const overlays = [...document.querySelectorAll("body *")].filter((el) => {
    const s = getComputedStyle(el);
    if (!["fixed", "sticky"].includes(s.position) || !visible(el)) return false;
    const r = el.getBoundingClientRect();
    return (r.width * r.height) / (vw * vh) > 0.3 && /cookie|consent|gdpr|privacy/i.test(text(el));
  }).length;
  const meta = (n) => document.querySelector(`meta[name="${n}"]`)?.getAttribute("content") || null;
  return {
    url: location.href,
    title: document.title.slice(0, 200),
    lang: doc.getAttribute("lang"),
    meta_description: (meta("description") || "").slice(0, 300) || null,
    viewport_meta: meta("viewport"),
    viewport: { width: vw, height: vh },
    scroll_width: Math.max(doc.scrollWidth, document.body ? document.body.scrollWidth : 0),
    client_width: doc.clientWidth,
    page_height: doc.scrollHeight,
    headings: headings.slice(0, 60),
    h1_count: headings.filter((h) => h.level === 1).length,
    h1_lines: h1Lines,
    images_total: imgs.length,
    images_broken: brokenImgs.slice(0, 20),
    images_missing_alt: missingAlt,
    same_origin_links: [...new Set(sameOrigin)].slice(0, 200),
    external_links: new Set(external).size,
    nav_links: navLinks.length,
    cta_count: ctaEls.length,
    cta_above_fold: ctaAboveFold,
    cta_samples: ctaEls.slice(0, 5).map((el) => (text(el) || el.value || "").slice(0, 60)),
    contact_routes: contactRoutes,
    forms: document.forms.length,
    small_text_ratio: textNodes ? smallText / textNodes : null,
    small_tap_targets: smallTaps,
    tap_targets: tapTargets.length,
    consent_overlay: overlays > 0,
    word_count: text(document.body || doc).split(" ").filter(Boolean).length,
  };
}
