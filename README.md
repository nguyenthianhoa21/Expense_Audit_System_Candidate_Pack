# AI Expense Audit System

Hệ thống đối soát 3 chiều bộ chứng từ thanh toán **PO - Invoice - Payment Request** bằng AI:
người dùng tải tệp lên → AI trích xuất thông tin → engine kiểm toán **13 quy tắc R0-R12**
chạy hoàn toàn bằng code Python thuần lập luận → hiển thị vi phạm đến từng ô dữ liệu → lưu lịch sử kiểm toán.

> Bộ sample kèm theo (`Sample/`) cố ý chứa lỗi để demo: bộ mẫu sẽ ra **REJECTED**
> với **1 CRITICAL (R2) + 3 HIGH (R3, R5, R7) + 1 MEDIUM (R12)**.

## 1. Kiến trúc hệ thống

```text
                 +----------------------------+         +-----------------------------+
                 | Extraction Engine (LLM)    |         | Deterministic Audit Engine   |
  PDF / ảnh -->  | Gemma 4 31B -> 26B (free)  |  JSON   | R0-R12 Python thuần lập luận| --> PASSED / WARNING / REJECTED
                 | + Retry/Timeout + Offline   | ------> | BGE-M3 + XOR Token Diff      |
                 +----------------------------+         +-----------------------------+
                            |                                           |
                            +----> SQLite (local) / PostgreSQL  <--------+
```

Nguyên tắc thiết kế:

- **AI chỉ ĐỌC, không ĐOÁN**: LLM chỉ trích xuất JSON. Mọi so sánh và phép tính nằm trong
  `backend/app/services/audit_engine.py` (không có LLM trong file này) → kết quả lặp lại được và
  giải thích được cho reviewer.
- **Failover 4 lớp** nên hệ thống luôn trả kết quả:

  | Lớp | Cơ chế | Nội dung |
  |---|---|---|
  | Layer 1 | Config Guard | Thiếu `OPENROUTER_API_KEY` hoặc tệp không đọc được văn bản |
  | Layer 2 | Model Chain | `google/gemma-4-31b-it:free` → `google/gemma-4-26b-a4b-it:free` |
  | Layer 3 | Retry & Timeout | Timeout 20s, tối đa 3 lần, exponential backoff |
  | Layer 4 | Offline Parser | pdfplumber + PyMuPDF + regex, luôn có kết quả |

- **Lỗi kỹ thuật không lọt lên giao diện**: chi tiết lỗi OpenRouter (kể cả HTTP 429) chỉ ghi log
  ở terminal; giao diện nhận thông báo tiếng Việt ngắn gọn do `_friendly_model_warning()` sinh ra.

- **Sở khớp mờ BGE-M3** (`bge_matcher.py`): fast-path → tokenize/clean → XOR diff → cosine similarity.
  Chỉ coi là khớp khi `len(diff)==0 AND sim >= 0.995`. Nếu chưa tải được model nặng (~2.2GB) thì tự
  fallback về token ratio nhưng vẫn giữ nguyên ngưỡng nghiêm ngặt.

## 2. Cấu trúc thư mục

