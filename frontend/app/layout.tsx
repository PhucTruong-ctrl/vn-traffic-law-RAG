import type { Metadata } from "next";

import "./globals.css";
import { dmMono, dmSans, sourceSerif } from "./fonts";

export const metadata: Metadata = {
  title: "VNLAW — Tra cứu pháp luật giao thông",
  description: "Trợ lý nghiên cứu pháp luật giao thông Việt Nam.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="vi"
      className={`${dmSans.variable} ${dmMono.variable} ${sourceSerif.variable}`}
    >
      <body>{children}</body>
    </html>
  );
}
