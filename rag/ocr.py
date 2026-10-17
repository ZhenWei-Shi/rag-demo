"""Cloud OCR with local Tesseract fallback; empty credentials select local OCR."""
import logging
import os

logger = logging.getLogger(__name__)


def _aliyun_ocr_pdf(content: bytes) -> str:
    # EN: Fast OCR using Aliyun's cloud API. Processes each page in parallel (ThreadPoolExecutor).
    #     Requires ALIYUN_OCR_AK and ALIYUN_OCR_SK environment variables.
    # ZH: 使用阿里云 OCR API 进行快速识别，多线程并行处理每一页。
    #     需要设置 ALIYUN_OCR_AK 和 ALIYUN_OCR_SK 环境变量。
    import io, json
    from pdf2image import convert_from_bytes
    from concurrent.futures import ThreadPoolExecutor
    from alibabacloud_ocr_api20210707.client import Client
    from alibabacloud_ocr_api20210707 import models as ocr_models
    from alibabacloud_tea_openapi import models as open_api_models

    config = open_api_models.Config(
        access_key_id=os.getenv("ALIYUN_OCR_AK"),
        access_key_secret=os.getenv("ALIYUN_OCR_SK"),
        endpoint="ocr-api.cn-hangzhou.aliyuncs.com",
    )
    client = Client(config)
    images = convert_from_bytes(content, dpi=150)

    def _ocr_page(img):
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        resp = client.recognize_general(ocr_models.RecognizeGeneralRequest(body=buf))
        data = json.loads(resp.body.data)
        # EN: Use the `content` field which contains the full page text.
        # ZH: 使用 `content` 字段获取整页文本内容。
        return data.get("content", "")

    workers = min(4, len(images))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pages = list(pool.map(_ocr_page, images))

    return "\n".join(pages)


def _aliyun_ocr_available() -> bool:
    return bool(os.getenv("ALIYUN_OCR_AK") and os.getenv("ALIYUN_OCR_SK"))


def _tesseract_ocr_pdf(content: bytes) -> str:
    # EN: Local OCR fallback using Tesseract. Slower but requires no API key.
    # ZH: 使用 Tesseract 的本地 OCR 兜底方案，速度较慢但无需 API Key。
    from pdf2image import convert_from_bytes
    import pytesseract
    from concurrent.futures import ThreadPoolExecutor

    images = convert_from_bytes(content, dpi=120)

    def _ocr_page(img):
        return pytesseract.image_to_string(img, lang="chi_sim+eng")

    workers = min(2, len(images))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pages = list(pool.map(_ocr_page, images))

    return "\n".join(pages)


def extract_pdf_text(content: bytes) -> str:
    # EN: Use Aliyun OCR if credentials are configured; fall back to Tesseract on any error.
    # ZH: 优先使用阿里云 OCR，任何错误（包括服务未开通）均自动降级为 Tesseract。
    if _aliyun_ocr_available():
        try:
            return _aliyun_ocr_pdf(content)
        except Exception as e:
            logger.warning("Aliyun OCR failed (%s), falling back to Tesseract", e)
    return _tesseract_ocr_pdf(content)
