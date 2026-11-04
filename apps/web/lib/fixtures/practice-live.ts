import type { PracticeType } from "@/lib/practice-client";
import type { QuestionListOut } from "@/lib/question-list-types";

// T8.7: fixed data for /design-preview/practice-live, which renders the real PracticeLive. The e2e
// answers web's /api/practice routes itself, so the main flow runs without core-api.

export const LIVE_SUBJECT = { id: "0b8f1d2e-0000-4000-8000-000000000001", name: "Mạng máy tính" };
export const LIVE_Q1 = "0b8f1d2e-0000-4000-8000-0000000000a1";
export const LIVE_Q2 = "0b8f1d2e-0000-4000-8000-0000000000a2";
export const LIVE_Q3 = "0b8f1d2e-0000-4000-8000-0000000000a3";
const LONG_TYPE = "Sosánhhaigiaothứcvậnchuyểnnângcao_tínhtoánđộtrễtruyềnvàthônglượng_kỳthi";

export const LIVE_LIST: QuestionListOut = {
  total: 3,
  ready: 2,
  due_today: 0,
  types: [],
  questions: [
    { id: LIVE_Q1, number: 1, prompt: "So sánh TCP và UDP về độ tin cậy, kiểm soát luồng và độ trễ khi truyền video trực tiếp.", origin: "bank", status: "ready", answer_source: "bank", type_name: LONG_TYPE, line: "Sẵn sàng", waiting_sections: [], due: false },
    { id: LIVE_Q2, number: 2, prompt: "Định nghĩa cửa sổ nhận (rwnd).", origin: "generated", status: "ready", answer_source: "ai", type_name: "Định nghĩa ngắn", line: "Sẵn sàng", waiting_sections: [], due: false },
    { id: LIVE_Q3, number: 3, prompt: "Tính thông lượng hiệu dụng của giao thức dừng-và-chờ.", origin: "bank", status: "waiting", answer_source: "bank", type_name: LONG_TYPE, line: "Chờ học: phần 4.1", waiting_sections: [], due: false },
  ],
};

export const LIVE_TYPES: PracticeType[] = [
  { type_id: "t1", name: LONG_TYPE, mastery: 0.7, attempts_counted: 10, mastery_line: "đúng 7 trên 10 lần gần nhất", sensitivity: "near", sensitivity_line: "gần mốc tham khảo · khoảng 3 phút mỗi câu", reference_seconds: 180, ref_origin: "default", formula_version: "v1" },
  { type_id: "t2", name: "Định nghĩa ngắn", mastery: null, attempts_counted: 1, mastery_line: "chưa đủ dữ liệu", sensitivity: "not_enough_data", sensitivity_line: "chưa đủ dữ liệu", reference_seconds: 60, ref_origin: "default", formula_version: "v1" },
];
