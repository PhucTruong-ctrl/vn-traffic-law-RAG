import React from "react";

export type AbstentionResultProps = {
  reason?: string | null;
  reasonCode?: string | null;
  disclaimer?: string | null;
};

export default function AbstentionResult({
  reason,
  reasonCode,
  disclaimer,
}: AbstentionResultProps) {
  return (
    <section
      className="abstention-result alert warning motion-entrance"
      role="status"
      aria-labelledby="abstention-title"
    >
      <div className="abstention-result__header">
        <span className="abstention-result__eyebrow">LƯU Ý VỀ CĂN CỨ</span>
        <h3 id="abstention-title">Chưa đủ căn cứ để kết luận</h3>
      </div>
      <p className="abstention-result__reason">
        {reason || "Không thể đưa ra kết luận chắc chắn cho câu hỏi này."}
      </p>
      {reasonCode && (
        <p className="abstention-result__code">
          <span>Mã lý do:</span> <code>{reasonCode}</code>
        </p>
      )}
      <p className="abstention-result__disclaimer">
        {disclaimer || "Hãy bổ sung tình tiết hoặc tham khảo cơ quan có thẩm quyền."}
      </p>
    </section>
  );
}
