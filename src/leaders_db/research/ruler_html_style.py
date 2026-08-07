"""Presentation-only style for the self-contained ruler evidence report."""

REPORT_CSS = """
body { margin:0; background:#f3f1eb; color:#202522;
  font:16px/1.55 system-ui,sans-serif }
main { max-width:1180px; margin:auto; background:#fff; padding:42px }
h1 { font:700 44px/1.1 Georgia,serif }
h2 { font:700 32px Georgia,serif; border-bottom:2px solid #1e5a4f;
  padding-bottom:8px }
h3 { font:700 23px Georgia,serif }
a { color:#075f6b }
.eyebrow,.meta,.quality,.gate { color:#52615c }
.summary { display:grid; grid-template-columns:repeat(3,1fr); gap:12px }
.summary div { background:#e8efe9; padding:16px }
.summary b { font-size:24px; display:block }
.summary span { font-size:13px }
nav { position:sticky; top:0; background:#143f38; padding:10px; z-index:3 }
nav a { color:white; margin-right:15px }
article { padding:24px 0; border-bottom:1px solid #ccd5d0 }
.answer { font-family:Georgia,serif; font-size:17px }
.cite { font:12px system-ui; background:#e5f1ef; padding:1px 4px;
  border-radius:3px }
details { margin-top:15px }
.evidence { background:#f6f7f4; border-left:4px solid #39766a;
  padding:12px; margin:12px 0 }
.evidence h4 { margin:0 }
blockquote { background:white; border-left:3px solid #aaa; margin:8px 0;
  padding:8px 12px }
table { border-collapse:collapse; width:100%; font-size:13px }
th,td { border:1px solid #ccd1ce; padding:7px; vertical-align:top }
th { background:#e5ece8; position:sticky; top:44px }
.total { font-weight:bold }
pre { white-space:pre-wrap; background:#f5f5f1; padding:16px }
@media(max-width:800px) { main { padding:18px } .summary {
  grid-template-columns:1fr 1fr } table { display:block; overflow:auto } }
"""

__all__ = ["REPORT_CSS"]
