# Essity — Kịch bản thuyết trình

> Thời lượng nói: khoảng 12 phút, cộng phần hỏi đáp. Mỗi mục ghi **Slide** đang chiếu và **Lời nói** để đọc.
> Nội dung bám README và tài liệu trong `documentation/` (ARCHITECTURE, AI, PRODUCT, DEPLOY) tại ngày 08/11/2026.
> Link demo: **https://essity.io.vn**. Tài khoản giám khảo: xem `.work/DEMO/account.md` (không chiếu mật khẩu lên màn hình).

## Bảng thời gian

| # | Mục | Slide | Thời lượng |
|---|---|---|---|
| 1 | Mở đầu và vấn đề | 1–2 | 1:30 |
| 2 | Giải pháp: vòng học của Essity | 3 | 1:00 |
| 3 | Demo trực tiếp | 4 | 2:30 |
| 4 | Công nghệ sử dụng | 5–6 | 2:00 |
| 5 | Kiến trúc hệ thống | 7–8 | 1:30 |
| 6 | Luồng hoạt động của các module | 9–11 | 1:30 |
| 7 | Vấn đề gặp phải và cách giải quyết | 12–13 | 1:30 |
| 8 | Kết quả, hướng phát triển, kết luận | 14–16 | 0:45 |

---

## 1. Mở đầu và vấn đề (Slide 1–2)

**Slide 1 — Bìa:** Essity — Ôn tập ngắt quãng, AI chấm theo chính giáo trình của bạn.

**Lời nói:**

"Kính chào ban giám khảo. Nhóm chúng em xin trình bày dự án Essity, một ứng dụng giúp sinh viên ghi nhớ kiến thức lâu dài.

**Slide 2 — Vấn đề.**

Bắt đầu từ một tình huống quen thuộc: sinh viên học dồn trong vài đêm trước kỳ thi, thi xong thì phần lớn kiến thức mất đi. Nghiên cứu về trí nhớ từ lâu đã mô tả hiện tượng này, gọi là *đường cong quên*: nếu không được nhắc lại, lượng kiến thức nhớ được giảm rất nhanh trong vài ngày đầu.

Phương pháp được khoa học xác nhận để chống quên là *ôn tập ngắt quãng*: nhắc lại một kiến thức đúng vào lúc mình sắp quên nó, và khoảng cách giữa các lần ôn giãn dần ra. Các ứng dụng như Anki đã làm việc này, nhưng khi áp dụng cho sinh viên Việt Nam, chúng em thấy ba trở ngại:

- **Thứ nhất, phải tự làm thẻ.** Biến một cuốn giáo trình hai trăm trang thành thẻ hỏi đáp tốn rất nhiều giờ, nên phần lớn sinh viên bỏ cuộc trước khi bắt đầu ôn.
- **Thứ hai, phải tự chấm.** Người học lật thẻ rồi tự bấm 'dễ' hay 'khó'. Việc tự đánh giá thường thiếu chính xác, và người học không phải diễn đạt lại kiến thức bằng lời của mình — trong khi chính việc diễn đạt mới giúp nhớ lâu.
- **Thứ ba, nội dung không bám tài liệu học.** Sinh viên học theo giáo trình và bài giảng của trường mình; bộ thẻ dùng chung trên mạng thường lệch nội dung và lệch thuật ngữ.

Essity được xây dựng để giải quyết đồng thời ba trở ngại này."

---

## 2. Giải pháp: vòng học của Essity (Slide 3)

**Lời nói:**

"Ý tưởng của Essity là: người học chỉ làm phần cần đến tư duy — đọc, hiểu và trả lời. Phần còn lại do hệ thống đảm nhận. Một vòng học gồm sáu bước:

