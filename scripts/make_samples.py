"""Build the sample PDFs in fixtures/inputs/ with headless Chrome (a realistic text layer).

    uv run scripts/make_samples.py

sample_en.pdf  two pages: title, headings, paragraphs, a bordered table, a coloured callout,
               a figure, footnotes, running header and page numbers
sample_hi.pdf  one Hindi page: heading, paragraphs, a small table, a footnote
"""

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent.parent / "fixtures" / "inputs"

CSS = """
@page { size: A4; margin: 22mm 20mm 24mm 20mm; }
body { font-family: 'Noto Serif', 'Noto Serif Devanagari', serif; font-size: 10.5pt; line-height: 1.45; color: #111; }
h1 { font-family: 'Noto Sans', 'Noto Sans Devanagari', sans-serif; font-size: 22pt; margin: 0 0 4pt; }
h2 { font-family: 'Noto Sans', 'Noto Sans Devanagari', sans-serif; font-size: 14pt; margin: 14pt 0 4pt; color: #1e3a8a; }
.subtitle { color: #555; font-size: 11pt; margin-bottom: 12pt; }
table { border-collapse: collapse; margin: 8pt 0; font-size: 9.5pt; }
th, td { border: 0.8pt solid #333; padding: 3pt 8pt; text-align: left; }
th { background: #e5e7eb; }
.callout { background: #fef3c7; border-left: 4pt solid #d97706; padding: 6pt 10pt; margin: 10pt 0; }
.figure { margin: 10pt 0; text-align: center; font-size: 9pt; color: #444; }
.footnotes { border-top: 0.6pt solid #999; margin-top: 14pt; padding-top: 4pt; font-size: 8pt; color: #333; }
.page { page-break-after: always; position: relative; }
.page:last-child { page-break-after: auto; }
.running { font-size: 8pt; color: #777; border-bottom: 0.5pt solid #ccc; margin-bottom: 10pt; }
.pageno { position: absolute; bottom: -14mm; right: 0; font-size: 9pt; color: #555; }
"""

FIGURE = """<svg width="300" height="110" xmlns="http://www.w3.org/2000/svg">
<rect x="10" y="60" width="40" height="40" fill="#4f46e5"/><rect x="70" y="35" width="40" height="65" fill="#4f46e5"/>
<rect x="130" y="20" width="40" height="80" fill="#4f46e5"/><rect x="190" y="45" width="40" height="55" fill="#4f46e5"/>
<line x1="5" y1="100" x2="245" y2="100" stroke="#111"/></svg>"""

EN = f"""
<div class="page">
  <div class="running">District Education Survey 2025 — Summary Report</div>
  <h1>District Education Survey 2025</h1>
  <div class="subtitle">Summary of findings for the planning committee</div>
  <p>This report summarises the results of the annual education survey conducted across twelve
  districts between January and March 2025. The survey covered primary and secondary schools, with a
  focus on enrolment, attendance and access to learning materials.<sup>1</sup></p>
  <h2>1. Key findings</h2>
  <p>Enrolment in primary schools increased in nine of the twelve districts. Attendance remained
  steady overall, although schools in remote areas reported lower attendance during the monsoon
  months. Access to textbooks improved after the new distribution scheme was introduced.</p>
  <table>
    <tr><th>District</th><th>Schools surveyed</th><th>Enrolment change</th><th>Attendance</th></tr>
    <tr><td>Northfield</td><td>48</td><td>+6.2%</td><td>91%</td></tr>
    <tr><td>Riverside</td><td>35</td><td>+3.8%</td><td>88%</td></tr>
    <tr><td>Hillcrest</td><td>27</td><td>−1.4%</td><td>79%</td></tr>
    <tr><td>Lakeview</td><td>41</td><td>+4.5%</td><td>93%</td></tr>
  </table>
  <div class="callout"><b>Note for the committee:</b> figures for Hillcrest are provisional because two
  schools could not be visited before the deadline.</div>
  <h2>2. Attendance across the year</h2>
  <p>Attendance was highest in the second quarter and lowest during the monsoon. The chart below shows
  the average attendance by quarter for all districts combined.</p>
  <div class="figure">{FIGURE}<br>Figure 1: Average attendance by quarter</div>
  <div class="footnotes"><sup>1</sup> The survey followed the methodology agreed by the committee in 2023.</div>
  <div class="pageno">1</div>
</div>
<div class="page">
  <div class="running">District Education Survey 2025 — Summary Report</div>
  <h2>3. Learning materials</h2>
  <p>Most schools now receive textbooks before the start of the academic year. However, teachers in
  several districts asked for more reading material in local languages, especially for the early
  grades.<sup>2</sup></p>
  <h2>4. Recommendations</h2>
  <p>The committee should consider the following actions for the next academic year:</p>
  <ul>
    <li>Extend the textbook distribution scheme to all remaining schools.</li>
    <li>Provide reading material in local languages for grades one to three.</li>
    <li>Arrange transport support in districts with low monsoon attendance.</li>
  </ul>
  <h2>5. Budget summary</h2>
  <table>
    <tr><th>Item</th><th>Estimated cost (₹ lakh)</th></tr>
    <tr><td>Textbook distribution</td><td>120</td></tr>
    <tr><td>Local-language readers</td><td>45</td></tr>
    <tr><td>Transport support</td><td>60</td></tr>
    <tr><th>Total</th><th>225</th></tr>
  </table>
  <div class="footnotes"><sup>2</sup> Requests were collected through the teacher feedback forms.</div>
  <div class="pageno">2</div>
</div>
"""

