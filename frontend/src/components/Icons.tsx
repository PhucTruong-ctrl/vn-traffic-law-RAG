type IconProps = { size?: number; className?: string };
const base = { fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
export function PlusIcon({size=18,className}:IconProps){return <svg className={className} width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" {...base}><path d="M12 5v14M5 12h14"/></svg>}
export function SearchIcon({size=18,className}:IconProps){return <svg className={className} width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" {...base}><circle cx="11" cy="11" r="6.5"/><path d="m16 16 4 4"/></svg>}
export function BookIcon({size=18,className}:IconProps){return <svg className={className} width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" {...base}><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H11v16H6.5A2.5 2.5 0 0 0 4 21.5zM20 5.5A2.5 2.5 0 0 0 17.5 3H13v16h4.5a2.5 2.5 0 0 1 2.5 2.5z"/></svg>}
export function PanelIcon({size=18,className}:IconProps){return <svg className={className} width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" {...base}><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16"/></svg>}
export function SendIcon({size=18,className}:IconProps){return <svg className={className} width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" {...base}><path d="m12 19V5m-6 6 6-6 6 6"/></svg>}
export function ChevronDownIcon({size=16,className}:IconProps){return <svg className={className} width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" {...base}><path d="m7 10 5 5 5-5"/></svg>}
