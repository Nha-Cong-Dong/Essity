import type { EdgeKind, GraphCard, GraphData, GraphEdge, GraphSection } from "@/lib/graph";
import { EDGE_KINDS } from "@/lib/graph";

// T9.10a: fixed data for /design-preview/graph. T9.10 replaces it with the T9.9 data endpoint.
// Shapes mirror core_api/domain/graph.py (EdgeKind, evidence quoted from both cards' anchors).

export type GraphState = "empty" | "few" | "many" | "filtered" | "selected" | "long" | "loading" | "error";
export const GRAPH_STATE_IDS: GraphState[] = ["empty", "few", "many", "filtered", "selected", "long", "loading", "error"];

export const SUBJECT_NAME = "Mạng máy tính";

const SECTIONS: GraphSection[] = [
  { id: "ch1", title: "Chương 1. Tầng giao vận", parentId: null },
  { id: "ch1-1", title: "1.1 Giao thức TCP", parentId: "ch1" },
  { id: "ch1-2", title: "1.2 Giao thức UDP", parentId: "ch1" },
  { id: "ch2", title: "Chương 2. Tầng mạng", parentId: null },
  { id: "ch2-1", title: "2.1 Địa chỉ IP", parentId: "ch2" },
];

function card(id: string, title: string, sectionId: string, body: string, quote: string, neededBy: string[] = []): GraphCard {
  return { id, title, body, sectionId, anchors: [{ id: `${id}-a`, label: `Slide ${id.slice(1)}`, quote }], neededBy };
}
const edge = (id: string, kind: EdgeKind, from: string, to: string, evidence: string): GraphEdge => ({
  id, kind, from, to, evidence,
});

const FEW_CARDS: GraphCard[] = [
  card("c1", "Bắt tay ba bước", "ch1-1", "Client gửi SYN, server trả SYN-ACK, client gửi ACK để mở kết nối TCP.", "Kết nối TCP được thiết lập bằng bắt tay ba bước.", ["Vì sao TCP cần bắt tay ba bước?"]),
  card("c2", "Số thứ tự và xác nhận", "ch1-1", "Mỗi byte có số thứ tự; bên nhận gửi ACK cho byte tiếp theo mong đợi.", "ACK mang số thứ tự của byte tiếp theo mà bên nhận mong đợi."),
  card("c3", "Điều khiển luồng", "ch1-1", "Bên nhận báo cửa sổ nhận để bên gửi không làm tràn bộ đệm.", "Cửa sổ nhận cho bên gửi biết còn bao nhiêu chỗ trong bộ đệm."),
  card("c4", "Truyền lại khi mất gói", "ch1-1", "Hết thời gian chờ ACK thì bên gửi truyền lại đoạn tin.", "Nếu hết thời gian chờ mà chưa có ACK, đoạn tin được truyền lại."),
  card("c5", "UDP không kết nối", "ch1-2", "UDP gửi gói rời, không bắt tay, không đảm bảo thứ tự.", "UDP không thiết lập kết nối và không đảm bảo thứ tự."),
];
const FEW_EDGES: GraphEdge[] = [
  edge("e1", "prerequisite", "c1", "c2", "Sau khi kết nối mở, mỗi byte được đánh số thứ tự."),
  edge("e2", "prerequisite", "c2", "c4", "Số thứ tự cho biết đoạn nào cần truyền lại."),
  edge("e3", "part_of", "c3", "c1", "Cửa sổ nhận được thông báo ngay từ đoạn SYN đầu tiên."),
  edge("e4", "contrast", "c1", "c5", "TCP bắt tay trước khi gửi; UDP gửi ngay không bắt tay."),
  edge("e5", "applies_to", "c4", "c3", "Truyền lại phải tôn trọng cửa sổ nhận hiện tại."),
  edge("e6", "example_of", "c5", "c2", "UDP là trường hợp không dùng số thứ tự."),
];

const LONG_TITLE =
  "Sosánhhaigiaothứcvậnchuyểnnângcao_tínhtoánđộtrễtruyềnvàthônglượngtrongmạngphântánquymôlớn_kỳthicuốikỳ";
const LONG_CARDS: GraphCard[] = [
  { ...FEW_CARDS[0]!, title: LONG_TITLE },
  { ...FEW_CARDS[1]!, title: "Số thứ tự và xác nhận trong giao thức vận chuyển tin cậy có kiểm soát lỗi và điều khiển luồng" },
  FEW_CARDS[2]!,
];
const LONG_EDGES: GraphEdge[] = [
  edge("e1", "prerequisite", "c1", "c2", "Sau khi kết nối mở, mỗi byte được đánh số thứ tự và được xác nhận bởi bên nhận ở đoạn tin kế tiếp."),
  edge("e3", "part_of", "c3", "c1", "Cửa sổ nhận được thông báo ngay từ đoạn SYN đầu tiên."),
];

/** 320 cards of "Chương 2" in ten clusters, so the section holds more than MAX_NODES. */
function manyCards(): { cards: GraphCard[]; edges: GraphEdge[] } {
  const cards: GraphCard[] = [];
  const edges: GraphEdge[] = [];
  for (let i = 0; i < 320; i++) {
    cards.push(card(`m${i}`, `Thẻ địa chỉ ${i + 1}`, "ch2-1", `Nội dung thẻ ${i + 1} về địa chỉ IP.`, `Câu trích số ${i + 1} trong slide.`));
    if (i % 32 !== 0) {
      const kind = EDGE_KINDS[i % EDGE_KINDS.length]!;
      edges.push(edge(`me${i}`, kind, `m${i - 1}`, `m${i}`, `Câu trích chung của thẻ ${i} và ${i + 1}.`));
    }
    if (i % 7 === 3 && i > 40) edges.push(edge(`mx${i}`, "contrast", `m${i}`, `m${i - 31}`, `So sánh thẻ ${i + 1} với thẻ ${i - 30}.`));
  }
  return { cards, edges };
}

export type GraphFixture = {
  data: GraphData | null;
  sectionId: string | null;
  kinds: EdgeKind[];
  selectedId: string | null;
  view: "graph" | "list";
  status: "ready" | "loading" | "error";
};

export function graphFixture(state: GraphState): GraphFixture {
  const base: GraphFixture = { data: null, sectionId: "ch1", kinds: [...EDGE_KINDS], selectedId: null, view: "graph", status: "ready" };
  switch (state) {
    case "empty":
      return { ...base, data: { sections: SECTIONS, cards: [], edges: [] } };
    case "few":
      return { ...base, data: { sections: SECTIONS, cards: FEW_CARDS, edges: FEW_EDGES } };
    case "filtered":
      return { ...base, data: { sections: SECTIONS, cards: FEW_CARDS, edges: FEW_EDGES }, kinds: ["prerequisite"] };
    case "selected":
      return { ...base, data: { sections: SECTIONS, cards: FEW_CARDS, edges: FEW_EDGES }, selectedId: "c1" };
    case "long":
      return { ...base, data: { sections: SECTIONS, cards: LONG_CARDS, edges: LONG_EDGES }, selectedId: "c1" };
    case "many": {
      const { cards, edges } = manyCards();
      return { ...base, data: { sections: SECTIONS, cards, edges }, sectionId: "ch2" };
    }
    case "loading":
      return { ...base, status: "loading" };
    case "error":
      return { ...base, status: "error" };
  }
}
