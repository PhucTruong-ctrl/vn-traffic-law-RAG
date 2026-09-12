import { BookOpen, ChevronDown, PanelLeft, Plus, Search, Send } from "lucide-react";
import type { LucideProps } from "lucide-react";

type IconProps = Pick<LucideProps, "size" | "className">;

export function PlusIcon({ size = 18, className }: IconProps) {
  return <Plus size={size} className={className} aria-hidden="true" />;
}

export function SearchIcon({ size = 18, className }: IconProps) {
  return <Search size={size} className={className} aria-hidden="true" />;
}

export function BookIcon({ size = 18, className }: IconProps) {
  return <BookOpen size={size} className={className} aria-hidden="true" />;
}

export function PanelIcon({ size = 18, className }: IconProps) {
  return <PanelLeft size={size} className={className} aria-hidden="true" />;
}

export function SendIcon({ size = 18, className }: IconProps) {
  return <Send size={size} className={className} aria-hidden="true" />;
}

export function ChevronDownIcon({ size = 16, className }: IconProps) {
  return <ChevronDown size={size} className={className} aria-hidden="true" />;
}
