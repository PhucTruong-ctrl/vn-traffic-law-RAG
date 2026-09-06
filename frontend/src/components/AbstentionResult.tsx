import React from "react";

export type AbstentionResultProps = {
  reason?: string | null;
  reasonCode?: string | null;
  disclaimer?: string | null;
};

export default function AbstentionResult({ reason, reasonCode, disclaimer }: AbstentionResultProps) {
  return (
    <div className="alert warning" role="status" aria-labelledby="abstention-title">
      <h3 id="abstention-title">Chưa đủ căn cứ để kết luận</h3>
      <p>{reason || "Không thể đưa ra kết luận chắc chắn cho câu hỏi này."}</p>
      {reasonCode && <p>Mã lý do: <code>{reasonCode}</code></p>}
      <p>{disclaimer || "Hãy bổ sung tình tiết hoặc tham khảo cơ quan có thẩm quyền."}</p>
    </div>
  );
}
