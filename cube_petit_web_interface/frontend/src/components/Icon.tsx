// Google Material Symbols(絵文字ではなくアイコンフォントを使う。index.htmlでフォント読み込み済み)
// https://fonts.google.com/icons からアイコン名をそのまま渡す(例: "swap_horiz", "battery_full", "map")
export function Icon({ name, size = 20, style }: { name: string; size?: number; style?: React.CSSProperties }) {
  return (
    <span
      className="material-symbols-outlined"
      style={{ fontSize: size, ...style }}
    >
      {name}
    </span>
  );
}
