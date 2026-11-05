"use client";

import { useState } from "react";

import styles from "./landing.module.css";

const CARDS: ReadonlyArray<{ id: string; front: string; page: string; before: string; mark: string; after: string }> = [
  {
    id: "k1",
    front: "Bắt tay ba bước dùng để làm gì?",
    page: "Giáo trình Mạng máy tính, trang 214",
    before: "Hai bên trao đổi số thứ tự để ",
    mark: "cùng xác nhận kết nối đáng tin cậy",
    after: " trước khi gửi dữ liệu.",
  },
  {
    id: "k2",
    front: "Vì sao bầu trời có màu xanh?",
    page: "Giáo trình Vật lý đại cương, trang 112",
    before: "Không khí ",
    mark: "tán xạ ánh sáng xanh nhiều hơn",
    after: " các màu khác.",
  },
  {
    id: "k3",
    front: "Mặt nạ mạng /24 cho bao nhiêu địa chỉ?",
    page: "Giáo trình Mạng máy tính, trang 97",
    before: "Phần máy chủ còn 8 bit, tức ",
    mark: "256 địa chỉ",
    after: ", trong đó 2 địa chỉ giữ riêng.",
  },
  {
    id: "k4",
    front: "UDP khác TCP ở đâu?",
    page: "Giáo trình Mạng máy tính, trang 231",
    before: "UDP ",
    mark: "không thiết lập kết nối",
    after: " và không bảo đảm thứ tự gói.",
  },
];

/** A strip of knowledge cards; "Nguồn" turns a card over to the textbook page with the proof highlighted. */
export function KhoBand() {
  const [open, setOpen] = useState<string | null>("k1");
  return (
    <div className={styles.khoStrip}>
      <ul className={styles.khoTrack}>
        {CARDS.map((c) => {
          const on = open === c.id;
          return (
            <li key={c.id} className={styles.khoCard} data-open={on}>
              <span className={styles.khoFront}>{c.front}</span>
              {on ? (
                <span className={styles.khoPage}>
                  <small>{c.page}</small>
                  <span>
                    {c.before}
                    <mark>{c.mark}</mark>
                    {c.after}
                  </span>
                </span>
              ) : null}
              <button
                type="button"
                className={styles.khoBtn}
                aria-pressed={on}
                aria-label={`Nguồn của thẻ: ${c.front}`}
                onClick={() => setOpen(on ? null : c.id)}
              >
                Nguồn
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
