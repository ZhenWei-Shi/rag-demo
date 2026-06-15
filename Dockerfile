# EN: Multi-stage-friendly single-stage build for the RAG Document Q&A app.
# ZH: RAG 文档问答系统的 Docker 构建文件。

FROM python:3.11-slim

# EN: Install system dependencies:
#   - tesseract-ocr + chi_sim: OCR engine with Chinese language support
#   - poppler-utils: required by pdf2image to convert PDF pages to images
# ZH: 安装系统依赖：
#   - tesseract-ocr + chi_sim：OCR 引擎及中文语言包
#   - poppler-utils：pdf2image 将 PDF 页面转换为图片所需
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-chi-sim \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# EN: Copy requirements first to leverage Docker layer caching.
#     Dependency layer only rebuilds when requirements.txt changes.
# ZH: 先复制依赖文件以利用 Docker 层缓存。
#     只有 requirements.txt 变更时才会重新安装依赖。
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# EN: Pre-download the embedding model at build time so the container
#     starts instantly without a cold-download delay.
# ZH: 构建时预下载嵌入模型，容器启动后无需等待下载，直接可用。
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# EN: Copy application source code.
# ZH: 复制应用源代码。
COPY . .

# EN: ChromaDB stores its data here; mount a volume to persist it across restarts.
# ZH: ChromaDB 数据目录，挂载 volume 以持久化索引数据。
VOLUME ["/app/chroma_data"]

EXPOSE 8000

# EN: Run the FastAPI app with uvicorn. Workers=1 is appropriate for the 2-core demo server.
# ZH: 使用 uvicorn 启动 FastAPI 应用。演示服务器为 2 核，单 worker 足够。
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
