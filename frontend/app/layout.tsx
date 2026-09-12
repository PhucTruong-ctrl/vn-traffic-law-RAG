import type { Metadata } from "next";

import "./globals.css";
import { appMono, appSans, appSerif } from "./fonts";

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
    <html lang="vi" className={`${appSans.variable} ${appMono.variable} ${appSerif.variable}`}>
      <body>{children}</body>
    </html>
  );
}