1. **Tạo môn học** và đặt ngày thi, ví dụ môn Xác suất thống kê thi ngày 18/12.
2. **Tải tài liệu lên**: PDF, Word, PowerPoint hoặc ảnh chụp. AI đọc tài liệu và dựng *đề cương* — mục lục các phần kiến thức của môn.
3. **AI tạo thẻ kiến thức** từ những phần đã học và đưa thẳng vào *Kho kiến thức*. Kho là nơi lưu chính thức; người học có thể xem và sửa trực tiếp.
4. **Màn Hôm nay** cho biết hôm nay cần ôn gì, sắp xếp theo nguy cơ quên, độ gần ngày thi và quan hệ tiền đề giữa các khái niệm.
5. **Người học gõ câu trả lời** bằng lời của mình. AI chấm Đúng, Một phần hoặc Sai, có nhận xét và **trích dẫn đúng đoạn trong giáo trình** làm căn cứ.
6. **Thuật toán FSRS** dùng kết quả chấm để tính ngày ôn tiếp theo cho từng thẻ. Ngoài thẻ, còn có câu hỏi luyện tập vận dụng, đồ thị kiến thức và thống kê tiến độ.

Ba điểm khác biệt so với các công cụ hiện có: không phải tự làm thẻ, không phải tự chấm, và mọi nội dung đều có nguồn từ chính tài liệu của người học."

---

## 3. Demo trực tiếp (Slide 4)

**Chuẩn bị trước giờ trình bày:**
- Mở https://essity.io.vn, đăng xuất sẵn, trình duyệt phóng to 110%.
- Tài khoản giám khảo đã có môn "Xác suất thống kê" với giáo trình PDF thật, đề cương, thẻ đến hạn và câu luyện tập.
- Kiểm tra key AI còn hạn (key hiện tại hết hạn 09/11/2026). Nếu không còn key, hệ thống vẫn chạy trọn luồng nhưng không chấm bằng AI thật — nói rõ với giám khảo.

| Thao tác | Lời nói |
|---|---|
| Trang chủ → **Đăng nhập** bằng tài khoản giám khảo | "Đây là bản đang chạy thật trên tên miền essity.io.vn. Em đăng nhập bằng tài khoản dành cho ban giám khảo." |
| Màn **Hôm nay** | "Đây là việc cần làm hôm nay: các thẻ đến hạn và câu luyện tập. Danh sách này do thuật toán tính, thay đổi theo mức độ ghi nhớ thực tế của người học." |
| Mở một thẻ đến hạn, **gõ câu trả lời thiếu một ý**, gửi | "Em không bấm 'dễ' hay 'khó'. Em gõ câu trả lời, và cố ý bỏ sót một ý." |
| Kết quả chấm | "AI chấm Một phần, chỉ ra ý còn thiếu, và trích đoạn giáo trình làm căn cứ. Đoạn trích này đã được hệ thống kiểm tra là có thật trong tài liệu. Kết quả đi thẳng vào FSRS để tính lịch ôn." |
| Môn học → **Đề cương** | "Đây là đề cương AI dựng từ giáo trình. Người học có thể sửa tay hoặc gõ lệnh tiếng Việt tự nhiên." |
| **Kho kiến thức** | "Mọi thẻ AI tạo đều nằm ở đây, mỗi thẻ gắn với nguồn trong tài liệu, và người học sửa trực tiếp được." |
| **Luyện tập**, rồi **Đồ thị** và **Thống kê** | "Luyện tập là câu hỏi vận dụng, chấm theo từng ý. Đồ thị cho thấy khái niệm nào là tiền đề của khái niệm nào. Thống kê chỉ so người học với chính mình, không có bảng xếp hạng." |

**Dự phòng:** nếu AI lỗi hoặc hết hạn mức, giải thích đó là cơ chế an toàn (hết hạn mức thì không gọi AI) và mở lịch sử các lần chấm trước.

---

## 4. Công nghệ sử dụng (Slide 5–6)

**Lời nói (mở):**

"Tiếp theo, em xin giới thiệu các công nghệ chúng em sử dụng. Với mỗi công nghệ, em giải thích ngắn nó là gì và được dùng vào việc gì trong Essity."

### 4.1. Giao diện và máy chủ ứng dụng (Slide 5)

