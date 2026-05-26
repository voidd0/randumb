import "./styles.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Vøiddo Rescue",
  description: "Public website checks, proof audit pages, monitoring, and small site fixes.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <a className="skip" href="#main">Skip to content</a>
        {children}
      </body>
    </html>
  );
}
