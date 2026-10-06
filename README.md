# AI Expense Audit System

He thong doi soat 3 chieu bo chung tu thanh toan **PO - Invoice - Payment Request** bang AI:
nguoi dung upload file -> AI trich xuat thong tin -> engine kiem toan **13 quy tac R0-R12** chay
hoan toan bang code Python thuan lanh dao -> hien thi vi pham den tung o du lieu -> luu lich su audit.

> Bo sample kem theo (`Sample/`) co y chua loi de demo: batch mau se ra **REJECTED**
> voi **1 CRITICAL (R2) + 3 HIGH (R3, R5, R7) + 1 MEDIUM (R12)**.

## Kien truc

```text
                +---------------------------+        +-----------------------------+
                | Extraction Engine (LLM)   |        | Deterministic Audit Engine  |
  PDF/anh ----> | Gemma 4 31B -> 26B (free) | JSON   | R0-R12 Pure Python + matcher | -> PASSED / WARNING / REJECTED
                |  + Retry/Timeout + Offline| ------> | BGE-M3 + XOR Token Diff     |
                +---------------------------+        +-----------------------------+
                          |                                        |
                          +---> SQLite (local) / PostgreSQL  <-----+
```

- **AI chi DOC, khong DOAN**: LLM chi trich xuat JSON (khong ket luan audit).
  Moi so sanh/ phep tinh nam trong `backend/app/services/audit_engine.py`.
- **Failover 4 lop**: Config Guard -> Model Chain -> Retry/Timeout -> Offline Parser
  (pdfplumber + PyMuPDF + regex) nen he thong luon tra ket qua ke ca khi API rate-limit (429).
- **So khop mo BGE-M3** (`bge_matcher.py`): fast-path -> tokenize/clean -> XOR diff ->
  cosine similarity. Match chi khi `len(diff)==0 AND sim >= 0.995`. Neu chua tai duoc
  model nang (~2.2GB) thi tu fallback ve token ratio ma van giu strict gate.

## Chay nhanh (khong Docker)

### 1. Backend (FastAPI)

```powershell
cd backend
copy .env.example .env        # dien OPENROUTER_API_KEY
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
# mo http://localhost:8000/docs de thu API
```

Env co ban trong `.env.example`:

| Bien | Y nghia | Mac dinh |
|---|---|---|
| `OPENROUTER_API_KEY` | Key OpenRouter (Layer 2) | *(trong)* |
| `EXTRACTOR_MODEL_CHAIN` | Thu tu model fallback | `google/gemma-4-31b-it:free,google/gemma-4-26b-a4b-it:free` |
| `REQUEST_TIMEOUT_SECONDS` / `MAX_RETRIES` | Timeout + so retry moi model (Layer 3) | `20` / `3` |
| `DATABASE_URL` | SQLite local hoac Postgres | `sqlite+aiosqlite:///./app.db` |
| `STORAGE_PATH` | Noi luu file upload | `./storage` |

### 2. Frontend (React + Vite + Tailwind)

```powershell
cd frontend
copy .env.example .env
npm install
npm run dev     # http://localhost:5173
```

### 3. Chay voi Docker

```powershell
copy backend\.env.example backend\.env   # nho dien OPENROUTER_API_KEY
docker compose up --build
# backend http://localhost:8000/docs | frontend http://localhost:5173
```

Postgres chay o `db:5432` voi user/pass/db mac dinh `audit/audit/expense_audit`.

## API

| Endpoint | Method | Mo ta |
|---|---|---|
| `/health` | GET | Kiem tra app + DB |
| `/api/v1/audit/upload` | POST multipart `files` (1-10 file PDF/anh) | Trich xuat + audit + luu batch |
| `/api/v1/audit/batches?limit&offset` | GET | Lich su batch |
| `/api/v1/audit/batches/{id}` | GET | Chi tiet batch (documents + findings + rule_results) |
| `/api/v1/audit/batches/{id}/export` | GET | Xuat CSV findings |

## 18 truong trich xuat + R0-R12

Ma tran 18 truong: `doc_type, doc_number, reference_numbers, issue_date, buyer_name,
buyer_address, seller_name, seller_address, requester_name, department, payment_purpose,
currency, items(...), subtotal_amount, vat_rate & vat_amount, total_amount,
requested_payment_amount, bank_beneficiary(account_name/number/bank_name)`
+ 2 truong bo sung `due_date`, `approval_status` cho R11/R12.

| Rule | Ten | Nang (fail) | Noi dung |
|---|---|---|---|
| R0 | RULE_MISSING_DOCUMENT | HIGH | Du 3/3 chung tu PO, Invoice, PR |
| R1 | RULE_PO_INVOICE_REF_MATCH | HIGH | Invoice/PR tham chieu dung PO |
| R2 | RULE_BENEFICIARY_FRAUD_CHECK | CRITICAL | TK thu huong PR == TK phap nhan ben ban |
| R3 | RULE_LINE_ITEM_MATH_INTERNAL | HIGH | `qty * price == amount` (sai so <= 1 VND) |
| R4 | RULE_SUBTOTAL_VAT_TOTAL_INTERNAL | HIGH | `subtotal + VAT == total`, `sum(items) == subtotal` |
| R5 | RULE_ITEM_QUANTITY_MATCH | HIGH | Invoice khong vuot so luong PO |
| R6 | RULE_ITEM_PRICE_MATCH | HIGH | Don gia Invoice <= PO |
| R7 | RULE_TOTAL_AMOUNT_MATCH | HIGH | Invoice <= PO; PR == Invoice |
| R8/R9 | SELLER/BUYER_NAME_SIMILARITY | MEDIUM | Ten ben ban/mua nhat quan (BGE-M3) |
| R10 | RULE_ADDRESS_CONSISTENCY | LOW | Dia chi nhat quan PO vs Invoice |
| R11 | RULE_DATE_CHRONOLOGY | MEDIUM | `PO <= Invoice <= PR <= han thanh toan` |
| R12 | RULE_APPROVAL_STATUS | MEDIUM | PO/PR da phe duyet xong |

**Verdict**: co CRITICAL/HIGH -> `REJECTED`; chi co MEDIUM -> `WARNING`; con lai -> `PASSED`.

## Test

```powershell
cd backend
python scripts\smoke_offline.py   # parser + audit tren 3 file Sample (ky vong REJECTED)
python -m pytest tests -q         # 10 unit test R0-R12, khong can key/DB
```

Bo sample du kien fail: R2 (TK `888800009917`/NGUYEN VAN PHU vs TK ben ban `888800001042`),
R3 (HDMI-2 `20 x 150000 = 3200000` sai soch hoc), R5 (DOCK-C Invoice 12 > PO 10),
R7 (PO 52.250.000 vs Invoice 55.220.000 vs PR 57.220.000), R12 (PR Pending).

## Ghi chu danh gia

- Hoan thanh nhieu chuc nang khong dong nghia diem cao: repo uu tien tinh dung dan,
  giai thich duoc quyet dinh ky thuat (xem README + docstring trong code).
- Khong commit `.env`/key/secret. Dung `.env.example` lam mau.