| Công nghệ | Giải thích đơn giản | Dùng trong Essity |
|---|---|---|
| **Next.js 16, React 19, TypeScript** | React là thư viện dựng giao diện từ các thành phần nhỏ ghép lại. Next.js là khung chạy React ở cả phía máy chủ, giúp trang tải nhanh. TypeScript là JavaScript có kiểm tra kiểu dữ liệu, bắt lỗi trước khi chạy. | Toàn bộ giao diện tiếng Việt. Next.js còn đóng vai trò **BFF** (*Backend for Frontend*): một lớp trung gian mỏng, giữ cookie đăng nhập và kiểm tra nguồn gốc yêu cầu; trình duyệt chỉ nói chuyện với lớp này. |
| **Tailwind CSS, Base UI** | Tailwind viết kiểu dáng bằng các lớp tiện ích ngắn; Base UI cung cấp các thành phần có sẵn hỗ trợ bàn phím và trình đọc màn hình. | Hệ thiết kế thống nhất cho mọi màn. |
| **Cytoscape, pdf.js, KaTeX** | Thư viện vẽ đồ thị; thư viện hiển thị PDF trong trình duyệt; thư viện hiển thị công thức toán. | Đồ thị kiến thức; xem giáo trình và đoạn trích nguồn; công thức trong môn Xác suất thống kê. |
| **Python 3.13, FastAPI** | FastAPI là khung viết API bằng Python, tự sinh tài liệu API và kiểm tra dữ liệu vào ra. | Hai dịch vụ backend: **core-api** và **ai-service**. |
| **SQLAlchemy 2, Alembic** | SQLAlchemy cho phép thao tác cơ sở dữ liệu bằng đối tượng Python. Alembic quản lý *migration* — các bước thay đổi cấu trúc bảng có đánh số, chạy tuần tự. | Mỗi dịch vụ có một chuỗi migration riêng; CI kiểm tra chỉ có một nhánh migration. |
| **py-fsrs** | FSRS (*Free Spaced Repetition Scheduler*) là thuật toán lập lịch ôn hiện đại: dự đoán xác suất người học còn nhớ một kiến thức theo thời gian, và hẹn ôn khi xác suất đó giảm tới ngưỡng. | Mỗi thẻ và mỗi câu luyện tập có lịch riêng. Kết quả chấm được quy đổi: Sai → *Again*, Một phần → *Hard*, Đúng → *Good*. Tham số được tối ưu lại hằng tuần theo từng người. |

### 4.2. Dữ liệu, AI và hạ tầng (Slide 6)

| Công nghệ | Giải thích đơn giản | Dùng trong Essity |
|---|---|---|
| **PostgreSQL** | Hệ quản trị cơ sở dữ liệu quan hệ, lưu dữ liệu dạng bảng, đảm bảo giao dịch toàn vẹn. | Mỗi dịch vụ một cơ sở dữ liệu và một tài khoản riêng. core-api chạy bằng tài khoản bị giới hạn quyền, không được sửa cấu trúc bảng. |
| **Redis (Streams)** | Kho dữ liệu trong bộ nhớ, rất nhanh. *Streams* là cấu trúc dạng "băng chuyền" tin nhắn: bên gửi đặt sự kiện lên, bên nhận lấy xuống xử lý. | Truyền sự kiện giữa hai dịch vụ, hàng đợi việc nền, đếm giới hạn tần suất đăng nhập. |
| **RustFS (tương thích S3)** | Kho lưu file theo chuẩn S3 của Amazon. *Presigned URL* là đường dẫn tải lên có chữ ký và thời hạn, cho phép trình duyệt gửi file thẳng vào kho mà không đi qua máy chủ ứng dụng. | Lưu giáo trình tải lên, đề cương và văn bản đã trích xuất. |
| **Anthropic Claude Haiku** | Mô hình ngôn ngữ lớn, nhanh và rẻ, gọi qua API. | Chấm bài, tạo thẻ, dựng đề cương, sinh câu luyện tập, đọc ảnh ghi chép, hiểu lệnh tiếng Việt. Mọi lời gọi đều đi qua ai-service. |
| **pypdfium2, python-docx, python-pptx** | Thư viện đọc nội dung file PDF, Word, PowerPoint. | Trích văn bản từ tài liệu trước khi đưa cho AI. |
| **Docker Compose** | Docker đóng gói mỗi thành phần vào một "container" chạy giống nhau trên mọi máy. Compose khởi động cả hệ thống nhiều container bằng một lệnh. | Toàn bộ hệ thống (khoảng 13 container) chạy bằng một file cấu hình. |
| **Cloudflare Tunnel** | Một đường hầm mã hóa từ máy chủ ra mạng Cloudflare, cho phép đưa ứng dụng lên Internet mà không cần mở cổng hay có IP tĩnh. | Đưa ứng dụng lên **essity.io.vn** và **s3.essity.io.vn** với HTTPS. |
| **SMTP (Gmail)** | Giao thức gửi thư điện tử. | Gửi thư xác minh tài khoản và đặt lại mật khẩu. |
| **OpenTelemetry, Jaeger** | Công cụ *truy vết*: ghi lại một yêu cầu đi qua những dịch vụ nào, mất bao lâu ở mỗi chặng. | Tìm chỗ chậm hoặc lỗi khi một yêu cầu đi qua ba dịch vụ. |
| **pytest, Vitest, Playwright, GitHub Actions** | Công cụ kiểm thử Python; kiểm thử giao diện; điều khiển trình duyệt thật để kiểm thử đầu-cuối; hệ thống chạy kiểm tra tự động mỗi lần đẩy code. | Mỗi pull request phải qua lint, kiểm tra kiểu, kiểm thử, quét bí mật và kiểm tra giấy phép thư viện mới được gộp. |