```text
.
├── backend/
│   ├── app/
│   │   ├── main.py                  # Khởi tạo FastAPI, CORS, mount static storage
│   │   ├── core/config.py           # Cấu hình đọc từ .env (pydantic-settings)
│   │   ├── db/
│   │   │   ├── models.py            # AuditBatch, Document, ValidationFinding
│   │   │   └── session.py           # Engine async, init_db, tự ALTER cho SQLite cũ
│   │   ├── schemas/
│   │   │   ├── extraction.py        # DocumentExtractionData (20+ trường) + Pydantic validators
│   │   │   └── validation.py        # RuleResult, Severity, Verdict, VerdictResult
│   │   ├── services/
│   │   │   ├── document_io.py       # Đọc PDF (pdfplumber/PyMuPDF) + validate input
│   │   │   ├── extractor.py         # Extraction Engine 4 lớp (gọi OpenRouter)
│   │   │   ├── offline_parser.py    # Regex parser dự phòng (Layer 4)
│   │   │   ├── audit_engine.py      # 13 quy tắc R0-R12, không dùng LLM
│   │   │   ├── audit_pipeline.py    # Orchestrate: upload → extract → audit → lưu DB
│   │   │   └── bge_matcher.py       # So khớp tên/địa chỉ mờ
│   │   └── api/v1/audit.py          # REST endpoints
│   ├── scripts/smoke_offline.py     # Smoke test không cần mạng
│   ├── tests/test_audit_rules.py    # 10 unit test R0-R12
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx                  # Điều phối 3 view: kiểm tra / lịch sử
│   │   ├── api.js                   # Axios client
│   │   ├── components/
│   │   │   ├── UploadPanel.jsx      # Chọn tệp, ô nhập số hoá đơn, tiến độ
│   │   │   ├── FindingsPanel.jsx    # Cảnh báo rủi ro, phân trang 3 mục/trang
│   │   │   ├── SideBySideViewer.jsx # Ma trận 3 cột PO | Invoice | PR + highlight
│   │   │   └── HistoryView.jsx      # Danh sách lịch sử kiểm toán
│   │   ├── utils/safeWarnings.js    # Chặn lỗi kỹ thuật thô lên UI
│   │   └── index.css
│   ├── Dockerfile
│   └── package.json
├── Sample/                          # 3 tệp mẫu (PO, Invoice, Payment Request)
├── docker-compose.yml               # Postgres + Backend + Frontend
└── README.md
```

## 3. Chạy nhanh (không dùng Docker)

### 3.1. Backend (FastAPI)

```powershell
cd backend
copy .env.example .env        # điền OPENROUTER_API_KEY của bạn vào .env
python -m pip install -r requirements.txt
$env:PYTHONPATH = "."         # Windows PowerShell, giúp import được app.*
uvicorn app.main:app --reload --port 8000
```

Mở http://localhost:8000/docs để thử API.

> **Lỗi thường gặp**: `ModuleNotFoundError: No module named 'app'` xảy ra khi chạy lệnh `uvicorn`
> từ thư mục `frontend/` hoặc thư mục gốc. Phải `cd backend` trước rồi mới chạy `uvicorn`.

Các biến môi trường (xem `backend/.env.example`):

| Biến | Ý nghĩa | Mặc định |
|---|---|---|
| `OPENROUTER_API_KEY` | Key OpenRouter dùng cho Layer 2 | *(rỗng)* |
| `OPENROUTER_BASE_URL` | Endpoint OpenRouter | `https://openrouter.ai/api/v1` |
| `EXTRACTOR_MODEL_CHAIN` | Thứ tự model fallback (phân tách bằng dấu phẩy) | `google/gemma-4-31b-it:free,google/gemma-4-26b-a4b-it:free` |
| `OPENROUTER_RESPONSE_FORMAT` | `json_object` \| `json_schema` \| `none` | `json_object` |
| `REQUEST_TIMEOUT_SECONDS` | Timeout mỗi lần gọi (Layer 3) | `20` |
| `MAX_RETRIES` | Số lần thử lại mỗi model (Layer 3) | `3` |
| `BACKOFF_BASE_SECONDS` | Hệ số exponential backoff | `1.5` |
| `DATABASE_URL` | SQLite cho local hoặc Postgres cho production | `sqlite+aiosqlite:///./app.db` |
| `STORAGE_PATH` | Nơi lưu tệp upload | `./storage` |
| `MAX_UPLOAD_MB` | Giới hạn dung lượng tệp | `20` |
| `CORS_ORIGINS` | Danh sách origin cho phép | `http://localhost:5173,http://127.0.0.1:5173` |

