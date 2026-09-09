import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "VNLAW — Tra cứu pháp luật giao thông",
  description:
    "Trợ lý nghiên cứu pháp luật giao thông Việt Nam với câu trả lời có căn cứ.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="vi">
      <body>{children}</body>
    </html>
  );
}