---

## 5. Kiến trúc hệ thống (Slide 7–8)

### 5.1. Ba khối chính (Slide 7)

**Lời nói:**

"Essity gồm ba dịch vụ chính, mỗi dịch vụ có một trách nhiệm rõ ràng.

- **web** — Next.js. Là cửa duy nhất mà trình duyệt nói chuyện. Nó hiển thị giao diện và chuyển yêu cầu tới core-api kèm một token dịch vụ.
- **core-api** — FastAPI. Là **nguồn sự thật** của hệ thống: tài khoản, môn học, thẻ, lịch ôn FSRS, và điều phối việc chấm bài. Dữ liệu nằm trong cơ sở dữ liệu `core`.
- **ai-service** — FastAPI. Là **cửa duy nhất đi ra AI**: mọi lời gọi mô hình, mọi việc đọc tài liệu, và hạn mức chi phí của từng người dùng đều nằm ở đây. Dữ liệu nằm trong cơ sở dữ liệu `ai` riêng.

Xung quanh là các thành phần hạ tầng: PostgreSQL, Redis, kho file S3, máy chủ thư SMTP và API của Anthropic.

Nguyên tắc quan trọng nhất: **core-api và ai-service không bao giờ import code của nhau**. Một script trong CI chặn việc này. Hai bên chỉ chia sẻ *hợp đồng* — các JSON Schema trong thư mục `contracts/` mô tả chính xác hình dạng của từng sự kiện và từng loại file. Nhờ vậy, có thể thay nhà cung cấp AI hay sửa ai-service mà không động tới dữ liệu người dùng."

### 5.2. Hai cách giao tiếp (Slide 8)

**Lời nói:**

"Hai dịch vụ giao tiếp theo hai cách, tùy loại việc.

**Cách thứ nhất — gọi trực tiếp qua HTTP**, dùng cho việc người dùng đang chờ, như chấm một câu trả lời. core-api gọi ai-service, kèm header `X-Service-Token` để ai-service biết yêu cầu đến từ đúng core-api.

**Cách thứ hai — sự kiện bất đồng bộ qua Redis Streams**, dùng cho việc chạy lâu, như đọc một giáo trình vài trăm trang. Có thể hình dung như hệ thống giao hàng có biên nhận:

1. core-api ghi thay đổi dữ liệu **và** sự kiện vào bảng `outbox` trong **cùng một giao dịch**. Hoặc cả hai cùng được lưu, hoặc không cái nào — nên không bao giờ có chuyện dữ liệu đã lưu mà sự kiện bị mất. Kỹ thuật này gọi là *transactional outbox*.
2. Tiến trình **core-relay** đọc bảng outbox và đẩy sự kiện lên luồng `events.core`.
3. **ai-consumer** nhận sự kiện, ai-service xử lý, rồi đẩy kết quả lên luồng `events.ai`.
4. **core-consumer** nhận kết quả và ghi vào core-api.

Sự kiện chỉ mang mã định danh và đường dẫn file, không mang nội dung — nội dung nằm trong kho file. Mỗi sự kiện có `event_id` để bên nhận bỏ qua bản trùng; sự kiện lỗi quá số lần cho phép được chuyển sang *hàng đợi thư chết* (dead-letter) để xem xét, không làm tắc cả hệ thống."