### 3.2. Frontend (React + Vite + Tailwind)

```powershell
cd frontend
copy .env.example .env        # VITE_API_BASE=http://localhost:8000
npm install
npm run dev                   # http://localhost:5173
```

### 3.3. Chạy với Docker

```powershell
copy backend\.env.example backend\.env   # nhớ điền OPENROUTER_API_KEY
docker compose up --build
# backend  http://localhost:8000/docs
# frontend http://localhost:5173
```

Postgres chạy ở `db:5432` với user/password/database mặc định `audit/audit/expense_audit`.

## 4. API

| Endpoint | Method | Mô tả |
|---|---|---|
| `/health` | GET | Kiểm tra trạng thái ứng dụng |
| `/api/v1/audit/upload` | POST multipart `files` (1-10 tệp PDF/ảnh) + `reference_label` | Trích xuất + kiểm toán + lưu batch |
| `/api/v1/audit/batches?limit&offset` | GET | Danh sách lịch sử batch |
| `/api/v1/audit/batches/{id}` | GET | Chi tiết batch (documents + findings + rule_results) |
| `/api/v1/audit/batches/{id}/export` | GET | Xuất CSV findings |

Trường `reference_label` là **số hoá đơn / tên chứng từ** do người dùng nhập ở giao diện, được lưu vào
cột `audit_batches.reference_label` (tự thêm cột bằng `_ensure_columns()` nếu chạy trên DB cũ).

## 5. Trường trích xuất và 13 quy tắc R0-R12

Ma trận trường trích xuất: `doc_type`, `doc_number`, `reference_numbers`, `issue_date`,
`buyer_name`, `buyer_address`, `seller_name`, `seller_address`, `requester_name`, `department`,
`payment_purpose`, `currency`, `items[]` (`item_code`, `description`, `quantity`, `unit`,
`unit_price`, `amount`), `subtotal_amount`, `vat_rate`, `vat_amount`, `total_amount`,
`requested_payment_amount`, `bank_beneficiary` (`account_name`, `account_number`, `bank_name`),
`due_date`, `approval_status`.

| Quy tắc | Tên | Mức khi fail | Nội dung kiểm tra |
|---|---|---|---|
| R0 | RULE_MISSING_DOCUMENT | HIGH | Đủ 3/3 chứng từ PO, Invoice, PR |
| R1 | RULE_PO_INVOICE_REF_MATCH | HIGH | Invoice/PR tham chiếu đúng số PO |
| R2 | RULE_BENEFICIARY_FRAUD_CHECK | CRITICAL | Tài khoản thụ hưởng PR khớp tài khoản pháp nhân bên bán |
| R3 | RULE_LINE_ITEM_MATH_INTERNAL | HIGH | `quantity × unit_price == amount` (sai số ≤ 1 VND) |
| R4 | RULE_SUBTOTAL_VAT_TOTAL_INTERNAL | HIGH | `subtotal + VAT == total`, `sum(items) == subtotal` |
| R5 | RULE_ITEM_QUANTITY_MATCH | HIGH | Số lượng trên Invoice không vượt PO |
| R6 | RULE_ITEM_PRICE_MATCH | HIGH | Đơn giá trên Invoice không vượt PO |
| R7 | RULE_TOTAL_AMOUNT_MATCH | HIGH | Invoice ≤ PO; PR == Invoice |
| R8 | RULE_SELLER_NAME_SIMILARITY | MEDIUM | Tên bên bán nhất quán (BGE-M3) |
| R9 | RULE_BUYER_NAME_SIMILARITY | MEDIUM | Tên bên mua nhất quán (BGE-M3) |
| R10 | RULE_ADDRESS_CONSISTENCY | LOW | Địa chỉ nhất quán giữa PO và Invoice |
| R11 | RULE_DATE_CHRONOLOGY | MEDIUM | Trình tự `PO ≤ Invoice ≤ PR` và hạn thanh toán |
| R12 | RULE_APPROVAL_STATUS | MEDIUM | PO/PR đã phê duyệt xong |

