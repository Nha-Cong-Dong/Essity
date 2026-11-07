// Demo data of the landing knowledge graph. LANDING-V62-FIX: a fuller, rounder cluster (about 45 notes) drawn like a
// vault graph view: ring nodes sized by how connected they are, a few accent nodes, a tiny label under every node.
export const GRAPH_HUBS = ["Vật lý", "Sinh học", "Đời sống"];
export const GRAPH_CARDS: Array<[number, string, string]> = [
      [0, "Bầu trời màu xanh", "Ánh sáng xanh bị không khí tán xạ mạnh nhất."], [0, "Hiệu ứng Mpemba", "Nước nóng đôi khi đóng băng nhanh hơn nước lạnh."],
      [0, "Định luật Bernoulli", "Dòng khí chảy nhanh thì áp suất thấp: cánh máy bay được nâng lên."], [0, "E = mc²", "Khối lượng và năng lượng là hai mặt của một thứ."],
      [0, "Cầu vồng", "Ánh sáng trắng bị giọt nước tách thành các màu."], [0, "Âm thanh cần môi trường", "Trong chân không không có tiếng động."],
      [1, "Bạch tuộc có 3 trái tim", "Hai tim bơm máu qua mang, một tim nuôi cơ thể."], [1, "Sứa bất tử", "Turritopsis dohrnii có thể trẻ lại."],
      [1, "Tim cá voi xanh", "Nặng cỡ một chiếc xe nhỏ."], [1, "Chuối là quả mọng", "Về thực vật học, dâu tây thì không."],
      [1, "Mắt bạch tuộc", "Không có điểm mù như mắt người."],
      [2, "Mật ong không bao giờ hỏng", "Ít nước, độ axit cao: vi khuẩn không sống nổi."], [2, "Muối làm tan băng", "Muối hạ điểm đóng băng của nước."],
      [2, "Kim tự tháp Giza", "Xây cách đây khoảng 4.500 năm."], [2, "Cà phê và đàn dê", "Truyền thuyết người chăn dê ở Ethiopia."], [2, "Vân tay lưỡi", "Mỗi người một khác."],
      [0, "Lực hấp dẫn", "Mọi vật có khối lượng đều hút nhau."], [0, "Quán tính", "Vật giữ nguyên chuyển động nếu không bị tác động."],
      [0, "Khúc xạ", "Ánh sáng đổi hướng khi qua môi trường khác."], [0, "Từ trường", "Vùng không gian quanh nam châm có lực từ."],
      [0, "Nhiệt dung", "Nước cần nhiều nhiệt để nóng lên."], [0, "Sóng âm", "Âm thanh là sóng cơ truyền qua vật chất."],
      [0, "Ma sát", "Lực cản khi hai bề mặt trượt lên nhau."], [0, "Áp suất khí quyển", "Không khí cũng có trọng lượng."],
      [1, "Tế bào", "Đơn vị nhỏ nhất của sự sống."], [1, "ADN", "Mã di truyền xoắn kép."],
      [1, "Quang hợp", "Cây biến ánh sáng thành đường."], [1, "Hô hấp tế bào", "Tế bào đốt đường để lấy năng lượng."],
      [1, "Tiến hóa", "Chọn lọc tự nhiên qua nhiều thế hệ."], [1, "Hệ thần kinh", "Mạng truyền tín hiệu của cơ thể."],
      [1, "Enzym", "Chất xúc tác của phản ứng sống."], [1, "San hô", "Động vật xây nên rạn đá ngầm."],
      [2, "Giấc ngủ", "Não dọn dẹp và củng cố trí nhớ khi ngủ."], [2, "Caffeine", "Chặn tín hiệu buồn ngủ trong não."],
      [2, "Trà xanh", "Giàu chất chống oxy hóa."], [2, "Bánh mì", "Men nở nhờ khí CO₂."],
      [2, "Nước sôi", "Sôi ở 100 °C khi ở mực nước biển."], [2, "Thời tiết", "Hơi nước ngưng tụ thành mây."],
      [2, "Gốm sứ", "Đất sét nung ở nhiệt độ cao."], [2, "Lửa", "Cháy cần nhiên liệu, oxy và nhiệt."],
      [2, "Sô-cô-la", "Làm từ hạt ca cao lên men."], [2, "Đường ray", "Khe hở để thép nở ra khi nóng."],
      [1, "Vi khuẩn", "Có mặt khắp nơi, phần lớn vô hại."],
];
// The original thirteen links of the mockup, then the links of the added notes (indices into GRAPH_CARDS).
const BASE_RELATIONS: Array<[number, number]> = [[0, 4], [1, 12], [2, 3], [0, 5], [6, 8], [6, 10], [7, 9], [11, 12], [13, 15], [14, 9], [1, 11], [3, 5], [8, 7]];
const MORE_RELATIONS: Array<[number, number]> = [
  // Vật lý
  [16, 17], [16, 3], [17, 22], [18, 4], [18, 0], [19, 5], [19, 3], [20, 1], [21, 5], [21, 19], [22, 23], [23, 2], [2, 16], [20, 23], [17, 21], [18, 19],
  // Sinh học
  [24, 25], [24, 26], [25, 31], [26, 27], [27, 30], [28, 29], [28, 8], [29, 6], [30, 31], [31, 7], [42, 24], [42, 9], [10, 29], [9, 26], [25, 28],
  // Đời sống
  [32, 33], [32, 14], [33, 14], [33, 12], [34, 33], [34, 32], [35, 38], [36, 11], [37, 36], [38, 39], [39, 41], [40, 41], [41, 36], [35, 34], [15, 40], [13, 37], [12, 38], [11, 35],
  // across the three subjects: the few long links that make it one map
  [20, 36], [18, 37], [4, 37], [32, 29], [33, 29], [35, 30], [41, 20], [34, 26],
];
export const GRAPH_RELATIONS: Array<[number, number]> = [...BASE_RELATIONS, ...MORE_RELATIONS];