---

## 6. Luồng hoạt động của các module (Slide 9–11)

### 6.1. Luồng tải và đọc tài liệu (Slide 9)

**Lời nói:**

"Khi người học tải giáo trình lên:

1. Trình duyệt xin web một đường dẫn tải lên. web hỏi core-api; core-api tạo bản ghi tài liệu và trả về **presigned URL**.
2. Trình duyệt gửi file **thẳng vào kho S3**, không đi qua máy chủ ứng dụng — nên file lớn không làm nghẽn API.
3. core-api phát sự kiện `document.uploaded` qua outbox.
4. ai-service đọc file, trích văn bản, dùng AI dựng đề cương và tách thành các đơn vị kiến thức, ghi kết quả vào kho file, rồi phát `document.indexed` (hoặc `document.failed` nếu lỗi).
5. core-api nhận kết quả và đưa các thẻ vào Kho kiến thức.

Người học không phải chờ: màn hình hiện trạng thái đang xử lý, xong thì đề cương xuất hiện."

### 6.2. Luồng chấm bài và lập lịch (Slide 10)

**Lời nói:**

"Khi người học gửi câu trả lời:

1. core-api gửi câu trả lời cùng **đoạn giáo trình liên quan** tới ai-service qua `/v1/grade`.
2. ai-service **kiểm tra hạn mức** chi phí của người dùng. Còn hạn mức mới gọi mô hình.
3. Mô hình trả về kết quả chấm kèm đoạn trích dẫn. ai-service **kiểm tra đoạn trích có thật trong nguồn** — nếu AI tự bịa trích dẫn, kết quả bị loại.
4. core-api lưu lần làm bài và **cập nhật trạng thái FSRS**: Sai → Again, Một phần → Hard, Đúng → Good. Từ đó tính ngày ôn kế tiếp.

Câu luyện tập đi cùng đường này, với tác vụ `grade_practice`, và cập nhật lịch riêng của từng câu."

### 6.3. Các module còn lại (Slide 11)

**Lời nói:**

"Các module khác, nói ngắn:

- **Hôm nay**: core-api tính danh sách từ trạng thái FSRS, ngày thi và đồ thị tiền đề — khái niệm nền được ưu tiên trước khái niệm phụ thuộc nó.
- **Tài khoản**: đăng ký bằng email và mật khẩu; mật khẩu băm bằng argon2. Đăng ký tạo một việc `send_email` trong hàng đợi; tiến trình **core-worker** gửi thư xác minh qua SMTP. Đặt lại mật khẩu đi cùng cơ chế.
- **Ghi chép buổi học**: ghi chép gõ tay hoặc ảnh chụp vở, AI đọc và biến thành kết quả buổi học.
- **Thanh lệnh**: người học gõ lệnh tiếng Việt như 'bỏ chương 5', AI chuyển thành thao tác sửa đề cương.
- **Đồ thị và thống kê**: quan hệ tiền đề giữa khái niệm, mức thành thạo và mức sẵn sàng cho kỳ thi.
- **Quản lý dữ liệu**: người dùng xuất được dữ liệu của mình và xóa tài khoản; việc xóa do một tài khoản cơ sở dữ liệu riêng thực hiện.
- **Việc nền** của core-worker: gửi thư, tối ưu tham số FSRS hằng tuần, dọn dữ liệu cũ, xóa tài khoản chưa xác minh, thử lại các lần chấm lỗi."

---

## 7. Vấn đề gặp phải và cách giải quyết (Slide 12–13)

**Lời nói (mở):** "Trong quá trình xây dựng, nhóm gặp nhiều vấn đề thực tế. Em xin trình bày những vấn đề chính và cách giải quyết."

### Slide 12 — Vấn đề về AI và dữ liệu

