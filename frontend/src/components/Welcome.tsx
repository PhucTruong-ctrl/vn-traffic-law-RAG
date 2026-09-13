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
      <div className="welcome-kicker welcome-enter__item">VNLAW</div>
      <h1 className="welcome-enter__item">
        Tra cứu pháp luật
        <span>giao thông Việt Nam</span>
      </h1>
      <p className="welcome-enter__item">
        Hỏi theo tình huống thực tế. Câu trả lời được đối chiếu với nguồn pháp luật trong hệ thống.
      </p>
      <div className="welcome-enter__item">
        <Composer id="question" value={question} hero onChange={onQuestion} onSubmit={onSubmit} />
      </div>
      <div className="prompt-chips welcome-enter__item" role="group" aria-label="Gợi ý">
        {suggestions.map((item, index) => (
          <button
            key={item}
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
