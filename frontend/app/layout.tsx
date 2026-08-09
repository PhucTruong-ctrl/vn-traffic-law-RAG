import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "VNLaw RAG",
  description: "VN Traffic Law RAG — frontend",
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
