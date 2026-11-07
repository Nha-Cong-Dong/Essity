// Demo data of the landing knowledge graph (from the approved mockup).
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
];
export const GRAPH_RELATIONS: Array<[number, number]> = [[0, 4], [1, 12], [2, 3], [0, 5], [6, 8], [6, 10], [7, 9], [11, 12], [13, 15], [14, 9], [1, 11], [3, 5], [8, 7]];
