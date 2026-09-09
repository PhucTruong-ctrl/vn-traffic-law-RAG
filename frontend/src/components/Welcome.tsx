import type { CSSProperties, FormEvent } from "react";
import Composer from "./Composer";
import LegalMark from "./LegalMark";
type WelcomeProps = {
  question: string;
  suggestions: string[];
  onQuestion: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
};
export default function Welcome({ question, suggestions, onQuestion, onSubmit }: WelcomeProps) {
  return (
    <div className="welcome welcome--enter">
      <LegalMark className="welcome-mark welcome-enter__item" />
      <h1 className="welcome-enter__item">Hỏi đáp pháp luật giao thông</h1>
      <p className="welcome-enter__item">
        Hỏi rõ điều bạn cần biết. Mỗi câu trả lời đều kèm căn cứ để kiểm tra.
      </p>
      <div className="welcome-enter__item">
        <Composer id="question" value={question} hero onChange={onQuestion} onSubmit={onSubmit} />
      </div>
      <div className="prompt-chips welcome-enter__item" aria-label="Gợi ý">
        {suggestions.map((item, index) => (
          <button
            style={{ "--chip-delay": `${index * 55}ms` } as CSSProperties}
            type="button"
            onClick={() => onQuestion(item)}
          >
            {item}
          </button>
        ))}
      </div>
    </div>
  );
}
