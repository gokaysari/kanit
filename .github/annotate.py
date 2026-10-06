"""Başarısız test çıktısını iş açıklamalarına (annotation) yazar.

Ham iş günlüğüne erişilemeyen ortamlarda hata nedenini API üzerinden okunabilir kılar.
"""

import sys

CHUNK = 3500
MAX = 4
LEVEL = sys.argv[2] if len(sys.argv) > 2 else "error"
TITLE = sys.argv[3] if len(sys.argv) > 3 else "pytest"

text = open(sys.argv[1], encoding="utf-8", errors="replace").read()
chunks = [text[i : i + CHUNK] for i in range(0, len(text), CHUNK)][-MAX:]
for n, chunk in enumerate(chunks, 1):
    body = chunk.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::{LEVEL} title={TITLE} {n}/{len(chunks)}::{body}")
