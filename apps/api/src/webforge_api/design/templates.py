"""Jinja templates for the deterministic concept renderer (renderer-1).

Autoescaping is always on; only the generated stylesheet and illustration (built from validated hex colours
by `renderer.py`) are marked safe. Pages contain no scripts, no external URLs and no named form fields.
"""

from __future__ import annotations

NOTICE = "Independent redesign concept — not the official website"

MACROS = """
{%- macro kind_tag(s) -%}
{%- if s.content_kind == 'assumption' %}<p class="tag tag-confirm">To be confirmed by the business</p>{% endif -%}
{%- endmacro -%}

{%- macro heading(level, text, id=None) -%}
<h{{ level }}{% if id %} id="{{ id }}"{% endif %}>{{ text }}</h{{ level }}>
{%- endmacro -%}

{%- macro items_grid(items, level, cls) -%}
{%- if items %}<ul class="{{ cls }}" role="list">{% for it in items %}<li class="card">{{ heading(level, it.title) }}<p>{{ it.text }}</p></li>{% endfor %}</ul>{% endif -%}
{%- endmacro -%}

{%- macro block(s, idx, h, ctx) -%}
<section class="block b-{{ s.block }} k-{{ s.content_kind }}" aria-labelledby="s{{ idx }}" data-kind="{{ s.content_kind }}">
<div class="wrap">
{%- if s.block == 'hero' %}
  {{ heading(h, s.heading, 's' ~ idx) }}
  {% if s.body %}<p class="lead">{{ s.body }}</p>{% endif %}
  {{ kind_tag(s) }}
  {% if s.cta_label %}<p><a class="button" href="inquiry">{{ s.cta_label }}</a></p>{% endif %}
{%- elif s.block == 'feature_grid' or s.block == 'service_cards' %}
  {{ heading(h, s.heading, 's' ~ idx) }}
  {% if s.body %}<p>{{ s.body }}</p>{% endif %}
  {{ kind_tag(s) }}
  {{ items_grid(s.items, h + 1, 'grid') }}
{%- elif s.block == 'process_steps' %}
  {{ heading(h, s.heading, 's' ~ idx) }}
  {% if s.body %}<p>{{ s.body }}</p>{% endif %}
  {{ kind_tag(s) }}
  {% if s.items %}<ol class="steps">{% for it in s.items %}<li>{{ heading(h + 1, it.title) }}<p>{{ it.text }}</p></li>{% endfor %}</ol>{% endif %}
{%- elif s.block == 'faq' %}
  {{ heading(h, s.heading, 's' ~ idx) }}
  {% if s.body %}<p>{{ s.body }}</p>{% endif %}
  {{ kind_tag(s) }}
  {% for it in s.items %}<details class="faq"><summary>{{ it.title }}</summary><p>{{ it.text }}</p></details>{% endfor %}
{%- elif s.block == 'cta_band' %}
  {{ heading(h, s.heading, 's' ~ idx) }}
  {% if s.body %}<p>{{ s.body }}</p>{% endif %}
  {{ kind_tag(s) }}
  {% if s.cta_label %}<p><a class="button" href="inquiry">{{ s.cta_label }}</a></p>{% endif %}
{%- elif s.block == 'gallery_placeholder' %}
  {{ heading(h, s.heading, 's' ~ idx) }}
  {% if s.body %}<p>{{ s.body }}</p>{% endif %}
  {{ kind_tag(s) }}
  <div class="gallery">{% for _ in range(3) %}<div class="tile">{{ ctx.illustration }}</div>{% endfor %}</div>
  <p class="tag">Original illustration placeholders. Real photography would be supplied or approved by the business.</p>
{%- elif s.block == 'inquiry_demo' %}
  {{ heading(h, s.heading, 's' ~ idx) }}
  {% if s.body %}<p>{{ s.body }}</p>{% endif %}
  <form class="demo" aria-describedby="demo-note-{{ idx }}" autocomplete="off" novalidate>
    <p id="demo-note-{{ idx }}" class="tag tag-demo">Demo only. This form does not send, save or collect anything.</p>
    <div class="field"><label for="f{{ idx }}-name">Your name</label><input id="f{{ idx }}-name" type="text" autocomplete="off"></div>
    <div class="field"><label for="f{{ idx }}-contact">Email or phone</label><input id="f{{ idx }}-contact" type="text" autocomplete="off"></div>
    <div class="field"><label for="f{{ idx }}-msg">How can we help?</label><textarea id="f{{ idx }}-msg" rows="4"></textarea></div>
    <button class="button" type="button">{{ s.cta_label or 'Send enquiry' }}</button>
  </form>
{%- elif s.block == 'contact_panel' %}
  {{ heading(h, s.heading, 's' ~ idx) }}
  {% if s.body %}<p>{{ s.body }}</p>{% endif %}
  {% if ctx.contact_facts %}
  <dl class="contact">{% for f in ctx.contact_facts %}<div><dt>{{ f.label }}</dt><dd>{{ f.value }}</dd></div>{% endfor %}</dl>
  {% else %}
  <p class="tag tag-confirm">Contact details will be added once the business confirms them.</p>
  {% endif %}
{%- else %}
  {{ heading(h, s.heading, 's' ~ idx) }}
  {% if s.body %}<p>{{ s.body }}</p>{% endif %}
  {{ kind_tag(s) }}
  {{ items_grid(s.items, h + 1, 'grid') }}
{%- endif %}
</div>
</section>
{%- endmacro -%}
"""

PAGE = """{% import 'macros' as m -%}
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:; form-action 'none'; base-uri 'none'">
<meta name="robots" content="noindex, nofollow">
<meta name="referrer" content="no-referrer">
<title>{{ page.title }} · {{ wordmark }} · Redesign concept</title>
<style>{{ css }}</style>
</head>
<body class="v-{{ variant }}">
<a class="skip" href="#main">Skip to content</a>
<div class="notice" role="note"><div class="wrap"><strong>{{ notice }}.</strong> A design proposal by {{ author_name }}; not affiliated with or endorsed by {{ wordmark }}.</div></div>
<header class="site">
  <div class="wrap bar">
    <a class="brand" href="home">{{ wordmark }}</a>
    <nav aria-label="Main">
      <ul role="list">{% for p in nav %}<li><a href="{{ p.slug }}"{% if p.slug == page.slug %} aria-current="page"{% endif %}>{{ p.title }}</a></li>{% endfor %}</ul>
    </nav>
  </div>
</header>
<main id="main">
{%- for s in page.sections %}
{{ m.block(s, loop.index, 1 if loop.first else 2, ctx) }}
{%- endfor %}
</main>
<footer class="site">
  <div class="wrap">
    <p><strong>{{ notice }}.</strong> Prepared by {{ author_name }}{% if author_url %} ({{ author_url }}){% endif %} to show how {{ wordmark }}'s website could look. Text marked "To be confirmed" is placeholder content; other wording is suggested copy. Illustrations are original artwork generated for this concept.</p>
  </div>
</footer>
</body>
</html>
"""
