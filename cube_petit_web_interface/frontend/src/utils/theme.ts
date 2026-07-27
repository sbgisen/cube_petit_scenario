// Canvas 2D の fillStyle/strokeStyle は CSS の var() 構文を解釈できないため、
// canvas描画で「接続中ロボットの色」を使いたい箇所は、これで実際の色を解決してから渡す。
export function getAccentColor(): string {
  const v = getComputedStyle(document.documentElement).getPropertyValue('--t-accent').trim();
  return v || '#ff6600';
}