| # | Vấn đề | Cách giải quyết |
|---|---|---|
| 1 | **Chi phí AI.** Ngân sách AI cho toàn bộ dự án chỉ 2 USD. Một người dùng có thể vô tình tiêu hết. | Hạn mức theo từng người dùng, theo ngày (0,20 USD) và tháng (2 USD), kiểm tra **trước** mỗi lời gọi. Chi phí tính chính xác đến micro-đô la, gồm cả giá bộ nhớ đệm prompt. Lời gọi đang chạy được "giữ chỗ" trong hạn mức, có khóa theo người dùng để không vượt khi gọi đồng thời. Nếu không đọc được mức chi tiêu thì **không gọi** (*fail closed*). Chọn mô hình Haiku vì nhanh và rẻ. |
| 2 | **AI chấm sai hoặc bịa trích dẫn.** Chấm sai thì lịch ôn sai. | Bắt AI trích đoạn nguồn làm căn cứ, và **code kiểm tra đoạn trích có thật trong tài liệu**. Kết quả sai định dạng thì thử lại rồi báo lỗi, không ghi vào lịch. Khi kiểm thử phát hiện câu trả lời lạc đề vẫn được "Một phần", nhóm sửa bộ chấm: **lạc đề thì chấm Sai**, kèm test. Có bộ đánh giá (evals) riêng cho từng tác vụ AI. |
| 3 | **Đọc tài liệu chạy lâu**, không thể bắt người dùng chờ. | Chuyển sang xử lý bất đồng bộ: transactional outbox, Redis Streams, consumer group, hàng đợi thư chết, chống trùng theo `event_id`. |
| 4 | **Hai dịch vụ dễ phụ thuộc lẫn nhau** khi code lớn dần. | Cấm import chéo, kiểm tra tự động trong CI. Hợp đồng duy nhất là JSON Schema; mỗi bên tự kiểm mô hình dữ liệu của mình với schema trong test. |

### Slide 13 — Vấn đề về triển khai và bảo mật

| # | Vấn đề | Cách giải quyết |
|---|---|---|
| 5 | **Thư xác minh không tới.** Khi đưa ra Internet, máy chủ thư dùng khi phát triển (Mailpit) không hỗ trợ đăng nhập SMTP, mọi thư đều lỗi. | Chuyển sang **Gmail SMTP** với App Password, mã hóa STARTTLS. Đã kiểm thử gửi thư thật tới hộp thư người đăng ký. |
| 6 | **Trình duyệt chặn tải file lên** do chính sách CORS: trang web và kho file ở hai tên miền khác nhau. | Presigned URL được ký cho địa chỉ công khai của kho file; script khởi động cấu hình CORS của kho để chỉ cho phép đúng tên miền web. |
| 7 | **Đưa ứng dụng lên Internet khi không có máy chủ riêng.** Đường hầm tạm của Cloudflare đổi địa chỉ mỗi lần khởi động lại. | Mua tên miền **essity.io.vn**, dùng **Cloudflare Tunnel cố định**: địa chỉ không đổi, có HTTPS, không cần mở cổng trên máy. |
| 8 | **Bảo mật đăng nhập.** | Mật khẩu băm argon2. Cookie phiên `__Host-` chỉ gửi qua HTTPS. web chỉ nhận yêu cầu thay đổi dữ liệu từ đúng tên miền của mình (chống CSRF). Giới hạn tần suất đăng nhập và đăng ký theo IP; nếu Redis lỗi thì **từ chối**, không bỏ qua. Mỗi dịch vụ **từ chối khởi động** nếu thấy cấu hình dành cho môi trường phát triển khi chạy production. Log băm các mã định danh. CI quét bí mật trong lịch sử git. |
| 9 | **Lỗi chỉ lộ ra khi chạy thật.** | Kiểm thử đầu-cuối bằng Playwright trên hệ thống đang chạy: đăng ký, xác minh thư, đăng nhập, quên mật khẩu, tải tài liệu, học, xuất dữ liệu. Các lỗi tìm được đều được ghi lại và sửa. |

**Lời nói (chốt mục):**

"Bài học chung của nhóm: với hệ thống có AI, phải thiết kế để **an toàn khi có lỗi** — hết tiền thì dừng gọi AI, AI bịa thì loại kết quả, hạ tầng lỗi thì từ chối thay vì cho qua."

---

## 8. Kết quả, hướng phát triển, kết luận (Slide 14–16)

### Slide 14 — Kết quả

**Lời nói:**

"Kết quả hiện tại:

- Vòng học hoàn chỉnh chạy thật trên **essity.io.vn**: đăng ký, xác minh email, tải tài liệu, AI dựng đề cương và tạo thẻ, ôn tập có chấm điểm, luyện tập, đồ thị và thống kê.
- Kiến trúc ba dịch vụ, hai cơ sở dữ liệu, giao tiếp đồng bộ và bất đồng bộ, với hợp đồng JSON Schema.
- Hơn 300 pull request, mỗi cái đi qua CI và review; hơn 5.600 test tự động; các quyết định kỹ thuật quan trọng được ghi thành văn bản kiến trúc (ADR).
- Hạn mức chi phí AI hoạt động: toàn bộ dự án nằm trong ngân sách 2 USD."

### Slide 15 — Hướng phát triển

**Lời nói:**

"Các bước tiếp theo:
1. Đăng nhập bằng Google.
2. Máy chủ riêng thay cho chạy trên máy cá nhân; dịch vụ email giao dịch trên tên miền essity.io.vn.
3. Đo độ chính xác của AI chấm trên dữ liệu thật — chỉ với người dùng đồng ý chia sẻ.
4. Ứng dụng di động."

### Slide 16 — Kết luận

**Lời nói:**

"Em xin tóm lại. Với Essity, sinh viên **không phải tự làm thẻ** — AI tạo từ giáo trình. **Không phải tự chấm** — AI chấm, có trích dẫn nguồn được kiểm chứng. Và **lịch ôn tự thích nghi** với mức độ ghi nhớ thật của từng người.

Mục tiêu của Essity không phải học nhiều hơn, mà là nhớ lâu hơn với ít thời gian hơn. Nhóm cũng chủ động không đưa vào bảng xếp hạng hay so sánh điểm giữa người học, vì áp lực không giúp ai nhớ lâu.

Ứng dụng đang chạy tại essity.io.vn. Cảm ơn ban giám khảo đã lắng nghe, nhóm em sẵn sàng trả lời câu hỏi."

---

# Phụ lục — Câu hỏi giám khảo có thể đặt

1. **AI chấm sai thì sao?** Đoạn trích căn cứ được code kiểm tra là có thật trong tài liệu; kết quả sai cấu trúc bị loại và thử lại. Có bộ evals cho chấm bài. Chưa đo độ chính xác trên dữ liệu người dùng thật — đây là bước tiếp theo.
2. **Khác Anki thế nào?** Anki bắt tự làm thẻ và tự chấm. Essity tạo thẻ từ tài liệu của chính người học, chấm câu trả lời gõ tay có dẫn nguồn, và dùng cùng loại thuật toán lập lịch hiện đại (FSRS).
3. **FSRS hoạt động thế nào?** Mỗi thẻ có hai đại lượng: *độ ổn định* (trí nhớ bền đến đâu) và *độ khó*. Từ đó thuật toán ước lượng xác suất còn nhớ theo thời gian và hẹn ôn khi xác suất giảm tới ngưỡng. Mỗi lần ôn đúng, khoảng cách giãn ra. Tham số được tối ưu hằng tuần theo lịch sử của từng người.
4. **Chi phí cho mỗi người dùng?** Mặc định tối đa 0,20 USD/ngày và 2 USD/tháng; chấm bài được phép vượt tối đa 3 lần hạn mức để người học không bị chặn giữa buổi, các việc khác thì hoãn lại.
5. **Vì sao tách ai-service?** Để mọi lời gọi AI đi qua một cửa có hạn mức và kiểm soát chất lượng, và để thay mô hình hoặc nhà cung cấp mà không ảnh hưởng dữ liệu người dùng.
6. **Mở rộng cho nhiều người dùng?** Các tiến trình nền tách riêng; consumer group của Redis Streams cho phép chạy nhiều bản consumer song song. Hiện chạy trên một máy, kiến trúc đã sẵn sàng để tách.
7. **Dữ liệu người dùng có an toàn?** argon2, HTTPS, cookie `__Host-`, chống CSRF, giới hạn tần suất, tài khoản cơ sở dữ liệu bị giới hạn quyền, log băm định danh; người dùng xuất và xóa được dữ liệu của mình.
8. **Hỗ trợ ảnh chụp, tài liệu tiếng Việt?** Có: PDF, DOCX, PPTX và ảnh; ảnh ghi chép được đọc bằng mô hình có khả năng nhìn. Chất lượng với bản scan mờ chưa được đo.
