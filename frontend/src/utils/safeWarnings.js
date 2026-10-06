/**
 * Chuẩn hoá cảnh báo trích xuất trước khi hiển thị.
 * - Chặn hoàn toàn nội dung lỗi kỹ thuật thô (HTTP 429, JSON của OpenRouter,
 *   "Hết số lần retry", "Het so lan retry"...) lọt lên giao diện.
 * - Chỉ giữ thông điệp tiếng Việt ngắn gọn, đầy đủ dấu.
 */
export function sanitizeWarnings(warnings) {
  const list = Array.isArray(warnings) ? warnings : warnings ? [warnings] : []
  const out = []
  for (const raw of list) {
    const text = String(raw ?? "")
    const low = text.toLowerCase()
    const isRawTech =
      low.includes("http 429") ||
      low.includes("429") && (low.includes("retry") || low.includes("rate-limit") || low.includes("rate limit")) ||
      low.includes("het so lan retry") ||
      low.includes("hết số lần retry") ||
      low.includes("provider returned error") ||
      low.includes("openrouter") && low.includes("{") ||
      low.includes('"error"') ||
      low.includes("upstream_provider") ||
      low.includes("remedy_hint") ||
      /google\/gemma-4-\S+:.*http/i.test(text)
    if (isRawTech) {
      if (!out.includes("RATE_LIMITED")) out.push("RATE_LIMITED")
      continue
    }
    // Cắt ngắn các warning quá dài nhưng vẫn giữ nội dung có ích.
    const short = text.length > 220 ? `${text.slice(0, 220).trim()}…` : text
    if (short && !out.includes(short)) out.push(short)
  }
  return out.map((w) =>
    w === "RATE_LIMITED"
      ? "AI trích xuất tạm thời bị giới hạn tốc độ (HTTP 429). Hệ thống đã tự động dùng bộ phân tích dự phòng cục bộ, vui lòng kiểm tra lại số liệu bằng mắt."
      : w
  )
}
