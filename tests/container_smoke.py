"""Run inside a fresh network-isolated Docker container, not against production.

No LLM is called. This verifies real OCR binaries, cached embeddings and storage.
"""
import io
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path


def request(path, data=None, method=None, headers=None):
    req = urllib.request.Request("http://127.0.0.1:8000" + path, data=data,
                                 method=method, headers=headers or {})
    with urllib.request.urlopen(req, timeout=90) as response:
        return json.load(response)


def main():
    assert os.environ.get("RAG_DATA_DIR") == "/tmp/rag-container-data"
    assert not any(os.getenv(key) for key in ("ALIYUN_OCR_AK", "ALIYUN_OCR_SK", "OPENAI_API_KEY", "DEEPSEEK_API_KEY"))
    assert not Path("/app/.env").exists()
    assert not Path("/app/evaluation").exists()
    assert not Path("/app/node_modules").exists()
    import torch
    assert torch.version.cuda is None, "Container unexpectedly installed CUDA wheels"
    langs = subprocess.check_output(["tesseract", "--list-langs"], text=True).splitlines()
    assert "eng" in langs and "chi_sim" in langs
    subprocess.run(["pdftoppm", "-v"], check=True, capture_output=True)
    for attempt in range(90):
        try:
            assert request("/documents")["documents"] == []
            break
        except (urllib.error.URLError, TimeoutError):
            if attempt == 89:
                raise
            time.sleep(1)

    # Exercise the actual packaged frontend, including every module dependency.
    with urllib.request.urlopen("http://127.0.0.1:8000/", timeout=10) as response:
        page = response.read().decode()
    assert 'src="/js/main.js"' in page and 'href="/styles.css"' in page
    assets = [Path("static/styles.css"), *sorted(Path("static/js").glob("*.js"))]
    assert len(assets) == 5, "Expected CSS and all four browser modules"
    for asset in assets:
        url = "http://127.0.0.1:8000/" + asset.relative_to("static").as_posix()
        with urllib.request.urlopen(url, timeout=10) as response:
            assert response.read() == asset.read_bytes(), str(asset)
            if asset.suffix == ".js":
                assert "javascript" in response.headers.get("Content-Type", ""), str(asset)

    from PIL import Image, ImageDraw, ImageFont
    import PyPDF2
    image = Image.new("RGB", (1600, 500), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=48)
    for y, line in zip((60, 170, 280), ("CONTAINER CHECK", "Reference code: COBALT731", "Loan duration: 23 days.")):
        draw.text((60, y), line, fill="black", font=font)
    pdf = io.BytesIO()
    image.save(pdf, format="PDF", resolution=150)
    assert not "".join(page.extract_text() or "" for page in PyPDF2.PdfReader(io.BytesIO(pdf.getvalue())).pages).strip()
    filename = "container-ocr-check.pdf"
    boundary = "RagContainerSmokeBoundary"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\nContent-Type: application/pdf\r\n\r\n".encode()
            + pdf.getvalue() + f"\r\n--{boundary}--\r\n".encode())
    try:
        uploaded = request("/upload", body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        assert uploaded["chunks"] > 0, uploaded
        assert request("/documents")["documents"] == [filename]
        from rag.embedder import embed
        from rag.store import query
        hits = query(embed(["What is the loan duration for COBALT731?"])[0], question="COBALT731 loan duration")
        text = " ".join(hit["text"] for hit in hits)
        assert "COBALT731" in text and "23" in text and "days" in text, text
        assert hits[0]["source"] == filename
        print(json.dumps({"ocr": "real image-only PDF via Tesseract", "retrieval": "COBALT731 / 23 days", "cuda": torch.version.cuda, "status": "passed"}))
    finally:
        request("/documents/" + filename, method="DELETE")
        assert request("/documents")["documents"] == []


if __name__ == "__main__":
    main()
