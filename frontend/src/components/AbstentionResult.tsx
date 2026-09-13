import React from "react";

export type AbstentionResultProps = {
  status?:
    | "GREETING"
    | "OUT_OF_SCOPE"
    | "CORPUS_NOT_COVERED"
    | "INSUFFICIENT_EVIDENCE"
    | "WORKFLOW_UNAVAILABLE";
  reason?: string | null;
  reasonCode?: string | null;
  disclaimer?: string | null;
};

const COPY = {
  GREETING: {
    eyebrow: "TRỢ LÝ VNLAW",
    title: "Bạn muốn tra cứu nội dung nào?",
    reason: "Hãy đặt câu hỏi cụ thể về pháp luật giao thông Việt Nam.",
    action: "Ví dụ: Mức phạt khi vượt đèn đỏ là bao nhiêu?",
  },
  OUT_OF_SCOPE: {
    eyebrow: "NGOÀI PHẠM VI DỮ LIỆU",
    title: "Câu hỏi nằm ngoài phạm vi tra cứu",
    reason: "VNLAW hiện chỉ tra cứu pháp luật giao thông Việt Nam.",
    action: "Hãy đặt lại câu hỏi về quy định, hành vi vi phạm hoặc mức phạt giao thông.",
  },
  CORPUS_NOT_COVERED: {
    eyebrow: "NGOÀI PHẠM VI DỮ LIỆU",
    title: "Dữ liệu hiện tại chưa bao phủ nội dung này",
    reason: "Kho văn bản đã lập chỉ mục chưa có nguồn phù hợp để trả lời.",
    action: "Thử nêu số văn bản, điều khoản hoặc tình huống giao thông cụ thể hơn.",
  },
  INSUFFICIENT_EVIDENCE: {
    eyebrow: "KHÔNG ĐỦ CĂN CỨ",
    title: "Chưa đủ căn cứ để kết luận",
    reason: "Nguồn tìm được chưa đủ để đưa ra kết luận chắc chắn.",
    action: "Bổ sung tình tiết, loại phương tiện, thời điểm hoặc điều khoản cần tra cứu.",
  },
  WORKFLOW_UNAVAILABLE: {
    eyebrow: "DỊCH VỤ TẠM GIÁN ĐOẠN",
    title: "Không thể hoàn tất đối chiếu nguồn",
    reason: "Dịch vụ tra cứu hoặc đối chiếu nguồn hiện chưa sẵn sàng.",
    action: "Thử lại sau vài giây. Nếu lỗi tiếp diễn, mở cuộc trò chuyện mới.",
  },
} as const;

export default function AbstentionResult({
  status = "INSUFFICIENT_EVIDENCE",
  reason,
  reasonCode,
  disclaimer,
}: AbstentionResultProps) {
  const copy = COPY[status];
  return (
    <section
      className="abstention-result alert warning motion-entrance"
      role="status"
      aria-live="polite"
    >
      <div className="abstention-result__header">
        <span className="abstention-result__eyebrow">{copy.eyebrow}</span>
        <h3>{copy.title}</h3>
      </div>
      <p className="abstention-result__reason">{reason || copy.reason}</p>
      {reasonCode && (
        <p className="abstention-result__code">
          <span>Mã lý do:</span> <code>{reasonCode}</code>
        </p>
      )}
      <p className="abstention-result__disclaimer">{disclaimer || copy.action}</p>
    </section>
  );
}
