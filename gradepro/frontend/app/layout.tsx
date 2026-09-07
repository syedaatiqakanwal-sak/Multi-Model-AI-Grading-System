import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "GradePro — Smart Grading, Clear Results",
  description: "Enterprise AI-Powered Assessment Grading Platform",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
