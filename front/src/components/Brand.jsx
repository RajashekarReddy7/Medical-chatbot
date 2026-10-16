import { Activity } from "lucide-react";

export default function Brand({ onClick }) {
  return (
    <span className="brand" onClick={onClick} style={onClick ? { cursor: "pointer" } : undefined}>
      <span className="brand-mark"><Activity size={19} strokeWidth={2.4} /></span>
      Care Companion
    </span>
  );
}
