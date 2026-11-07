// Forgetting curve of the FSRS demo (landing v6.1): retrievability r = exp(-t / S) between reviews, the stability S
// grows after every review. Pure geometry in a 900 x 300 viewBox, so it renders on the server and is easy to test.
const STABILITY = [160, 340, 720, 1500];
const WIDTH = 900;
const y = (r: number) => 30 + ((1 - r) / 0.4) * 230;

export function fsrsCurve() {
  const reviews = [0];
  for (let i = 0; i < STABILITY.length - 1; i++) reviews.push(reviews[i] + STABILITY[i] * 0.357);
  let d = "";
  for (let i = 0; i < reviews.length; i++) {
    const from = reviews[i];
    const to = i < reviews.length - 1 ? reviews[i + 1] : WIDTH;
    for (let x = from; x <= to; x += 4) d += `${d ? "L" : "M"}${x.toFixed(1)} ${y(Math.exp(-(x - from) / STABILITY[i])).toFixed(1)}`;
  }
  // the deepest point right before the third review: the "review just as it is about to fade" moment the demo circles
  const trough = { x: Number(reviews[3].toFixed(2)), y: Number(y(Math.exp(-(reviews[3] - reviews[2]) / STABILITY[2])).toFixed(2)) };
  return { d, trough, dots: reviews.slice(1).map((x) => Number(x.toFixed(2))), y1: y(1), width: WIDTH };
}