HI = """
<div class="page">
  <div class="running">ज़िला स्वास्थ्य रिपोर्ट 2025</div>
  <h1>ग्रामीण स्वास्थ्य सेवाएँ</h1>
  <div class="subtitle">वार्षिक समीक्षा का सारांश</div>
  <p>इस रिपोर्ट में ज़िले के ग्रामीण क्षेत्रों में स्वास्थ्य सेवाओं की स्थिति का सारांश दिया गया है। सर्वेक्षण
  जनवरी से मार्च 2025 के बीच किया गया और इसमें प्राथमिक स्वास्थ्य केंद्रों को शामिल किया गया।<sup>1</sup></p>
  <h2>1. मुख्य निष्कर्ष</h2>
  <p>अधिकांश स्वास्थ्य केंद्रों में दवाओं की उपलब्धता में सुधार हुआ है। फिर भी दूरदराज़ के गाँवों में
  डॉक्टरों की कमी बनी हुई है, और मरीज़ों को इलाज के लिए लंबी दूरी तय करनी पड़ती है।</p>
  <table>
    <tr><th>प्रखंड</th><th>स्वास्थ्य केंद्र</th><th>डॉक्टर</th></tr>
    <tr><td>उत्तरपुर</td><td>12</td><td>9</td></tr>
    <tr><td>दक्षिणगंज</td><td>8</td><td>5</td></tr>
    <tr><td>पूर्वी घाट</td><td>10</td><td>6</td></tr>
  </table>
  <h2>2. सुझाव</h2>
  <p>समिति को अगले वर्ष के लिए मोबाइल स्वास्थ्य शिविरों की संख्या बढ़ाने और दवाओं की आपूर्ति को नियमित
  करने पर विचार करना चाहिए।</p>
  <div class="footnotes"><sup>1</sup> आँकड़े ज़िला स्वास्थ्य कार्यालय से प्राप्त किए गए।</div>
  <div class="pageno">1</div>
</div>
"""


def main():
    """Print the English and Hindi sample pages to PDFs in fixtures/inputs/ with Chrome."""
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        page = browser.new_page()
        for name, body, lang in [("sample_en.pdf", EN, "en"), ("sample_hi.pdf", HI, "hi")]:
            page.set_content(
                f"<html lang='{lang}'><head><meta charset='utf-8'><style>{CSS}</style></head><body>{body}</body></html>"
            )
            (OUT / name).write_bytes(page.pdf(prefer_css_page_size=True, print_background=True))
            print("wrote", OUT / name)
        browser.close()


if __name__ == "__main__":
    main()