**Kết luận (verdict)**: có CRITICAL hoặc HIGH → `REJECTED`; chỉ có MEDIUM → `WARNING`; còn lại → `PASSED`.

## 6. Giao diện người dùng

- **Tải lên bộ chứng từ**: kéo thả nhiều tệp PDF/ảnh, có ô nhập **số hoá đơn / tên chứng từ**,
  thanh tiến độ tải lên và trạng thái "Đang trích xuất dữ liệu và đối soát…".
- **Cảnh báo rủi ro**: danh sách vi phạm, phân trang **3 mục mỗi trang**, có nút "Trang trước /
  Trang sau" và chấm mực trang.
- **Điều hướng tới ô lỗi**: bấm một cảnh báo sẽ tự động chuyển đúng tab và cuộn đến các ô dữ liệu
  liên quan trong ma trận 3 cột, đồng thời làm nhấp nháy để dễ nhận biết. Ánh xạ rule → ô được quản
  lý tập trung trong `RULE_HIGHLIGHT` (`audit_pipeline.py`), backend là nguồn duy nhất.
- **Màu mức rủi ro ô dữ liệu**: CRITICAL/HIGH/MEDIUM/INFO tương ứng 4 mức tô sáng khác nhau.
- **Màn hình lịch sử**: liệt kê các batch đã kiểm toán, mở lại được kết quả cũ.
- **Thông báo lỗi AI thân thiện**: khi OpenRouter giới hạn tốc độ (HTTP 429), giao diện hiện dòng
  thông báo tiếng Việt dễ hiểu thay vì đổ nguyên payload JSON kỹ thuật.

## 7. Kiểm thử

```powershell
cd backend
$env:PYTHONPATH = "."
$env:DISABLE_BGE = "1"        # bỏ qua tải BGE-M3 (~2.2GB), dùng token ratio
python -m pytest tests -q     # 10 unit test cho R0-R12
python scripts\smoke_offline.py   # chạy parser + audit trên 3 tệp Sample, kỳ vọng REJECTED
```

```powershell
cd frontend
npm run build                # kiểm tra build production
```

Bộ sample cố ý fail:

- **R2** – tài khoản thụ hưởng `888800009917` / `NGUYEN VAN PHU` khác tài khoản bên bán `888800001042`
- **R3** – dòng `HDMI-2`: `20 × 150000 = 3200000` sai số học
- **R5** – `DOCK-C` trên Invoice ghi 12, trên PO ghi 10
- **R7** – PO `52.250.000` ≠ Invoice `55.220.000` ≠ PR `57.220.000`
- **R12** – Payment Request còn trạng thái `Pending`

## 8. Bảo mật

- **Không commit `.env`** — file này nằm trong `.gitignore` (cả `.gitignore` ở thư mục gốc và trong `backend/`).
- `backend/.env.example` chỉ chứa **giá trị rỗng**, không có API key thật.
- Nếu bạn từng nhập key vào `.env.example`, hãy đặt lại (revoke) key đó trên
  https://openrouter.ai/settings/keys vì key đã bị lộ trong lịch sử Git.
- File `backend/storage/` và `app.db` cũng được ignore.

## 9. Ghi chú đánh giá

- Repo ưu tiên tính đúng đắn và giải thích được quyết định kỹ thuật: 13 quy tắc kiểm toán chạy bằng
  code thuần lập luận, có docstring giải thích từng bước so sánh.
- Toàn bộ nội dung hiển thị trên giao diện dùng tiếng Việt **có đầy đủ dấu**.
- Prompt trích xuất yêu cầu mô hình giữ nguyên tiếng Việt có dấu trong tên công ty, địa chỉ và mô tả
  hàng hoá để dữ liệu trích xuất không bị mất dấu.
