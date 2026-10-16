import type { Metadata } from "next";

import { Shell } from "@/components/shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export const metadata: Metadata = { title: "Design tokens · Essity" };

// Reference page for the design tokens (T1.1). Switch the OS between light and dark to check
// both modes; there is no toggle on purpose.

const SURFACES = [
  ["background", "bg-background text-foreground"],
  ["card", "bg-card text-card-foreground"],
  ["primary", "bg-primary text-primary-foreground"],
  ["secondary", "bg-secondary text-secondary-foreground"],
  ["muted", "bg-muted text-muted-foreground"],
  ["accent", "bg-accent text-accent-foreground"],
  ["success", "bg-success text-success-foreground"],
  ["pending", "bg-pending text-pending-foreground"],
  ["destructive", "bg-destructive text-destructive-foreground"],
] as const;

const CHARTS = ["bg-chart-1", "bg-chart-2", "bg-chart-3", "bg-chart-4", "bg-chart-5"] as const;

export default function TokensPage() {
  return (
    <Shell wide>
      <div className="flex flex-col gap-2">
        <h1 className="font-heading text-2xl font-semibold">Design tokens</h1>
        <p className="text-muted-foreground">
          Tiếng Việt có dấu: Ôn tập đều đặn mỗi ngày giúp nhớ lâu hơn. Ừ, được rồi — thử chữ
          ẩ, ỡ, ự, ỷ, Đ, đ.
        </p>
      </div>

      <section className="flex flex-col gap-3">
        <h2 className="font-medium">Bề mặt và chữ</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {SURFACES.map(([name, classes]) => (
            <div key={name} className={`${classes} rounded-lg border p-4 text-sm`}>
              <div className="font-medium">{name}</div>
              <div className="opacity-90">Câu hỏi hôm nay</div>
            </div>
          ))}
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="font-medium">Trạng thái</h2>
        <div className="flex flex-wrap gap-2">
          <Badge variant="success">Đã ôn</Badge>
          <Badge variant="pending">Chưa làm</Badge>
          <Badge>Hôm nay</Badge>
          <Badge variant="secondary">Mạng máy tính</Badge>
          <Badge variant="outline">12 câu</Badge>
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="font-medium">Nút</h2>
        <div className="flex flex-wrap gap-2">
          <Button>Bắt đầu phiên</Button>
          <Button variant="secondary">Ôn thêm</Button>
          <Button variant="outline">Dừng tại đây</Button>
          <Button variant="ghost">Bỏ câu này</Button>
          <Button variant="link">Vì sao câu này?</Button>
          <Button variant="destructive">Xóa tài khoản</Button>
        </div>
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Câu 3 / 12</CardTitle>
          <CardDescription>Mạng máy tính · vận dụng</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          <Label htmlFor="answer">Vì sao TCP cần bắt tay ba bước?</Label>
          <Input id="answer" placeholder="Viết câu trả lời của bạn" />
        </CardContent>
        <CardFooter className="gap-2">
          <Button>Gửi</Button>
          <Button variant="ghost">Không nhớ</Button>
        </CardFooter>
      </Card>

      <section className="flex flex-col gap-3">
        <h2 className="font-medium">Biểu đồ</h2>
        <div className="flex h-24 items-end gap-2">
          {CHARTS.map((color, i) => (
            <div
              key={color}
              className={`${color} w-10 rounded-t-md`}
              style={{ height: `${40 + i * 12}%` }}
            />
          ))}
        </div>
      </section>
    </Shell>
  );
}