export type GraphNode = { id: string; name: string; tip?: string; hub: boolean; hubOf?: number; degree: number; r: number; accent: string };
export type GraphLink = { a: number; b: number; own: boolean };

/** Ring-node radius: a hub is the biggest, the rest grow with their number of links (centrality), capped so the cluster stays calm. */
export function nodeRadius(degree: number, hub: boolean): number {
  return hub ? 11 + Math.min(degree, 20) * 0.3 : 3.6 + Math.min(Math.sqrt(degree), 3.4) * 1.5;
}

/** Nodes (3 hubs first, then the cards) and links (card -> its hub, then the relations), with degree, radius and the few accent nodes. */
export function graphModel(): { nodes: GraphNode[]; links: GraphLink[] } {
  const hubN = GRAPH_HUBS.length;
  const links: GraphLink[] = GRAPH_CARDS.map((c, i) => ({ a: hubN + i, b: c[0], own: true })).concat(
    GRAPH_RELATIONS.map(([a, b]) => ({ a: hubN + a, b: hubN + b, own: false })),
  );
  const degree = new Array<number>(hubN + GRAPH_CARDS.length).fill(0);
  links.forEach((l) => {
    degree[l.a]++;
    degree[l.b]++;
  });
  const nodes: GraphNode[] = [
    ...GRAPH_HUBS.map((name, i): GraphNode => ({ id: "h" + i, name, hub: true, degree: degree[i], r: nodeRadius(degree[i], true), accent: "" })),
    ...GRAPH_CARDS.map((c, i): GraphNode => ({ id: "c" + i, name: c[1], tip: c[2], hub: false, hubOf: c[0], degree: degree[hubN + i], r: nodeRadius(degree[hubN + i], false), accent: "" })),
  ];
  // accents: the "next up" card (teal) and the two best-connected cards after it (rose, gold)
  nodes[hubN].accent = "teal";
  const rest = nodes.map((n, i) => ({ n, i })).filter(({ n, i }) => !n.hub && i !== hubN).sort((x, y) => y.n.degree - x.n.degree || x.i - y.i);
  if (rest[0]) rest[0].n.accent = "gold";
  if (rest[1]) rest[1].n.accent = "rose";
  return { nodes, links };
}

/** Home positions in the unit disc (x, y in -1..1): the three hubs on a triangle, each hub with its own round lobe of cards (a sunflower
 *  spiral, the best-connected nearest the hub), so the lobes merge into one full, round cluster and most links stay short.
 *  The motion layer only relaxes overlaps. */
export function graphLayout(nodes: GraphNode[]): Array<{ x: number; y: number }> {
  const hubN = nodes.filter((n) => n.hub).length;
  const out = new Array<{ x: number; y: number }>(nodes.length);
  const hubPos = nodes.slice(0, hubN).map((_, i) => {
    const a = (-90 + (360 / hubN) * i) * (Math.PI / 180);
    return { x: Math.cos(a) * 0.4, y: Math.sin(a) * 0.4 };
  });
  hubPos.forEach((p, i) => (out[i] = p));
  for (let h = 0; h < hubN; h++) {
    const mine = nodes.map((n, i) => ({ n, i })).filter(({ n }) => !n.hub && n.hubOf === h).sort((a, b) => b.n.degree - a.n.degree || a.i - b.i);
    mine.forEach(({ i }, k) => {
      const rad = Math.sqrt((k + 0.9) / (mine.length + 0.4)) * 0.56;
      const ang = k * 2.39996 + h * 1.7;
      let x = hubPos[h].x + Math.cos(ang) * rad;
      let y = hubPos[h].y + Math.sin(ang) * rad;
      const d = Math.hypot(x, y);
      if (d > 0.97) {
        x = (x / d) * 0.97;
        y = (y / d) * 0.97;
      }
      out[i] = { x, y };
    });
  }
  return out;
}
