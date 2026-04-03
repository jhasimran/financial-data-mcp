import "./globals.css";
import type { ReactNode } from "react";

export const metadata = {
  title: "Financial Data Assistant",
  description: "Upload statements and ask finance questions."
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
